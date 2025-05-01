from __future__ import annotations

"""ux_guidelines.py – Step 5.1 Understand Theoretical Concepts 🖥️🧠

This module operationalises the *UX Principle* **"Minimise friction and cognitive
load in AI workflows"** together with macOS *Human Interface Guidelines* (HIG)
and Jakob Nielsen's heuristics (**visibility**, **control & freedom**, **error
prevention**, **recognition over recall**).  It provides two complementary
utilities:

1. ``generate_markdown()`` – produce a concise markdown document that teams can
   embed in *docs/ux_guidelines.md* or wiki pages.
2. ``audit_ux()`` – run lightweight textual heuristics against a UI *spec*
   (markdown, Figma export, etc.) to flag missing aspects early in the design
   process.

Design Goals
~~~~~~~~~~~~
* **Self-contained** – no heavyweight NLP dependencies; pure *stdlib* +
  :pypi:`typer` (already used elsewhere).
* **Extensible** – keyword lists live in ``_CHECK_RULES`` so designers can tweak
  them without editing logic.
* **Secure by default** – no file writes unless explicitly requested via CLI.

CLI examples
------------
1. Preview guidelines in the terminal (default)::

       python -m src.ux_guidelines doc

2. Write to *docs/ux_guidelines.md* (create dirs automatically)::

       python -m src.ux_guidelines doc --write --path docs/ux_guidelines.md

3. Audit a UI spec (markdown)::

       python -m src.ux_guidelines audit ui_spec.md --json
"""

import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "generate_markdown",
    "audit_ux",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Check-rule definitions – human editable ⚠️
# ---------------------------------------------------------------------------
# Each rule maps to Nielsen / HIG principles with associated *keyword* patterns.

_CHECK_RULES: Dict[str, Sequence[str]] = {
    "visibility": (
        r"status",
        r"progress",
        r"loading",
        r"feedback",
        r"preview",
    ),
    "control": (
        r"undo",
        r"redo",
        r"cancel",
        r"dismiss",
        r"override",
    ),
    "error_prevention": (
        r"confirm",
        r"validation",
        r"warning",
        r"constraints?",
    ),
    "recognition_over_recall": (
        r"autocomplete",
        r"suggest",
        r"hint",
        r"placeholder",
        r"tooltip",
    ),
}

# ---------------------------------------------------------------------------
# Dataclasses for machine-readable output
# ---------------------------------------------------------------------------


@dataclass
class UXCheck:  # noqa: D101 – simple value holder
    name: str
    ok: bool
    hits: int = 0

    def as_dict(self) -> Dict[str, str | int | bool]:  # pragma: no cover – trivial helper
        return asdict(self)


@dataclass
class UXReport:  # noqa: D101 – summarises audit results
    created_at: str
    path: str | None
    all_ok: bool
    checks: List[UXCheck]

    def as_dict(self) -> Dict[str, object]:  # pragma: no cover – trivial helper
        return {
            "created_at": self.created_at,
            "path": self.path,
            "all_ok": self.all_ok,
            "checks": [c.as_dict() for c in self.checks],
        }

    def to_json(self, **kwargs) -> str:  # pragma: no cover – convenience
        return json.dumps(self.as_dict(), indent=2, **kwargs)

# ---------------------------------------------------------------------------
# Guideline document generator
# ---------------------------------------------------------------------------


def generate_markdown() -> str:  # noqa: D401 – imperative mood fine
    """Return markdown string capturing core UX principles & heuristics."""

    lines: List[str] = [
        "# UX Guidelines – AI Workflow Interfaces",
        "",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## 1 Design North Star",
        "Minimise friction and cognitive load throughout AI-assisted flows, "
        "mirroring macOS *Human Interface Guidelines* (HIG) values of speed, "
        "polish, and agency.",
        "",
        "## 2 Heuristic Foundations",
        "| Heuristic | Description |",
        "|-----------|-------------|",
        "| Visibility of system status | Keep users informed with immediate and clear feedback. |",
        "| User control & freedom | Provide easy undo/redo and escape hatches. |",
        "| Error prevention | Design to prevent problems before they occur. |",
        "| Recognition over recall | Surface options, autocomplete & context to reduce memory load. |",
        "",
        "## 3 Practical Check-list",
        "- [ ] Is every long-running action accompanied by progress feedback?",
        "- [ ] Can the user easily *undo* or *cancel* AI suggestions?",
        "- [ ] Are destructive actions confirmed and validated?",
        "- [ ] Do inputs leverage autocomplete, contextual hints or presets?",
        "",
        "## 4 macOS HIG Alignment Tips",
        "1. Follow platform accent colours & spacing (SF Symbols, 8-pt grid).",
        "2. Use *command*-style keyboard shortcuts and support *Quick Look* previews.",
        "3. Adopt *Dark Mode* and *Dynamic Type* out of the box.",
        "",
        "## 5 Continuous Improvement",
        "Embed `audit_ux()` into CI to flag regressions as designs evolve.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Audit helper – text heuristics
# ---------------------------------------------------------------------------


def _count_hits(patterns: Sequence[str], text: str) -> int:
    return sum(len(re.findall(p, text, re.I)) for p in patterns)


def audit_ux(*, text: str | None = None, path: str | Path | None = None) -> UXReport:
    """Return :class:`UXReport` by scanning *text* or a file at *path*.

    Exactly **one** of *text* or *path* must be provided.
    """

    if (text is None) == (path is None):  # xor
        raise ValueError("Provide either 'text' or 'path'.")

    source_text: str
    if path is not None:
        p = Path(path).expanduser()
        source_text = p.read_text(encoding="utf-8")
        source_path = str(p)
    else:
        source_text = text or ""
        source_path = None

    checks: List[UXCheck] = []
    for name, patterns in _CHECK_RULES.items():
        hits = _count_hits(patterns, source_text)
        checks.append(UXCheck(name, hits > 0, hits))

    report = UXReport(
        created_at=datetime.utcnow().isoformat() + "Z",
        path=source_path,
        all_ok=all(c.ok for c in checks),
        checks=checks,
    )
    return report

# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate guidelines or audit UI specs (Step 5.1)")


@app.command()
def doc(
    write: bool = typer.Option(False, "--write", help="Write file instead of printing"),
    path: Path = typer.Option(Path("docs/ux_guidelines.md"), "--path", "-p", help="Destination markdown path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without prompt"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show or write the UX guidelines markdown."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_markdown()
    if write:
        path = path.expanduser()
        if path.exists() and not force:
            typer.echo(f"Error: {path} exists – use --force to overwrite", err=True)
            raise typer.Exit(code=1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        typer.secho(f"Guidelines written to {path.resolve()}", fg="green")
    else:
        typer.echo(md)


@app.command()
def audit(
    file: Path = typer.Argument(..., exists=True, readable=True, help="UI spec to audit ('-' for STDIN)"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run heuristic UX audit for *file*."""

    setup_logging("DEBUG" if verbose else "INFO")

    text = sys.stdin.read() if str(file) == "-" else file.read_text(encoding="utf-8")
    report = audit_ux(text=text)

    if json_output:
        typer.echo(report.to_json())
    else:
        status = "✔ PASS" if report.all_ok else "✖ ISSUES"
        colour = "green" if report.all_ok else "red"
        typer.secho(f"UX Audit – {status}\n", fg=colour, bold=True)
        for c in report.checks:
            c_colour = "green" if c.ok else "red"
            typer.secho(f"{c.name:<25}: {'OK' if c.ok else 'MISSING'} (hits={c.hits})", fg=c_colour)


if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter