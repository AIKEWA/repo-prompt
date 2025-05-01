from __future__ import annotations

"""use_case_deployment.py – Step 7.2 Real-World Use Case Deployment 🚀📦

This module operationalises the *7.2 – Real-World Use Case Deployment* theory
block.  It helps a **10-developer macOS team** integrate the *Repo Prompt*
workflow by providing:

1. A **deploy-status registry** (append-only JSONL) that records installation
   details for every developer machine.
2. A **training log** for *prompt literacy* sessions aimed at team leads.
3. A **pipeline checker** that validates pre-commit & PR review integration for
   *Repo Prompt* within the current Git repository.
4. **Metrics events** mirroring the KPI trio: *copy-paste reduction*, *token
   savings*, *prompt reuse rate*.
5. A **Typer CLI** so non-Python stakeholders can manage the deployment via
   ``python -m src.use_case_deployment …`` commands.

All functionality is *local-only* – absolutely **no network calls** are made.
The design aligns with other Step-modules such as
:pyfile:`src.prompt_ops_framework` and :pyfile:`src.training_and_support`.

Security & Ethics
~~~~~~~~~~~~~~~~~
* Inputs are validated and stored with minimal personally identifiable data
  (hostname instead of full device details).
* The registry lives inside the repository to ensure transparency & auditability.
* Metric events are *aggregated* – no raw user data is exposed in summaries.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "MachineDeploymentRecord",
    "TrainingSessionRecord",
    "CopyPasteReductionEvent",
    "TokenUsageEvent",
    "PromptReuseEvent",
    "DeploymentStore",
    "check_pipeline_integration",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. Dataclasses                                                              #
###############################################################################


@dataclass(kw_only=True)
class _BaseRecord:  # noqa: D401 – simple value holder
    """Common metadata + JSON serialisation helper."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property
    def type(self) -> str:  # noqa: D401 – property for type string
        return self.__class__.__name__

    # -----------------------
    # Serialisation helpers
    # -----------------------

    def to_json(self) -> str:  # noqa: D401 – imperative
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


@dataclass
class MachineDeploymentRecord(_BaseRecord):
    """Represents *one* developer machine deployment.

    Parameters
    ----------
    hostname:
        Output of ``platform.node()`` – uniquely identifies the workstation.
    repo_prompt_version:
        Version string of the installed **Repo Prompt** package (or ``CLI``).
    precommit_installed:
        ``True`` when the *pre-commit* hook (`tools/precommit_verify.py`) is
        linked in ``.git/hooks/pre-commit``.
    pr_check_enabled:
        ``True`` if PR review rules require *Repo Prompt* CI checks (heuristic).
    verification_ok:
        Result of running :pyfunc:`src.tool_setup.verify_system` – ``True`` when
        all checks pass.
    """

    hostname: str
    repo_prompt_version: str | None
    precommit_installed: bool
    pr_check_enabled: bool
    verification_ok: bool


@dataclass
class TrainingSessionRecord(_BaseRecord):
    """Capture a *prompt literacy* training session for team leads."""

    lead_name: str
    date: str  # YYYY-MM-DD
    topics: List[str] | None = None
    duration_min: int | None = None


###############################################################################
# Metric Events                                                               #
###############################################################################


@dataclass
class _MetricBase(_BaseRecord):
    """Base class for KPI metric events."""

    @property
    def category(self) -> str:  # noqa: D401 – imperative tone ok
        return self.__class__.__name__.replace("Event", "").lower()


@dataclass
class CopyPasteReductionEvent(_MetricBase):
    """Record lines of *copy-paste* removed thanks to *Repo Prompt* integration."""

    baseline_lines: int
    improved_lines: int

    @property
    def lines_saved(self) -> int:  # noqa: D401 – convenience
        return max(self.baseline_lines - self.improved_lines, 0)


@dataclass
class TokenUsageEvent(_MetricBase):
    """Track token consumption before vs after optimisation."""

    baseline_tokens: int
    improved_tokens: int

    @property
    def tokens_saved(self) -> int:  # noqa: D401 – convenience
        return max(self.baseline_tokens - self.improved_tokens, 0)


@dataclass
class PromptReuseEvent(_MetricBase):
    """Capture how often a prompt template is reused across tasks."""

    template_name: str
    reuse_count: int


###############################################################################
# 2. Append-only JSONL store                                                  #
###############################################################################


