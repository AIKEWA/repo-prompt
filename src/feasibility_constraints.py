"""feasibility_constraints.py – Step 4.3 Evaluate Feasibility & Constraints ✅⚙️

This module operationalises the *4.3 Evaluate Feasibility and Constraints* theory
block.  While earlier steps (see :pymod:`src.feasibility_fit` **2.3** and
:pymod:`src.constraints_evaluation` **3.3**) already cover *foundational*
aspects, **4.3** shifts the focus to *advanced* local-AI workflows.

Specifically we assess whether a repository / developer workstation can support
*token-aware prompting* and *diff-based editing* **locally** while also
preparing for *carbon-aware scheduling* and *standardised telemetry*.

Key capabilities
----------------
* **Runtime readiness** – verifies that either *Ollama* or a `llama.cpp` binary
  is available so models like *Mistral* or *LLaMA* can run on-device.
* **UI integration check** – ensures :pymod:`src.token_estimator` and
  :pymod:`src.patch_apply` modules are importable (required for token & diff
  tooling).
* **Hardware sufficiency** – tighter thresholds (≥8 CPU cores, ≥16 GB RAM)
  reflecting real-world model requirements.
* **Telemetry support** – detects presence of *MELODI* or *CodeCarbon*
  libraries so energy KPIs can be tracked out-of-the-box.
* **Carbon-aware scheduling hooks** – looks for a `GRID_API_TOKEN` environment
  variable (or importable `carbontracker` / `codecarbon`) as proxy for grid
  integration readiness.
* **Weighted score** – combines checks into a 0-100 index, higher means fewer
  blockers.
* **Typer CLI** – `python -m src.feasibility_constraints assess --pretty` prints
  a human-friendly table, `--json` outputs machine-readable JSON.

Security & privacy
~~~~~~~~~~~~~~~~~~
All checks run *locally* and never transmit data.  We only inspect metadata
(e.g. CPU count, env vars, presence of Python packages).
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "CheckResult",
    "FeasibilityConstraintsReport",
    "evaluate_feasibility_constraints",
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
    weight: int  # contribution to total score (negative for blockers)
    details: str | None = None

    def as_dict(self) -> Dict[str, Any]:  # convenience for JSON serialisation
        return asdict(self)


@dataclass
class FeasibilityConstraintsReport:  # noqa: D101 – documented in module docstring
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))
    repository: str | None = None
    score: int = 0  # 0-100 (100 = perfect readiness)
    checks: List[CheckResult] = field(default_factory=list)

    # --------------
    # Serialisation
    # --------------

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – simple helper
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


def evaluate_feasibility_constraints(repo_root: str | Path = ".") -> FeasibilityConstraintsReport:
    """Return a :class:`FeasibilityConstraintsReport` for *repo_root*.

    The evaluator inspects the **local environment** and **repository** to gauge
    how feasible it is to run advanced local-AI editing workflows.
    """

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    _log.debug("Evaluating 4.3 feasibility/constraints for %s", root)

    checks: List[CheckResult] = []

    # -------------------------------
    # 1️⃣ Runtime readiness – Ollama / llama.cpp
    # -------------------------------
    ollama_available = shutil.which("ollama") is not None
    llama_cpp_available = _command_exists("llama")
    runtime_ok = ollama_available or llama_cpp_available
    checks.append(
        CheckResult(
            name="Local LLM runtime (Ollama / llama.cpp)",
            passed=runtime_ok,
            weight=25 if runtime_ok else -25,
            details=(
                "`ollama` CLI detected"
                if ollama_available
                else ("`llama` binary detected" if llama_cpp_available else "No local LLM runtime on PATH")
            ),
        )
    )

    # ----------------------------------
    # 2️⃣ UI integration – token & diff tooling
    # ----------------------------------
    token_lib_ok = _module_exists("src.token_estimator")
    diff_tool_ok = _module_exists("src.patch_apply")
    ui_integration_ok = token_lib_ok and diff_tool_ok
    details_ui = []
    if not token_lib_ok:
        details_ui.append("token_estimator missing")
    if not diff_tool_ok:
        details_ui.append("patch_apply missing")
    checks.append(
        CheckResult(
            name="UI integration (token/diff)",
            passed=ui_integration_ok,
            weight=20 if ui_integration_ok else -10,
            details="; ".join(details_ui) if details_ui else "token & diff helpers present",
        )
    )

    # -------------------------------
    # 3️⃣ Hardware sufficiency – CPU & RAM
    # -------------------------------
    min_cores = 8
    cpu_cores = os.cpu_count() or 1
    cpu_ok = cpu_cores >= min_cores

    ram_ok = _has_enough_ram(min_gb=16)

    hardware_ok = cpu_ok and ram_ok
    checks.append(
        CheckResult(
            name="Compute resources (≥8 cores & ≥16 GB RAM)",
            passed=hardware_ok,
            weight=20 if hardware_ok else -20,
            details=f"{cpu_cores} core(s), RAM {'ok' if ram_ok else 'low'}",
        )
    )

    # ----------------------------------
    # 4️⃣ Telemetry framework readiness
    # ----------------------------------
    melodi_ok = _module_exists("melodi")
    codecarbon_ok = _module_exists("codecarbon")
    telemetry_ok = melodi_ok or codecarbon_ok
    checks.append(
        CheckResult(
            name="Telemetry libs (MELODI / CodeCarbon)",
            passed=telemetry_ok,
            weight=15 if telemetry_ok else -15,
            details="Found " + ("MELODI" if melodi_ok else ("CodeCarbon" if codecarbon_ok else "none")),
        )
    )

    # ----------------------------------
    # 5️⃣ Carbon-aware scheduling readiness
    # ----------------------------------
    grid_api_token = os.getenv("GRID_API_TOKEN")
    carbontracker_ok = _module_exists("carbontracker")
    carbon_ready = bool(grid_api_token) or carbontracker_ok or codecarbon_ok
    detail_carbon = []
    if grid_api_token:
        detail_carbon.append("GRID_API_TOKEN set")
    if carbontracker_ok:
        detail_carbon.append("carbontracker lib")
    if codecarbon_ok:
        detail_carbon.append("CodeCarbon lib")
    checks.append(
        CheckResult(
            name="Carbon-aware scheduling hooks",
            passed=carbon_ready,
            weight=20 if carbon_ready else -10,
            details=", ".join(detail_carbon) if detail_carbon else "No grid API / carbon libs",
        )
    )

    # ------------------------------------------------------------------
    # Score computation – weighted sum clipped to 0-100
    # ------------------------------------------------------------------
    raw_score = sum(c.weight for c in checks if c.passed) + sum(
        c.weight for c in checks if not c.passed and c.weight < 0
    )
    score = max(min(raw_score, 100), 0)

    return FeasibilityConstraintsReport(repository=str(root), score=score, checks=checks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _module_exists(name: str) -> bool:
    """Return *True* if *name* can be imported without side effects."""

    try:
        importlib.import_module(name)
        return True
    except Exception:  # broad except ok – we only care about availability
        return False


def _command_exists(cmd: str) -> bool:
    """Return *True* when *cmd* is found on `$PATH`."""

    return shutil.which(cmd) is not None


def _has_enough_ram(min_gb: int = 16) -> bool:
    """Best-effort RAM check – returns *True* if ≥ *min_gb* of memory present."""

    sys_platform = platform.system()
    try:
        if sys_platform == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            mem_bytes = int(out.strip())
            return mem_bytes >= min_gb * 1_073_741_824  # 1024³
        if sys_platform == "Linux":
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal"):
                        parts = line.split()
                        mem_kb = int(parts[1])
                        return mem_kb >= min_gb * 1_048_576  # 1024²
    except Exception as exc:  # noqa: BLE001 – best-effort
        _log.debug("RAM check failed: %s", exc)
        # fallthrough to assume insufficient
    return False


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="4.3 Feasibility & Constraints assessment")


@app.command()
def assess(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root to analyse."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run 4.3 feasibility evaluation and print a summary."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        report = evaluate_feasibility_constraints(repo_path)
    except Exception as exc:
        _log.error("Evaluation failed: %s", exc)
        raise typer.Exit(code=2)

    if json_output:
        print(report.to_json())
    else:
        _pretty_print(report)

    # CI gating – require score ≥60
    raise typer.Exit(code=0 if report.score >= 60 else 1)


# ---------------------------------------------------------------------------
# Pretty printing helper
# ---------------------------------------------------------------------------

def _pretty_print(report: FeasibilityConstraintsReport) -> None:  # noqa: D401 – imperative mood not necessary
    """Rich/console rendering of the report."""

    try:
        from rich import box
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        # Plain fallback
        print(f"Feasibility & Constraints report (score {report.score}/100)\n")
        for chk in report.checks:
            icon = "✅" if chk.passed else "❌"
            print(f"{icon} {chk.name}: {chk.details or ('ok' if chk.passed else 'failed')}")
        return

    console = Console()
    table = Table(title=f"4.3 Feasibility & Constraints (score {report.score}/100)", box=box.SIMPLE)
    table.add_column("Status", justify="center", style="bold")
    table.add_column("Check")
    table.add_column("Details")

    for chk in report.checks:
        icon = "✅" if chk.passed else "❌"
        table.add_row(icon, chk.name, chk.details or ("ok" if chk.passed else "failed"))

    console.print(table)