"""
real_world_context_analysis.py – Step 6.2 Real-World Context Analysis 📊

This module converts the *6.2 – Real-World Context Analysis* theory block into
**executable** Python utilities that capture market-access constraints and
suggest actionable mitigations.

Context
~~~~~~~
The specification identified three primary *target user* groups that are
currently underserved due to pricing and platform limitations:

* **Students & Universities** – budget-constrained, require free / discounted tiers.
* **Windows/Linux Developers** – excluded by the existing macOS-only build.
* **Early-stage Start-ups** – price-sensitive teams needing flexible seats.

Corresponding *constraints* recognised are:

1. **macOS-only deployment** – narrows the potential user base.
2. **$200–$250 flat fee** – misaligned with academic purchasing norms.
3. **Missing free / limited tier** – hinders trial and brand adoption.

The code below keeps heuristics *transparent* and *auditable* by relying on a
static mapping from *constraint* ➜ *mitigation recommendation*. No network
calls or user telemetry are performed.

Security & ethics
~~~~~~~~~~~~~~~~~
* Local-only execution – no external requests.
* Inputs are validated & logged at DEBUG level for transparency.
* Recommendations are *suggestions* – human review required (# REVIEW).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "TargetUser",
    "Constraint",
    "Mitigation",
    "analyze_market_context",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enumerations – explicit & serialisable (lower-snake_case values)
# ---------------------------------------------------------------------------


class TargetUser(str, Enum):
    """Enumerates the primary *affected* user cohorts."""

    STUDENTS_UNIVERSITIES = "students_universities"
    WINDOWS_LINUX_DEVELOPERS = "windows_linux_developers"
    EARLY_STAGE_STARTUPS = "early_stage_startups"


class Constraint(str, Enum):
    """Enumerates marketplace constraints blocking adoption."""

    MACOS_ONLY_DEPLOYMENT = "macos_only_deployment"
    FLAT_FEE_PRICING = "flat_fee_pricing"
    NO_FREE_TIER = "no_free_tier"


# ---------------------------------------------------------------------------
# Dataclasses & helpers
# ---------------------------------------------------------------------------


@dataclass
class Mitigation:
    """Represents a single *recommendation* to alleviate a constraint."""

    constraint: Constraint
    message: str
    related_modules: List[str]

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return {
            "constraint": self.constraint.value,
            "message": self.message,
            "related_modules": self.related_modules,
        }


# Static mapping – easy to extend & audit
_CONSTRAINT_RECOMMENDATIONS: Dict[Constraint, Mitigation] = {
    Constraint.MACOS_ONLY_DEPLOYMENT: Mitigation(
        constraint=Constraint.MACOS_ONLY_DEPLOYMENT,
        message=(
            "Prioritise a cross-platform build pipeline or lightweight web UI. "
            "Leverage *engineering_stack* helpers to define modular build steps "
            "and *offline_awareness* utilities to keep parity between OSes."
        ),
        related_modules=[
            "engineering_stack",
            "offline_awareness",
            "adaptive_scaling",
        ],
    ),
    Constraint.FLAT_FEE_PRICING: Mitigation(
        constraint=Constraint.FLAT_FEE_PRICING,
        message=(
            "Introduce tiered & usage-based pricing models. Utilise "
            "*economic_accessibility* score helpers to simulate scenarios and "
            "surface optimal student / starter plans."
        ),
        related_modules=[
            "economic_accessibility",
            "resource_allocation",
        ],
    ),
    Constraint.NO_FREE_TIER: Mitigation(
        constraint=Constraint.NO_FREE_TIER,
        message=(
            "Launch a limited free tier or 30-day trial. Combine with the "
            "*feedback_mechanism* to capture onboarding hurdles and track early "
            "activation metrics via *success_metrics*."
        ),
        related_modules=[
            "feedback_mechanism",
            "success_metrics",
            "training_support",
        ],
    ),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_market_context(
    *,
    target_users: List[str] | None = None,
    constraints: List[str] | None = None,
) -> Dict[str, Any]:
    """Analyse *market constraints* and return mitigation suggestions.

    Parameters
    ----------
    target_users:
        Optional list limiting the analysis to specific *target user* names.
        When *None*, the default cohort list is used.
    constraints:
        Optional list limiting analysis to specific *constraint* names. When
        *None*, all supported constraints are considered.

    Returns
    -------
    Dict[str, Any]
        JSON-serialisable structure containing timestamp, users, constraints
        and detailed mitigation recommendations.
    """

    # Resolve TargetUser
    if target_users is None:
        selected_users = list(TargetUser)
    else:
        selected_users = []
        for name in target_users:
            try:
                selected_users.append(TargetUser(name))
            except ValueError:
                _log.warning("Unknown target user '%s' – skipping", name)

    # Resolve Constraint
    if constraints is None:
        selected_constraints = list(Constraint)
    else:
        selected_constraints = []
        for name in constraints:
            try:
                selected_constraints.append(Constraint(name))
            except ValueError:
                _log.warning("Unknown constraint '%s' – skipping", name)

    _log.debug(
        "Analysing market context – users: %s | constraints: %s",
        [u.value for u in selected_users],
        [c.value for c in selected_constraints],
    )

    recommendations = [
        _CONSTRAINT_RECOMMENDATIONS[c].as_dict()
        for c in selected_constraints
        if c in _CONSTRAINT_RECOMMENDATIONS
    ]

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "target_users": [u.value for u in selected_users],
        "constraints": [c.value for c in selected_constraints],
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Typer CLI – quick standalone usage
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=False,
    help="6.2 Real-World Context analyser – maps constraints to mitigations.",
)


@app.command()
def report(
    include_users: List[str] = typer.Option(
        None,
        "--users",
        "-u",
        help="Comma-separated target user names to analyse (default: all).",
    ),
    include_constraints: List[str] = typer.Option(
        None,
        "--constraints",
        "-c",
        help="Comma-separated constraint names to analyse (default: all).",
    ),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty human-readable output"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a **mitigation report** limited by *users* / *constraints*."""

    setup_logging("DEBUG" if verbose else "INFO")

    users_list = [u.strip() for u in include_users] if include_users else None
    constraints_list = [c.strip() for c in include_constraints] if include_constraints else None

    data = analyze_market_context(target_users=users_list, constraints=constraints_list)

    if json_output:
        typer.echo(json.dumps(data, indent=2))
    elif pretty:
        _pretty_print(data)
    else:
        typer.echo(json.dumps(data))


# ---------------------------------------------------------------------------
# Helper – simple pretty printer
# ---------------------------------------------------------------------------

def _pretty_print(data: Dict[str, Any]) -> None:  # noqa: D401 – imperative mood not required
    """Render *data* as colourful CLI output (requires *rich*)."""

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="6.2 Market Constraints – Mitigation Report")
        table.add_column("Constraint", style="cyan", no_wrap=True)
        table.add_column("Recommendation", style="green")
        table.add_column("Modules", style="magenta")

        for rec in data["recommendations"]:
            table.add_row(
                rec["constraint"],
                rec["message"],
                ", ".join(rec["related_modules"]),
            )

        console.print(table)
    except ImportError:
        # Fallback plain JSON if rich is unavailable
        typer.echo(json.dumps(data, indent=2))