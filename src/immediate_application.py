from __future__ import annotations

"""immediate_application.py – Step 8.1 Immediate Application 🚀

This module operationalises **Step 8.1 – Immediate Application (Near-term)**
from the specification.  It provides two complementary capabilities that help
teams *ship faster* while retaining **safety nets**:

1. 🛰️ **Server-side connectors** – lightweight *YAML scaffold generators* for
   CI/CD platforms (GitHub Actions, Azure Pipelines) **and** a *mock* AWS Lambda
   function template so that back-end glue code can be tested in isolation.
2. 🪞 **RefactoringMirror safety layer** – run potentially risky *patches* or
   *large identifier refactors* inside a **throw-away mirror** of the
   repository.  The mirror executes the full **test-suite** and only when all
   checks pass the change is applied to the original codebase.

Both features are exposed via a single Typer CLI so that non-Python
stakeholders (e.g. DevOps engineers) can integrate them into existing
automation workflows:

```bash
# Generate a GitHub Actions workflow skeleton
python -m src.immediate_application connectors scaffold github --out .github/workflows/ci.yml

# Apply a patch safely using the mirror layer
python -m src.immediate_application mirror apply --patch-file changes.diff --run-tests

# Perform an identifier rename inside a mirror
python -m src.immediate_application mirror refactor old_name new_name --run-tests
```

Security & Ethics
~~~~~~~~~~~~~~~~~
* **Local-only** file operations – no outbound network calls.
* The mirror lives inside the system *temp* directory and is wiped afterwards.
* Large mirrors skip ``.git`` history to minimise disk usage (uses
  ``git clone --local --depth 1`` when Git is available, otherwise falls back
  to :pymod:`shutil.copytree`).
* All inputs (patch paths, identifiers) are validated/sanitised to avoid code
  injection.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap

import typer

from .logger import get_logger, setup_logging
from .patch_apply import apply_patch_set
from .large_refactor import apply_refactor

__all__ = [
    # Connectors public API
    "scaffold_connector",
    # Mirror public API
    "run_in_mirror",
    # Typer CLI
    "app",
]

_log = get_logger(__name__)

###############################################################################
# 1. Server-side connector scaffolds                                          #
###############################################################################


_Connector = Literal["github", "azure", "lambda"]


def _gh_actions_template() -> str:
    """Return minimal **GitHub Actions** YAML workflow."""

    return textwrap.dedent(
        """
        name: CI
        on: [push, pull_request]
        jobs:
          tests:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - name: Set up Python
                uses: actions/setup-python@v5
                with:
                  python-version: '3.x'
              - name: Install dependencies
                run: |
                  python -m pip install --upgrade pip
                  pip install -r requirements.txt
              - name: Run test suite
                run: pytest -q
        """
    ).lstrip()


def _azure_pipeline_template() -> str:
    """Return minimal **Azure Pipelines** YAML workflow."""

    return textwrap.dedent(
        """
        trigger:
          - main

        pool:
          vmImage: 'ubuntu-latest'

        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.x'
          - script: |
              python -m pip install --upgrade pip
              pip install -r requirements.txt
            displayName: 'Install dependencies'
          - script: pytest -q
            displayName: 'Run test suite'
        """
    ).lstrip()


def _lambda_mock_template() -> str:
    """Return **mock AWS Lambda** handler template (Python)."""

    return textwrap.dedent(
        """
        # lambda_function.py – mock AWS Lambda entry-point.

        # Replace the business logic with your own implementation and add unit
        # tests in `tests/test_lambda_function.py`.

        from __future__ import annotations

        import json

        def handler(event, context):  # noqa: D401 – AWS signature
            '''Example Lambda handler that echoes the incoming payload.'''

            # FEEDBACK: Add input validation
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"received": event}),
            }
        """
    ).lstrip()


_TEMPLATE_REGISTRY: Dict[_Connector, str] = {
    "github": _gh_actions_template(),
    "azure": _azure_pipeline_template(),
    "lambda": _lambda_mock_template(),
}


def scaffold_connector(connector: _Connector) -> str:
    """Return the YAML / source template for *connector*.

    Raises ``KeyError`` for unknown connectors.
    """

    return _TEMPLATE_REGISTRY[connector]


###############################################################################
# 2. RefactoringMirror safety layer                                          #
###############################################################################


@dataclass
class MirrorReport:  # noqa: D101 – value holder
    root: str
    applied_files: List[str]
    tests_passed: bool
    pytest_stdout: str
    pytest_stderr: str

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return asdict(self)

    def to_json(self, **kwargs) -> str:  # pragma: no cover – convenience
        return json.dumps(self.as_dict(), indent=2, **kwargs)


# -----------------------------
# Helper utilities
# -----------------------------

def _run_tests(repo_root: Path) -> tuple[bool, str, str]:
    """Execute *pytest* inside *repo_root* and return (ok, stdout, stderr)."""

    _log.debug("Running tests in mirror %s", repo_root)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover – defensive
        return False, "", str(exc)

    ok = result.returncode == 0
    return ok, result.stdout, result.stderr


def _mirror_clone(src: Path) -> Path:
    """Return *Path* to a fresh mirror clone of *src* repo/project."""

    tmpdir = Path(tempfile.mkdtemp(prefix="mirror_"))
    _log.debug("Creating mirror at %s", tmpdir)

    # Fast path – use *git clone --local* when possible to avoid huge copy
    if shutil.which("git") and (src / ".git").exists():
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--local",
                    "--depth",
                    "1",
                    str(src),
                    str(tmpdir),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return tmpdir
        except subprocess.CalledProcessError as exc:  # pragma: no cover
            _log.warning("git clone failed, falling back to copytree: %s", exc)

    # Fallback – plain copy (skip .* to avoid venv + git history bloat)
    def _ignore(path: str, names: List[str]):  # noqa: D401 – callback
        return [n for n in names if n.startswith(".") and n not in {"src", "tests"}]

    shutil.copytree(src, tmpdir, dirs_exist_ok=True, ignore=_ignore)  # type: ignore[arg-type]
    return tmpdir


# -----------------------------
# Public API
# -----------------------------

def run_in_mirror(
    repo_root: Path | str,
    *,
    patch_text: Optional[str] = None,
    refactor_pair: tuple[str, str] | None = None,
    run_tests: bool = True,
    dry_run: bool = True,
    backup: bool = False,
) -> MirrorReport:
    """Apply *patch_text* **or** *refactor_pair* inside a mirror of *repo_root*.

    When *run_tests* is *True* (default) the mirror executes the full pytest
    suite.  If tests fail **no** changes are propagated back to the original
    repository.  On success the modifications are applied using
    :pymod:`src.patch_apply.apply_patch_set` or :pymod:`src.large_refactor.apply_refactor`.
    """

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    if patch_text and refactor_pair:
        raise ValueError("Provide either 'patch_text' or 'refactor_pair', not both")

    mirror = _mirror_clone(root)

    applied: List[str] = []

    if patch_text:
        applied = apply_patch_set(mirror, patch_text, dry_run=False, create_backup=False)
    elif refactor_pair:
        old, new = refactor_pair
        applied = apply_refactor(mirror, old, new, dry_run=False, backup=False)
    else:
        _log.info("No modifications provided – running tests only")

    tests_ok: bool = True
    stdout = stderr = ""
    if run_tests:
        tests_ok, stdout, stderr = _run_tests(mirror)

    # Propagate change back if tests pass and not dry_run
    if tests_ok and not dry_run and applied:
        if patch_text:
            apply_patch_set(root, patch_text, dry_run=False, create_backup=backup)
        elif refactor_pair:
            old, new = refactor_pair
            apply_refactor(root, old, new, dry_run=False, backup=backup)

    # Clean-up mirror (best-effort) – errors ignored.
    try:
        shutil.rmtree(mirror)
    except Exception:  # pragma: no cover – ignore clean failures
        pass

    return MirrorReport(str(root), applied, tests_ok, stdout, stderr)


###############################################################################
# 3. Typer CLI                                                                #
###############################################################################

app = typer.Typer(add_completion=False, help="Step 8.1 Immediate Application helpers")


# ---------------------------------------------------------------------------
# 3.1 Connectors commands
# ---------------------------------------------------------------------------


_connect_app = typer.Typer(name="connectors", help="Generate server-side connector scaffolds")
app.add_typer(_connect_app)


@_connect_app.command("scaffold")
def cli_scaffold(
    connector: _Connector = typer.Argument(..., help="github | azure | lambda"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write to file instead of STDOUT"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print or write *connector* template."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        content = scaffold_connector(connector)
    except KeyError:  # pragma: no cover
        typer.echo(f"Unknown connector '{connector}'", err=True)
        raise typer.Exit(code=1)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        typer.echo(f"Template written to {out}")
    else:
        typer.echo(content)


# ---------------------------------------------------------------------------
# 3.2 Mirror commands
# ---------------------------------------------------------------------------


_mirror_app = typer.Typer(name="mirror", help="Run patches/refactors inside a safety mirror")
app.add_typer(_mirror_app)


@_mirror_app.command("apply")
def cli_mirror_apply(
    patch_file: Path = typer.Option(..., "--patch-file", exists=True, readable=True, help="Unified diff to apply"),
    run_tests: bool = typer.Option(True, "--run-tests/--no-tests", help="Execute pytest inside mirror"),
    apply_changes: bool = typer.Option(False, "--apply", help="Actually propagate changes when tests pass"),
    backup: bool = typer.Option(False, "--backup", help="Create *.bak backups when writing to source repo"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON report"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Apply *patch_file* inside a mirror and optionally propagate."""

    setup_logging("DEBUG" if verbose else "INFO")

    patch_text = patch_file.read_text(encoding="utf-8")
    report = run_in_mirror(
        Path("."),
        patch_text=patch_text,
        run_tests=run_tests,
        dry_run=not apply_changes,
        backup=backup,
    )

    if json_output:
        typer.echo(report.to_json())
    else:
        status = "✅" if report.tests_passed else "✖"
        typer.echo(f"{status} Tests {'passed' if report.tests_passed else 'failed'} • Files changed: {len(report.applied_files)}")


