from __future__ import annotations

"""Feasibility & Fit evaluator – Step 2.3.

This module operationalises the theoretical **2.3 Evaluate Feasibility and Fit**
section.  It inspects the *local environment* and the *repository* in order to
answer the question:

"Is it technically and organisationally feasible to roll-out the AI-assisted
workflow here – and if so, how good a *fit* is it right now?"

Key capabilities
----------------
* **OS compatibility** – verifies macOS requirement (configurable override).
* **XML prompt readiness** – scans the repo for XML prompt/diff artefacts to
  estimate the learning curve impact.
* **LLM connectivity** – checks whether *at least one* supported Large
  Language Model provider can be reached (env vars for cloud / `ollama` CLI for
  local).
* **Resource validation** – ensures the team has version control in place and
  other prerequisites are met.
* **Feasibility score** – combines the individual checks into an easy-to-grasp
  0-100 index.
* **Typer CLI** – `python -m src.feasibility_fit assess --pretty` prints a
  human-readable report; `--json` produces machine-readable output.

Security & privacy
~~~~~~~~~~~~~~~~~~
The evaluator is **read-only** and never transmits repository contents.  It only
reads file names and environment variables that are already local to the
machine.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import json
import os
import platform
import shutil
import re

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "FeasibilityReport",
    "evaluate_feasibility",
    "app",
]

_log = get_logger(__name__)

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:  # noqa: D101 – simple value holder
    name: str
    passed: bool
    weight: int  # 0-100 contribution weight (can be negative for blockers)
    details: str | None = None


@dataclass
class FeasibilityReport:  # noqa: D101 – documented in module docstring
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))
    repository: str | None = None
    score: int = 0
    checks: List[CheckResult] = field(default_factory=list)

    # ---------------------
    # Serialisation helpers
    # ---------------------

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – simple helper
        return {
            "created_at": self.created_at,
            "repository": self.repository,
            "score": self.score,
            "checks": [asdict(c) for c in self.checks],
        }

    def to_json(self) -> str:  # pragma: no cover
        return json.dumps(self.as_dict(), indent=2, sort_keys=False)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_feasibility(
    repo_root: str | Path = ".",
    *,
    allow_non_macos: bool = False,
    xml_scan_limit: int = 50,
) -> FeasibilityReport:
    """Return a :class:`FeasibilityReport` for *repo_root*.

    Parameters
    ----------
    repo_root:
        Path to the repository root directory.
    allow_non_macos:
        If *True* the macOS-only constraint is downgraded from a blocker to a
        warning (score penalty instead of hard failure).  This is useful for
        CI environments or exploratory checks on other OSes.
    xml_scan_limit:
        Maximum number of files to scan when looking for XML prompt artefacts
        (performance safeguard).
    """

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    _log.debug("Evaluating feasibility for %s", root)

    checks: List[CheckResult] = []

    # --------------------------
    # 1️⃣ OS compatibility check
    # --------------------------
    is_macos = platform.system() == "Darwin"
    if is_macos:
        checks.append(CheckResult(name="macOS requirement", passed=True, weight=25))
    else:
        msg = "Running on non-macOS host. The workflow officially supports macOS only."
        if allow_non_macos:
            checks.append(CheckResult(name="macOS requirement", passed=True, weight=10, details=msg))
        else:
            checks.append(CheckResult(name="macOS requirement", passed=False, weight=-40, details=msg))

    # ---------------------------------------------
    # 2️⃣ XML prompt / diff learning-curve heuristic
    # ---------------------------------------------
    xml_files = list(root.rglob("*.xml"))[:xml_scan_limit]
    xml_ready = bool(xml_files)
    details = None
    if not xml_ready:
        # Try to detect docs mentioning XML prompts
        pattern = re.compile(r"xml prompt", re.I)
        for doc_path in root.rglob("*.md"):
            try:
                text = doc_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if pattern.search(text):
                xml_ready = True
                break
        if not xml_ready:
            details = "No XML prompt artefacts or documentation detected. Higher learning curve expected."

    checks.append(
        CheckResult(
            name="XML prompt readiness",
            passed=xml_ready,
            weight=20 if xml_ready else -10,
            details=details,
        )
    )

    # -----------------------------------
    # 3️⃣ LLM connectivity / API presence
    # -----------------------------------
    api_keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
    }
    have_keys = any(api_keys.values())
    ollama_available = shutil.which("ollama") is not None

    if have_keys or ollama_available:
        details = None
        if have_keys:
            details = "Cloud LLM credentials detected."
        elif ollama_available:
            details = "Local 'ollama' runtime available."
        checks.append(CheckResult(name="LLM connectivity", passed=True, weight=25, details=details))
    else:
        checks.append(
            CheckResult(
                name="LLM connectivity",
                passed=False,
                weight=-20,
                details="No cloud credentials nor 'ollama' CLI detected.",
            )
        )

    # --------------------------
    # 4️⃣ Version control presence
    # --------------------------
    has_git = (root / ".git").exists()
    checks.append(
        CheckResult(
            name="Git repository",
            passed=has_git,
            weight=15 if has_git else -10,
            details=None if has_git else "Repository is not initialised with Git.",
        )
    )

    # ------------------------------------------------------------------
    # Score computation: simple weighted sum clipped to 0-100 for now
    # ------------------------------------------------------------------
    raw_score = sum(c.weight for c in checks if c.passed) + sum(c.weight for c in checks if not c.passed and c.weight < 0)
    score = max(min(raw_score, 100), 0)

    report = FeasibilityReport(repository=str(root), score=score, checks=checks)
    _log.debug("Feasibility report: %s", report.as_dict())
    return report

# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Evaluate feasibility & fit (Step 2.3).")


@app.command()
def assess(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root to analyse."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    allow_non_macos: bool = typer.Option(False, "--allow-non-macos", help="Downgrade macOS requirement to warning"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run feasibility evaluation and print the report."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        report = evaluate_feasibility(repo_path, allow_non_macos=allow_non_macos)
    except Exception as exc:
        _log.error("Evaluation failed: %s", exc)
        raise typer.Exit(code=2)

    if json_output:
        print(report.to_json())
    else:
        _pretty_print(report)

    # Non-zero exit when score < 50 to allow CI gating
    raise typer.Exit(code=0 if report.score >= 50 else 1)

# ---------------------------------------------------------------------------
# Helper – pretty printing
# ---------------------------------------------------------------------------

def _pretty_print(report: FeasibilityReport) -> None:  # noqa: D401 – imperative mood not necessary
    """Render a human-friendly summary to *stdout*."""

    try:
        from rich import box
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        # Fallback – plain text
        print(f"Feasibility & Fit report (score {report.score}/100)\n")
        for chk in report.checks:
            status = "✅" if chk.passed else "❌"
            print(f"{status} {chk.name}: {chk.details or ('ok' if chk.passed else 'failed')}")
        return

    console = Console()
    table = Table(title=f"Feasibility & Fit (score {report.score}/100)", box=box.SIMPLE)
    table.add_column("Status", justify="center", style="bold")
    table.add_column("Check")
    table.add_column("Details")

    for chk in report.checks:
        icon = "✅" if chk.passed else "❌"
        table.add_row(icon, chk.name, chk.details or ("ok" if chk.passed else "failed"))

    console.print(table)