# new file
from __future__ import annotations

"""stakeholder_communication.py – Step 4.11 Stakeholder Communication 📣🌱

This module generates **Developer Sustainability Impact Reports** and simple
*infographics* that visualise *per-action* energy savings derived from the
quantitative *success metrics* captured by :pymod:`src.success_metrics`.

It translates the *4.11 Stakeholder Communication* theoretical section into a
small set of production-ready helpers so sustainability champions can:

1. Create **monthly markdown reports** that summarise total energy
   consumption, local-execution ratios, and carbon savings.
2. Produce **infographics** (markdown bar charts) that showcase how much energy
   each *local* execution saved compared to a hypothetical remote baseline.

A minimal **Typer CLI** exposes the building blocks for non-developer
stakeholders:

```console
# Preview the current month report (markdown on stdout)
python -m src.stakeholder_communication report --month 2025-04

# Write the infographic to docs/
python -m src.stakeholder_communication infographic --month 2025-04 \
    --output docs/energy_savings_2025-04.md
```

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* Works on **local** JSON-Lines files – no network traffic.
* Aggregates **non-identifiable** statistics only.
* All heuristics are transparent and can be adapted easily.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import textwrap

import typer

from .logger import get_logger, setup_logging
from .success_metrics import MetricsStore, EnergyEvent, _DEFAULT_STORE_PATH

__all__ = [
    "SustainabilityReport",
    "generate_sustainability_report",
    "report_to_markdown",
    "generate_infographic",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
# ⚖️ Energy heuristic constants – keep in sync with success_metrics/offline_awareness
_LOC_KWH_PER_TOKEN = 1e-7
_REM_KWH_PER_TOKEN = 5e-7

# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------


@dataclass
class SustainabilityReport:  # noqa: D101 – trivial container
    month: str  # YYYY-MM
    events: int
    total_kwh: float
    avg_kwh: float
    local_ratio_pct: float
    total_saving_kwh: float
    avg_saving_per_local_kwh: float

    # ---------------- Serialisation helpers ----------------
    def to_dict(self) -> Dict[str, Any]:  # noqa: D401 – imperative fine
        return {
            "month": self.month,
            "events": self.events,
            "total_kwh": round(self.total_kwh, 6),
            "average_kwh": round(self.avg_kwh, 6),
            "local_execution_ratio_pct": round(self.local_ratio_pct, 2),
            "total_saving_kwh": round(self.total_saving_kwh, 6),
            "average_saving_per_local_kwh": round(self.avg_saving_per_local_kwh, 6),
        }

    def to_json(self) -> str:  # noqa: D401 – imperative fine
        import json

        return json.dumps(self.to_dict(), separators=(",", ":"))


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _parse_iso(dt: str) -> datetime:
    """Return *dt* parsed as UTC ``datetime`` using :data:`ISO_FMT`."""

    return datetime.strptime(dt, ISO_FMT).replace(tzinfo=timezone.utc)


def _events_in_month(store: MetricsStore, *, month: str) -> List[EnergyEvent]:
    """Return all :class:`EnergyEvent`s that fall into *month* (YYYY-MM)."""

    try:
        year, mon = map(int, month.split("-", 1))
    except ValueError as exc:  # pragma: no cover – basic validation
        raise ValueError("month must be YYYY-MM") from exc

    events: List[EnergyEvent] = []
    for ev in store.load_events():
        if isinstance(ev, EnergyEvent):
            ts = _parse_iso(ev.created_at)
            if ts.year == year and ts.month == mon:
                events.append(ev)
    return events


def generate_sustainability_report(
    month: str,
    metrics_path: Path | str = _DEFAULT_STORE_PATH,
) -> SustainabilityReport:
    """Compute :class:`SustainabilityReport` for *month* (YYYY-MM)."""

    store = MetricsStore(metrics_path)
    events = _events_in_month(store, month=month)

    if not events:
        _log.warning("No EnergyEvent records found for %s", month)

    total_kwh = sum(ev.energy_kwh for ev in events)
    avg_kwh = total_kwh / len(events) if events else 0.0
    local_events = [ev for ev in events if ev.local_execution]
    local_ratio_pct = (len(local_events) / len(events) * 100) if events else 0.0

    # -----------------------
    # Energy savings heuristic
    # -----------------------
    total_saving_kwh = 0.0
    for ev in local_events:
        # Baseline assumes remote execution energy per token
        remote_kwh = ev.tokens * _REM_KWH_PER_TOKEN
        total_saving_kwh += max(remote_kwh - ev.energy_kwh, 0.0)

    avg_saving = total_saving_kwh / len(local_events) if local_events else 0.0

    report = SustainabilityReport(
        month=month,
        events=len(events),
        total_kwh=total_kwh,
        avg_kwh=avg_kwh,
        local_ratio_pct=local_ratio_pct,
        total_saving_kwh=total_saving_kwh,
        avg_saving_per_local_kwh=avg_saving,
    )

    _log.debug("Generated sustainability report: %s", report.to_dict())
    return report


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


def report_to_markdown(report: SustainabilityReport) -> str:  # noqa: D401 – imperative fine
    """Return a **markdown** representation of *report*."""

    return textwrap.dedent(
        f"""
        # 🌱 Developer Sustainability Impact Report – {report.month}

        _Generated: {datetime.utcnow().strftime(ISO_FMT)}_

        ## Overview
        - Events analysed: **{report.events}**
        - Total energy consumption: **{report.total_kwh:.6f} kWh**
        - Average per operation: **{report.avg_kwh:.6f} kWh**
        - Local execution ratio: **{report.local_ratio_pct:.2f}%**

        ## Energy Savings (local vs remote baseline)
        - Total saved: **{report.total_saving_kwh:.6f} kWh**
        - Average saving per local operation: **{report.avg_saving_per_local_kwh:.6f} kWh**
        """
    ).strip() + "\n"


def _bar(value: float, *, max_value: float, width: int = 20) -> str:
    """Return a simple bar of length proportional to *value*."""

    if max_value <= 0:
        return ""
    filled = int(round((value / max_value) * width))
    return "█" * filled + "░" * (width - filled)


def generate_infographic(
    month: str,
    metrics_path: Path | str = _DEFAULT_STORE_PATH,
    *,
    top_n: int = 10,
) -> str:
    """Return a markdown *infographic* showing per-action energy savings."""

    store = MetricsStore(metrics_path)
    events = [ev for ev in _events_in_month(store, month=month) if ev.local_execution]

    if not events:
        _log.warning("No local EnergyEvent records for %s", month)
        return "_No local execution events to display._\n"

    # Compute savings per event (remote baseline – actual)
    savings = [max(ev.tokens * _REM_KWH_PER_TOKEN - ev.energy_kwh, 0.0) for ev in events]
    # Pair with created_at for identificaton (index)
    entries = list(zip(events, savings))
    # Sort by saving desc
    entries.sort(key=lambda tup: tup[1], reverse=True)

    # Normalise bars to the largest saving
    max_saving = entries[0][1]

    lines: List[str] = [
        f"# 📊 Energy Savings Infographic – {month}",
        "",
        "_Each bar shows kWh saved by executing locally instead of remotely_",
        "",
        "| Operation | kWh Saved | |",
        "|---|---:|:---|",
    ]

    for idx, (ev, saved_kwh) in enumerate(entries[:top_n], 1):
        bar = _bar(saved_kwh, max_value=max_saving)
        ts_short = _parse_iso(ev.created_at).strftime("%d %H:%M")
        lines.append(f"| {idx}\|{ts_short} | {saved_kwh:.6f} | {bar} |")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Typer CLI – expose helpers for non-dev stakeholders
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Step 4.11 – Stakeholder Communication utilities")


@app.command()
def report(
    month: str = typer.Option(datetime.utcnow().strftime("%Y-%m"), "--month", "-m", help="Target month YYYY-MM"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write markdown report to file"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON instead of markdown"),
    metrics_file: Path = typer.Option(_DEFAULT_STORE_PATH, "--metrics", help="Custom metrics file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *monthly* Developer Sustainability Impact Report."""

    setup_logging("DEBUG" if verbose else "INFO")

    rep = generate_sustainability_report(month, metrics_path=metrics_file)

    if json_output:
        output_txt = rep.to_json()
    else:
        output_txt = report_to_markdown(rep)

    if output:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(output_txt, encoding="utf-8")
        typer.echo(f"✅ Report written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(output_txt)


@app.command()
def infographic(
    month: str = typer.Option(datetime.utcnow().strftime("%Y-%m"), "--month", "-m", help="Target month YYYY-MM"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    top_n: int = typer.Option(10, "--top", help="Number of top events to display"),
    metrics_file: Path = typer.Option(_DEFAULT_STORE_PATH, "--metrics", help="Custom metrics file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *infographic* summarising per-action energy savings."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_infographic(month, metrics_path=metrics_file, top_n=top_n)

    if output:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✅ Infographic written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)


if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter