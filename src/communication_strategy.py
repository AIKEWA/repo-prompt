from __future__ import annotations

"""communication_strategy.py – Step 3.11 Communication Strategy 📣🏛️

This module translates the *3.11 Communication Strategy* theoretical block
into production-ready helpers that address two concrete outreach goals:

1. **Whitepaper Publication** – Generate and (optionally) write markdown
   *whitepapers* that frame *offline AI* as a **digital right** rather than a
   mere feature.  The markdown output can be committed directly to the project
   `docs/` folder and rendered via GitHub Pages or any static site generator.

2. **Data-Sovereignty Dashboard** – Produce an at-a-glance dashboard focused
   **exclusively** on *data-sovereignty* KPIs so stakeholders can validate – in
   real-time – how the application upholds local processing guarantees.

Both building blocks are exposed via a small **Typer CLI** so non-developer
stakeholders can create whitepapers or inspect dashboards without writing
Python code:

```console
# Draft a new whitepaper (stdout preview)
python -m src.communication_strategy whitepaper draft --title "Offline AI as a Right"

# Publish directly to docs/whitepapers/<slug>.md
python -m src.communication_strategy whitepaper publish --title "Offline AI as a Right" \
    --output docs/whitepapers --overwrite

# Show sovereignty KPIs (pretty print)
python -m src.communication_strategy dashboard show

# Export markdown dashboard
python -m src.communication_strategy dashboard export --output docs/sovereignty_dashboard.md
```

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* All metrics are derived from **local files** – *no outbound traffic*.
* Whitepaper templates include a ***Rights-first*** framing rooted in
  Kantian ethics and the project vision.
* The dashboard aggregates only *non-identifiable* statistics.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import json
import re
import textwrap

import typer

from .logger import get_logger, setup_logging
from .trust_metrics import evaluate_trust
from .success_metrics import MetricsStore

__all__ = [
    "WhitepaperMeta",
    "draft_whitepaper",
    "publish_whitepaper",
    "aggregate_sovereignty_metrics",
    "dashboard_to_markdown",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Whitepaper helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Return filesystem-safe slug derived from *text*."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "whitepaper"


@dataclass
class WhitepaperMeta:  # noqa: D101 – trivial container
    title: str
    author: str = "AI-Assisted Coding Team"
    summary: str = "This whitepaper outlines why offline AI capabilities must be treated as a fundamental digital right."
    published_at: str = datetime.utcnow().strftime(ISO_FMT)

    # ---------------- Serialisation helpers ----------------
    def filename(self) -> str:
        return f"{_slugify(self.title)}.md"

    def to_markdown(self) -> str:  # noqa: D401 – imperative fine
        """Return full markdown string for the whitepaper."""

        return textwrap.dedent(
            f"""
            # {self.title}

            *{self.published_at}*
            **Author:** {self.author}

            ---
            ## Executive Summary
            {self.summary}

            Offline AI – the ability to perform intelligent computation *without* permanent
            network connectivity – is increasingly framed as a *feature* by vendors. We argue
            that offline AI is a **right**, intrinsic to digital autonomy and data sovereignty.

            ### 1. Digital Autonomy and Kantian Ethics
            From a Kantian perspective, individuals must remain ends-in-themselves.  Reliance
            on cloud-based AI can create asymmetric power dynamics where users become means
            to providers' ends.  Local inference restores autonomy by ensuring computations
            occur under the user's control.

            ### 2. Data Sovereignty Guarantees
            Our implementation stores data locally via an encrypted *Data Vault* and routes
            all AI tasks through offline-capable models by default. Consent prompts guard any
            optional remote fallback.  See the *Data-Sovereignty Dashboard* for live KPIs.

            ### 3. Societal Impact
            Treating offline AI as a right democratizes access, mitigates connectivity gaps,
            and strengthens privacy protections worldwide.

            ### 4. Implementation Blueprint
            1. Ship compact, local-first models.
            2. Transparently prompt for consent when remote resources are unavoidable.
            3. Publish verifiable metrics demonstrating compliance (`communication_strategy dashboard`).

            ### 5. Call to Action
            We invite regulators, developers, and users to adopt the rights-first framing of
            offline AI, contributing to standards that enshrine these principles in policy.
            """
        ).strip() + "\n"


def draft_whitepaper(meta: WhitepaperMeta) -> str:  # noqa: D401 – imperative fine
    """Return *draft* markdown for *meta* (no disk IO)."""

    md = meta.to_markdown()
    _log.debug("Drafted whitepaper '%s' (%d chars)", meta.title, len(md))
    return md


def publish_whitepaper(meta: WhitepaperMeta, output_dir: Path, *, overwrite: bool = False) -> Path:
    """Write *meta* as markdown to *output_dir* and return the file path."""

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / meta.filename()
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists – use --overwrite to replace")

    path.write_text(meta.to_markdown(), encoding="utf-8")
    _log.info("Whitepaper written to %s", path)
    return path


# ---------------------------------------------------------------------------
# Data-Sovereignty Dashboard helpers
# ---------------------------------------------------------------------------

_CONSENT_PATH = Path.home() / ".consent.json"
_VAULT_PATH = Path.home() / ".data_vault"


def _consent_stats(consent_path: Path = _CONSENT_PATH) -> Dict[str, Any]:
    """Return basic consent approval/rejection counts (mirror monitoring_dashboard)."""

    if not consent_path.exists():
        return {}

    try:
        data: Dict[str, bool] = json.loads(consent_path.read_text("utf-8"))
    except json.JSONDecodeError:  # pragma: no cover – corruption handling
        return {}

    total = len(data)
    if total == 0:
        return {}

    approved = sum(1 for allowed in data.values() if allowed)
    return {
        "events": total,
        "approved": approved,
        "rejected": total - approved,
        "approval_rate": round((approved / total) * 100, 1),
    }


def _vault_entry_count(vault_path: Path = _VAULT_PATH) -> int:
    """Return number of (plaintext) identifier lines in *vault_path*."""

    if not vault_path.exists():
        return 0
    try:
        with vault_path.open("r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except Exception as exc:  # pragma: no cover – IO errors are non-fatal
        _log.warning("Failed to count vault entries: %s", exc)
        return 0


def aggregate_sovereignty_metrics() -> Dict[str, Any]:  # noqa: D401 – imperative fine
    """Return aggregated data-sovereignty KPIs as dictionary."""

    _log.debug("Aggregating data-sovereignty metrics")

    metrics: Dict[str, Any] = {
        "generated_at": datetime.utcnow().strftime(ISO_FMT),
        "vault_entries": _vault_entry_count(),
    }

    consent = _consent_stats()
    if consent:
        metrics["consent"] = consent

    # Local-only operation KPI from success_metrics (optional)
    sm = MetricsStore().aggregate().get("local_only_operation")
    if sm:
        metrics["local_only_operation"] = sm

    # Trust metrics (reuse existing helper)
    trust_report = evaluate_trust().as_dict()
    metrics["trust"] = {
        "total_score": trust_report.get("total_score"),
        "metrics": trust_report.get("metrics"),
    }

    return metrics


def dashboard_to_markdown(data: Dict[str, Any]) -> str:  # noqa: D401 – imperative fine
    """Render *data* from :func:`aggregate_sovereignty_metrics` as markdown string."""

    lines: list[str] = [
        "# 🛡️ Data-Sovereignty Dashboard",
        f"_Generated: {data.get('generated_at', '-')}_",
        "",
    ]

    lines += [f"**Vault entries:** {data.get('vault_entries', 0)}", ""]

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

    if "local_only_operation" in data:
        loc = data["local_only_operation"]
        lines += [
            "## ⚙️ Local-Only Operation KPI",
            f"- Events: **{loc['events']}**",
            f"- Success rate: **{loc['success_rate_pct']}%**",
            "",
        ]

    if "trust" in data:
        t = data["trust"]
        lines += [
            "## 🕊️ Trust Overview",
            f"- Total score: **{t['total_score']} / 100**",
        ]
        for m in t.get("metrics", []):
            lines.append(f"  - {m['name']}: {m['score']} – {m.get('details','')}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Communication strategy utilities (step 3.11)")

whitepaper_app = typer.Typer(add_completion=False, help="Generate & publish whitepapers")
dashboard_app = typer.Typer(add_completion=False, help="Inspect data-sovereignty dashboard")

app.add_typer(whitepaper_app, name="whitepaper")
app.add_typer(dashboard_app, name="dashboard")

# ---------------- whitepaper commands ----------------


@whitepaper_app.command("draft")
def _cmd_draft(
    title: str = typer.Option("Offline AI as a Right", "--title", help="Whitepaper title"),
    author: str = typer.Option("AI-Assisted Coding Team", "--author", help="Author line"),
    summary: str = typer.Option(
        "This whitepaper outlines why offline AI capabilities must be treated as a fundamental digital right.",
        "--summary",
        help="Executive summary paragraph",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print a whitepaper draft to STDOUT (no file written)."""

    setup_logging("DEBUG" if verbose else "INFO")
    meta = WhitepaperMeta(title=title, author=author, summary=summary)
    typer.echo(draft_whitepaper(meta))


