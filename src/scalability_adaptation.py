from __future__ import annotations

"""Scalability & Adaptation helper utilities (Step 2.11).

This module operationalises the theoretical **2.11 Scalability and Adaptation**
requirements by providing *ready-to-use* artefacts that make it trivial to roll
out the **Repo-Prompt** workflow across *multiple* repositories *and* adapt the
configuration to different engineering teams (frontend ⇢ backend ⇢ full-stack).

Key capabilities
----------------
1. **Shell aliases** – a small *bash/zsh/fish* snippet that can be sourced from
   a dot-file to expose friendly `rp-*` commands.
2. **Context presets** – a JSON config mapping `frontend`/`backend`/`fullstack`
   to `include` / `exclude` regex patterns consumed by
   :pymod:`src.context_builder.ContextBuilder`.

Design notes
~~~~~~~~~~~~
* *Read-only* by default – artefacts are *previewed* unless the `--write` flag
  is supplied (mirrors :pymod:`src.standardization`).
* No external dependencies besides :pypi:`typer` (already part of the stack).
* Paths are opinionated but overrideable via CLI flags.

Security considerations
~~~~~~~~~~~~~~~~~~~~~~~
* Purely local file writes – no network or shell execution.
* Generated aliases reference only *local* scripts; no secrets stored.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import json
import textwrap

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "FileSpec",
    "generate_aliases",
    "generate_presets_json",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileSpec:
    """Represents a file to be created by the *Scalability & Adaptation* helper."""

    path: Path
    content: str

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – simple helper
        return {"path": str(self.path), "content": self.content}


# ---------------------------------------------------------------------------
# Preset definitions – extend/fork as needed
# ---------------------------------------------------------------------------

_PRESETS: Dict[str, Dict[str, str | None]] = {
    # Focus on JS/TS/CSS/HTML code, ignore build artefacts
    "frontend": {
        "include": r"\.(js|jsx|ts|tsx|css|scss|sass|html)$",
        "exclude": r"(^|/)node_modules/|(^|/)dist/|(^|/)build/",
    },
    # Focus on server-side languages, ignore tests & virtualenvs
    "backend": {
        "include": r"\.(py|go|rs|java|kt|cs)$",
        "exclude": r"(^|/)(\.venv|venv|env)/|(^|/)tests?/|(^|/)docs?/",
    },
    # Union of both – suitable for monorepos
    "fullstack": {
        "include": r"\.(py|go|rs|java|kt|cs|js|jsx|ts|tsx|css|scss|sass|html)$",
        "exclude": r"(^|/)node_modules/|(^|/)dist/|(^|/)build/|(^|/)(\.venv|venv|env)/|(^|/)tests?/",
    },
}


# ---------------------------------------------------------------------------
# Alias generator
# ---------------------------------------------------------------------------

_SUPPORTED_SHELLS: List[str] = ["bash", "zsh", "fish"]

_ALIASES_COMMON = {
    "rp": "python -m src.prompt",
    "rp-context": "python -m src.context_builder.search",
    "rp-diff": "python -m src.patch_apply",
    "rp-metrics": "python -m src.evaluation_criteria summary",
}


def _alias_line(shell: str, name: str, cmd: str) -> str:
    """Return *alias* definition line for *shell*."""

    if shell == "fish":
        return f"alias {name} \"{cmd} $argv\""
    # bash / zsh share the same syntax
    return f"alias {name}=\"{cmd} \$@\""


def generate_aliases(shell: Literal["bash", "zsh", "fish"] = "bash") -> str:  # noqa: D401
    """Return the shell alias snippet for *shell*.

    Parameters
    ----------
    shell:
        Target shell flavour. Must be *bash*, *zsh* or *fish*.
    """

    if shell not in _SUPPORTED_SHELLS:
        raise ValueError(f"Unsupported shell '{shell}'. Choose from: {', '.join(_SUPPORTED_SHELLS)}")

    header = textwrap.dedent(
        f"""\
        # Repo-Prompt shell aliases (Step 2.11)
        # Generated for *{shell}*.  Source this file from ~/.{shell}rc:
        #   source <path>/repo_prompt_aliases.sh
        #
        # The aliases provide concise access to common Repo-Prompt utilities.
        """
    )

    lines: List[str] = [header.strip()]
    for name, cmd in _ALIASES_COMMON.items():
        lines.append(_alias_line(shell, name, cmd))
    lines.append("")  # trailing newline for POSIX compliance
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Preset config generator
# ---------------------------------------------------------------------------

def generate_presets_json(team: Optional[str] = None, *, indent: int = 2) -> str:  # noqa: D401
    """Return a JSON string containing context builder presets.

    Parameters
    ----------
    team:
        Restrict output to *team* ("frontend", "backend", "fullstack").  If
        *None* (default) all presets are included.
    indent:
        Pretty-print indentation level.
    """

    if team:
        if team not in _PRESETS:
            raise ValueError(f"Unknown team '{team}'. Available: {', '.join(_PRESETS)}")
        data = {team: _PRESETS[team]}
    else:
        data = _PRESETS

    return json.dumps(data, indent=indent, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Helper to bundle artefacts into FileSpec objects
# ---------------------------------------------------------------------------

def _file_specs(repo_root: Path | str, *, shell: str, team: Optional[str]) -> List[FileSpec]:
    root = Path(repo_root).resolve()

    specs = [
        FileSpec(root / "Scripts" / "repo_prompt_aliases.sh", generate_aliases(shell)),
        FileSpec(root / ".repo_prompt_presets.json", generate_presets_json(team)),
    ]

    _log.debug("Prepared %d file specs (shell=%s, team=%s)", len(specs), shell, team or "all")
    return specs


# ---------------------------------------------------------------------------
# CLI (Typer)
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate scaling artefacts (Step 2.11 – scalability & adaptation)")


@app.command()
def aliases(
    shell: str = typer.Option("bash", "--shell", help="Target shell (bash|zsh|fish)"),
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write file to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the *repo_prompt_aliases.sh* helper only."""

    setup_logging("DEBUG" if verbose else "INFO")

    spec = FileSpec(Path(repo_path).resolve() / "Scripts" / "repo_prompt_aliases.sh", generate_aliases(shell))
    _output([spec], write, force)


