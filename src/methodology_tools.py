from __future__ import annotations

"""Methodologies & Tools scaffolder (Step 2.5).

This module operationalises the theoretical *2.5 Methodologies and Tools*
section from the project specification. It focuses on

* **Agile integration** – provides a *Sprint Planning* markdown skeleton that
  can be checked into version control and referenced during daily stand-ups.
* **TDD + LLM collaboration** – generates Continuous Integration (CI)
  workflows that run the **Repo-Prompt** diff-apply cycle as part of pull-request
  validation to ensure that code generated via Large Language Models passes
  the test-suite.
* **Tooling verification** – offers a quick **read-only** readiness check for
  prerequisites such as *Repo Prompt* availability, proper Git remote
  configuration (GitHub/GitLab) and LLM credentials.

Usage examples
--------------
Verify local repository readiness::

    python -m src methodology verify --pretty

Generate sprint template and write to disk::

    python -m src methodology all

Scaffold GitHub Actions workflow::

    python -m src methodology ci --write

Security notes
~~~~~~~~~~~~~~
* The module never transmits repository contents – it only reads Git metadata
  and environment variables.
* No secrets are written to generated CI files. Instead placeholders are used
  and must be replaced by the repository owner.
"""

import json
import os
import platform
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import typer
from git import Repo  # type: ignore – GitPython optional but imported lazily in CLI

from .logger import get_logger, setup_logging

