# new file
from __future__ import annotations

"""economic_accessibility.py – Step 6.1 Economic Accessibility 💸🏫

This module **operationalises** the *6.1 – Understanding the Theory* block of
our blueprint by translating *economic accessibility* concepts into executable
Python utilities.

The goal is to **measure and improve** cost & platform accessibility so that
LLM-powered developer tooling becomes affordable for *students*, *educators*
and early-stage adopters.

Key capabilities
~~~~~~~~~~~~~~~~
* **Dataclasses** representing *Pricing Tiers* & *Discount Models* and a
  consolidated *AccessibilityScore* helper.
* **JSON-Lines store** (``.economic_accessibility.jsonl``) for append-only
  logging that works locally & in CI.
* **Aggregation helpers** returning an "accessibility health" summary ready for
  dashboards or markdown export.
* **Typer CLI** – ``python -m src.economic_accessibility …`` – for ad-hoc
  recording and reporting.

Security & privacy
~~~~~~~~~~~~~~~~~~
* Purely local file writes – **no** external network calls.
* No sensitive data (credentials, payment details) is persisted – only public
  pricing metadata.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "PricingTierEntry",
    "DiscountEntry",
    "EconomicAccessibilityStore",
    "AccessibilityScore",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

_DEFAULT_FILE = Path(os.getenv("ECONOMIC_ACCESSIBILITY_FILE", ".economic_accessibility.jsonl"))
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(kw_only=True)
class BaseEntry:  # noqa: D101 – documented in subclasses
    """Base dataclass adding *created_at* metadata + JSON serialisation."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property  # noqa: D401 – imperative mood not required
    def type(self) -> str:  # FEEDBACK: future subtype introspection improvements
        return self.__class__.__name__

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Concrete entry types
# ---------------------------------------------------------------------------


@dataclass
class PricingTierEntry(BaseEntry):
    """Represents a *pricing tier* (e.g. *Free*, *Pro*, *Enterprise*).

    Parameters
    ----------
    name:
        Human-friendly name of the tier.
    monthly_cost:
        Recurring cost **per user** in *USD* (after any automatic discounts).
    platform:
        Supported platform / OS family (e.g. "macOS", "Windows", "All").  Use
        "All" when there is full feature parity across platforms.
    description:
        Optional free-form description clarifying feature limits.
    """

    name: str
    monthly_cost: float  # USD for parity; convert beforehand if needed
    platform: str = "All"
    description: str | None = None


@dataclass
class DiscountEntry(BaseEntry):
    """Represents a *discount model* (e.g. *Student 50% off*).

    Parameters
    ----------
    category:
        Discount category identifier (e.g. "student", "educational", "oss").
    percent:
        Discount percentage (0-100).
    eligibility:
        Short text explaining who qualifies.
    description:
        Optional additional details (e.g. link to policy docs).
    """

    category: str
    percent: float  # 0-100
    eligibility: str
    description: str | None = None


# ---------------------------------------------------------------------------
# Aggregation helper structures
# ---------------------------------------------------------------------------


@dataclass
class AccessibilityScore:  # noqa: D101 – lightweight score container
    """Composite accessibility score (0-100, higher = more affordable)."""

    score: float
    # breakdown for transparency – can be extended later
    avg_monthly_cost: float
    avg_discount_pct: float

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – simple helper
        return asdict(self)


# ---------------------------------------------------------------------------
# JSON-Lines store
# ---------------------------------------------------------------------------