@app.command()
def presets(
    team: Optional[str] = typer.Option(None, "--team", help="Limit to preset team (frontend|backend|fullstack)"),
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write file to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the *.repo_prompt_presets.json* file only."""

    setup_logging("DEBUG" if verbose else "INFO")

    spec = FileSpec(Path(repo_path).resolve() / ".repo_prompt_presets.json", generate_presets_json(team))
    _output([spec], write, force)


@app.command()
def all(
    shell: str = typer.Option("bash", "--shell", help="Target shell (bash|zsh|fish)"),
    team: Optional[str] = typer.Option(None, "--team", help="Limit presets to team (frontend|backend|fullstack)"),
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write files to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *both* shell aliases and presets (default preview)."""

    setup_logging("DEBUG" if verbose else "INFO")

    specs = _file_specs(repo_path, shell=shell, team=team)
    _output(specs, write, force)


# ---------------------------------------------------------------------------
# Internal I/O helpers
# ---------------------------------------------------------------------------

def _output(specs: List[FileSpec], write: bool, force: bool) -> None:  # noqa: D401
    """Write or preview *specs* depending on *write* flag."""

    for spec in specs:
        if write:
            if spec.path.exists() and not force:
                _log.warning("Skipping existing %s (use --force to overwrite)", spec.path)
                continue
            spec.path.parent.mkdir(parents=True, exist_ok=True)
            spec.path.write_text(spec.content, encoding="utf-8")
            typer.echo(f"✅ {spec.path.relative_to(Path.cwd())} written")
        else:
            header = f"----- {spec.path.relative_to(Path.cwd())} -----"
            typer.echo(header)
            typer.echo(spec.content.rstrip())
            typer.echo("-" * len(header))