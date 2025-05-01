"""
real_world_context.py – Step 3.2 Analyze the Real-World Context 🛰️

This module converts the theoretical *3.2 Analyze the Real-World Context* section
of the project specification into *executable* Python code so it can be embedded
in prompts, automation workflows or CI checks.

High-level Goal
---------------
Provide **structured insights** for Large Language Models (LLMs) and developers
about *compliance*, *trust* and *infrastructure* constraints when shipping
software in privacy-sensitive or highly-regulated environments.

The analyser focuses on three questions:

1. **Who is the target domain?** – developer-facing SaaS, finance, healthcare, etc.
2. **Which data-protection regimes apply?** – GDPR, DPDP, PIPL…
3. **What technical controls are recommended?** – on-prem deployments, encryption-at-rest, HITL consent, etc.

It intentionally keeps heuristics *simple* so results remain explainable and do
not require access to user secrets or proprietary datasets.

Security/Ethical Notes
~~~~~~~~~~~~~~~~~~~~~
* Runs fully *locally* – no network calls.
* Does *not* inspect file contents, only metadata and configuration flags.
* All heuristics are transparent + documented so humans can audit bias quickly.

# REVIEW: Regulatory mappings below require periodic updates – please verify
         against latest legal texts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set

import typer

from .logger import get_logger

_log = get_logger(__name__)

__all__ = [
    "analyze_real_world_context",
    "Regulation",
    "Domain",
    "app",
]

# ---------------------------------------------------------------------------
# Enumerations – make the mapping *explicit*
# ---------------------------------------------------------------------------


class Domain(str, Enum):
    """Supported high-level domains.

    Feel free to extend – keep names *lower-snake_case* for JSON friendliness.
    """

    DEVELOPER_TOOLING = "developer_tooling"
    FINANCE = "finance"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    JOURNALISM = "journalism"
    OTHER = "other"


class Regulation(str, Enum):
    """Known data-protection regimes (non-exhaustive)."""

    GDPR = "GDPR"  # EU
    DPDP = "DPDP"  # India – Digital Personal Data Protection Act 2023
    PIPL = "PIPL"  # Mainland China – Personal Information Protection Law
    HIPAA = "HIPAA"  # US healthcare
    PCI_DSS = "PCI-DSS"  # Payment card industry (finance)
    FERPA = "FERPA"  # US education privacy


# ---------------------------------------------------------------------------
# Static knowledge base (very coarse heuristics)
# ---------------------------------------------------------------------------

# Domain → default regulation set
_DOMAIN_REGULATIONS: Dict[Domain, Set[Regulation]] = {
    Domain.DEVELOPER_TOOLING: {Regulation.GDPR},
    Domain.FINANCE: {Regulation.GDPR, Regulation.PCI_DSS, Regulation.DPDP},
    Domain.HEALTHCARE: {Regulation.GDPR, Regulation.HIPAA},
    Domain.EDUCATION: {Regulation.GDPR, Regulation.FERPA},
    Domain.JOURNALISM: {Regulation.GDPR},
    Domain.OTHER: set(),
}

# Regulation → recommended technical controls (plain English)
_REGULATION_CONTROLS: Dict[Regulation, List[str]] = {
    Regulation.GDPR: [
        "Encrypt data at rest & in transit",
        "Provide data-subject export & deletion endpoints (Art. 15/17)",
        "Minimise personal data collection (Art. 5 – data minimisation)",
    ],
    Regulation.DPDP: [
        "Localise critical personal data inside India unless explicit consent",
        "Appoint data-protection officer reachable in India",
    ],
    Regulation.PIPL: [
        "Store personal data of Chinese users on mainland servers",
        "Perform security assessment before cross-border transfers",
    ],
    Regulation.HIPAA: [
        "Enable audit logging for all PHI access",
        "Implement Business Associate Agreements (BAA) with vendors",
    ],
    Regulation.PCI_DSS: [
        "Never store CVV; truncate PAN where possible",
        "Enforce network segmentation for cardholder data environment (CDE)",
    ],
    Regulation.FERPA: [
        "Restrict disclosure of student educational records",
        "Allow students to review & request corrections",
    ],
}

# Generic controls independent of regulation but derived from spec (cloud vs on-prem)
_GENERIC_CONTROLS = [
    "Offer on-prem or single-tenant deployment options to reduce cloud reliance",
    "Provide client-side encryption or local data-vault mechanism (see DataVault)",
    "Give users clear consent dialogs & data-sharing toggles",
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_real_world_context(
    domain: Domain | str,
    *,
    extra_regulations: List[str] | None = None,
) -> Dict[str, Any]:
    """Return compliance & control recommendations for *domain*.

    Parameters
    ----------
    domain:
        The primary domain/category your product targets. Accepts either a
        :class:`Domain` member or an arbitrary string (falls back to
        :pyattr:`Domain.OTHER`).
    extra_regulations:
        Optional list of additional regulation *names* (case-insensitive) to
        include in the assessment, e.g. ``["LGPD"]``. Unknown items are
        preserved in the output but have empty control lists – humans can fill
        gaps later (# DISCUSS: consider adding automatic lookup).

    Returns
    -------
    Dict[str, Any]
        JSON-serialisable structure with keys ``domain``, ``regulations`` and
        ``controls``.
    """

    _log.debug("Analyzing real-world context for domain %s", domain)

    try:
        domain_enum = Domain(domain) if isinstance(domain, str) else domain
    except ValueError:
        _log.warning("Unknown domain '%s' – treating as 'other'", domain)
        domain_enum = Domain.OTHER

    regulations: Set[Regulation | str] = set(_DOMAIN_REGULATIONS.get(domain_enum, set()))

    if extra_regulations:
        for r in extra_regulations:
            # Preserve case of unknown regulation
            match = next((reg for reg in Regulation if reg.value.lower() == r.lower()), None)
            regulations.add(match or r)  # type: ignore[arg-type]

    # Build list of control recommendations
    controls: List[str] = []
    for reg in regulations:
        if isinstance(reg, Regulation):
            controls.extend(_REGULATION_CONTROLS.get(reg, []))
    controls.extend(_GENERIC_CONTROLS)

    result: Dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "domain": domain_enum.value,
        "regulations": sorted(r.value if isinstance(r, Regulation) else r for r in regulations),
        "controls": sorted(set(controls)),  # de-duplicate & sort for stable output
    }

    _log.debug("Real-world context result: %s", result)
    return result


# ---------------------------------------------------------------------------
# Typer CLI – quick ad-hoc checks
# ---------------------------------------------------------------------------

app = typer.Typer(help="3.2 Real-World Context analyser – compliance cheat-sheet generator")


@app.command()
def assess(
    domain: str = typer.Option(
        ..., "--domain", "-d", help="Target domain e.g. finance, healthcare"
    ),
    extra: List[str] = typer.Option(None, "--extra", help="Additional regulation names"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI wrapper around :pyfunc:`analyze_real_world_context`."""

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    data = analyze_real_world_context(domain, extra_regulations=extra or None)

    if pretty:
        _pretty_print(data)
    else:
        typer.echo(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pretty_print(data: Dict[str, Any]) -> None:  # noqa: D401 – imperative mood not necessary
    """Human-readable CLI printer."""

    typer.echo(f"📊 Real-World Context Assessment – {data['domain']}\n")
    typer.echo("Regulations in scope:")

    for reg in data["regulations"]:
        typer.echo(f"  • {reg}")

    typer.echo("\nRecommended controls:")
    for ctrl in data["controls"]:
        typer.echo(f"  • {ctrl}")


# ---------------------------------------------------------------------------
# Self-test (manual) – ``python -m src.real_world_context assess developer_tooling --pretty``
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()