"""Apply-mode diff review standards helper.

This module addresses *Step 2.6 – Embed Apply-mode into review cycles* by
providing a **single source of truth** for what constitutes an *acceptable*
LLM-generated patch.  It serves two complementary purposes:

1. Generate markdown documentation that teams can reference in their pull-
   request templates or wiki pages.
2. Offer a lightweight *linter* that analyses a unified diff and highlights
   potential review blockers (e.g. missing tests, large deletions, secrets).

The implementation purposefully stays dependency-free (standard library +
typer).  Static guidelines live in this file for easy modification.
"""

# pylint: disable=missing-module-docstring
# (Docstring is provided at top-level)

import re
from pathlib import Path
from typing import List

import typer

__all__ = [
    "generate_guidelines",
    "lint_diff",
    "app",
]

# ---------------------------------------------------------------------------
# Static markdown guidelines – update as your team evolves
# ---------------------------------------------------------------------------

_GUIDELINES_MD = """# Diff Review Standards (Apply-mode)

Follow these rules **before** approving or applying any unified diff produced
by an AI assistant or human contributor.

| # | Category | Guideline |
|---|----------|-----------|
| 1 | *Security* | No hard-coded secrets (API keys, passwords). |
| 2 | *Testing* | New behaviour **must** include or update tests. |
| 3 | *Consistency* | Keep coding style aligned with project linters. |
| 4 | *Performance* | Avoid quadratic algorithms unless justified. |
| 5 | *Documentation* | Public APIs require docstrings + changelog entry. |
| 6 | *Danger zone* | Deletions > 300 lines need explicit human sign-off. |
| 7 | *Data Sovereignty* | Each PR **must reference** a *Data Sovereignty Review* checklist. |
| 8 | *Privacy & HITL* | Privacy flags and HITL toggles are **non-negotiable** – they cannot be removed or disabled. |
| 9 | *Transparency* | Encourage **open-source audits** and link external reports when available. |
"""

_SECRET_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"[A-Za-z0-9_]{20,}=="),  # generic base64 key ending with ==
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google API key
    re.compile(r"sk_live_[0-9a-zA-Z]{24}"),  # Stripe secret key (example)
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def generate_guidelines() -> str:
    """Return markdown table of review standards."""

    return _GUIDELINES_MD + "\n"


def lint_diff(diff_text: str) -> List[str]:
    """Return list of *issues* detected in *diff_text*.

    The linter performs best-effort heuristics; it is **not** a full static
    analysis.  The goal is to catch obvious red flags early.
    """

    problems: List[str] = []

    # 1) Secrets
    for pat in _SECRET_PATTERNS:
        if pat.search(diff_text):
            problems.append("Potential secret detected – verify & rotate if real.")
            break

    # 2) Large deletions
    deletions = sum(1 for ln in diff_text.splitlines() if ln.startswith("-"))
    if deletions > 300:
        problems.append(f"Large deletion detected ({deletions} lines) – requires senior review.")

    # 3) Privacy/HITL flags – ensure they are not removed or disabled
    _flag_regex = re.compile(r"(?i)(privacy[_\-]?flag|privacy_mode|hitl|human[-_ ]in[-_ ]the[-_ ]loop)")

    for ln in diff_text.splitlines():
        if ln.startswith("-") and _flag_regex.search(ln):
            problems.append("Removal of privacy/HITL toggle detected – prohibited.")
            break  # one alert is enough
        if ln.startswith("+") and _flag_regex.search(ln) and re.search(r"=\s*False|:\s*false", ln, re.I):
            problems.append("Privacy/HITL toggle set to 'False' – prohibited.")
            break

    # 4) Test presence – naive check for tests/ path or *_test.py
    additions = [ln[1:] for ln in diff_text.splitlines() if ln.startswith("+")]
    added_files = [ln for ln in additions if ln.startswith("+++ ")]  # diff headers
    if not any(re.search(r"tests?/|_test\.py", ln) for ln in added_files):
        problems.append("No test changes detected – ensure coverage for new behaviour.")

    # 5) Data Sovereignty Review reference
    if "Data Sovereignty Review" not in diff_text:
        problems.append("Diff does not reference 'Data Sovereignty Review' – include checklist link in PR description.")

    return problems


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate guidelines or lint unified diffs.")


@app.command()
def show():
    """Print markdown guidelines to STDOUT."""

    typer.echo(generate_guidelines())


@app.command()
def lint(
    diff_file: Path = typer.Argument(..., help="Path to unified diff ('-' for STDIN)"),
):
    """Run heuristic linter against *diff_file* and print issues (if any)."""

    if diff_file == Path("-") or str(diff_file) == "-":
        diff_text = typer.get_text_stream("stdin").read()
    else:
        diff_text = diff_file.read_text()

    issues = lint_diff(diff_text)
    if not issues:
        typer.secho("✅ No blocking issues detected", fg="green")
    else:
        typer.secho("✖ Issues detected:", fg="red")
        for i, msg in enumerate(issues, 1):
            typer.echo(f"{i}. {msg}")