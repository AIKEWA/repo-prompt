from __future__ import annotations

"""evaluation_monitoring.py – Step 8.4 Evaluation, Monitoring & Feedback ⚙️📈

This module operationalises **Step 8.4 – Evaluation, Monitoring, and Feedback
Mechanisms**.  It extends the KPI infrastructure provided by
:pymod:`src.evaluation_feedback_loops`, :pymod:`src.documentation_monitoring`
and :pymod:`src.collaborative_cognitive_architecture` by aggregating
**post-refactor code accuracy, prompt performance metrics, and the *CIP growth
index***.

Key metrics
===========
* **Code accuracy (post-refactor)** – derived from the *average diff
  accuracy* captured via :class:`src.success_metrics.AccuracyEvent` **or** (as
  fallback) the diff *success rate* recorded in
  :class:`src.documentation_monitoring.DiffAppliedEvent`.
* **Prompt latency & token usage** – calculated from the *PromptSessionEvent*
  log to surface UX regressions.
* **CIP growth index** – mean *Collaborative Improvement Progress* (**CIP**)
  score across all personas (see :class:`src.collaborative_cognitive_architecture.CIPStore`).
* **Legacy KPIs** – token efficiency, task speed, error rate and alignment
  satisfaction from *Step 7.6* remain accessible for *holistic* dashboards.

The aggregated snapshot can be:
* **Written as Prometheus textfile** – for pull-based monitoring stacks.
* **Dumped to *.ide_metrics.json*** – enabling *real-time* IDE plug-in status
  bars.
* **Inspected via CLI** – ``python -m src.evaluation_monitoring summary``.

Security & Ethics
-----------------
* *Read-only* access to local JSON-Lines stores – no outbound network traffic.
* Timestamps included in IDE reports for traceability.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

import typer

from .evaluation_feedback_loops import compute_kpis, KpiSnapshot
from .documentation_monitoring import _combine_kpis
from .collaborative_cognitive_architecture import CIPStore
from .logger import get_logger, setup_logging

__all__ = [
    "E84Snapshot",
    "gather_metrics",
    "to_prometheus_text",
    "write_ide_report",
    "app",
]

_log = get_logger(__name__)

###############################################################################
# 1. Data model                                                               #
###############################################################################


@dataclass
class E84Snapshot:  # noqa: D101 – simple container
    code_accuracy: float | None = None  # 0-1 (or % when diff fallback)
    avg_prompt_latency_ms: float | None = None
    avg_prompt_tokens: float | None = None
    cip_growth_index: float | None = None  # 0-100

    # Step 7.6 carry-overs ---------------------------------------------------
    token_efficiency: float | None = None
    task_speed_avg: float | None = None
    error_rate_pct: float | None = None
    alignment_satisfaction: float | None = None

    # -----------------
    # Serialisation
    # -----------------
    def to_dict(self) -> Dict[str, Any]:  # noqa: D401 – imperative style ok
        return asdict(self)


###############################################################################
# 2. Aggregation helpers                                                      #
###############################################################################


def _cip_growth_index(store: Optional[CIPStore] = None) -> float | None:
    """Return *mean* CIP score across personas (None when unavailable)."""

    store = store or CIPStore()
    data = store.aggregate()
    scores: Dict[str, float] = data.get("scores", {})  # {persona: score%}
    if not scores:
        return None
    value = round(mean(scores.values()), 2)
    _log.debug("CIP growth index computed: %.2f", value)
    return value


def gather_metrics() -> E84Snapshot:  # noqa: D401
    """Return an :class:`E84Snapshot` combining *all* relevant KPI sources."""

    # Step 7.6 snapshot -----------------------------------------------------
    kpi: KpiSnapshot = compute_kpis()

    # Lower-level event aggregates -----------------------------------------
    data = _combine_kpis()
    _log.debug("Combined KPI sources: %s", data)

    # Code accuracy ---------------------------------------------------------
    code_acc: float | None = None
    if (acc := data.get("accuracy")) is not None:
        code_acc = acc.get("average_diff_accuracy")
    # Fallback: diff success rate (%)
    if code_acc is None and (diffs := data.get("diffs")) is not None:
        # Convert percentage → 0-1 float
        sr = diffs.get("success_rate")
        code_acc = round(sr / 100, 4) if sr is not None else None

    # Prompt performance ----------------------------------------------------
    lat_ms: float | None = None
    tokens_avg: float | None = None
    if (ps := data.get("prompt_sessions")) is not None:
        lat_ms = ps.get("avg_latency_ms")
        tokens_avg = ps.get("avg_total_tokens")

    # CIP growth index ------------------------------------------------------
    cip_index = _cip_growth_index()

    snapshot = E84Snapshot(
        code_accuracy=code_acc,
        avg_prompt_latency_ms=lat_ms,
        avg_prompt_tokens=tokens_avg,
        cip_growth_index=cip_index,
        # Carry overs ------------------------------------------------------
        token_efficiency=kpi.token_efficiency,
        task_speed_avg=kpi.task_speed_avg,
        error_rate_pct=kpi.error_rate_pct,
        alignment_satisfaction=kpi.alignment_satisfaction,
    )
    _log.info("Step 8.4 snapshot: %s", snapshot)
    return snapshot


###############################################################################
# 3. Prometheus exporter                                                      #
###############################################################################


_PROM_FILE = Path(os.getenv("E84_PROM_FILE", "step_8_4_metrics.prom"))

_PROM_HEADER = """# HELP repoprompt_code_accuracy Code accuracy post-refactor (0-1)
# TYPE repoprompt_code_accuracy gauge
# HELP repoprompt_prompt_latency_avg_ms Average prompt latency (ms)
# TYPE repoprompt_prompt_latency_avg_ms gauge
# HELP repoprompt_prompt_tokens_avg Average total tokens per prompt session
# TYPE repoprompt_prompt_tokens_avg gauge
# HELP repoprompt_cip_growth_index Collaborative Improvement Progress (CIP) growth index (0-100)
# TYPE repoprompt_cip_growth_index gauge
# HELP repoprompt_token_efficiency_avg Average total tokens per prompt session (legacy KPI)
# TYPE repoprompt_token_efficiency_avg gauge
# HELP repoprompt_task_speed_avg_seconds Average time saved per task (seconds)
# TYPE repoprompt_task_speed_avg_seconds gauge
# HELP repoprompt_error_rate_pct Diff application error rate (percent)
# TYPE repoprompt_error_rate_pct gauge
# HELP repoprompt_alignment_satisfaction_avg Developer satisfaction (1-10)
# TYPE repoprompt_alignment_satisfaction_avg gauge
"""


def to_prometheus_text(snapshot: E84Snapshot) -> str:  # noqa: D401 – imperative
    """Return Prometheus *textfile* representation of *snapshot*."""

    lines: List[str] = [ln for ln in _PROM_HEADER.splitlines() if ln]

    if snapshot.code_accuracy is not None:
        lines.append(f"repoprompt_code_accuracy {snapshot.code_accuracy}")
    if snapshot.avg_prompt_latency_ms is not None:
        lines.append(f"repoprompt_prompt_latency_avg_ms {snapshot.avg_prompt_latency_ms}")
    if snapshot.avg_prompt_tokens is not None:
        lines.append(f"repoprompt_prompt_tokens_avg {snapshot.avg_prompt_tokens}")
    if snapshot.cip_growth_index is not None:
        lines.append(f"repoprompt_cip_growth_index {snapshot.cip_growth_index}")

    # Legacy Step 7.6 KPIs -------------------------------------------------
    if snapshot.token_efficiency is not None:
        lines.append(f"repoprompt_token_efficiency_avg {snapshot.token_efficiency}")
    if snapshot.task_speed_avg is not None:
        lines.append(f"repoprompt_task_speed_avg_seconds {snapshot.task_speed_avg}")
    if snapshot.error_rate_pct is not None:
        lines.append(f"repoprompt_error_rate_pct {snapshot.error_rate_pct}")
    if snapshot.alignment_satisfaction is not None:
        lines.append(
            f"repoprompt_alignment_satisfaction_avg {snapshot.alignment_satisfaction}"
        )

    text = "\n".join(lines) + "\n"
    _log.debug("Prometheus snapshot:\n%s", text)
    return text


###############################################################################
# 4. IDE plug-in report helper                                               #
###############################################################################


_IDE_METRICS_FILE = Path(os.getenv("IDE_METRICS_FILE", ".ide_metrics.json"))


def write_ide_report(path: Path | str | None = None) -> Path:  # noqa: D401 – imperative
    """Write JSON snapshot for IDE plug-ins and return the file path."""

    target = Path(path or _IDE_METRICS_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "ts": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        **gather_metrics().to_dict(),
    }
    target.write_text(json.dumps(payload, indent=2))
    _log.info("IDE metrics written to %s", target)
    return target


###############################################################################
# 5. Typer CLI                                                               #
###############################################################################


app = typer.Typer(add_completion=False, help="Step 8.4 – Evaluation, Monitoring & Feedback")


@app.command()
def summary(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print aggregated Step 8.4 metrics snapshot."""

    setup_logging("DEBUG" if verbose else "INFO")
    snap = gather_metrics()

    if json_output:
        json.dump(snap.to_dict(), typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        if snap.code_accuracy is not None:
            typer.echo(f"🎯 Code accuracy: {snap.code_accuracy}")
        if snap.avg_prompt_latency_ms is not None:
            typer.echo(f"⏱️  Prompt latency: {snap.avg_prompt_latency_ms} ms")
        if snap.avg_prompt_tokens is not None:
            typer.echo(f"🔢 Prompt tokens avg: {snap.avg_prompt_tokens}")
        if snap.cip_growth_index is not None:
            typer.echo(f"📈 CIP growth index: {snap.cip_growth_index}%")
        # Legacy ----------------------------------------------------------
        if snap.token_efficiency is not None:
            typer.echo(f"📉 Token efficiency avg: {snap.token_efficiency}")
        if snap.task_speed_avg is not None:
            typer.echo(f"⚡ Time saved avg: {snap.task_speed_avg}s")
        if snap.error_rate_pct is not None:
            typer.echo(f"❌ Error rate: {snap.error_rate_pct}%")
        if snap.alignment_satisfaction is not None:
            typer.echo(f"😊 Alignment satisfaction: {snap.alignment_satisfaction}")


@app.command()
def prometheus(
    output: Path = typer.Option(_PROM_FILE, "--output", "-o", help="Prometheus textfile output path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Write Prometheus *textfile* snapshot to *output*."""

    setup_logging("DEBUG" if verbose else "INFO")
    output.write_text(to_prometheus_text(gather_metrics()))
    typer.secho(f"✅ Prometheus snapshot written to {output}", fg=typer.colors.GREEN)


@app.command("ide-report")
def cli_ide_report(
    path: Path = typer.Option(_IDE_METRICS_FILE, "--out", "-o", help="Target *.json* file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a *.ide_metrics.json* snapshot for the in-IDE status bar."""

    setup_logging("DEBUG" if verbose else "INFO")
    target = write_ide_report(path)
    typer.secho(f"✅ IDE metrics written to {target}", fg=typer.colors.GREEN)