class DeploymentStore:
    """Persistent storage for deployment & metric records (append-only JSONL)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("USE_CASE_DEPLOYMENT_FILE", ".use_case_deployment.jsonl")).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Deployment store initialised at %s", self.path)

    # -------------------
    # CRUD helpers
    # -------------------

    def append(self, record: _BaseRecord) -> None:  # noqa: D401 – imperative ok
        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        _log.info("Recorded %s", record.type)

    # Private loader – returns raw dict for flexibility
    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        data: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                try:
                    data.append(json.loads(ln))
                except json.JSONDecodeError:
                    _log.warning("Skipping invalid JSON line: %s", ln[:80])
        return data

    # -------------------
    # Aggregations & export
    # -------------------

    def summary(self) -> Dict[str, Any]:  # noqa: D401 – imperative
        raw = self._load()
        machines = [r for r in raw if r.get("type") == "MachineDeploymentRecord"]
        trainings = [r for r in raw if r.get("type") == "TrainingSessionRecord"]
        metrics = [r for r in raw if r.get("type", "").endswith("Event")]

        # KPI aggregations (simple sums / averages)
        copy_paste_saved = sum(e.get("lines_saved", 0) for e in metrics if e.get("type") == "CopyPasteReductionEvent")
        tokens_saved = sum(e.get("tokens_saved", 0) for e in metrics if e.get("type") == "TokenUsageEvent")
        total_prompt_reuse = sum(e.get("reuse_count", 0) for e in metrics if e.get("type") == "PromptReuseEvent")

        return {
            "machines_total": len(machines),
            "machines_verified": sum(1 for m in machines if m.get("verification_ok")),
            "trainings": len(trainings),
            "metrics": {
                "copy_paste_saved": copy_paste_saved,
                "tokens_saved": tokens_saved,
                "prompt_reuse": total_prompt_reuse,
            },
        }

    def export_markdown(self) -> str:
        """Return a human-readable deployment status report in Markdown."""

        data = self.summary()
        lines: List[str] = ["# 7.2 Real-World Use Case Deployment – Status Report\n"]
        lines.append(f"*Machines verified:* **{data['machines_verified']} / {data['machines_total']}**\n")
        lines.append(f"*Training sessions:* **{data['trainings']}**\n")
        m = data["metrics"]
        lines.append("## KPI Snapshot\n")
        lines.append(f"* Copy-paste lines saved: **{m['copy_paste_saved']}**")
        lines.append(f"* Tokens saved: **{m['tokens_saved']}**")
        lines.append(f"* Prompt reuse instances: **{m['prompt_reuse']}**\n")
        return "\n".join(lines)


###############################################################################
# 3. Helper – Pipeline integration check                                      #
###############################################################################


def _is_precommit_hook_installed(repo_root: Path) -> bool:
    return (repo_root / ".git" / "hooks" / "pre-commit").exists()


def _has_repo_prompt_in_hooks(repo_root: Path) -> bool:
    hook = repo_root / ".git" / "hooks" / "pre-commit"
    if not hook.exists():
        return False
    try:
        content = hook.read_text("utf-8")
    except Exception:  # pragma: no cover – defensive
        return False
    return "repo-prompt" in content or "precommit_verify" in content


def _pr_check_enabled(repo_root: Path) -> bool:
    """Heuristic: check if GitHub Actions workflow references repo-prompt."""

    workflows = repo_root / ".github" / "workflows"
    if not workflows.exists():
        return False

    for wf in workflows.glob("*.yml"):
        try:
            if "repo-prompt" in wf.read_text("utf-8"):
                return True
        except Exception:  # pragma: no cover
            continue
    return False


def check_pipeline_integration(repo_path: Path | str = Path(".")) -> Dict[str, bool]:
    """Return boolean flags describing pipeline integration status."""

    repo_root = Path(repo_path).resolve()
    return {
        "precommit_installed": _is_precommit_hook_installed(repo_root),
        "precommit_contains_repo_prompt": _has_repo_prompt_in_hooks(repo_root),
        "pr_check_enabled": _pr_check_enabled(repo_root),
    }


###############################################################################
# 4. Typer CLI                                                                #
###############################################################################


app = typer.Typer(add_completion=False, help="7.2 Use Case Deployment CLI utilities")


a_metrics = typer.Typer(help="Record metric events")
app.add_typer(a_metrics, name="metrics")


a_store_opt = typer.Option(".use_case_deployment.jsonl", "--store", help="JSONL store path")


# ------------------------------------------------------------------
# Machine deployment commands
# ------------------------------------------------------------------


@app.command("record-machine")
def record_machine(  # noqa: D401 – CLI entry point
    repo_prompt_version: str | None = typer.Option(None, "--version", "-v", help="Repo Prompt version string"),
    store_path: Path = a_store_opt,  # type: ignore[arg-type]
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Append a :class:`MachineDeploymentRecord` for the *current* machine."""

    setup_logging("DEBUG" if verbose else "INFO")

    from .tool_setup import verify_system  # local import to avoid circular

    verify = verify_system(Path("."))
    pi = check_pipeline_integration(Path("."))

    record = MachineDeploymentRecord(
        hostname=platform.node(),
        repo_prompt_version=repo_prompt_version,
        precommit_installed=pi["precommit_installed"],
        pr_check_enabled=pi["pr_check_enabled"],
        verification_ok=verify["all_ok"],
    )

    DeploymentStore(store_path).append(record)


