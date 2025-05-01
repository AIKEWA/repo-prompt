from __future__ import annotations

"""Clear Communication & Stakeholder Training utilities (Step 2.12).

This module operationalises *Step 2.12 – Clear Communication & Stakeholder
Training* as described in the theory-to-code execution spec.

Key deliverables handled by this helper:
1. **Onboarding webinar registry** – track past and upcoming *Cognition Meets
   Code* sessions.
2. **Internal playbooks** – markdown files and/or wiki pages teaching prompt
   crafting and cognitive alignment best practices.

The implementation deliberately mirrors :pymod:`src.training_comm` so that all
*learning & enablement* resources share the same **append-only JSON-Lines**
format and CLI conventions.

Security & privacy considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* All stored metadata is non-sensitive by design (titles, paths, URLs).
* Files are written locally only – no external network calls.

Example
-------
>>> from src.stakeholder_training import Webinar, StakeholderTrainingStore
>>> store = StakeholderTrainingStore()
>>> store.append(Webinar(title="Cognition Meets Code – June 2024", url="https://meet.example.com/abc"))
>>> store.aggregate()
{'webinars': 1, 'playbooks': 0}
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "Webinar",
    "Playbook",
    "StakeholderTrainingStore",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_FILE = Path(os.getenv("STAKEHOLDER_TRAINING_FILE", ".stakeholder_training.jsonl"))
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------------------
# Dataclass primitives
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _BaseRecord:
    """Shared metadata + JSON serialisation for child records."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # ----------------------
    # Helper properties
    # ----------------------

    @property
    def type(self) -> str:  # noqa: D401 – property naming OK
        return self.__class__.__name__

    # ----------------------
    # Serialisation helpers
    # ----------------------

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


@dataclass
class Webinar(_BaseRecord):
    """Represents an *onboarding webinar* event.

    Parameters
    ----------
    title:
        Descriptive webinar title e.g. "Cognition Meets Code – Q3 Kick-off".
    date:
        Optional ISO-8601 date string (YYYY-MM-DD).  Defaults to current UTC
        date if omitted.
    url:
        Link to the webinar (live session or recording).
    description:
        Optional free-form summary.
    duration_min:
        Optional duration in **minutes**; helps understand effort required.
    tags:
        Optional comma-separated list of topics ("prompting,alignment").
    """

    title: str
    url: str
    date: str | None = None
    description: str | None = None
    duration_min: int | None = None
    tags: str | None = None

    # Fill *date* post-init if not provided
    def __post_init__(self) -> None:  # noqa: D401
        if self.date is None:
            self.date = datetime.utcnow().strftime("%Y-%m-%d")


@dataclass
class Playbook(_BaseRecord):
    """Represents an *internal playbook* (markdown file or wiki page).

    Parameters
    ----------
    topic:
        Short topic identifier, e.g. "prompt_crafting".
    path:
        File system path or wiki slug where the playbook lives.
    description:
        Optional free-form description.
    version:
        Optional semantic version ("1.0") or Git commit SHA.
    """

    topic: str
    path: str
    description: str | None = None
    version: str | None = None


# ---------------------------------------------------------------------------
# JSON-Lines store
# ---------------------------------------------------------------------------


class StakeholderTrainingStore:
    """Append-only storage & aggregation for Step 2.12 resources."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Stakeholder training store initialised at %s", self.path)

    # --------------
    # CRUD helpers
    # --------------

    def append(self, record: _BaseRecord) -> None:  # noqa: D401 – imperative mood
        """Serialise *record* to disk (append-only)."""

        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        _log.info("Recorded %s", record.type)

    # ------------------------------
    # Loading & aggregation helpers
    # ------------------------------

    def _load(self) -> List[_BaseRecord]:
        if not self.path.exists():
            return []

        records: List[_BaseRecord] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                r_type = data.pop("type", None)
                if r_type == "Webinar":
                    records.append(Webinar(**data))
                elif r_type == "Playbook":
                    records.append(Playbook(**data))
        return records

    def aggregate(self) -> Dict[str, Any]:
        """Return counts per resource type."""

        # FEEDBACK: We might want to track *unique participants* per webinar in
        # future iterations – that would require an additional field or an
        # external attendance log.

        webinars: List[Webinar] = []
        playbooks: List[Playbook] = []
        for r in self._load():
            if isinstance(r, Webinar):
                webinars.append(r)
            elif isinstance(r, Playbook):
                playbooks.append(r)
        return {
            "webinars": len(webinars),
            "playbooks": len(playbooks),
        }

    # --------------------
    # Export helper (md)
    # --------------------

    def export_markdown(self) -> str:
        """Return a human-friendly markdown overview of all records."""

        lines: List[str] = ["# Stakeholder Training Resources\n"]

        webinars = [r for r in self._load() if isinstance(r, Webinar)]
        playbooks = [r for r in self._load() if isinstance(r, Playbook)]

        if webinars:
            lines.append("## Onboarding Webinars\n")
            for w in webinars:
                lines.append(f"* **{w.title}** – {w.date} ([link]({w.url}))")
                if w.description:
                    lines.append(f"  \- {w.description}")
            lines.append("")

        if playbooks:
            lines.append("## Internal Playbooks\n")
            for p in playbooks:
                lines.append(f"* **{p.topic}** – {p.path}")
                if p.description:
                    lines.append(f"  \- {p.description}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------


app = typer.Typer(add_completion=False, help="Register and report stakeholder training resources (Step 2.12)")


@app.command()
def webinar(
    title: str = typer.Argument(..., help="Webinar title"),
    url: str = typer.Option(..., "--url", "-u", help="Webinar URL"),
    date: str | None = typer.Option(None, "--date", "-d", help="ISO-8601 date (YYYY-MM-DD)"),
    description: str | None = typer.Option(None, "--description", "-s", help="Optional description"),
    duration: int | None = typer.Option(None, "--duration", "-t", help="Duration in minutes"),
    tags: str | None = typer.Option(None, "--tags", help="CSV tags"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register an *onboarding webinar* entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = StakeholderTrainingStore(store_path)
    store.append(
        Webinar(
            title=title,
            url=url,
            date=date,
            description=description,
            duration_min=duration,
            tags=tags,
        )
    )


@app.command()
def playbook(
    topic: str = typer.Argument(..., help="Topic identifier e.g. 'prompt_crafting'"),
    path: str = typer.Argument(..., help="File path or wiki slug"),
    description: str | None = typer.Option(None, "--description", "-s", help="Optional description"),
    version: str | None = typer.Option(None, "--version", "-v", help="Version or commit SHA"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a *playbook* entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = StakeholderTrainingStore(store_path)
    store.append(Playbook(topic=topic, path=path, description=description, version=version))


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Print simple counts per resource type."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = StakeholderTrainingStore(store_path)
    agg = store.aggregate()
    if json_output:
        typer.echo(json.dumps(agg))
    else:
        typer.echo("\n".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in agg.items()))


@app.command()
def export(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Export a markdown overview of all resources."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = StakeholderTrainingStore(store_path)
    md = store.export_markdown()

    if output:
        output = output.expanduser().resolve()
        if output.exists():
            _log.warning("Overwriting existing file at %s", output)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown exported to {output}")
    else:
        typer.echo(md)