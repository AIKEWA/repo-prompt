from __future__ import annotations

"""feasibility_constraints_ui.py – Step 5.3 Feasibility & Constraints 🧩🍎

This module operationalises the *5.3 Feasibility & Constraints* theory block.
Whereas previous feasibility helpers focus on **tooling** (see
:pymod:`src.feasibility_fit`) or low-level **runtime** limits (see
:pymod:`src.feasibility_constraints`), **5.3** zooms in on the *product & user
experience* constraints that arise when shipping a **macOS-native** AI coding
assistant.

We inspect three key areas:

1. **Technical feasibility** – is the host *actually* macOS and are essential
   tool-chain components (*Swift*, *Git*) available?  High-level capability is a
   prerequisite for a native experience.
2. **Onboarding gap** – do onboarding docs or interactive tutorials exist that
   lower the *steep learning curve*?  Presence of *docs/onboarding.md* or the
   :pymod:`src.training_support` module counts as mitigation.
3. **Cognitive overload** – do UX heuristics indicate the UI is *too busy* for
   casual users?  If the project embeds :pymod:`src.ux_guidelines` *and* a
   guideline doc exists, we consider this risk addressed.

The evaluator produces a *0-100* score where **higher** means fewer blockers.
Run via CLI:

```bash
python -m src.feasibility_constraints_ui assess --pretty
```

Security & privacy
~~~~~~~~~~~~~~~~~~
* Fully *local-first* – only inspects file-system metadata & environment.
* No network calls or telemetry collection.
"""

import json
import platform
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "UICheckResult",
    "UIFeasibilityReport",
    "evaluate_ui_feasibility_constraints",
    "app",
]

_log = get_logger(__name__)

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class UICheckResult:  # noqa: D101 – simple value holder
    name: str
    passed: bool
    weight: int  # contribution to total score (negative for blockers)
    details: str | None = None

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – convenience only
        return asdict(self)


@dataclass
class UIFeasibilityReport:  # noqa: D101 – documented above
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))
    repository: str | None = None
    score: int = 0  # 0-100 scale (100 = perfect)
    checks: List[UICheckResult] = field(default_factory=list)

    # --------------
    # Serialisation
    # --------------

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return {
            "created_at": self.created_at,
            "repository": self.repository,
            "score": self.score,
            "checks": [c.as_dict() for c in self.checks],
        }

    def to_json(self) -> str:  # pragma: no cover
        return json.dumps(self.as_dict(), indent=2) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_ui_feasibility_constraints(repo_root: str | Path = ".") -> UIFeasibilityReport:
    """Return a :class:`UIFeasibilityReport` for *repo_root*.

    The function evaluates UX-level feasibility & constraints for delivering a
    macOS-native AI coding assistant as described in the 5.3 theory block.
    """

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    _log.debug("Evaluating 5.3 UI feasibility/constraints for %s", root)

    checks: List[UICheckResult] = []

    # -------------------------------------------
    # 1️⃣ Technical feasibility – macOS & tool-chain
    # -------------------------------------------
    is_macos = platform.system() == "Darwin"
    swift_ok = shutil.which("swift") is not None  # Xcode command-line tools
    git_ok = shutil.which("git") is not None

    tech_ok = is_macos and swift_ok and git_ok
    details = []
    if not is_macos:
        details.append("Non-macOS host")
    if not swift_ok:
        details.append("'swift' compiler missing")
    if not git_ok:
        details.append("Git missing")

    checks.append(
        UICheckResult(
            name="Technical feasibility (macOS + Swift + Git)",
            passed=tech_ok,
            weight=40 if tech_ok else -40,
            details=", ".join(details) if details else "All requirements met",
        )
    )

    # -------------------------------------------
    # 2️⃣ Onboarding gap – documentation / tutorial
    # -------------------------------------------
    onboarding_docs = _find_onboarding_docs(root)
    training_support_mod = _module_exists("src.training_support")
    onboarding_ok = onboarding_docs or training_support_mod

    details_onb = []
    if onboarding_docs:
        details_onb.append("docs/onboarding.md found")
    if training_support_mod:
        details_onb.append("training_support module present")
    if not details_onb:
        details_onb.append("No onboarding artefacts detected")

    checks.append(
        UICheckResult(
            name="Onboarding resources present",
            passed=onboarding_ok,
            weight=30 if onboarding_ok else -15,
            details="; ".join(details_onb),
        )
    )

    # -------------------------------------------
    # 3️⃣ Cognitive overload – UX guideline mitigation
    # -------------------------------------------
    ux_guidelines_mod = _module_exists("src.ux_guidelines")
    ux_guidelines_doc = _find_ux_guidelines_doc(root)
    cognitive_ok = ux_guidelines_mod and ux_guidelines_doc

    details_cog = []
    if ux_guidelines_mod:
        details_cog.append("ux_guidelines module")
    if ux_guidelines_doc:
        details_cog.append("docs/ux_guidelines.md found")
    if not details_cog:
        details_cog.append("No UX guideline artefacts")

    checks.append(
        UICheckResult(
            name="Cognitive overload mitigation",
            passed=cognitive_ok,
            weight=30 if cognitive_ok else -15,
            details="; ".join(details_cog),
        )
    )

    # ------------------------------------------------------------------
    # Score computation – weighted sum clipped to 0-100
    # ------------------------------------------------------------------
    raw_score = sum(c.weight for c in checks if c.passed) + sum(
        c.weight for c in checks if not c.passed and c.weight < 0
    )
    score = max(min(raw_score, 100), 0)

    return UIFeasibilityReport(repository=str(root), score=score, checks=checks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _module_exists(name: str) -> bool:
    """Return *True* if *name* can be imported without side effects."""

    import importlib

    try:
        importlib.import_module(name)
        return True
    except Exception:  # broad except ok – availability check only
        return False


def _find_onboarding_docs(root: Path) -> bool:
    """Return *True* when onboarding markdown exists inside *root*/docs."""

    docs_dir = root / "docs"
    if not docs_dir.exists():
        return False
    for p in docs_dir.glob("onboarding.*"):
        if p.suffix.lower() in {".md", ".markdown"}:
            return True
    return False


def _find_ux_guidelines_doc(root: Path) -> bool:
    """Return *True* when *docs/ux_guidelines.md* exists."""

    return (root / "docs" / "ux_guidelines.md").exists()


# ---------------------------------------------------------------------------
# CLI entry-point – quick manual checks
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="5.3 UI Feasibility & Constraints assessor.")


@app.command()
def assess(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root to analyse."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty table output (requires *rich*)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run feasibility evaluation and print the report."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        report = evaluate_ui_feasibility_constraints(repo_path)
    except Exception as exc:  # pragma: no cover – quick CLI helper
        _log.error("Evaluation failed: %s", exc)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(report.to_json())
    elif pretty:
        try:
            _pretty_print(report)
        except ImportError:
            _log.warning("rich not installed – falling back to raw output")
            typer.echo(report.to_json())
    else:
        typer.echo(report.to_json())


# ---------------------------------------------------------------------------
# Pretty-print helper using *rich* (optional dependency)
# ---------------------------------------------------------------------------


def _pretty_print(report: UIFeasibilityReport) -> None:  # noqa: D401
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console()

    table = Table(title=f"5.3 Feasibility & Constraints (score {report.score}/100)", box=box.SIMPLE)
    table.add_column("Check")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    for chk in report.checks:
        status = "✅" if chk.passed else "❌"
        table.add_row(chk.name, status, chk.details or "-")

    console.print(table)