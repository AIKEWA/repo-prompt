from __future__ import annotations

"""evaluation_feedback_loops.py – Step 7.6 Evaluation & Feedback Loops 🚀📊

This module operationalises the *7.6 – Evaluation and Feedback Loops* theory
section.  It complements the existing KPI infrastructure by providing three
high-level capabilities:

1. **KPI Summary Helper** – derives *token efficiency*, *task speed*, *error
   rate* and *alignment satisfaction* from the existing JSON-Lines stores.
2. **Prometheus Exporter** – renders the KPI snapshot in the *Prometheus text
   exposition* format so that tools like **Grafana** can scrape and chart the
   values without additional services.
3. **Quarterly *Prompt Audits*** – scans the local ``.prompts/`` repository to
   flag templates that may be *outdated*, *biased* or *redundant*.

Design highlights
~~~~~~~~~~~~~~~~~
* **Zero external dependencies** – the exporter writes a plain text file; no
  need for the `prometheus_client` wheel.
* **Configuration-driven** – thresholds and output paths can be overridden via
  environment variables so CI pipelines can adopt the module without code
  changes.
* **Security & ethics** – *audit* heuristics are *read-only* and never send
  data over the network.  Only *public* prompt template fields are parsed.

CLI usage
~~~~~~~~~
```bash
# 1) Write a Prometheus snapshot (default: ./kpi_metrics.prom)
python -m src.evaluation_feedback_loops prometheus --output /var/lib/node_exporter/textfile_collector/repoprompt.prom

# 2) Run a prompt audit and export JSON
python -m src.evaluation_feedback_loops prompt-audit --json > audit.json
```
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Sequence

import typer

from .logger import get_logger, setup_logging
from .documentation_monitoring import _combine_kpis
from .prompt_ops_framework import list_templates, PromptTemplate

__all__ = [
    "KpiSnapshot",
    "compute_kpis",
    "to_prometheus_text",
    "audit_prompts",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# 1. KPI snapshot helpers                                                    #
# ---------------------------------------------------------------------------


@dataclass
class KpiSnapshot:  # noqa: D101 – simple DTO
    """Container for the four primary KPIs defined in §7.6."""

    token_efficiency: float | None = None  # avg tokens per session
    task_speed_avg: float | None = None  # average *time_saved* (seconds)
    error_rate_pct: float | None = None  # % of failed diffs
    alignment_satisfaction: float | None = None  # developer satisfaction 0-10

    # -----------------
    # Serialisation
    # -----------------

    def to_dict(self) -> Dict[str, Any]:  # noqa: D401 – imperative style ok
        return asdict(self)


# -----------------------------
# KPI derivation logic
# -----------------------------


def compute_kpis() -> KpiSnapshot:  # noqa: D401
    """Return a :class:`KpiSnapshot` derived from existing KPI stores."""

    data = _combine_kpis()
    _log.debug("Combined KPI source: %s", data)

    tokens_avg: float | None = None
    if ps := data.get("prompt_sessions"):
        tokens_avg = ps.get("avg_total_tokens")

    time_saved_avg: float | None = None
    if eff := data.get("efficiency"):
        time_saved_avg = eff.get("average_time_saved")

    error_rate: float | None = None
    if diffs := data.get("diffs"):
        success_rate = diffs.get("success_rate")
        if success_rate is not None:
            error_rate = round(100.0 - success_rate, 2)

    satisfaction: float | None = None
    if dl := data.get("developer_load"):
        satisfaction = dl.get("average_satisfaction")

    snapshot = KpiSnapshot(
        token_efficiency=tokens_avg,
        task_speed_avg=time_saved_avg,
        error_rate_pct=error_rate,
        alignment_satisfaction=satisfaction,
    )
    _log.info("KPI snapshot computed: %s", snapshot)
    return snapshot


# -----------------------------
# Prometheus exporter
# -----------------------------


_PROM_FILE = Path(os.getenv("KPI_PROM_FILE", "kpi_metrics.prom"))


_PROM_HEADER = """# HELP repoprompt_token_efficiency_avg Average total tokens per prompt session\n# TYPE repoprompt_token_efficiency_avg gauge\n# HELP repoprompt_task_speed_avg_seconds Average time saved per task (seconds)\n# TYPE repoprompt_task_speed_avg_seconds gauge\n# HELP repoprompt_error_rate_pct Diff application error rate (percent)\n# TYPE repoprompt_error_rate_pct gauge\n# HELP repoprompt_alignment_satisfaction_avg Developer satisfaction (1-10)\n# TYPE repoprompt_alignment_satisfaction_avg gauge\n"""


