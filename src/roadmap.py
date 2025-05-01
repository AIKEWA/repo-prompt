from __future__ import annotations

"""Strategic roadmap generator.

Purpose
-------
Provide a lightweight helper that outputs a markdown roadmap skeleton covering
vision, planned features, optimisation tracks, and security/ethics milestones.
The output can be redirected to a file and version-controlled.
"""

from datetime import datetime
from pathlib import Path
from typing import List

import typer

__all__ = ["generate_roadmap", "app"]


SECTIONS = [
    "## Vision",
    "Describe the overarching goal and long-term impact of the project.",
    "",
    "## Near-term Features (0-3 months)",
    "- Placeholder for upcoming epics",
    "",
    "## Mid-term Initiatives (3-6 months)",
    "- Placeholder for innovations / optimisation tracks",
    "",
    "## Security & Ethics Milestones",
    "| Quarter | Activity | Owner |",  # table header
    "|---------|----------|-------|",
    "| Q1 | Threat-model update & pen-test | Security Team |",
    "| Q2 | Bias audit on recommendation engine | Ethics Lead |",
    "",
    "## KPIs & Success Metrics",
    "Reference *success_metrics* module outputs to track progress.",
    "",
    "## Timeline Gantt (high-level)",
    "```",
    "2024Q1: ██████ Security hardening",
    "2024Q2:    ██████ Feature XYZ",
    "```",
]


def generate_roadmap() -> str:
    """Return a default roadmap markdown string with today's date."""

    lines: List[str] = ["# Project Roadmap", ""]
    lines.append(f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")
    lines.extend(SECTIONS)
    return "\n".join(lines) + "\n"


app = typer.Typer(add_completion=False, help="Generate strategic roadmap markdown.")


@app.command()
def create(
    output: Path = typer.Argument(Path("ROADMAP.md"), help="Output markdown file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate default ROADMAP.md."""

    md = generate_roadmap()
    output.write_text(md, encoding="utf-8")
    if verbose:
        typer.echo(f"Roadmap written to {output.resolve()}") 