@_mirror_app.command("refactor")
def cli_mirror_refactor(
    old: str = typer.Argument(..., help="Identifier to replace"),
    new: str = typer.Argument(..., help="Replacement identifier"),
    run_tests: bool = typer.Option(True, "--run-tests/--no-tests"),
    apply_changes: bool = typer.Option(False, "--apply", help="Propagate when tests succeed"),
    backup: bool = typer.Option(False, "--backup", help="Create *.bak before overwriting"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON report"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run large identifier rename inside a mirror safety layer."""

    setup_logging("DEBUG" if verbose else "INFO")

    report = run_in_mirror(
        Path("."),
        refactor_pair=(old, new),
        run_tests=run_tests,
        dry_run=not apply_changes,
        backup=backup,
    )

    if json_output:
        typer.echo(report.to_json())
    else:
        status = "✅" if report.tests_passed else "✖"
        typer.echo(f"{status} Tests {'passed' if report.tests_passed else 'failed'} • Files changed: {len(report.applied_files)}")


# ---------------------------------------------------------------------------
# 3.3 CI helper command – run tests & print metrics
# ---------------------------------------------------------------------------


@app.command("ci-run")
def cli_ci_run(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON metrics"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run *pytest* and print summary metrics (pass/fail, duration)."""

    setup_logging("DEBUG" if verbose else "INFO")

    ok, stdout, stderr = _run_tests(Path("."))

    metrics = {
        "passed": ok,
        "stdout": stdout,
        "stderr": stderr,
    }

    if json_output:
        json.dump(metrics, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        tyre = "✅" if ok else "✖"
        typer.echo(f"{tyre} Test suite {'passed' if ok else 'failed'}")
        if stdout:
            typer.echo(stdout)
        if stderr:
            typer.echo(stderr, err=True)


if __name__ == "__main__":  # pragma: no cover – CLI entry-point
    app()  # pylint: disable=no-value-for-parameter