def to_prometheus_text(snapshot: KpiSnapshot) -> str:  # noqa: D401 – imperative
    """Return Prometheus *textfile* representation for *snapshot*."""

    lines: List[str] = [ln for ln in _PROM_HEADER.splitlines() if ln]

    if snapshot.token_efficiency is not None:
        lines.append(f"repoprompt_token_efficiency_avg {snapshot.token_efficiency}")
    if snapshot.task_speed_avg is not None:
        lines.append(f"repoprompt_task_speed_avg_seconds {snapshot.task_speed_avg}")
    if snapshot.error_rate_pct is not None:
        lines.append(f"repoprompt_error_rate_pct {snapshot.error_rate_pct}")
    if snapshot.alignment_satisfaction is not None:
        lines.append(f"repoprompt_alignment_satisfaction_avg {snapshot.alignment_satisfaction}")

    text = "\n".join(lines) + "\n"
    _log.debug("Prometheus snapshot:\n%s", text)
    return text


# ---------------------------------------------------------------------------
# 2. Prompt audit                                                            #
# ---------------------------------------------------------------------------


_OUTDATED_DAYS = int(os.getenv("PROMPT_OUTDATED_DAYS", "90"))
_BIAS_KEYWORDS: Sequence[str] = [
    # Naïve keyword list – extend / replace with NLP model for production.
    "race",
    "gender",
    "religion",
    "political",
    "age",
    "sexual",
]


@dataclass
class AuditFinding:  # noqa: D101 – simple DTO
    name: str
    version: str
    issues: List[str]

    def to_dict(self) -> Dict[str, Any]:  # noqa: D401
        return asdict(self)


# -----------------------------
# Core audit logic
# -----------------------------


def _is_outdated(tmpl: PromptTemplate) -> bool:
    updated_at = datetime.fromisoformat(tmpl.updated_at.replace("Z", "+00:00"))
    return updated_at < datetime.now(timezone.utc) - timedelta(days=_OUTDATED_DAYS)


def _is_biased(tmpl: PromptTemplate) -> bool:
    content = json.dumps(tmpl.as_dict()).lower()
    return any(kw in content for kw in _BIAS_KEYWORDS)


def _hash_template(tmpl: PromptTemplate) -> str:
    # Hash roles + description only – ignore metadata
    payload = json.dumps({"roles": tmpl.roles, "description": tmpl.description}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def audit_prompts(repo_path: Path | str | None = None) -> List[AuditFinding]:  # noqa: D401 – imperative
    """Return audit findings for templates under *repo_path* (default cwd)."""

    templates = list_templates(repo_path=repo_path)
    _log.info("Auditing %d prompt templates", len(templates))

    # Identify duplicates via content hash
    seen_hashes: Dict[str, str] = {}
    findings: List[AuditFinding] = []

    for tmpl in templates:
        issues: List[str] = []

        if _is_outdated(tmpl):
            issues.append("outdated")
        if _is_biased(tmpl):
            issues.append("biased")

        hsh = _hash_template(tmpl)
        if hsh in seen_hashes:
            issues.append(f"redundant (duplicate of {seen_hashes[hsh]})")
        else:
            seen_hashes[hsh] = tmpl.name

        if issues:
            findings.append(AuditFinding(tmpl.name, tmpl.version, issues))

    # Sort by severity (more issues first) then name
    findings.sort(key=lambda f: (-len(f.issues), f.name))
    _log.debug("Audit findings: %s", findings)
    return findings


# ---------------------------------------------------------------------------
# 3. Typer CLI                                                               #
# ---------------------------------------------------------------------------


app = typer.Typer(add_completion=False, help="Evaluation & Feedback Loops (step 7.6)")


# -----------------
# Prometheus export
# -----------------


@app.command()
def prometheus(
    output: Path = typer.Option(_PROM_FILE, "--output", "-o", help="Prometheus textfile output path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Write KPI snapshot to *output* in Prometheus format."""

    setup_logging("DEBUG" if verbose else "INFO")
    snap = compute_kpis()
    text = to_prometheus_text(snap)
    output.write_text(text, encoding="utf-8")
    _log.info("Prometheus metrics written to %s", output.resolve())
    typer.echo(f"✅ Metrics written to {output}")


# -----------------
# Prompt audits
# -----------------


@app.command("prompt-audit")
def prompt_audit_cmd(
    repo_path: Path | None = typer.Option(None, "--repo", "-r", help="Path containing .prompts/ (defaults: git root)"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run the quarterly *prompt audit* and print a report."""

    setup_logging("DEBUG" if verbose else "INFO")
    findings = audit_prompts(repo_path)

    if json_output:
        json.dump([f.to_dict() for f in findings], typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        if not findings:
            typer.echo("🎉 No issues found – all prompts look good!")
            raise typer.Exit()

        typer.echo("# 🕵️‍♂️ Prompt Audit Findings\n")
        for f in findings:
            issues = ", ".join(f.issues)
            typer.echo(f"- {f.name}@{f.version}: {issues}")
        typer.echo(f"\n{len(findings)} template(s) require attention.")


# Allow `python -m src.evaluation_feedback_loops …`
if __name__ == "__main__":
    app()