class EconomicAccessibilityStore:
    """Persistent storage & aggregation for economic accessibility metadata."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("EconomicAccessibility store initialised at %s", self.path)

    # -----------------
    # Mutating helpers
    # -----------------

    def append(self, entry: BaseEntry) -> None:
        """Append *entry* to the JSON-Lines store."""

        # Basic validation – sanitise inputs (# SECURITY)
        if isinstance(entry, PricingTierEntry) and entry.monthly_cost < 0:
            raise ValueError("monthly_cost must be >= 0")
        if isinstance(entry, DiscountEntry) and not (0 <= entry.percent <= 100):
            raise ValueError("percent must be between 0 and 100")

        line = entry.to_json()
        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _log.info("Recorded %s", entry.type)

    # -----------------
    # Loading helpers
    # -----------------

    def _load(self) -> List[BaseEntry]:
        if not self.path.exists():
            return []

        items: List[BaseEntry] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                e_type = data.pop("type", None)
                if e_type == "PricingTierEntry":
                    items.append(PricingTierEntry(**data))
                elif e_type == "DiscountEntry":
                    items.append(DiscountEntry(**data))
        return items

    # ---------------------------
    # Aggregation + scoring
    # ---------------------------

    def aggregate(self) -> Dict[str, Any]:
        """Return aggregated statistics for accessibility tiers & discounts."""

        pricing: List[PricingTierEntry] = []
        discounts: List[DiscountEntry] = []
        for it in self._load():
            if isinstance(it, PricingTierEntry):
                pricing.append(it)
            elif isinstance(it, DiscountEntry):
                discounts.append(it)

        # Calculate averages – guard against division by zero
        avg_price = mean(p.monthly_cost for p in pricing) if pricing else 0.0
        avg_discount = mean(d.percent for d in discounts) if discounts else 0.0

        # Simple heuristic: lower price & higher discount => higher score
        # weight 70% price, 30% discount (tweakable)
        price_component: float
        if pricing:
            price_component = max(0.0, 1 - (avg_price / 50)) * 70  # baseline $50
        else:
            price_component = 0.0  # no data → neutral impact

        discount_component: float = (avg_discount / 100) * 30 if discounts else 0.0

        score = round(price_component + discount_component, 2)

        summary = {
            "tiers": len(pricing),
            "discounts": len(discounts),
            "average_monthly_cost_usd": round(avg_price, 2),
            "average_discount_pct": round(avg_discount, 2),
            "accessibility_score": score,
        }
        return summary

    # --------------------------------------
    # Human-readable + markdown export
    # --------------------------------------

    def to_markdown(self) -> str:
        """Return a Markdown table summary – handy for READMEs / dashboards."""

        stats = self.aggregate()
        lines: List[str] = ["# Economic Accessibility Snapshot (Step 6.1)\n"]
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key, val in stats.items():
            lines.append(f"| {key.replace('_', ' ').title()} | {val} |")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Typer CLI – convenience wrapper
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Economic Accessibility utilities (Step 6.1)")


@app.command()
def add_tier(
    name: str = typer.Argument(..., help="Name of the pricing tier, e.g. Free, Pro"),
    monthly_cost: float = typer.Argument(..., help="Monthly cost in USD (per user)"),
    platform: str = typer.Option("All", "--platform", "-p", help="Target platform / OS family"),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional description"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *PricingTierEntry*."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = EconomicAccessibilityStore(store_path)
    store.append(PricingTierEntry(name=name, monthly_cost=monthly_cost, platform=platform, description=description))
    typer.secho("✅ Pricing tier recorded", fg="green")


@app.command()
def add_discount(
    category: str = typer.Argument(..., help="Discount category e.g. student, educational"),
    percent: float = typer.Argument(..., help="Discount percent 0-100"),
    eligibility: str = typer.Argument(..., help="Who is eligible for this discount?"),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional description"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *DiscountEntry*."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = EconomicAccessibilityStore(store_path)
    store.append(DiscountEntry(category=category, percent=percent, eligibility=eligibility, description=description))
    typer.secho("✅ Discount model recorded", fg="green")


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print an aggregated **accessibility snapshot** for quick inspection."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = EconomicAccessibilityStore(store_path)
    stats = store.aggregate()
    if json_output:
        typer.echo(json.dumps(stats, indent=2) + "\n")
    else:
        for k, v in stats.items():
            typer.echo(f"{k.replace('_', ' ').title()}: {v}")


@app.command()
def export_md(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown summary to *output* file"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Export the summary as *Markdown* – defaults to **stdout** if *output* is not given."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = EconomicAccessibilityStore(store_path)
    md = store.to_markdown()

    if output is None:
        typer.echo(md)
    else:
        output = output.expanduser().resolve()
        output.write_text(md, encoding="utf-8")
        typer.secho(f"✅ Markdown written to {output}", fg="green")


# Enable ``python -m src.economic_accessibility …``
if __name__ == "__main__":  # pragma: no cover – manual usage only
    app()