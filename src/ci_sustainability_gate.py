from __future__ import annotations

"""ci_sustainability_gate.py – CI Gate for token/energy budget (Step 4.13)

Add this script to your *continuous-integration* workflow to **block merges** when
pull-request diffs exceed a configured *token* or *kWh* threshold.  The helper
is intentionally lightweight and dependency-free outside the project's own
:pyfunc:`src.token_estimator.estimate_tokens` function.

Typical GitHub Actions usage – run after fetching the commit range:

```yaml
- name: Sustainability gate
  run: |
    python -m src.ci_sustainability_gate --range "${{ steps.range.outputs.range }}" \\
      --max-tokens 50000 --max-kwh 0.08
```

If **either** limit is breached the command exits with *code 1*, causing the job
(and therefore the merge) to fail.
"""

from pathlib import Path
import subprocess
import sys
from typing import List, Optional

import typer

from .token_estimator import estimate_tokens
from .logger import get_logger, setup_logging

__all__ = ["app"]

_log = get_logger(__name__)

_DEFAULT_KWH_PER_TOKEN = 5e-7  # assume remote/cloud execution for worst-case

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _git_diff(commit_range: str | None = None, *, cwd: Optional[Path] = None) -> str:
    """Return *unified diff* between commits in *commit_range* (A..B).

    When *commit_range* is *None*, compare *HEAD~1* to *HEAD* (last commit).
    """

    if not commit_range:
        commit_range = "HEAD~1..HEAD"

    _log.debug("Running git diff for range %s", commit_range)
    try:
        diff_bytes = subprocess.check_output([
            "git",
            "diff",
            "--unified=0",  # no context to avoid double-counting unchanged lines
            commit_range,
        ], cwd=cwd)
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        _log.error("git diff failed: %s", exc)
        raise typer.Exit(code=1) from exc

    return diff_bytes.decode("utf-8", errors="replace")


def _extract_added_lines(diff_text: str) -> List[str]:
    """Return list of *added* source lines (ignoring diff metadata)."""

    added: List[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):  # real addition
            added.append(line[1:])  # strip leading +
    return added

# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Fail CI when token/kWh budget exceeded")


@app.command()
def check(
    commit_range: Optional[str] = typer.Option(None, "--range", help="Git commit range (e.g. abc123..def456)"),
    diff_file: Optional[Path] = typer.Option(None, "--diff-file", help="Pre-generated unified diff (use '-' for STDIN)"),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="Abort when added lines exceed this many tokens"),
    max_kwh: Optional[float] = typer.Option(None, "--max-kwh", help="Abort when estimated energy exceeds this many kWh"),
    kwh_per_token: float = typer.Option(
        _DEFAULT_KWH_PER_TOKEN,
        "--kwh-per-token",
        show_default=True,
        help="Energy coefficient (kWh/token). Use lower value if CI builds on green hardware.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Validate *added lines* in diff against *token* & *kWh* budgets.

    You can supply **either** a *commit range* or a *diff file* (or STDIN).  If
    neither is provided the helper defaults to `HEAD~1..HEAD`.
    """

    if max_tokens is None and max_kwh is None:
        typer.echo("ERROR: Must specify at least one of --max-tokens or --max-kwh", err=True)
        raise typer.Exit(code=2)

    setup_logging("DEBUG" if verbose else "INFO")

    # ------------------------------------------------------
    # Obtain diff text – favour explicit diff_file over range
    # ------------------------------------------------------
    if diff_file:  # user provided diff file or '-'
        if str(diff_file) == "-":
            diff_text = sys.stdin.read()
        else:
            diff_text = diff_file.read_text()
    else:
        diff_text = _git_diff(commit_range)

    # ----------------------------------------
    # Token & energy calculation on *additions*
    # ----------------------------------------
    added_lines = _extract_added_lines(diff_text)
    added_text = "\n".join(added_lines)
    tokens = estimate_tokens(added_text)
    energy_kwh = tokens * kwh_per_token

    typer.echo(f"Added lines: {len(added_lines)} • Tokens: {tokens} • ≈{energy_kwh:.6f} kWh")

    # ----------------------
    # Budget enforcement
    # ----------------------
    errors: List[str] = []

    if max_tokens is not None and tokens > max_tokens:
        errors.append(f"Token budget exceeded: {tokens} > {max_tokens}")
    if max_kwh is not None and energy_kwh > max_kwh:
        errors.append(f"Energy budget exceeded: {energy_kwh:.6f} kWh > {max_kwh} kWh")

    if errors:
        for err in errors:
            typer.secho(f"✖ {err}", fg="red")
        raise typer.Exit(code=1)

    typer.secho("✅ Sustainability gate passed", fg="green")


if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter