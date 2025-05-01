# new file
from __future__ import annotations

"""structured_execution_plan.py – Step 6.4 Structured Execution Plan 📅🛠️

This module operationalises the *6.4 – Structured Step-by-Step Execution Plan*.
It converts the high-level **six-week roadmap** (see theory section) into
*machine-readable* data structures, a **markdown generator**, and a **Typer CLI**
so that downstream utilities (dashboards, CI checks, prompt builders) can query
or render the plan programmatically.

Design goals
~~~~~~~~~~~~
* **Pure stdlib** + :pypi:`typer` + project :pymod:`src.logger` only.
* **Transparent & auditable** – all data is stored in a static list within this
  file and therefore version-controlled.
* **Human-friendly** – ``generate_markdown()`` outputs a polished table for
  READMEs or project wikis.
* **CLI-first** – ``python -m src.structured_execution_plan doc --write`` writes
  a markdown file with default naming.

Security & ethics
~~~~~~~~~~~~~~~~~
* No network or file-system introspection besides an optional *--write* path.
* Fully deterministic output – no randomness or external dependencies.
"""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "ExecutionStep",
    "get_execution_plan",
    "generate_markdown",
    "app",
]

_log = get_logger(__name__)

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Data catalogue – edit here to extend 📝
# ---------------------------------------------------------------------------


@dataclass
class ExecutionStep:  # noqa: D101 – simple value holder
    """Represents one *concrete* roadmap step in the six-week execution plan."""

    id: int
    title: str
    weeks: str  # e.g. "1-2" or "6+" for ongoing phases
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


_STEPS: List[ExecutionStep] = [
    ExecutionStep(
        id=1,
        title="Platform Access Planning",
        weeks="1-2",
        description=(
            "Scope Windows/Linux feature parity and establish a priority list. "
            "Begin cross-platform technology assessment (e.g. Mac Catalyst, Swift "
            "Cross-Platform, Electron)."
        ),
        key_actions=(
            "Compile feature parity matrix for Windows/Linux",
            "Rank platform gaps by user impact",
            "Evaluate cross-platform tooling options",
        ),
    ),
    ExecutionStep(
        id=2,
        title="Tier Design + Backend Integration",
        weeks="2-3",
        description=(
            "Define three new SKUs and connect pricing logic to backend licencing "
            "services."
        ),
        key_actions=(
            "Draft 'Free Starter' tier – basic prompts, no CodeMap",
            "Draft 'Student/Academic' tier – 50% discount, full features",
            "Draft 'Startup Team Pack' – sliding scale pricing, capped per-seat",
            "Update backend schema for tier metadata",
        ),
    ),
    ExecutionStep(
        id=3,
        title="EDU Verification + Billing Logic",
        weeks="3-4",
        description="Integrate SheerID / GitHub Education Pack and automate tier activation.",
        key_actions=(
            "Implement SheerID/GitHub OAuth verification flow",
            "Persist verification status in user profile",
            "Hook licence manager to activate Student/Academic tier automatically",
        ),
    ),
    ExecutionStep(
        id=4,
        title="Public Rollout Prep",
        weeks="4-5",
        description="Prepare marketing collateral and updated pricing page for launch.",
        key_actions=(
            "Publish updated pricing & tier comparison page",
            "Launch campaign \"Code More, Pay Less\" targeting students & startups",
            "Coordinate announcement schedule across social/email channels",
        ),
    ),
    ExecutionStep(
        id=5,
        title="Monitor, Evaluate, Optimize",
        weeks="6+",
        description="Deploy analytics & feedback loops to measure adoption and iterate.",
        key_actions=(
            "Instrument Mixpanel/Plausible events for tier adoption",
            "Track EDU conversion and Free ➜ Paid upgrade ratios",
            "Analyse platform adoption per OS via telemetry",
            "Collect exit surveys and NPS data for continuous improvement",
        ),
    ),
]

# Quick lookup tables
_STEPS_BY_ID: Dict[int, ExecutionStep] = {s.id: s for s in _STEPS}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_execution_plan(*, weeks: str | Sequence[str] | None = None) -> List[Dict[str, Any]]:
    """Return the execution plan filtered by *weeks* (default: all).

    Parameters
    ----------
    weeks: str | Sequence[str] | None, optional
        When provided, filters steps to the specified **week numbers** (e.g. "1", "3-4").
        Accepts a single string or a list of strings. Ranges ("3-4") are expanded.

    Returns
    -------
    List[Dict[str, Any]]
        The steps (order preserved) as JSON-serialisable dictionaries.
    """

    if weeks is None:
        selected = _STEPS
    else:
        week_set: set[int] = set()
        if isinstance(weeks, str):
            weeks = [weeks]
        for w in weeks:  # type: ignore[assignment]
            if "+" in w:  # handle "6+" style open-ended phases
                start = int(w.rstrip("+"))
                week_set.update(range(start, 99))
            elif "-" in w:
                start, end = w.split("-", 1)
                week_set.update(range(int(start), int(end) + 1))
            else:
                week_set.add(int(w))

        def _matches(step: ExecutionStep) -> bool:
            for part in step.weeks.split(","):
                part = part.strip()
                if "+" in part:
                    s = int(part.rstrip("+"))
                    if any(wk >= s for wk in week_set):
                        return True
                elif "-" in part:
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

def generate_markdown() -> str:  # noqa: D401 – imperative tone fine
    """Return a markdown document representing the execution roadmap."""

    lines: List[str] = [
        "# Structured Execution Plan (Step 6.4)",
        "",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| ID | Weeks | Title | Key Actions |",
        "|----|-------|-------|-------------|",
    ]

    for s in _STEPS:
        actions = "<br>".join(s.key_actions)
        lines.append(f"| {s.id} | {s.weeks} | **{s.title}** | {actions} |")

    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# Typer CLI – programmatic access 🚀
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate or query the 6.4 execution plan.")


@app.command()
def doc(
    write: bool = typer.Option(False, "--write", help="Write markdown to file instead of stdout"),
    path: Path = typer.Option(Path("docs/structured_execution_plan.md"), "--path", "-p", help="Destination markdown path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without prompt"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Render the execution plan as markdown."""

    md = generate_markdown()
    if write:
        if path.exists() and not force:
            typer.echo(f"Error: {path} exists. Use --force to overwrite.")
            raise typer.Exit(code=1)
        path.write_text(md, encoding="utf-8")
        if verbose:
            typer.echo(f"Execution plan written to {path.resolve()}")
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
    """Print machine-readable JSON or pretty summary of the selected steps."""

    selected = get_execution_plan(weeks=weeks)

    if json_output:
        typer.echo(json.dumps(selected, indent=2))
    else:
        for step in selected:
            typer.echo(f"* Week(s) {step['weeks']}: {step['title']}")
            for act in step["key_actions"]:
                typer.echo(f"  - {act}")
            typer.echo()

    if verbose:
        typer.echo(f"Returned {len(selected)} step(s)")