"""design_practical_solutions.py – Step 6.3 Design Practical Solutions 🚀📈

This module operationalises the *6.3 – Design Practical Solutions* theory block.
It translates the high-level mitigation table into executable Python helpers so
other tools (dashboards, CLIs, prompt builders) can surface the *exact*
recommendations – or extend them over time.

The catalogue intentionally remains **static & file-local** to keep things
transparent, auditable and dependency-free at runtime (no network, no DB).

Key capabilities
~~~~~~~~~~~~~~~~
* Simple :pyclass:`Solution` dataclass with JSON-serialisable helpers.
* Static list of **challenge ➜ solution ➜ method** triples pre-populated from
  the 6.3 design document.
* Markdown generator producing a beautifully formatted table for READMEs or
  wiki docs.
* Typer CLI (`python -m src.design_practical_solutions …`) offering:
    * ``doc`` – print or write the markdown catalogue.
    * ``recommend`` – filter solutions by *challenge* key.
* Optional *ROI token-saving simulator* to back the "lack of perceived value"
  challenge – this reuses :pymod:`src.token_estimator` for quick estimates.

Security & ethics
~~~~~~~~~~~~~~~~~
* Pure stdlib (+ :pyPi:`typer` & project's :pymod:`src.logger`).
* No external I/O other than optional markdown writes ‑> local filesystem.
* "ROI" calculator is *approximate* — flagged for human validation (``# REVIEW``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging
from .token_estimator import estimate_tokens  # lightweight reuse

__all__ = [
    "Solution",
    "get_solutions",
    "generate_markdown",
    "simulate_roi_savings",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data catalogue – edit here to extend 📝
# ---------------------------------------------------------------------------


@dataclass
class Solution:  # noqa: D101 – simple value holder
    challenge: str
    practical_solution: str
    tool_method: str

    def as_dict(self) -> Dict[str, str]:  # pragma: no cover – trivial helper
        return asdict(self)


# Initial solutions captured from the design brief
_SOLUTIONS: List[Solution] = [
    Solution(
        challenge="macos_exclusivity",
        practical_solution="Build & release Windows/Linux beta",
        tool_method="Cross-platform Swift or Electron alternative",
    ),
    Solution(
        challenge="high_entry_price",
        practical_solution="Introduce 'Free Starter' plan",
        tool_method="Limit features (e.g. 1 tab, no XML Apply mode)",
    ),
    Solution(
        challenge="no_student_academic_access",
        practical_solution="Implement edu-verification with SheerID or GitHub OAuth",
        tool_method="Automate onboarding & discounts",
    ),
    Solution(
        challenge="sme_team_affordability",
        practical_solution="Create tiered team licences & 'startup ramp' pricing",
        tool_method="Revenue-based pricing (Stripe Connect / Paddle)",
    ),
    Solution(
        challenge="lack_of_perceived_value",
        practical_solution="Embed ROI calculator in purchase flow",
        tool_method="Token-saving simulator based on repo size & edit type",
    ),
]

# Fast lookup table
_SOL_BY_KEY: Dict[str, Solution] = {s.challenge: s for s in _SOLUTIONS}

# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------

def get_solutions(*, challenges: List[str] | None = None) -> List[Dict[str, str]]:
    """Return *solutions* filtered by *challenges* (default: all).

    Parameters
    ----------
    challenges:
        Optional list of challenge keys (see :pyattr:`Solution.challenge`). If
        *None*, all catalogue entries are returned.

    Returns
    -------
    List[Dict[str, str]]
        JSON-serialisable list of solution dicts.
    """

    if challenges is None:
        selected = _SOLUTIONS
    else:
        unknown: List[str] = [c for c in challenges if c not in _SOL_BY_KEY]
        for name in unknown:
            _log.warning("Unknown challenge '%s' – skipping", name)
        selected = [_SOL_BY_KEY[c] for c in challenges if c in _SOL_BY_KEY]

    return [s.as_dict() for s in selected]


# ---------------------------------------------------------------------------
# Markdown generator – docs 📄
# ---------------------------------------------------------------------------

def generate_markdown() -> str:  # noqa: D401 – imperative fine
    """Return markdown table for the solutions catalogue."""

    header = [
        "# Practical Solutions (Step 6.3)",
        "",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| Challenge | Practical Solution | Tools / Methods |",
        "|-----------|-------------------|-----------------|",
    ]

    rows = [
        f"| {s.challenge.replace('_', ' ')} | **{s.practical_solution}** | {s.tool_method} |"
        for s in _SOLUTIONS
    ]

    return "\n".join(header + rows) + "\n"


# ---------------------------------------------------------------------------
# ROI token-saving simulator (optional) 💰
# ---------------------------------------------------------------------------

_DEFAULT_TOKENS_PER_LINE = 4  # heuristic – average code line → ~4 GPT-4 tokens

_EDIT_TYPE_MULTIPLIER: Dict[str, float] = {
    "renaming": 0.1,
    "bug_fix": 0.25,
    "refactor": 0.5,
    "feature": 0.75,
}


def simulate_roi_savings(
    repo_lines_of_code: int,
    *,
    edit_type: str = "refactor",
    sessions: int = 10,
    model: str | None = None,
) -> Dict[str, Any]:
    """Return *approximate* token savings for onboarding calculator.

    Parameters
    ----------
    repo_lines_of_code:
        Estimated total lines of code in the user's repository.
    edit_type:
        One of ``renaming``, ``bug_fix``, ``refactor`` or ``feature``. Determines
        the fraction of the codebase typically affected per edit. Values can be
        extended via :pydata:`_EDIT_TYPE_MULTIPLIER`.
    sessions:
        Number of AI-assisted coding sessions the user expects per month.
    model:
        Optional model name forwarded to :pyfunc:`src.token_estimator.estimate_tokens` for
        encoding selection.

    Returns
    -------
    Dict[str, Any]
        Dictionary with *estimated_tokens_saved* and breakdown context.
    """

    if edit_type not in _EDIT_TYPE_MULTIPLIER:
        raise ValueError(f"Unknown edit_type '{edit_type}'. Valid: {list(_EDIT_TYPE_MULTIPLIER)}")

    affected_fraction = _EDIT_TYPE_MULTIPLIER[edit_type]
    edited_lines_per_session = int(repo_lines_of_code * affected_fraction)

    # Quick heuristic: join dummy placeholders to approximate token cost of edited lines
    dummy_code = "\n".join(["x = 1" for _ in range(edited_lines_per_session)])
    tokens_per_session = estimate_tokens(dummy_code, model or "gpt-3.5-turbo")

    # Assume 30% reduction compared to manual prompts (# REVIEW: verify assumption)
    tokens_saved_per_session = int(tokens_per_session * 0.3)
    total_saved = tokens_saved_per_session * sessions

    _log.debug(
        "ROI simulation – loc=%s edit_type=%s sessions=%s ➜ saved=%s tokens",
        repo_lines_of_code,
        edit_type,
        sessions,
        total_saved,
    )

    return {
        "repo_loc": repo_lines_of_code,
        "edit_type": edit_type,
        "sessions": sessions,
        "estimated_tokens_saved": total_saved,
    }


# ---------------------------------------------------------------------------
# Typer CLI – quick access 💻
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=False,
    help="6.3 Design Practical Solutions helper – generates docs & ROI simulations.",
)


@app.command()
def doc(
    write: bool = typer.Option(False, "--write", help="Write file instead of printing"),
    path: Path = typer.Option(Path("docs/design_practical_solutions.md"), "--path", "-p", help="Destination markdown path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without prompt"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show or write the solutions markdown catalogue."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_markdown()
    if write:
        path = path.expanduser()
        if path.exists() and not force:
            typer.echo(f"Error: {path} exists – use --force to overwrite", err=True)
            raise typer.Exit(code=1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        typer.secho(f"Solutions written to {path.resolve()}", fg="green")
    else:
        typer.echo(md)


@app.command()
def recommend(
    challenges: List[str] = typer.Option(
        None,
        "--challenge",
        "-c",
        help="Comma-separated challenge keys to filter (default: all).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Emit practical solutions for *challenges* (all when not provided)."""

    setup_logging("DEBUG" if verbose else "INFO")

    selected = get_solutions(challenges=challenges)
    if json_output:
        typer.echo(json.dumps(selected))
    else:
        for sol in selected:
            typer.echo(f"• {sol['challenge']}: {sol['practical_solution']} → {sol['tool_method']}")


@app.command()
def roi(
    repo_loc: int = typer.Argument(..., help="Total lines of code in the repo"),
    edit_type: str = typer.Option("refactor", "--type", "-t", help="Edit type (renaming, bug_fix, refactor, feature)"),
    sessions: int = typer.Option(10, "--sessions", "-s", help="Expected sessions per month"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Quick ROI token-saving simulation suitable for checkout flows."""

    setup_logging("DEBUG" if verbose else "INFO")

    res = simulate_roi_savings(repo_loc, edit_type=edit_type, sessions=sessions)
    if json_output:
        typer.echo(json.dumps(res))
    else:
        typer.echo(
            f"Estimated **{res['estimated_tokens_saved']:,}** tokens saved/month "
            f"({sessions} sessions, edit={edit_type}, repo={repo_loc:,} LOC)"
        )