@whitepaper_app.command("publish")
def _cmd_publish(
    title: str = typer.Option("Offline AI as a Right", "--title", help="Whitepaper title"),
    author: str = typer.Option("AI-Assisted Coding Team", "--author", help="Author line"),
    summary: str = typer.Option(
        "This whitepaper outlines why offline AI capabilities must be treated as a fundamental digital right.",
        "--summary",
        help="Executive summary paragraph",
    ),
    output: Path = typer.Option(Path("docs/whitepapers"), "--output", "-o", help="Output directory"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Write a whitepaper markdown file to *output* directory."""

    setup_logging("DEBUG" if verbose else "INFO")
    meta = WhitepaperMeta(title=title, author=author, summary=summary)
    path = publish_whitepaper(meta, output, overwrite=overwrite)
    typer.echo(str(path))


# ---------------- dashboard commands ----------------


def _pretty_print(data: Dict[str, Any]) -> None:
    """Human-friendly pretty print of *data* (subset)."""

    md = dashboard_to_markdown(data)
    typer.echo(md)


@dashboard_app.command("show")
def _cmd_show(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Display sovereignty KPIs (pretty print or JSON)."""

    setup_logging("DEBUG" if verbose else "INFO")
    data = aggregate_sovereignty_metrics()
    if json_output:
        typer.echo(json.dumps(data, indent=2))
    else:
        _pretty_print(data)


@dashboard_app.command("export")
def _cmd_export(
    output: Path = typer.Option(Path("docs/sovereignty_dashboard.md"), "--output", "-o", help="Markdown file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Write sovereignty dashboard markdown to *output* path."""

    setup_logging("DEBUG" if verbose else "INFO")
    data = aggregate_sovereignty_metrics()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dashboard_to_markdown(data), encoding="utf-8")
    typer.echo(f"Dashboard written to {output}")


if __name__ == "__main__":  # pragma: no cover – convenience entry-point
    app()