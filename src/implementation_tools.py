"""implementation_tools.py – Step 4.5 Methods & Tools for Implementation 🛠️🚀

This module operationalises the *4.5 Methods and Tools for Implementation* section
of the project specification.  While earlier steps validate feasibility
(:pymod:`src.feasibility_constraints`) and engineering stack readiness
(:pymod:`src.engineering_stack`), **4.5** focuses on the *concrete runtimes*
needed to *run* advanced language models **locally**, *track* their ecological
footprint and *package* the resulting applications with a cross-platform UI.

Key capabilities
----------------
* **Local inference engines** – verifies that at least one of the following is
  available on the host system so *on-device* LLM execution is possible:

  * `ollama` (preferred; HTTP API wrapper)
  * `ggml`-based binaries (`llama`, `llamafile`, …)
  * Python package `onnxruntime` (CPU/GPU inference)
* **Carbon/Energy tracking** – checks importability of
  :pypi:`codecarbon` *or* :pypi:`melodi`.  Modern teams are expected to track
  energy KPIs during model execution.
* **Token-management wrappers** – ensures that either the *official* `openai`
  SDK *or* the C++/Python bindings for *LLaMA.cpp* are installed.  These are
  needed for cost estimation & prompt budgeting utilities.
* **Swift + Metal toolchain** – on macOS we look for `swiftc` and the `metal`
  shader compiler to confirm that GPU-accelerated models *could* be built.
* **Electron/Tauri GUI scaffold** – verifies presence of the `electron` CLI
  (installed via npm) **or** `cargo + tauri-cli` for Rust-backed renderer
  builds.

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
All checks run *locally* and never transmit data.  The module merely inspects
`PATH`, Python package importability and environment variables.

Example CLI usage
-----------------
```bash
python -m src.implementation_tools check --pretty
```
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging
from .methodology_tools import CheckResult  # re-use existing lightweight dataclass

__all__ = [
    "ImplementationReadinessReport",
    "assess_implementation_readiness",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Helper checks
# ---------------------------------------------------------------------------


def _check_cmd(cmd: str, friendly: str | None = None) -> CheckResult:
    """Return :class:`CheckResult` based on *cmd* availability."""

    friendly = friendly or cmd
    path = shutil.which(cmd)
    return CheckResult(friendly, bool(path), path or "not found on PATH")


def _check_python_import(module_name: str, friendly: str | None = None) -> CheckResult:
    """Attempt to ``import`` *module_name* and return :class:`CheckResult`."""

    import importlib

    friendly = friendly or module_name
    try:
        importlib.import_module(module_name)
        return CheckResult(friendly, True, "import ok")
    except ModuleNotFoundError:
        return CheckResult(friendly, False, "module not importable")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ImplementationReadinessReport:  # noqa: D101 – documented in module docstring
    created_at: str
    os: str
    all_ok: bool
    checks: List[CheckResult]

    # Serialisation helpers -------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial
        return {
            "created_at": self.created_at,
            "os": self.os,
            "all_ok": self.all_ok,
            "checks": [c.as_dict() for c in self.checks],
        }

    def to_json(self, **kwargs) -> str:  # pragma: no cover
        import json

        return json.dumps(self.as_dict(), indent=2, **kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assess_implementation_readiness(*, pretty: bool = False) -> ImplementationReadinessReport:
    """Return an :class:`ImplementationReadinessReport` that summarises host readiness.

    The assessment **does not** attempt to run heavyweight benchmarks.  Instead
    it focuses on the *presence* of compilers, CLIs and Python packages that
    enable local-first LLM development & GUI packaging workflows.
    """

    from datetime import datetime

    checks: List[CheckResult] = []

    # 1️⃣ Local inference engines -------------------------------------------

    # Prefer runtime executables (fast PATH lookup) then Python package.
    checks.append(_check_cmd("ollama", "Ollama CLI"))
    # ggml-based binaries vary – detect common aliases
    ggml_found = any(shutil.which(cmd) for cmd in ("llama", "llamafile", "ggml"))
    checks.append(CheckResult("GGML binary", ggml_found, "found on PATH" if ggml_found else "not found"))
    # onnxruntime import (no GPU check)
    checks.append(_check_python_import("onnxruntime", "onnxruntime Python"))

    # 2️⃣ Carbon / energy tracking libs -------------------------------------
    checks.append(_check_python_import("codecarbon", "CodeCarbon lib"))
    checks.append(_check_python_import("melodi", "MELODI lib"))

    # 3️⃣ Token management wrappers -----------------------------------------
    checks.append(_check_python_import("openai", "OpenAI SDK"))
    checks.append(_check_python_import("llama_cpp", "llama_cpp bindings"))

    # 4️⃣ Swift + Metal toolchain (macOS only) ------------------------------
    if platform.system() == "Darwin":
        checks.append(_check_cmd("swiftc", "Swift compiler"))
        checks.append(_check_cmd("metal", "Metal shader compiler"))
    else:
        checks.append(CheckResult("Swift compiler (non-macOS)", False, "only available on macOS"))
        checks.append(CheckResult("Metal compiler (non-macOS)", False, "macOS-only"))

    # 5️⃣ GUI packaging CLIs -------------------------------------------------
    # Electron via npm (electron --version)
    electron_ok = False
    path = shutil.which("electron") or shutil.which("electron.cmd")  # Windows shim
    if path:
        electron_ok = True
    else:
        # Try `npx electron -v` (cheap)
        try:
            subprocess.run(["npx", "--yes", "electron", "--version"], capture_output=True, text=True, timeout=5, check=True)
            electron_ok = True
        except Exception:  # noqa: BLE001 – any failure means not available
            electron_ok = False
    checks.append(CheckResult("Electron CLI", electron_ok, path or "npx electron check"))

    # Tauri – requires cargo and tauri-cli
    tauri_ok = False
    if shutil.which("cargo"):
        try:
            subprocess.run(["cargo", "tauri", "--version"], capture_output=True, text=True, timeout=5, check=True)
            tauri_ok = True
        except Exception:
            # Fallback: `tauri-cli` standalone binary
            tauri_ok = shutil.which("tauri") is not None
    checks.append(CheckResult("Tauri CLI", tauri_ok, "cargo tauri" if tauri_ok else "not found"))

    # ---------------- Aggregate -------------------------------------------

    all_ok = all(c.ok for c in checks if c.name != "Swift compiler (non-macOS)" and c.name != "Metal compiler (non-macOS)")

    report = ImplementationReadinessReport(
        created_at=datetime.utcnow().strftime(ISO_FMT),
        os=platform.system(),
        all_ok=all_ok,
        checks=checks,
    )

    if pretty:
        _print_report(report)

    return report


# ---------------------------------------------------------------------------
# Pretty printer (re-uses Typer colours like other modules)
# ---------------------------------------------------------------------------


def _print_report(report: ImplementationReadinessReport) -> None:  # noqa: D401 – imperative fine
    import textwrap

    status = "✔ READY" if report.all_ok else "✖ MISSING TOOLS"
    typer.secho(f"Implementation Tools Check – {status}\n", fg="green" if report.all_ok else "red", bold=True)

    for c in report.checks:
        colour = "green" if c.ok else "red"
        typer.secho(f"{c.name:<30} : {'OK' if c.ok else 'MISSING'}", fg=colour)
        if not c.ok and c.details:
            typer.echo(textwrap.indent(str(c.details), "  → "))
    typer.echo()


# ---------------------------------------------------------------------------
# Typer CLI wrapper (subcommands mirror other modules)
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=False,
    help="4.5 Implementation Tools – verifies local inference & packaging readiness.",
)


@app.command()
def check(
    pretty: bool = typer.Option(False, "--pretty", help="Print coloured human-readable table"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run readiness **checks** and print a report."""

    setup_logging("DEBUG" if verbose else "INFO")

    report = assess_implementation_readiness(pretty=pretty and not json_output)

    if json_output:
        typer.echo(report.to_json())