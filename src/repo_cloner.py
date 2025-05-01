from __future__ import annotations

"""Utilities and CLI helpers for cloning Git repositories.

This module translates the *theoretical* guideline of *project repository cloning* into
production-ready code that integrates with the existing **Repo-Prompt** tool-chain.  In
particular it fulfils *Step 1 – Projekt-Repository klonen* by exposing a Python API and a
Typer sub-command that perform a secure `git clone` operation.

Key implementation requirements addressed
----------------------------------------
1. *Code Integration* – integrates seamlessly with the current `src` package and Typer
   CLI (see :pymod:`src.__main__`).
2. *Documentation Support* – provides rich doc-strings plus inline comments.
3. *Feedback Readiness* – emits structured logs via :pymod:`src.logger`.
4. *Maintainability* – stateless functional API; no hard-coded secrets; masking of PAT
   in logs.
5. *Security & Ethics* – token never written to disk or exposed via log output.
6. *Testing Coverage* – see ``tests/test_repo_cloner.py`` for unit tests.

The public surface area intentionally remains *minimal* – hiding low-level details
behind a single `clone_repository` helper.
"""

from pathlib import Path
import subprocess
import shutil
import sys
from typing import Optional
from urllib.parse import urlparse

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "clone_repository",
    "app",
]

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1. Private helpers
# ---------------------------------------------------------------------------

def _masked_token(token: str) -> str:
    """Return a *masked* representation of *token* (first/last 2 chars remain)."""

    if len(token) <= 8:  # pragma: no cover – unlikely but defensive
        return "****"
    return f"{token[:2]}…{token[-2:]}"  # e.g. **gh→gh…ZZ**


def _build_auth_url(url: str, token: Optional[str] = None) -> str:
    """Insert *token* into *url* if provided and return the *auth* URL.

    Only *http*/*https* schemes are supported for PAT injection because the
    credential must be transmitted via *basic auth*.
    """

    if token is None:
        return url

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            "Token authentication currently supported for http(s) clone URLs only"
        )

    # Inject the token as the *username* component – Git ignores the password
    auth_netloc = f"{token}@{parsed.netloc}"
    return parsed._replace(netloc=auth_netloc).geturl()


# ---------------------------------------------------------------------------
# 2. Public API
# ---------------------------------------------------------------------------

def clone_repository(
    repo_url: str,
    destination: Path | str,
    *,
    token: str | None = None,
    depth: int = 0,
    mirror: bool = False,
) -> Path:
    """Clone *repo_url* into *destination* directory.

    Parameters
    ----------
    repo_url:
        The *HTTPS* or *SSH* Git URL.
    destination:
        Target directory **must not** already exist.  It will be created by
        ``git clone``.
    token:
        Optional GitHub *Personal Access Token*.  When given, it will be injected
        into the clone URL so that private repositories can be cloned from
        CI/CD environments without interactive prompts.  The token is **never**
        written to disk and replaced by a masked version in log messages.
    depth:
        Perform a *shallow* clone with the given history depth.  ``0`` disables
        the flag (default – full history).
    mirror:
        When *True* a `--mirror` clone is created.  This implies *bare* and is
        useful for creating a full repository mirror on the local file-system.

    Returns
    -------
    Path
        Absolute path to the *destination* directory.

    Raises
    ------
    RuntimeError
        If the `git` executable is missing, the *destination* already exists, or
        the clone operation fails.
    """

    dest_path = Path(destination).expanduser().resolve()
    if dest_path.exists():
        raise RuntimeError(f"Destination {dest_path} already exists – aborting clone")

    if shutil.which("git") is None:
        raise RuntimeError("`git` executable not found – ensure Git is installed")

    auth_url = _build_auth_url(repo_url, token)

    cmd: list[str] = [
        "git",
        "clone",
    ]
    if mirror:
        cmd.append("--mirror")
    if depth > 0:
        cmd.extend(["--depth", str(depth)])
    cmd.extend([auth_url, str(dest_path)])

    masked_url = _build_auth_url(repo_url, _masked_token(token) if token else None)
    _log.info("Cloning %s → %s", masked_url, dest_path)

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:  # pragma: no cover – propagate
        # Surface *stderr* to the caller while hiding secrets
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else str(exc.stderr)
        _log.error("git clone failed: %s", stderr.splitlines()[-1] if stderr else exc)
        raise RuntimeError("git clone failed – see logs for details") from None

    return dest_path


# ---------------------------------------------------------------------------
# 3. Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Safely clone a Git repository with optional PAT")


@app.command("run")
def cli_clone(
    repo_url: str = typer.Argument(..., help="Repository URL to clone"),
    destination: Path = typer.Argument(
        None,
        dir_okay=False,
        exists=False,
        show_default=False,
        help="Destination directory (defaults to repo-name)",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        envvar="GIT_PAT",
        help="GitHub personal access token (env: GIT_PAT)",
    ),
    depth: int = typer.Option(
        0,
        "--depth",
        "-d",
        help="Shallow clone depth (0 = full history)",
    ),
    mirror: bool = typer.Option(False, "--mirror", help="Create a --mirror clone (bare)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI wrapper around :pyfunc:`clone_repository`."""

    setup_logging("DEBUG" if verbose else "INFO")

    # Derive destination when omitted → <repo-name>
    if destination is None:
        repo_name = Path(urlparse(repo_url).path).stem or "cloned_repo"
        destination = Path(repo_name)

    try:
        dest = clone_repository(repo_url, destination, token=token, depth=depth, mirror=mirror)
    except RuntimeError as exc:  # pragma: no cover – user-facing errors
        typer.echo(f"✖ {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"✅ Repository cloned to {dest}")