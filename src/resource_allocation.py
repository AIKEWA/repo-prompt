from __future__ import annotations

"""Resource allocation tracker – Step 2.8.

This module operationalises the theoretical **2.8 Resource Allocation** section
by providing a **lightweight registry** for both *personnel* and *budget*
requirements.  Usage mirrors existing helper modules such as
`training_comm` and `success_metrics` to ensure a familiar developer
experience and append-only audit trail that works well with Git.

Key capabilities
----------------
* **Dataclasses** for *Personnel* and *Budget* entries with built-in
  serialisation helpers.
* **JSON-Lines store** (`.resource_allocation.jsonl` by default) for
  append-only logging – safe in both local and CI environments.
* **Aggregation helpers** returning counts (per role) and cost summaries
  (per category & total), ready for dashboards or markdown export.
* **Typer CLI** – ``python -m src.resource_allocation …`` – for ad-hoc
  recording and reporting without additional scripting.

Security & privacy
~~~~~~~~~~~~~~~~~~
* Purely local file writes – no external network calls.
* No sensitive data (API keys, credentials) is stored.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "PersonnelEntry",
    "BudgetEntry",
    "ResourceStore",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

_DEFAULT_FILE = Path(os.getenv("RESOURCE_FILE", ".resource_allocation.jsonl"))
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(kw_only=True)
class BaseEntry:  # noqa: D101 – documented in subclasses
    """Base dataclass adding *created_at* metadata and JSON serialisation."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property  # noqa: D401 – imperative mood not required
    def type(self) -> str:
        return self.__class__.__name__

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Concrete entry types
# ---------------------------------------------------------------------------


@dataclass
class PersonnelEntry(BaseEntry):
    """Represents a *personnel allocation*.

    Parameters
    ----------
    role:
        Short role/name, e.g. "Cognitive-computing champion".
    quantity:
        Number of people required (can be fractional for FTE calculations).
    notes:
        Optional free-form notes, e.g. "One per team".
    """

    role: str
    quantity: float = 1.0
    notes: str | None = None


@dataclass
class BudgetEntry(BaseEntry):
    """Represents a *budget line*.

    Parameters
    ----------
    category:
        Category label, e.g. "LLM API".
    amount:
        Monetary amount **per period** – see *period*.
    currency:
        ISO currency code, default "USD".
    period:
        Either "one-off", "monthly" or "annual".
    description:
        Optional details or cost assumptions.
    """

    category: str
    amount: float
    currency: str = "USD"
    period: str = "one-off"  # could be monthly/annual
    description: str | None = None

    def annualised(self) -> float:
        """Return annualised amount (simplistic helper)."""

        if self.period == "one-off":
            return self.amount
        if self.period == "monthly":
            return self.amount * 12
        if self.period == "annual":
            return self.amount
        _log.debug("Unknown period '%s' – assuming one-off", self.period)
        return self.amount


# ---------------------------------------------------------------------------
# JSON-Lines store
# ---------------------------------------------------------------------------