# ------------------------------------------------------------------
# Training session commands
# ------------------------------------------------------------------


@app.command("record-training")
def record_training(  # noqa: D401 – CLI entry point
    lead_name: str = typer.Argument(..., help="Team lead name"),
    date: str = typer.Option(lambda: datetime.utcnow().strftime("%Y-%m-%d"), "--date", "-d", help="ISO date YYYY-MM-DD"),
    topics: Optional[str] = typer.Option(None, "--topics", "-t", help="Comma-separated topic list"),
    duration: int | None = typer.Option(None, "--duration", "-m", help="Duration in minutes"),
    store_path: Path = a_store_opt,  # type: ignore[arg-type]
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Log a *prompt literacy* training session for a team lead."""

    setup_logging("DEBUG" if verbose else "INFO")
    record = TrainingSessionRecord(
        lead_name=lead_name,
        date=date,
        topics=[t.strip() for t in topics.split(",")] if topics else None,
        duration_min=duration,
    )
    DeploymentStore(store_path).append(record)


# ------------------------------------------------------------------
# Metric recording commands
# ------------------------------------------------------------------


@a_metrics.command("copy-paste")
def metric_copy_paste(  # noqa: D401
    baseline: int = typer.Argument(..., help="Baseline copy-paste lines"),
    improved: int = typer.Argument(..., help="Lines after Repo Prompt adoption"),
    store_path: Path = a_store_opt,  # type: ignore[arg-type]
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Record a *CopyPasteReductionEvent*."""

    setup_logging("DEBUG" if verbose else "INFO")
    DeploymentStore(store_path).append(CopyPasteReductionEvent(baseline_lines=baseline, improved_lines=improved))


@a_metrics.command("tokens")
def metric_tokens(  # noqa: D401
    baseline: int = typer.Argument(..., help="Baseline token count"),
    improved: int = typer.Argument(..., help="Tokens after optimisation"),
    store_path: Path = a_store_opt,  # type: ignore[arg-type]
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Record a *TokenUsageEvent*."""

    setup_logging("DEBUG" if verbose else "INFO")
    DeploymentStore(store_path).append(TokenUsageEvent(baseline_tokens=baseline, improved_tokens=improved))


@a_metrics.command("reuse")
def metric_reuse(  # noqa: D401
    template_name: str = typer.Argument(..., help="Prompt template identifier"),
    count: int = typer.Argument(..., help="Number of times reused"),
    store_path: Path = a_store_opt,  # type: ignore[arg-type]
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Record a *PromptReuseEvent*."""

    setup_logging("DEBUG" if verbose else "INFO")
    DeploymentStore(store_path).append(PromptReuseEvent(template_name=template_name, reuse_count=count))


# ------------------------------------------------------------------
# Reporting commands
# ------------------------------------------------------------------


@app.command("summary")
def summary(  # noqa: D401 – CLI entry point
    store_path: Path = a_store_opt,  # type: ignore[arg-type]
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Print an *aggregate* deployment & KPI summary."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeploymentStore(store_path)
    data = store.summary()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(store.export_markdown())


# ------------------------------------------------------------------
# Self-test entry-point (manual): ``python -m src.use_case_deployment summary``
# ------------------------------------------------------------------

if __name__ == "__main__":
    app()