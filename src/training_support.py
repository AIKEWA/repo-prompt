from __future__ import annotations

"""Training & Support utilities (Step 2.13).

This module operationalises *Step 2.13 – Training and Support* from the
Theory→Code execution framework.

Deliverables addressed:
1. **Workshop series registry** – capture metadata about internal workshops
   (e.g. *Thinking in Chunks: Using CodeMaps*).
2. **Mentorship pairings** – link newcomers with *Repo-Prompt* champions for
   guided onboarding.

Implementation notes
-------------------
* Mirrors ``src.stakeholder_training`` for consistency (append-only JSONL,
  Typer CLI, markdown export).
* Purely local operations – no network calls, secrets, or mutable shared state.

Example usage
-------------
>>> from src.training_support import Workshop, TrainingSupportStore
>>> store = TrainingSupportStore()
>>> store.append(Workshop(title="Thinking in Chunks: Using CodeMaps", facilitator="Jane Doe"))
>>> print(store.aggregate())
{'workshops': 1, 'mentorship_pairs': 0}
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
    "Workshop",
    "MentorshipPair",
    "TrainingSupportStore",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

_DEFAULT_FILE = Path(os.getenv("TRAINING_SUPPORT_FILE", ".training_support.jsonl"))
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(kw_only=True)
class _BaseRecord:
    """Shared record metadata with JSON serialisation helpers."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property
    def type(self) -> str:  # noqa: D401
        return self.__class__.__name__

    def to_json(self) -> str:  # noqa: D401
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Record types
# ---------------------------------------------------------------------------


@dataclass
class Workshop(_BaseRecord):
    """Metadata for an internal training *workshop*.

    Parameters
    ----------
    title:
        Workshop title, e.g. "Attention Engineering with Context Builder".
    facilitator:
        Person or team running the workshop.
    date:
        Optional ISO-8601 date string (YYYY-MM-DD).  Defaults to today.
    duration_min:
        Optional workshop length in minutes.
    description:
        Optional free-form details.
    recording_url:
        Optional link to recording/slides.
    tags:
        Optional CSV string categorising workshop topics.
    """

    title: str
    facilitator: str
    date: str | None = None
    duration_min: int | None = None
    description: str | None = None
    recording_url: str | None = None
    tags: str | None = None

    def __post_init__(self) -> None:  # noqa: D401
        if self.date is None:
            self.date = datetime.utcnow().strftime("%Y-%m-%d")


@dataclass
class MentorshipPair(_BaseRecord):
    """Represents a *mentorship* pairing.

    Parameters
    ----------
    mentee:
        Username or e-mail of the mentee.
    mentor:
        Username or e-mail of the mentor (Repo-Prompt champion).
    start_date:
        Optional ISO-8601 string (YYYY-MM-DD).  Defaults to today.
    status:
        Current status ("active", "completed", "on-hold" …).
    topics:
        Optional CSV topics the mentorship focuses on.
    notes:
        Optional notes / expectations.
    """

    mentee: str
    mentor: str
    start_date: str | None = None
    status: str = "active"
    topics: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:  # noqa: D401
        if self.start_date is None:
            self.start_date = datetime.utcnow().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# JSONL storage
# ---------------------------------------------------------------------------


class TrainingSupportStore:
    """Append-only store & aggregation helper for Step 2.13 resources."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Training support store initialised at %s", self.path)

    # ------------------
    # CRUD helpers
    # ------------------

    def append(self, record: _BaseRecord) -> None:
        """Append *record* to the JSONL store."""

        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        _log.info("Recorded %s", record.type)

    # ------------------
    # Load & aggregate
    # ------------------

    def _load(self) -> List[_BaseRecord]:
        if not self.path.exists():
            return []

        records: List[_BaseRecord] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                r_type = data.pop("type", None)
                if r_type == "Workshop":
                    records.append(Workshop(**data))
                elif r_type == "MentorshipPair":
                    records.append(MentorshipPair(**data))
        return records

    def aggregate(self) -> Dict[str, Any]:
        """Return counts for workshops and mentorship pairs."""

        workshops: List[Workshop] = []
        mentorships: List[MentorshipPair] = []
        for r in self._load():
            if isinstance(r, Workshop):
                workshops.append(r)
            elif isinstance(r, MentorshipPair):
                mentorships.append(r)
        return {
            "workshops": len(workshops),
            "mentorship_pairs": len(mentorships),
        }

    # -----------------
    # Export markdown
    # -----------------

    def export_markdown(self) -> str:
        """Return a markdown report of stored workshops & mentorships."""

        lines: List[str] = ["# Training & Support Resources\n"]

        workshops = [r for r in self._load() if isinstance(r, Workshop)]
        mentorships = [r for r in self._load() if isinstance(r, MentorshipPair)]

        if workshops:
            lines.append("## Workshop Series\n")
            for w in workshops:
                lines.append(f"* **{w.title}** – {w.date} (Facilitator: {w.facilitator})")
                if w.description:
                    lines.append(f"  \- {w.description}")
            lines.append("")

        if mentorships:
            lines.append("## Mentorship Pairings\n")
            for m in mentorships:
                lines.append(f"* **{m.mentee} ↔ {m.mentor}** – {m.start_date} ({m.status})")
                if m.notes:
                    lines.append(f"  \- {m.notes}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------


app = typer.Typer(add_completion=False, help="Register and report training support resources (Step 2.13)")


@app.command()
def workshop(
    title: str = typer.Argument(..., help="Workshop title"),
    facilitator: str = typer.Option(..., "--facilitator", "-f", help="Facilitator name"),
    date: str | None = typer.Option(None, "--date", "-d", help="ISO-8601 date (YYYY-MM-DD)"),
    duration: int | None = typer.Option(None, "--duration", "-t", help="Duration in minutes"),
    description: str | None = typer.Option(None, "--description", "-s", help="Optional description"),
    recording_url: str | None = typer.Option(None, "--recording-url", "-r", help="Recording/slides URL"),
    tags: str | None = typer.Option(None, "--tags", help="CSV tags"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a *workshop* entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingSupportStore(store_path)
    store.append(
        Workshop(
            title=title,
            facilitator=facilitator,
            date=date,
            duration_min=duration,
            description=description,
            recording_url=recording_url,
            tags=tags,
        )
    )


@app.command()
def mentorship(
    mentee: str = typer.Argument(..., help="Mentee username/email"),
    mentor: str = typer.Argument(..., help="Mentor username/email"),
    start_date: str | None = typer.Option(None, "--start-date", "-d", help="Start date (YYYY-MM-DD)"),
    status: str = typer.Option("active", "--status", "-s", help="Status"),
    topics: str | None = typer.Option(None, "--topics", help="CSV topics"),
    notes: str | None = typer.Option(None, "--notes", help="Optional notes"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a *mentorship pair* entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingSupportStore(store_path)
    store.append(
        MentorshipPair(
            mentee=mentee,
            mentor=mentor,
            start_date=start_date,
            status=status,
            topics=topics,
            notes=notes,
        )
    )


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Print counts for workshops and mentorship pairs."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingSupportStore(store_path)
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
    """Export a markdown report of all Training & Support resources."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingSupportStore(store_path)
    md = store.export_markdown()

    if output:
        output = output.expanduser().resolve()
        if output.exists():
            _log.warning("Overwriting existing file at %s", output)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown exported to {output}")
    else:
        typer.echo(md)