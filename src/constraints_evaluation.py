"""
constraints_evaluation.py – Step 3.3 Feasibility and Constraints Evaluation ⚖️

This module translates the **3.3 Feasibility and Constraints Evaluation** theory
block into *executable* Python code.  It inspects the *local environment*, the
*repository* and optional *domain context* in order to surface **constraints**
that might hinder an *offline*, privacy-first AI-assisted workflow – as well as
**enablers** that could mitigate these risks.

Why another *feasibility* helper? 🤔
----------------------------------
Step 2.3 already provides a *generic* feasibility score focused on tooling
requirements (Git, macOS, LLM connectivity).  Step 3.3 goes deeper into
*runtime* constraints – model size, hardware capabilities, cross-jurisdiction
compliance – that only become relevant once an organisation explores **on-device
or edge deployments**.

Key capabilities
----------------
* **Hardware profiling** – basic CPU & RAM heuristics using the *standard
  library* only (no heavy `psutil` dep).
* **Offline model readiness** – detects whether a *local* LLM runtime such as
  `ollama` is present.
* **Regulatory complexity** – re-uses :pyfunc:`src.real_world_context.analyze_real_world_context`
  to estimate how many *simultaneous* data-protection regimes the product must
  obey.
* **Constraint scoring** – combines the individual checks into a *0-100* index
  where higher = fewer blockers.
* **Typer CLI** – `python -m src.constraints_evaluation assess --pretty` prints
  a human-readable table; `--json` is machine-readable.

Security & privacy
~~~~~~~~~~~~~~~~~~
* Entirely *local* – no network requests.
* Reads only *metadata* (CPU count, env vars) – no user data.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from .logger import get_logger, setup_logging
from .real_world_context import analyze_real_world_context, Domain  # optional import – heavy logic inside

_log = get_logger(__name__)

__all__ = [
    "ConstraintCheck",
    "ConstraintsReport",
    "evaluate_constraints",
    "app",
]

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ConstraintCheck:  # noqa: D101 – simple value holder
    name: str
    passed: bool
    weight: int  # contribution 0-100 (negative for blockers)
    details: str | None = None

    def as_dict(self) -> Dict[str, Any]:  # convenience for JSON serialisation
        return asdict(self)


@dataclass
class ConstraintsReport:  # noqa: D101 – documented in module docstring
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))
    repository: str | None = None
    domain: str | None = None
    score: int = 0  # 0-100 (100 = no blockers)
    checks: List[ConstraintCheck] = field(default_factory=list)

    # --------------
    # Serialisation
    # --------------

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – simple helper
        return {
            "created_at": self.created_at,
            "repository": self.repository,
            "domain": self.domain,
            "score": self.score,
            "checks": [c.as_dict() for c in self.checks],
        }

    def to_json(self) -> str:  # pragma: no cover
        return json.dumps(self.as_dict(), indent=2) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_constraints(
    repo_root: str | Path = ".",
    *,
    domain: str | Domain | None = None,
) -> ConstraintsReport:
    """Return a :class:`ConstraintsReport` for *repo_root*.

    Parameters
    ----------
    repo_root:
        Path pointing at the repository root (used for Git / env checks).
    domain:
        Target *business* domain (e.g. "finance", "developer_tooling").  If
        *None* the cross-jurisdiction check is skipped.
    """

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    _log.debug("Evaluating constraints for %s (domain=%s)", root, domain)

    checks: List[ConstraintCheck] = []

    # -------------------------------
    # 1️⃣ Hardware – CPU & RAM check
    # -------------------------------
    min_cores = 4
    cpu_cores = os.cpu_count() or 1
    cpu_ok = cpu_cores >= min_cores
    checks.append(
        ConstraintCheck(
            name="CPU cores ≥ 4",
            passed=cpu_ok,
            weight=20 if cpu_ok else -20,
            details=f"{cpu_cores} core(s) detected",
        )
    )

    # RAM (rough heuristic: Darwin/Linux only; Windows fallback unknown)
    ram_ok = _has_enough_ram(min_gb=8)
    checks.append(
        ConstraintCheck(
            name="RAM ≥ 8 GB",
            passed=ram_ok,
            weight=20 if ram_ok else -20,
            details=None if ram_ok else "Less than 8 GB RAM detected",
        )
    )

    # -------------------------------------------------------
    # 2️⃣ Offline model runtime (e.g. *ollama*, llama.cpp)
    # -------------------------------------------------------
    ollama_available = shutil.which("ollama") is not None
    llama_cpp_available = _command_exists("llama")  # many users alias llama.cpp binary as `llama`

    offline_ok = ollama_available or llama_cpp_available
    detail_msg = (
        "`ollama` CLI detected"
        if ollama_available
        else ("`llama` binary detected" if llama_cpp_available else "No local LLM runtime on PATH")
    )

    checks.append(
        ConstraintCheck(
            name="Offline LLM runtime",
            passed=offline_ok,
            weight=30 if offline_ok else -30,
            details=detail_msg,
        )
    )

    # -----------------------------------------------------------------
    # 3️⃣ Cross-jurisdiction complexity → regulation count heuristic
    # -----------------------------------------------------------------
    if domain is not None:
        ctx = analyze_real_world_context(domain)
        reg_count = len(ctx["regulations"])
        # ≤2 regulations → considered manageable; else higher complexity
        multi_reg = reg_count > 2
        checks.append(
            ConstraintCheck(
                name="Regulatory complexity (≤2 regimes)",
                passed=not multi_reg,
                weight=30 if not multi_reg else -15,
                details=f"{reg_count} regime(s): {', '.join(ctx['regulations'])}",
            )
        )
    else:
        checks.append(
            ConstraintCheck(
                name="Regulatory complexity (skipped)",
                passed=True,
                weight=10,
                details="Domain not specified – check skipped",
            )
        )

    # ------------------------------------------------------------------
    # Score computation – weighted sum clipped to 0-100
    # ------------------------------------------------------------------
    raw_score = sum(c.weight for c in checks if c.passed) + sum(c.weight for c in checks if not c.passed and c.weight < 0)
    score = max(min(raw_score, 100), 0)

    return ConstraintsReport(
        repository=str(root),
        domain=str(domain) if domain is not None else None,
        score=score,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _has_enough_ram(min_gb: int = 8) -> bool:
    """Return *True* if the system has at least *min_gb* RAM (best effort).

    Uses `sysctl` on macOS and `/proc/meminfo` on Linux.  Falls back to *True*
    on unsupported platforms so we don't block Windows users unnecessarily.
    """

    sys_platform = platform.system()
    try:
        if sys_platform == "Darwin":
            # sysctl hw.memsize returns bytes
            output = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            mem_bytes = int(output.strip())
            return mem_bytes >= min_gb * 1_073_741_824  # 1024^3
        elif sys_platform == "Linux":
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal"):
                        parts = line.split()
                        # value is kB
                        mem_kb = int(parts[1])
                        return mem_kb >= min_gb * 1_048_576  # 1024^2
    except Exception as exc:  # pragma: no cover – best effort; ignore
        _log.debug("RAM check failed: %s", exc)

    # Unsupported platform → assume ok
    return True


def _command_exists(name: str) -> bool:
    """Return *True* if an executable *name* exists on `$PATH`."""

    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Evaluate Step 3.3 constraints & enablers")


@app.command()
def assess(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root to analyse."),
    domain: str = typer.Option(None, "--domain", "-d", help="Target domain e.g. finance, healthcare"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run constraints evaluation and print report."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        report = evaluate_constraints(repo_path, domain=domain)
    except Exception as exc:
        _log.error("Evaluation failed: %s", exc)
        raise typer.Exit(code=2)

    if json_output:
        print(report.to_json())
    else:
        _pretty_print(report)

    # CI gating: fail when score < 50
    raise typer.Exit(code=0 if report.score >= 50 else 1)


# ---------------------------------------------------------------------------
# Pretty printing helper (Rich optional)
# ---------------------------------------------------------------------------

def _pretty_print(report: ConstraintsReport) -> None:  # noqa: D401 – imperative mood not necessary
    """Render a human-friendly summary to *stdout*."""

    try:
        from rich import box
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        # Fallback – plain text
        print(f"Constraints report (score {report.score}/100)\n")
        for chk in report.checks:
            status = "✅" if chk.passed else "❌"
            print(f"{status} {chk.name}: {chk.details or ('ok' if chk.passed else 'failed')}")
        return

    console = Console()
    table = Table(title=f"Constraints (score {report.score}/100)", box=box.SIMPLE)
    table.add_column("Status", justify="center", style="bold")
    table.add_column("Check")
    table.add_column("Details")

    for chk in report.checks:
        icon = "✅" if chk.passed else "❌"
        table.add_row(icon, chk.name, chk.details or ("ok" if chk.passed else "failed"))

    console.print(table)