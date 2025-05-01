"""practical_ux_solutions.py – Step 5.4 Design Practical UX Solutions 🎨📐

This module operationalises the *5.4 Design Practical UX Solutions* theory
block.  Building upon earlier UX analysis (see :pymod:`src.ux_guidelines`,
:pymod:`src.real_world_usage_context`) and feasibility checks
(:pymod:`src.feasibility_constraints_ui`), **5.4** focuses on *actionable* UI
improvements that immediately address common friction points discovered during
research.

We maintain a *static* catalogue that maps **problems** → **practical
solutions** → **tool/method suggestions** so downstream tools (e.g. prompt
builders, dashboards, CI gates) can automatically surface relevant UX advice.

Features
~~~~~~~~
* **Pure stdlib** – zero third-party runtime deps aside from the already-used
  :pypi:`typer` & local :pymod:`src.logger` helper.
* **Machine-readable** – helpers return JSON-serialisable structures (ideal for
  prompts or telemetry events).
* **Human-friendly** – ``generate_markdown()`` formats the catalogue as a HIG-
  compliant markdown table – perfect for wikis or README snippets.
* **Typer CLI** – ``python -m src.practical_ux_solutions doc --write`` writes a
  markdown doc; ``report`` filters recommendations for specific problems.

Security/Ethics
~~~~~~~~~~~~~~~
* Reads **no user code** and **no network** calls – catalogue is static.
* Transparent & auditable mapping; teams can extend the catalogue by editing
  the ``_SOLUTIONS`` list.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "Solution",
    "get_solutions",
    "generate_markdown",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data catalogue – edit to extend 📝
# ---------------------------------------------------------------------------


@dataclass
class Solution:  # noqa: D101 – simple value holder
    problem: str
    practical_solution: str
    tool_method: str

    def as_dict(self) -> Dict[str, str]:  # pragma: no cover – trivial helper
        return asdict(self)


_SOLUTIONS: List[Solution] = [
    Solution(
        problem="high_learning_curve",
        practical_solution="First-run wizard with tooltips",
        tool_method="SwiftUI onboarding flows + inline contextual help",
    ),
    Solution(
        problem="feature_overload",
        practical_solution="Progressive disclosure for advanced tools",
        tool_method="\u201cShow advanced features\u201d toggle",
    ),
    Solution(
        problem="missing_context_examples",
        practical_solution="Preloaded template gallery",
        tool_method="Task-oriented UX (e.g. bug fix, test gen)",
    ),
    Solution(
        problem="visual_inconsistency",
        practical_solution="UI audit & polish sprint",
        tool_method="Apple HIG compliance checklist",
    ),
    Solution(
        problem="platform_transparency",
        practical_solution="Roadmap modal & in-app announcements",
        tool_method="macOS NotificationCenter + modal view",
    ),
]

# Helper dict for quick lookup ¬
_SOL_BY_KEY: Dict[str, Solution] = {s.problem: s for s in _SOLUTIONS}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_solutions(*, problems: List[str] | None = None) -> List[Dict[str, str]]:
    """Return a list of *solutions* filtered by *problems* (optional).

    Parameters
    ----------
    problems:
        Optional list of problem **keys** (see :pyattr:`Solution.problem`).
        When *None* (default) all catalogue entries are returned.

    Returns
    -------
    List[Dict[str, str]]
        List of solutions as JSON-serialisable dicts.
    """

    if problems is None:
        selected = _SOLUTIONS
    else:
        unknown: List[str] = [p for p in problems if p not in _SOL_BY_KEY]
        for name in unknown:
            _log.warning("Unknown problem '%s' – skipping", name)
        selected = [_SOL_BY_KEY[p] for p in problems if p in _SOL_BY_KEY]

    return [s.as_dict() for s in selected]


# ---------------------------------------------------------------------------
# Markdown generator – human docs 📄
# ---------------------------------------------------------------------------


def generate_markdown() -> str:  # noqa: D401 – imperative mood fine
    """Return markdown table representing the UX solutions catalogue."""

    header = [
        "# Practical UX Solutions",
        "",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| Problem | Practical Solution | Tool / Method |",
        "|---------|-------------------|---------------|",
    ]

    rows = [
        f"| {s.problem.replace('_', ' ').title()} | **{s.practical_solution}** | {s.tool_method} |"
        for s in _SOLUTIONS
    ]

    return "\n".join(header + rows) + "\n"


# ---------------------------------------------------------------------------
# Typer CLI – quick standalone usage 💻
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=False,
    help="5.4 Practical UX solutions helper – generates markdown or JSON recommendations.",
)


@app.command()
def doc(
    write: bool = typer.Option(False, "--write", help="Write file instead of printing"),
    path: Path = typer.Option(Path("docs/practical_ux_solutions.md"), "--path", "-p", help="Destination markdown path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without prompt"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show or write the UX solutions markdown catalogue."""

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
def report(
    problems: List[str] = typer.Option(
        None,
        "--problem",
        "-p",
        help="Problem keys to filter (comma-separated). Default: all.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Emit solutions for *problems* (all when not provided)."""

    setup_logging("DEBUG" if verbose else "INFO")

    problem_list = [p.strip() for p in problems] if problems else None
    solutions = get_solutions(problems=problem_list)

    if json_output:
        typer.echo(json.dumps(solutions, indent=2))
    else:
        for s in solutions:
            typer.echo(f"• {s['problem'].replace('_', ' ').title()}: {s['practical_solution']} -> {s['tool_method']}")