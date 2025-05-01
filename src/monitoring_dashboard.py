"""
monitoring_dashboard.py – Step 3.7 Monitoring, Documentation & Resource Allocation 📊

This module realises the **3.7 Monitoring, Documentation, and Resource
Allocation** theoretical block.  It *consolidates* usage logs, success metrics,
trust KPIs and resource allocation data into **one** convenient dashboard.

Key capabilities
----------------
* Aggregates data from existing stores:
  - :pyclass:`src.documentation_monitoring.SessionStore` → prompt sessions &
    diff application stats.
  - :pyclass:`src.success_metrics.MetricsStore` → efficiency & accuracy KPIs.
  - :pyfunc:`src.trust_metrics.evaluate_trust` → transparency & consent scores.
  - :pyclass:`src.resource_allocation.ResourceStore` → personnel & budget
    requirements.
* Computes additional *consent approval/rejection* stats directly from the
  HITL consent registry (:file:`~/.consent.json`).
* Exposes a **Typer CLI** with two commands:
  ``summary`` – print dashboard to stdout (human-readable or JSON)
  ``export``  – write a markdown report to *--output* file.

Security & privacy
~~~~~~~~~~~~~~~~~~
* All reads are **local-only** (JSON lines, home-dir files).
* No network calls are performed.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from .documentation_monitoring import SessionStore
from .success_metrics import MetricsStore
from .trust_metrics import evaluate_trust
from .resource_allocation import ResourceStore
from .logger import get_logger, setup_logging

__all__ = [
    "aggregate_dashboard",
    "to_markdown",
    "app",
]

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
_CONSENT_PATH = Path.home() / ".consent.json"

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _consent_stats(consent_path: Path = _CONSENT_PATH) -> Dict[str, Any]:
    """Return basic *approval/rejection* counts from *consent_path*.

    The consent registry stores a mapping ``{action: bool}`` where *bool*
    represents whether the user granted permission.  Statistics are derived
    from this mapping.  When the file is missing or empty, an *empty* dict is
    returned so callers can ``dict.update`` safely.
    """

    if not consent_path.exists():
        _log.debug("Consent registry %s does not exist", consent_path)
        return {}

    try:
        data: Dict[str, bool] = json.loads(consent_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover – corruption handling
        _log.warning("Failed to parse consent registry: %s", exc)
        return {}

    total = len(data)
    if total == 0:
        return {}

    approved = sum(1 for allowed in data.values() if allowed)
    rejected = total - approved
    approval_rate = round((approved / total) * 100, 1)

    return {
        "events": total,
        "approved": approved,
        "rejected": rejected,
        "approval_rate": approval_rate,  # in percent
    }


# ---------------------------------------------------------------------------
# Aggregation logic – central public helper
# ---------------------------------------------------------------------------

def aggregate_dashboard() -> Dict[str, Any]:
    """Return **combined** monitoring & resource KPIs as a dictionary."""

    _log.debug("Aggregating dashboard metrics")

    combined: Dict[str, Any] = {
        "generated_at": datetime.utcnow().strftime(ISO_FMT),
    }

    # Usage & diff stats
    usage = SessionStore().aggregate()
    if usage:
        combined["usage"] = usage

    # Success metrics (efficiency, accuracy …)
    sm = MetricsStore().aggregate()
    if sm:
        combined["success_metrics"] = sm

    # Trust metrics (transparency, consent freq, HITL)
    trust_report = evaluate_trust().as_dict()
    combined["trust"] = {
        "total_score": trust_report.get("total_score"),
        "metrics": trust_report.get("metrics"),
    }

    # Resource allocation summary
    res_alloc = ResourceStore().aggregate()
    if res_alloc:
        combined["resources"] = res_alloc

    # Consent approval/rejection counts
    consent = _consent_stats()
    if consent:
        combined["consent"] = consent

    return combined


# ---------------------------------------------------------------------------
# Rendering helpers – markdown & pretty print
# ---------------------------------------------------------------------------

def to_markdown(data: Dict[str, Any]) -> str:
    """Return *data* rendered as a simple markdown dashboard."""

    lines: list[str] = [
        "# 📊 Monitoring & Resource Dashboard (Step 3.7)",
        f"_Generated: {data.get('generated_at', '-')}_",
        "",
    ]

    # Consent section
    if "consent" in data:
        c = data["consent"]
        lines += [
            "## ✅ Consent Statistics",
            f"- Events: **{c['events']}**",
            f"- Approved: **{c['approved']}**",
            f"- Rejected: **{c['rejected']}**",
            f"- Approval rate: **{c['approval_rate']}%**",
            "",
        ]

    # Usage section (prompt sessions & diffs)
    if "usage" in data:
        u = data["usage"]
        lines += [
            "## 🖥️ Usage",
        ]
        if "prompt_sessions" in u:
            ps = u["prompt_sessions"]
            lines.append(
                f"- Prompts: **{ps['events']}** sessions – avg **{ps['avg_total_tokens']}** tokens, "
                f"{ps['avg_latency_ms']} ms latency"
            )
        if "diffs" in u:
            d = u["diffs"]
            lines.append(
                f"- Diffs: **{d['events']}** – success rate **{d['success_rate']}%**, "
                f"files modified Σ {d['files_modified_total']}"
            )
        lines.append("")

    # Success metrics
    if "success_metrics" in data:
        sm = data["success_metrics"]
        lines += [
            "## 📈 Success Metrics",
        ]
        if "efficiency" in sm:
            eff = sm["efficiency"]
            lines.append(
                f"- Efficiency: **{eff['average_time_saved']}s** avg time-saved across "
                f"{eff['events']} events (Σ {eff['total_time_saved']}s)"
            )
        if "accuracy" in sm:
            acc = sm["accuracy"]
            lines.append(
                f"- Accuracy: **{acc['average_diff_accuracy']*100:.1f}%** avg across "
                f"{acc['events']} events"
            )
        lines.append("")

    # Trust metrics (transparency, consent freq, HITL)
    if "trust" in data:
        t = data["trust"]
        lines += [
            "## 🤝 Trust",
            f"Aggregate score: **{t['total_score']}%**",
        ]
        for m in t.get("metrics", []):
            lines.append(f"- {m['name']}: **{m['score']}%** ({m.get('details','')})")
        lines.append("")

    # Resources
    if "resources" in data:
        r = data["resources"]
        lines += [
            "## 🧑‍💻 Resources",
            "### Personnel",
        ]
        for role, qty in r.get("personnel", {}).items():
            lines.append(f"- {role}: **{qty}**")
        lines.append("\n### Budget (annualised)")
        budget = r.get("budget", {})
        per_cat = budget.get("per_category", {})
        for cat, amt in per_cat.items():
            lines.append(f"- {cat}: **{amt:.2f} USD**")  # TODO currency per-line
        total = budget.get("total_annualised")
        if total is not None:
            lines.append(f"- **Total**: {total:.2f} USD")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Monitoring dashboard (step 3.7)")


@app.command()
def summary(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print combined dashboard to *stdout*."""

    setup_logging("DEBUG" if verbose else "INFO")
    data = aggregate_dashboard()

    if json_output:
        json.dump(data, typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        typer.echo(to_markdown(data))


@app.command()
def export(
    output: Path = typer.Option(Path("dashboard.md"), "--output", "-o", help="Markdown file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Write markdown dashboard to *output* file (default: ./dashboard.md)."""

    setup_logging("DEBUG" if verbose else "INFO")
    data = aggregate_dashboard()
    md = to_markdown(data)
    output.write_text(md, encoding="utf-8")
    typer.secho(f"✅ Dashboard written to {output}")


# CLI entry-point → ``python -m src.monitoring_dashboard …``
if __name__ == "__main__":  # pragma: no cover – CLI manual usage
    app()