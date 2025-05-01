# new file
from __future__ import annotations

"""ux_implementation_plan.py  Step 5.5 UX Implementation Plan 🗺️🚀

This module operationalises the **5.5 Step-by-Step Plan for UX Implementation** theory block.
It converts the high-level roadmap (see *docs* or the project specification) into **machine-
readable data structures**, a **markdown generator**, and a **Typer CLI** so downstream tools
(dashboards, CI checks, prompt builders) can surface the plan programmatically.

The plan covers six calendar weeks and focuses on these initiatives:

1. *Onboarding Wizard* – interactive tutorial (Week 1-2)
2. *Feature Tiers* – opt-in advanced panes (Week 2-3)
3. *Template Library* – curated prompt gallery (Week 3-4)
4. *UI Polish Sprint* – visual & interaction refinements (Week 4-6)
5. *Comms Enhancements* – in-app announcements & CTAs (Week 6)

Design goals
~~~~~~~~~~~~
* **Pure stdlib** – reuses :pypi:`typer` + local :pymod:`src.logger` only.
* **Static & auditable** – the roadmap is stored in a hard-coded list and can be reviewed via git.
* **Human-friendly** – ``generate_markdown()`` outputs a polished table for wikis or READMEs.
* **CLI-first** – ``python -m src.ux_implementation_plan doc --write`` writes a markdown file.

Security & ethics
~~~~~~~~~~~~~~~~~
* No network or file-system introspection beyond optional *--write* path.
* Perfectly transparent – all logic is declarative and visible.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "UXStep",
    "get_plan",
    "generate_markdown",
    "app",
]

_log = get_logger(__name__)

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Data catalogue – edit to extend 📋
# ---------------------------------------------------------------------------


@dataclass
class UXStep:  # noqa: D101 – simple value holder
    """Represents one *concrete* UX initiative on the six-week roadmap."""

    id: int
    title: str
    weeks: str  # e.g. "1-2" or "6" for single week
    description: str
    key_actions: Sequence[str]

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return {
            "id": self.id,
            "title": self.title,
            "weeks": self.weeks,
            "description": self.description,
            "key_actions": list(self.key_actions),
        }


_STEPS: List[UXStep] = [
    UXStep(
        id=1,
        title="Onboarding Wizard",
        weeks="1-2",
        description="Design "Select → Prompt → Diff → Apply" interactive tutorial with animation & progressive disclosure.",
        key_actions=(
            "Interactive tutorial",
            "Progressive disclosure",
            "Animated transitions",
        ),
    ),
    UXStep(
        id=2,
        title="Feature Tiers",
        weeks="2-3",
        description="Hide advanced panes (CodeMap, regex, multi-model) behind opt-in toggles in Settings.",
        key_actions=(
            "Opt-in advanced panes",
            "Settings toggles",
            "User preference persistence",
        ),
    ),
    UXStep(
        id=3,
        title="Template Library",
        weeks="3-4",
        description="Provide 10+ ready-to-run prompts (Add docstring, Generate unit tests, …) sorted by use-case with live preview.",
        key_actions=(
            "Prompt gallery (≥10 items)",
            "Use-case sorting",
            "Live preview",
        ),
    ),
    UXStep(
        id=4,
        title="UI Polish Sprint",
        weeks="4-6",
        description="Refactor menu-bar integration, toolbar clarity, dark/light mode contrasts. Align XML-diff colours with Git diffs.",
        key_actions=(
            "Menu-bar refactor",
            "Toolbar clarity",
            "Dark/Light mode QA",
            "XML-diff colour alignment",
        ),
    ),
    UXStep(
        id=5,
        title="Comms Enhancements",
        weeks="6",
        description="Add in-app messages for feature updates, pricing & roadmap. Clear CTAs in post-install flow.",
        key_actions=(
            "In-app announcements",
            "Feature update feed",
            "Pricing prompts",
            "Roadmap modal",
            "Post-install CTAs",
        ),
    ),
]

# Pre-compute mapping for quick lookup by *id* or *week* --------
_STEPS_BY_ID: Dict[int, UXStep] = {s.id: s for s in _STEPS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_plan(*, weeks: str | Sequence[str] | None = None) -> List[Dict[str, Any]]:
    """Return the UX implementation plan as a JSON-serialisable list.

    Parameters
    ----------
    weeks: str | Sequence[str] | None, optional
        When provided, filters steps to the specified **week numbers** (e.g. "1", "3-4").
        Accepts a single string or a list of strings. Ranges ("3-4") are expanded.

    Returns
    -------
    List[Dict[str, Any]]
        The steps (order preserved) in machine-readable form.
    """

    if weeks is None:
        selected = _STEPS
    else:
        week_set: set[int] = set()
        if isinstance(weeks, str):
            weeks = [weeks]
        for w in weeks:  # type: ignore[assignment]
            if "-" in w:
                start, end = w.split("-", 1)
                week_set.update(range(int(start), int(end) + 1))
            else:
                week_set.add(int(w))

        def _matches(step: UXStep) -> bool:
            for part in step.weeks.split(","):
                part = part.strip()
                if "-" in part:
                    s, e = part.split("-", 1)
                    if any(int(s) <= wk <= int(e) for wk in week_set):
                        return True
                else:
                    if int(part) in week_set:
                        return True
            return False

        selected = [s for s in _STEPS if _matches(s)]

    return [s.as_dict() for s in selected]


# ---------------------------------------------------------------------------
# Markdown generator – docs / wiki 📄
# ---------------------------------------------------------------------------

def generate_markdown() -> str:  # noqa: D401 – imperative mood fine
    """Return a markdown document representing the UX implementation roadmap."""

    lines: List[str] = [
        "# UX Implementation Sprint Plan",
        "",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| Week(s) | Initiative | Description | Key Actions |",
        "|---------|------------|-------------|-------------|",
    ]

    for step in _STEPS:
        actions = ", ".join(step.key_actions)
        lines.append(f"| {step.weeks} | **{step.title}** | {step.description} | {actions} |")

    # Quick legend / usage note
    lines.extend(
        [
            "",
            "<!-- Auto-generated via `python -m src.ux_implementation_plan doc` -->",
        ]
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Typer CLI – quick standalone usage 💻
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=False,
    help="5.5 UX implementation plan helper – outputs markdown or JSON roadmap.",
)


@app.command()
def doc(
    write: bool = typer.Option(False, "--write", help="Write file instead of printing"),
    path: Path = typer.Option(Path("docs/ux_implementation_plan.md"), "--path", "-p", help="Destination markdown path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without prompt"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show or write the UX implementation **markdown** roadmap."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_markdown()
    if write:
        path = path.expanduser()
        if path.exists() and not force:
            typer.echo(f"Error: {path} exists – use --force to overwrite", err=True)
            raise typer.Exit(code=1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        typer.secho(f"Roadmap written to {path.resolve()}", fg="green")
    else:
        typer.echo(md)


@app.command()
def report(
    weeks: List[str] = typer.Option(
        None,
        "--week",
        "-w",
        help="Filter by week numbers (comma-separated, ranges allowed, e.g. 2,4-6). Default: all.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Emit the UX plan for selected **week(s)** – default: all."""

    setup_logging("DEBUG" if verbose else "INFO")

    week_list = [w.strip() for w in weeks] if weeks else None
    plan = get_plan(weeks=week_list) if week_list else get_plan()

    if json_output:
        typer.echo(json.dumps(plan, indent=2))
    else:
        for step in plan:
            actions = ", ".join(step["key_actions"])
            typer.echo(f"• Week {step['weeks']} – {step['title']}: {actions}")