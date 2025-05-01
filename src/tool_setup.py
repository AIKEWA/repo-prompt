from __future__ import annotations

"""System tooling readiness verifier (step 1.4).

This module translates the *"1.4 Tool and Methodology Setup"* theory block
into executable code that checks whether the **local developer machine** is
prepared for the Repo-Prompt workflow. It performs **read-only** diagnostics –
no modifications are made automatically – and returns a structured report that
can be inspected manually or embedded into CI logs.

Checks implemented
------------------
1. **Operating system** – macOS 12 (Monterey) or newer.
2. **Essential CLI tools** – ``git`` and either a *local* LLM binary (``ollama``)
   **or** an environment-backed *remote* LLM provider (``OPENAI_API_KEY`` or
   ``ANTHROPIC_API_KEY``).
3. **Repository hygiene** – project is under Git control **and** has a
   ``.gitignore`` file.
4. **Repo-Prompt install** – verifies that the `repo-prompt` CLI is on *PATH*
   **or** that a Python package called ``repo_prompt`` is importable.

Run via CLI:
    $ python -m src.tool_setup --repo-path .
"""

import os
import platform
import shutil
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List

from .logger import get_logger

_log = get_logger(__name__)

__all__ = [
    "verify_system",
]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Structured outcome of a single requirement verification."""

    name: str  # requirement title
    ok: bool   # did the check pass?
    details: str  # human readable explanation / path

    def as_dict(self) -> Dict[str, Any]:  # convenience for JSON serialisation
        return asdict(self)


# ---------------------------------------------------------------------------
# Individual low-level checks
# ---------------------------------------------------------------------------


def _check_os() -> CheckResult:
    """Require macOS 12 + as per spec."""

    system = platform.system()
    if system != "Darwin":
        return CheckResult("Operating system", False, f"Detected {system}, expected macOS")

    release, *_ = platform.mac_ver()[0:1]
    # Handle empty string on some CI runners
    if not release:
        return CheckResult("macOS version", False, "Unable to detect macOS version")

    try:
        major_version = int(release.split(".")[0])
    except ValueError:
        major_version = 0

    if major_version < 12:
        return CheckResult("macOS version", False, f"macOS {release} < 12 is unsupported")

    return CheckResult("macOS version", True, f"macOS {release}")


def _check_command(cmd: str, display_name: str | None = None) -> CheckResult:
    """Verify *cmd* is discoverable on PATH using :pyfunc:`shutil.which`."""

    path = shutil.which(cmd)
    ok = bool(path)
    return CheckResult(display_name or cmd, ok, path or "Not found on PATH")


def _check_gitignore(repo_path: Path) -> CheckResult:
    """Ensure the repository is initialised and has a ``.gitignore`` file."""

    if not (repo_path / ".git").exists():
        return CheckResult("Git repository", False, "Missing .git directory – initialise with `git init`")

    if (repo_path / ".gitignore").exists():
        return CheckResult(".gitignore", True, ".gitignore present")
    return CheckResult(".gitignore", False, "Missing .gitignore file")


def _check_llm_access() -> CheckResult:
    """Pass if either a *local* ollama binary **or** an API key is available."""

    if shutil.which("ollama"):
        return CheckResult("Ollama LLM", True, "`ollama` binary detected – local inference available")

    if os.getenv("OPENAI_API_KEY"):
        return CheckResult("OpenAI API key", True, "OPENAI_API_KEY set – remote inference available")

    if os.getenv("ANTHROPIC_API_KEY"):
        return CheckResult("Anthropic API key", True, "ANTHROPIC_API_KEY set – remote inference available")

    return CheckResult(
        "LLM availability",
        False,
        "Neither a local `ollama` install nor remote API keys found",
    )


def _check_repo_prompt() -> CheckResult:
    """Detect the Repo-Prompt tool either as CLI or Python module."""

    if shutil.which("repo-prompt"):
        return CheckResult("repo-prompt CLI", True, "Executable on PATH")

    try:
        import importlib  # local import to avoid top-level dependency

        importlib.import_module("repo_prompt")
        return CheckResult("repo_prompt Python package", True, "Importable as module")
    except ModuleNotFoundError:
        return CheckResult("Repo-Prompt tool", False, "Not installed – install with `pip install repo-prompt`")


# ---------------------------------------------------------------------------
# Public orchestration API
# ---------------------------------------------------------------------------


def verify_system(repo_path: Path | str = Path(".")) -> Dict[str, Any]:
    """Run all checks and return a machine-readable report.

    Parameters
    ----------
    repo_path:
        Root of the repository that should be validated.

    Returns
    -------
    dict
        ``{"results": [...], "all_ok": bool}``
    """

    repo_path = Path(repo_path).resolve()

    _log.info("Verifying system prerequisites for %s", repo_path)

    checks: List[CheckResult] = [
        _check_os(),
        _check_command("git"),
        _check_gitignore(repo_path),
        _check_llm_access(),
        _check_repo_prompt(),
    ]

    report = {
        "results": [c.as_dict() for c in checks],
        "all_ok": all(c.ok for c in checks),
    }

    _log.debug("Verification report: %s", report)
    return report


# ---------------------------------------------------------------------------
# CLI entry point – follows the lightweight pattern used in other modules
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="Check local toolchain readiness (step 1.4)")
    parser.add_argument("--repo-path", type=Path, default=Path("."), help="Path to project root")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human text")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose / debug output")
    args = parser.parse_args()

    from .logger import setup_logging

    setup_logging("DEBUG" if args.verbose else "INFO")
    summary = verify_system(args.repo_path)

    if args.json:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for res in summary["results"]:
            glyph = "✅" if res["ok"] else "❌"
            print(f"{glyph} {res['name']}: {res['details']}")
        print("---")
        print("Environment ready ✔" if summary["all_ok"] else "Environment incomplete ✖")

    # exit code signals readiness – handy for CI gating
    sys.exit(0 if summary["all_ok"] else 1) 