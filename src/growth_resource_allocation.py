from __future__ import annotations

"""growth_resource_allocation.py – Step 6.5 Resource Allocation 🎯📈

This module **operationalises** the *6.5 – Resource Allocation* block by
providing an *out-of-the-box* preset that registers **cross-functional**
personnel requirements required to roll-out the *Growth & Licensing* work
stream.  It leverages the generic :pymod:`src.resource_allocation` helpers
for storage, aggregation & reporting – avoiding any data-model duplication.

Roles covered
~~~~~~~~~~~~~
| Role            | Responsibility                                    |
|-----------------|----------------------------------------------------|
| DevOps          | Cross-platform build support                       |
| Growth PM       | Tier segmentation & pricing logic                  |
| Backend Dev     | Licence key logic + SheerID/OAuth integration      |
| Marketing       | Campaign assets, onboarding flows                  |
| Customer Success| EDU support, startup inquiries                     |

Key features
~~~~~~~~~~~~
* **Re-use** of :class:`src.resource_allocation.ResourceStore` &
  :class:`src.resource_allocation.PersonnelEntry` for persistence.
* **CLI-first** – ``python -m src.growth_resource_allocation seed`` seeds the
  preset; run ``resource_allocation.summary`` afterwards for a dashboard view.
* **Security** – pure local file I/O; no secrets or external requests.

"""

from pathlib import Path
import os
import typer

from .logger import get_logger, setup_logging
from .resource_allocation import ResourceStore, PersonnelEntry

__all__ = [
    "seed_growth_resources",
    "app",
]

_log = get_logger(__name__)

_DEFAULT_FILE = Path(os.getenv("RESOURCE_FILE", ".resource_allocation.jsonl"))

# ---------------------------------------------------------------------------
# Public helper – main entry-point used by other modules / CI scripts
# ---------------------------------------------------------------------------


def seed_growth_resources(store_path: str | Path = _DEFAULT_FILE) -> None:
    """Append *Step 6.5* growth resource allocation entries to *store_path*.

    Parameters
    ----------
    store_path:
        Path to the JSON-Lines resource store.  Falls back to the environment
        variable ``$RESOURCE_FILE`` or ``.resource_allocation.jsonl`` when not
        provided.
    """

    store = ResourceStore(store_path)

    _log.debug("Seeding growth resource allocation into %s", store.path)

    # Conventional preset – quantities reflect *minimum viable* head-count.
    presets: list[tuple[str, float, str | None]] = [
        ("DevOps", 1, "Cross-platform build support"),
        ("Growth PM", 1, "Tier segmentation & pricing logic"),
        ("Backend Dev", 2, "Licence key logic + SheerID/OAuth integration"),
        ("Marketing", 1, "Campaign assets & onboarding flows"),
        ("Customer Success", 1, "EDU support & startup inquiries"),
    ]

    for role, qty, note in presets:
        store.append(PersonnelEntry(role=role, quantity=qty, notes=note))

    # REVIEW: Consider a follow-up step that automatically raises a *feedback*
    # event once all presets across steps 5.x–6.x have been seeded – enabling
    # consolidated dashboards.  For now we only log an INFO line.
    _log.info("Growth resource allocation preset added – run 'resource_allocation.summary' to inspect.")


# ---------------------------------------------------------------------------
# Typer CLI – convenience wrapper around :func:`seed_growth_resources`
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Seed Step 6.5 growth resource allocation preset.")


@app.command()
def seed(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI command that seeds the Step 6.5 preset into *store_path*."""

    setup_logging("DEBUG" if verbose else "INFO")
    seed_growth_resources(store_path)
    typer.secho("✅ Growth resource allocation seeded (Step 6.5)")


# Allow ``python -m src.growth_resource_allocation seed``
if __name__ == "__main__":  # pragma: no cover – manual usage only
    app()