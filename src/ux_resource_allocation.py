# new file
from __future__ import annotations

"""ux_resource_allocation.py – Step 5.6 Resource Allocation 🧑‍💻📦

This module operationalises the **5.6 Resource Allocation** theory block for
building the macOS *Onboarding Wizard* and surrounding UX assets.

It builds on the generic :pymod:`src.resource_allocation` infrastructure by
adding a *dedicated* preset that records the multidisciplinary **personnel**
requirements outlined in the specification:

| Resource Type     | Quantity | Role details                                       |
|-------------------|----------|---------------------------------------------------|
| UX Designer       | 1        | HIG compliance, wizard flow                       |
| Swift Developer   | 2        | Wizard coding, UI state management                |
| Dev Advocate      | 1        | Templates, onboarding docs, tutorial videos       |
| QA Engineer       | 1        | Usability testing, feature-flags testing          |

Key features
~~~~~~~~~~~~
* **Zero duplication** – reuses :class:`src.resource_allocation.ResourceStore` &
  :class:`src.resource_allocation.PersonnelEntry` for storage & aggregation.
* **CLI-first** – ``python -m src.ux_resource_allocation seed`` seeds the
  preset; use ``resource_allocation.summary`` afterwards to verify.
* **Security & privacy** – purely local file writes, no network calls.
"""

from pathlib import Path
import os
import typer

from .logger import get_logger, setup_logging
from .resource_allocation import ResourceStore, PersonnelEntry

__all__ = [
    "seed_wizard_resources",
    "app",
]

_log = get_logger(__name__)

_DEFAULT_FILE = Path(os.getenv("RESOURCE_FILE", ".resource_allocation.jsonl"))

# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def seed_wizard_resources(store_path: str | Path = _DEFAULT_FILE) -> None:
    """Append *Step 5.6* personnel requirements to *store_path* JSONL.

    Parameters
    ----------
    store_path:
        Path to the JSON-Lines resource store (defaults to
        ``$RESOURCE_FILE`` env var or ``.resource_allocation.jsonl``).
    """

    store = ResourceStore(store_path)

    _log.debug("Seeding wizard resource allocation into %s", store.path)

    presets = [
        ("UX Designer (HIG compliance & wizard flow)", 1),
        ("Swift Developer (wizard coding & UI state management)", 2),
        ("Developer Advocate (templates, onboarding docs, tutorial videos)", 1),
        ("QA Engineer (usability testing & feature flags testing)", 1),
    ]

    for role, qty in presets:
        store.append(PersonnelEntry(role=role, quantity=qty))

    _log.info("Wizard resource allocation preset added – run 'resource_allocation.summary' to inspect.")


# ---------------------------------------------------------------------------
# Typer CLI – convenience wrapper
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Seed Step 5.6 wizard resource allocation preset.")


@app.command()
def seed(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI entry-point to :func:`seed_wizard_resources`."""

    setup_logging("DEBUG" if verbose else "INFO")
    seed_wizard_resources(store_path)
    typer.secho("✅ Wizard resource allocation seeded (Step 5.6)")


# Allow ``python -m src.ux_resource_allocation seed``
if __name__ == "__main__":  # pragma: no cover – manual usage only
    app()