__all__ = [
    "CheckResult",
    "verify_methodology_tools",
    "generate_sprint_template",
    "generate_github_workflow",
    "generate_gitlab_ci",
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
    ok: bool
    details: str | None = None

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return asdict(self)


@dataclass
class VerificationReport:  # noqa: D101 – documented in module docstring
    created_at: str = datetime.utcnow().strftime(ISO_FMT)
    repository: str | None = None
    all_ok: bool = False
    results: List[CheckResult] = None  # type: ignore[assignment]

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return {
            "created_at": self.created_at,
            "repository": self.repository,
            "all_ok": self.all_ok,
            "results": [r.as_dict() for r in self.results or []],
        }

    # convenience encoder
    def to_json(self) -> str:  # pragma: no cover – trivial helper
        return json.dumps(self.as_dict(), indent=2)


# ---------------------------------------------------------------------------
# Low-level checks (re-using patterns from *tool_setup*)
# ---------------------------------------------------------------------------


def _check_repo_prompt() -> CheckResult:
    path = shutil.which("repo-prompt")
    if path:
        return CheckResult("Repo-Prompt CLI", True, path)
    try:
        import importlib

        importlib.import_module("repo_prompt")
        return CheckResult("repo_prompt module", True, "Importable Python package")
    except ModuleNotFoundError:
        return CheckResult("Repo-Prompt availability", False, "Neither CLI nor Python package found")


def _check_vcs_remote(repo_root: Path) -> CheckResult:
    try:
        repo = Repo(repo_root)
    except Exception as exc:  # pragma: no cover – runtime dependency injection missing
        return CheckResult("Git repository", False, f"Not a Git repo: {exc}")

    try:
        remote_url = next(repo.remote().urls)
    except (IndexError, ValueError, StopIteration):  # noqa: PERF401 – explicit list comprehension not needed here
        return CheckResult("Git remote", False, "Repository has no remotes configured")

    if re.search(r"github\.com[:/].+/.+", remote_url, re.I):
        return CheckResult("GitHub remote", True, remote_url)
    if re.search(r"gitlab\.com[:/].+/.+", remote_url, re.I):
        return CheckResult("GitLab remote", True, remote_url)
    return CheckResult("Supported remote (GitHub/GitLab)", False, remote_url)


def _check_llm_access() -> CheckResult:
    if shutil.which("ollama"):
        return CheckResult("Ollama LLM", True, "Local 'ollama' runtime detected")
    if os.getenv("OPENAI_API_KEY"):
        return CheckResult("OPENAI API key", True, "OPENAI_API_KEY present")
    if os.getenv("ANTHROPIC_API_KEY"):
        return CheckResult("Anthropic API key", True, "ANTHROPIC_API_KEY present")
    return CheckResult("LLM credentials", False, "No local runtime or API token detected")


def _check_tests_exist(repo_root: Path) -> CheckResult:
    tests_dir = repo_root / "tests"
    if tests_dir.is_dir() and any(tests_dir.glob("test_*.py")):
        return CheckResult("Test suite", True, "tests/ directory with pytest files found")
    return CheckResult("Test suite", False, "No pytest files detected – set up TDD scaffold")


def _check_os() -> CheckResult:  # lighter than in *tool_setup*
    sys_name = platform.system()
    return CheckResult("Operating system", sys_name in {"Darwin", "Linux", "Windows"}, sys_name)


# ---------------------------------------------------------------------------
# Public verification helper (JSON-friendly)
# ---------------------------------------------------------------------------


def verify_methodology_tools(repo_root: str | Path = ".") -> VerificationReport:
    """Return a :class:`VerificationReport` for *repo_root*.

    The report summarises whether the repository meets the prerequisites for
    Agile + TDD + LLM collaboration.
    """

    root = Path(repo_root).resolve()
    report = VerificationReport(repository=str(root), results=[])

    checks = [_check_os(), _check_repo_prompt(), _check_llm_access(), _check_vcs_remote(root), _check_tests_exist(root)]

    report.results = checks
    report.all_ok = all(c.ok for c in checks)
    return report


# ---------------------------------------------------------------------------
# File generation helpers (sprint template & CI)
# ---------------------------------------------------------------------------


def generate_sprint_template() -> str:
    """Return a markdown *Sprint Planning* template."""

    today = datetime.utcnow().strftime("%Y-%m-%d")
    return (
        f"# Sprint Backlog\n\n"
        f"_Created {today}_\n\n"
        "| Issue | Epic | Description | Story Points | Status | TDD/LLM Notes |\n"
        "|-------|------|-------------|--------------|--------|--------------|\n"
        "|  |  |  |  |  |  |\n"
        "\n"
        "## Definition of Done\n\n"
        "1. Unit tests written and passing (pytest).\n"
        "2. Repo-Prompt *apply* run with zero diff errors.\n"
        "3. Code reviewed and merged into *main*.\n"
    )


_GITHUB_CI_YML = """name: Repo-Prompt & Tests (CI)

on:
  pull_request:
    branches: [ main ]

jobs:
  rp_tdd:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install repo-prompt  # FEEDBACK: pin version once stable

      - name: Run Repo-Prompt in apply-mode (dry-run)
        run: |
          python -m src --help  # placeholder – replace with actual rp command

      - name: Run tests (pytest)
        run: |
          pytest -q
"""


_GITLAB_CI = """stages:
  - tdd

author_bot:
  stage: tdd
  image: python:3.11-slim
  script:
    - pip install -r requirements.txt repo-prompt
    - python -m src --help  # TODO: replace with repo-prompt apply command
    - pytest -q
"""


def generate_github_workflow() -> str:
    """Return GitHub Actions YAML for Repo-Prompt + pytest."""

    return _GITHUB_CI_YML


def generate_gitlab_ci() -> str:
    """Return GitLab CI YAML for Repo-Prompt + pytest."""

    return _GITLAB_CI


# ---------------------------------------------------------------------------
# Dataclass representing writable files (mirrors *standardization.py*)
# ---------------------------------------------------------------------------


@dataclass
class FileSpec:
    path: Path
    content: str

    def as_dict(self) -> Dict[str, Any]:
        return {"path": str(self.path), "content": self.content}


# ---------------------------------------------------------------------------
# Internal helper to prepare set of files
# ---------------------------------------------------------------------------


def _file_specs(repo_root: Path | str, *, gitlab: bool) -> List[FileSpec]:
    root = Path(repo_root).resolve()

    specs = [
        FileSpec(root / "docs" / "sprint_template.md", generate_sprint_template()),
        FileSpec(root / ".github" / "workflows" / "repo_prompt_ci.yml", generate_github_workflow()),
    ]
    if gitlab:
        specs.append(FileSpec(root / ".gitlab-ci.yml", generate_gitlab_ci()))

    _log.debug("Prepared %d file specs (gitlab=%s)", len(specs), gitlab)
    return specs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


app = typer.Typer(add_completion=False, help="Scaffold Agile + TDD tooling (Step 2.5)")


@app.command()
def verify(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root to validate"),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty human text output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run readiness checks for methodologies & tooling."""

    setup_logging("DEBUG" if verbose else "INFO")

    report = verify_methodology_tools(repo_path)

    if json_output:
        typer.echo(report.to_json())
    else:
        for res in report.results:
            glyph = "✅" if res.ok else "❌"
            typer.echo(f"{glyph} {res.name}: {res.details or ''}")
        typer.echo("---")
        typer.echo("Environment ready ✔" if report.all_ok else "Environment incomplete ✖")

    raise typer.Exit(code=0 if report.all_ok else 1)


@app.command()
def sprint(
    repo_path: Path = typer.Option(Path("."), "--repo", help="Repository root (write location)"),
    write: bool = typer.Option(False, "--write", help="Write file instead of preview"),
    force: bool = typer.Option(False, "--force", help="Overwrite if exists"),
):
    """Generate *docs/sprint_template.md*."""

    spec = FileSpec(Path(repo_path).resolve() / "docs" / "sprint_template.md", generate_sprint_template())
    _output([spec], write, force)


@app.command()
def ci(
    repo_path: Path = typer.Option(Path("."), "--repo", help="Repository root (write location)"),
    platform: str = typer.Option("github", "--platform", "-p", help="CI platform: github|gitlab"),
    write: bool = typer.Option(False, "--write", help="Write file(s) instead of preview"),
    force: bool = typer.Option(False, "--force", help="Overwrite if exists"),
):
    """Generate CI workflow(s) for Repo-Prompt + pytest."""

    if platform not in {"github", "gitlab"}:
        raise typer.BadParameter("--platform must be 'github' or 'gitlab'")

    specs = _file_specs(repo_path, gitlab=(platform == "gitlab"))
    if platform == "gitlab":
        # Keep only GitLab file if that is the only requested one
        specs = [s for s in specs if s.path.match("*.gitlab-ci.yml")]
    elif platform == "github":
        specs = [s for s in specs if "github" in str(s.path)]
    _output(specs, write, force)


@app.command()
def all(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    gitlab: bool = typer.Option(False, "--gitlab", help="Include GitLab CI file in addition to GitHub"),
    write: bool = typer.Option(False, "--write", help="Write files to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
):
    """Generate sprint template **and** CI workflow(s)."""

    specs = _file_specs(repo_path, gitlab=gitlab)
    _output(specs, write, force)


# ---------------------------------------------------------------------------
# Common private output helper
# ---------------------------------------------------------------------------


def _output(specs: List[FileSpec], write: bool, force: bool) -> None:  # noqa: D401 – imperative mood not required
    if write:
        for spec in specs:
            path = spec.path
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and not force:
                _log.warning("Skipping existing %s (use --force to overwrite)", path)
                continue
            path.write_text(spec.content, encoding="utf-8")
            _log.info("Wrote %s", path)
    else:
        for spec in specs:
            typer.echo(f"--- {spec.path} ---\n{spec.content}\n")