class ResourceStore:
    """Persistent storage & aggregation helper for resource allocations."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Resource store initialised at %s", self.path)

    # -----------------
    # Mutating helpers
    # -----------------

    def append(self, entry: BaseEntry) -> None:
        """Append *entry* to the JSONL store."""

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
                if e_type == "PersonnelEntry":
                    items.append(PersonnelEntry(**data))
                elif e_type == "BudgetEntry":
                    items.append(BudgetEntry(**data))
        return items

    # ---------------------------
    # Aggregation + export helpers
    # ---------------------------

    def aggregate(self) -> Dict[str, Any]:
        """Return simple aggregated view (personnel counts, budget totals)."""

        personnel: List[PersonnelEntry] = []
        budgets: List[BudgetEntry] = []
        for it in self._load():
            if isinstance(it, PersonnelEntry):
                personnel.append(it)
            elif isinstance(it, BudgetEntry):
                budgets.append(it)

        # Aggregate personnel by role
        role_counts: Dict[str, float] = {}
        for p in personnel:
            role_counts[p.role] = role_counts.get(p.role, 0.0) + p.quantity

        # Aggregate budget by category (annualised) & grand total
        category_totals: Dict[str, float] = {}
        for b in budgets:
            category_totals[b.category] = category_totals.get(b.category, 0.0) + b.annualised()
        grand_total = sum(category_totals.values())

        return {
            "personnel": role_counts,
            "budget": {
                "per_category": category_totals,
                "total_annualised": round(grand_total, 2),
            },
        }

    def to_markdown(self) -> str:
        """Return a markdown table summary of the current store."""

        data = self.aggregate()
        lines: List[str] = ["# Resource Allocation Summary", ""]

        # Personnel
        lines.append("## Personnel Requirements")
        if not data["personnel"]:
            lines.append("No personnel recorded.")
        else:
            lines.append("| Role | Quantity |")
            lines.append("|------|----------|")
            for role, qty in data["personnel"].items():
                lines.append(f"| {role} | {qty} |")
        lines.append("")

        # Budget
        lines.append("## Budget Overview (Annualised)")
        budget = data["budget"]["per_category"]
        if not budget:
            lines.append("No budget lines recorded.")
        else:
            lines.append("| Category | Annualised Cost | Currency |")
            lines.append("|----------|-----------------|----------|")
            for cat, amt in budget.items():
                lines.append(f"| {cat} | {amt:.2f} | USD |")  # FIXME currency per line
            lines.append("| **Total** | **{:.2f}** | USD |".format(data["budget"]["total_annualised"]))
        lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Register and report resource allocations (Step 2.8)")


@app.command()
def personnel(
    role: str = typer.Argument(..., help="Role/position label"),
    quantity: float = typer.Option(1, "--qty", help="Number of people (supports decimals for FTE)"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Optional notes"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Register a *personnel* requirement."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = ResourceStore(store_path)
    store.append(PersonnelEntry(role=role, quantity=quantity, notes=notes))


@app.command()
def budget(
    category: str = typer.Argument(..., help="Budget category label"),
    amount: float = typer.Option(..., "--amount", "-a", help="Amount per period"),
    currency: str = typer.Option("USD", "--currency", "-c", help="ISO currency code"),
    period: str = typer.Option("one-off", "--period", "-p", help="one-off|monthly|annual"),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional description"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Register a *budget* line item."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = ResourceStore(store_path)
    store.append(
        BudgetEntry(category=category, amount=amount, currency=currency, period=period, description=description)
    )


@app.command()
def preset_green_ai(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Seed *Green AI Coding* resource presets (Step 4.7).

    Adds the following **personnel** entries:

    * 2 × *AI/ML engineer* – local model integration
    * 1 × *Energy analytics engineer* – CodeCarbon & scheduling
    * 1 × *UX researcher* – sustainable developer experience

    Call once per project. Existing entries with identical role labels are
    **not** deduplicated; run ``resource_allocation.summary`` afterwards to
    verify.
    """

    setup_logging("DEBUG" if verbose else "INFO")

    store = ResourceStore(store_path)

    presets = [
        ("AI/ML engineer (local model integration)", 2),
        ("Energy analytics engineer (CodeCarbon + scheduling)", 1),
        ("UX researcher (sustainable developer experience)", 1),
    ]

    for role, qty in presets:
        store.append(PersonnelEntry(role=role, quantity=qty))

    typer.echo("✅ Green AI resource presets added – run 'resource_allocation.summary' to inspect.")


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print aggregate *resource* summary."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = ResourceStore(store_path)
    data = store.aggregate()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
    else:
        # Pretty print via markdown tables (rendered plain in console)
        md = store.to_markdown()
        typer.echo(md)


@app.command()
def export(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown summary to file"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Export summary to markdown file (or STDOUT)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = ResourceStore(store_path)
    md = store.to_markdown()

    if output is None:
        typer.echo(md)
    else:
        output.write_text(md, encoding="utf-8")
        if verbose:
            typer.echo(f"Markdown written to {output.resolve()}")