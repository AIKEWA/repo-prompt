"""developer_support.py – Step 4.12 Training & Developer Support 🧑‍💻📚

This module operationalises *Step 4.12 – Training and Developer Support* from
our theory–to–code execution framework.

It adds lightweight helpers so internal enablement teams can:

* Register **developer tutorials** (e.g. "How to Code Green with Repo Prompt").
* Schedule **office-hour sessions** with engineers (local setup support).
* Curate a **knowledge base** of benchmark comparisons & best-practice docs.

Design principles
-----------------
* **Append-only JSONL** storage (mirrors :pymod:`src.training_support`).
* **Purely local** side-effects – no network calls or secrets.
* **Typer CLI** for non-dev usage (`python -m src.developer_support --help`).
* Clear docstrings + exhaustive typing to aid maintainability.

Example
~~~~~~~
>>> from src.developer_support import Tutorial, DeveloperSupportStore
>>> store = DeveloperSupportStore()
>>> store.append(Tutorial(title="How to Code Green with Repo Prompt", presenter="Alice"))
>>> store.aggregate()
{'tutorials': 1, 'office_hours': 0, 'knowledge_entries': 0}
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "Tutorial",
    "OfficeHour",
    "KnowledgeEntry",
    "AuthorisedEngineer",
    "send_reminders",
    "generate_kb_html",
    "DeveloperSupportStore",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

_DEFAULT_FILE = Path(os.getenv("DEVELOPER_SUPPORT_FILE", ".developer_support.jsonl"))
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


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


# ---------------------------------------------------------------------------
# Record types
# ---------------------------------------------------------------------------


@dataclass
class Tutorial(_BaseRecord):
    """Metadata for a *developer tutorial* event.

    Parameters
    ----------
    title:
        Tutorial title (e.g. "How to Code Green with Repo Prompt").
    presenter:
        Who presents the tutorial.
    date:
        Optional ISO-8601 date (YYYY-MM-DD). Defaults to *today*.
    duration_min:
        Optional length in minutes.
    description:
        Optional free-form summary.
    recording_url:
        Optional link to recording or slides.
    tags:
        Optional CSV topic tags.
    """

    title: str
    presenter: str
    date: str | None = None
    duration_min: int | None = None
    description: str | None = None
    recording_url: str | None = None
    tags: str | None = None

    def __post_init__(self) -> None:  # noqa: D401 – imperative ok
        if self.date is None:
            self.date = datetime.utcnow().strftime("%Y-%m-%d")


@dataclass
class OfficeHour(_BaseRecord):
    """Represents an *office-hour session* with engineers.

    Parameters
    ----------
    engineer:
        Engineer hosting the session.
    date:
        ISO-8601 date (YYYY-MM-DD). Defaults to *today*.
    start_time:
        Local start time (HH:MM, 24h).
    end_time:
        Local end time (HH:MM, 24h).
    location:
        Optional meeting link or physical room.
    summary:
        Optional short description.
    tags:
        Optional CSV topic tags.
    """

    engineer: str
    start_time: str  # HH:MM 24h
    end_time: str
    date: str | None = None
    location: str | None = None
    summary: str | None = None
    tags: str | None = None

    def __post_init__(self) -> None:  # noqa: D401
        if self.date is None:
            self.date = datetime.utcnow().strftime("%Y-%m-%d")


@dataclass
class KnowledgeEntry(_BaseRecord):
    """Represents a *knowledge-base entry* (benchmarks, docs, etc.).

    Parameters
    ----------
    title:
        Display title.
    path:
        File-system path or wiki slug.
    summary:
        Optional summary or benchmark highlight.
    version:
        Optional semantic version or commit SHA.
    tags:
        Optional CSV tags.
    """

    title: str
    path: str
    summary: str | None = None
    version: str | None = None
    tags: str | None = None


@dataclass
class AuthorisedEngineer(_BaseRecord):
    """Represents an *authorised engineer* allowed to host office hours."""

    name: str  # display name
    email: str | None = None
    handle: str | None = None  # e.g. Slack handle
    notes: str | None = None


# ---------------------------------------------------------------------------
# JSONL store – append only
# ---------------------------------------------------------------------------


class DeveloperSupportStore:
    """Append-only storage & aggregation for Step 4.12 resources."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Developer support store initialised at %s", self.path)

    # ------------------
    # CRUD helpers
    # ------------------

    def append(self, record: _BaseRecord) -> None:  # noqa: D401 – imperative mood
        """Serialise *record* to disk (append-only)."""

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
                if r_type == "Tutorial":
                    records.append(Tutorial(**data))
                elif r_type == "OfficeHour":
                    records.append(OfficeHour(**data))
                elif r_type == "KnowledgeEntry":
                    records.append(KnowledgeEntry(**data))
                elif r_type == "AuthorisedEngineer":
                    records.append(AuthorisedEngineer(**data))
        return records

    def aggregate(self) -> Dict[str, Any]:  # noqa: D401 – imperative ok
        """Return counts for tutorials, office hours & knowledge entries."""

        tutorials: List[Tutorial] = []
        office_hours: List[OfficeHour] = []
        knowledge: List[KnowledgeEntry] = []
        for r in self._load():
            if isinstance(r, Tutorial):
                tutorials.append(r)
            elif isinstance(r, OfficeHour):
                office_hours.append(r)
            elif isinstance(r, KnowledgeEntry):
                knowledge.append(r)
        return {
            "tutorials": len(tutorials),
            "office_hours": len(office_hours),
            "knowledge_entries": len(knowledge),
            "authorised_engineers": sum(isinstance(r, AuthorisedEngineer) for r in self._load()),
        }

    # -----------------
    # Export markdown
    # -----------------

    def export_markdown(self) -> str:  # noqa: D401 – imperative ok
        """Return a markdown overview of all developer-support resources."""

        lines: List[str] = ["# Training & Developer Support Resources (Step 4.12)\n"]

        tutorials = [r for r in self._load() if isinstance(r, Tutorial)]
        office_hours = [r for r in self._load() if isinstance(r, OfficeHour)]
        knowledge = [r for r in self._load() if isinstance(r, KnowledgeEntry)]
        engineers = [r for r in self._load() if isinstance(r, AuthorisedEngineer)]

        if tutorials:
            lines.append("## Tutorials\n")
            for t in tutorials:
                presenter = f" (Presenter: {t.presenter})" if t.presenter else ""
                lines.append(f"* **{t.title}** – {t.date}{presenter}")
                if t.description:
                    lines.append(f"  \- {t.description}")
            lines.append("")

        if office_hours:
            lines.append("## Office-Hour Sessions\n")
            for o in office_hours:
                time_range = f"{o.start_time}–{o.end_time}" if o.start_time and o.end_time else "TBD"
                lines.append(f"* **{o.engineer}** – {o.date} ({time_range})")
                if o.location:
                    lines.append(f"  \- Location: {o.location}")
                if o.summary:
                    lines.append(f"  \- {o.summary}")
            lines.append("")

        if knowledge:
            lines.append("## Knowledge Base Entries\n")
            for k in knowledge:
                version = f" (v{k.version})" if k.version else ""
                lines.append(f"* **{k.title}** – {k.path}{version}")
                if k.summary:
                    lines.append(f"  \- {k.summary}")
            lines.append("")

        if engineers:
            lines.append("## Authorised Engineers\n")
            for e in engineers:
                contact = e.email or e.handle or ""
                contact_str = f" ({contact})" if contact else ""
                lines.append(f"* **{e.name}**{contact_str}")
                if e.notes:
                    lines.append(f"  \\– {e.notes}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------


app = typer.Typer(add_completion=False, help="Register and report developer support resources (Step 4.12)")


# ------------------
# Tutorial command
# ------------------


@app.command()
def tutorial(
    title: str = typer.Argument(..., help="Tutorial title"),
    presenter: str = typer.Option(..., "--presenter", "-p", help="Presenter name"),
    date: str | None = typer.Option(None, "--date", "-d", help="ISO-8601 date (YYYY-MM-DD)"),
    duration: int | None = typer.Option(None, "--duration", "-t", help="Duration in minutes"),
    description: str | None = typer.Option(None, "--description", "-s", help="Optional description"),
    recording_url: str | None = typer.Option(None, "--recording-url", "-r", help="Recording/slides URL"),
    tags: str | None = typer.Option(None, "--tags", help="CSV tags"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a **tutorial** entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeveloperSupportStore(store_path)
    store.append(
        Tutorial(
            title=title,
            presenter=presenter,
            date=date,
            duration_min=duration,
            description=description,
            recording_url=recording_url,
            tags=tags,
        )
    )


# ------------------
# Office-hour command
# ------------------


@app.command()
def officehour(
    engineer: str = typer.Argument(..., help="Engineer hosting the session"),
    start_time: str = typer.Argument(..., help="Start time HH:MM (24h)"),
    end_time: str = typer.Argument(..., help="End time HH:MM (24h)"),
    date: str | None = typer.Option(None, "--date", "-d", help="ISO-8601 date (YYYY-MM-DD)"),
    location: str | None = typer.Option(None, "--location", "-l", help="Link or room"),
    summary: str | None = typer.Option(None, "--summary", "-s", help="Optional summary"),
    tags: str | None = typer.Option(None, "--tags", help="CSV tags"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register an **office-hour session**."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeveloperSupportStore(store_path)
    store.append(
        OfficeHour(
            engineer=engineer,
            start_time=start_time,
            end_time=end_time,
            date=date,
            location=location,
            summary=summary,
            tags=tags,
        )
    )


# ------------------
# Knowledge-base command
# ------------------


@app.command()
def knowledge(
    title: str = typer.Argument(..., help="Entry title"),
    path: str = typer.Argument(..., help="File path or wiki slug"),
    summary: str | None = typer.Option(None, "--summary", "-s", help="Optional summary"),
    version: str | None = typer.Option(None, "--version", "-v", help="Version or commit SHA"),
    tags: str | None = typer.Option(None, "--tags", help="CSV tags"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a *knowledge-base* entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeveloperSupportStore(store_path)
    store.append(
        KnowledgeEntry(
            title=title,
            path=path,
            summary=summary,
            version=version,
            tags=tags,
        )
    )


# ------------------
# Summary & export
# ------------------


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Print aggregate counts for developer-support resources."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeveloperSupportStore(store_path)
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
    """Export a markdown report of all developer-support resources."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeveloperSupportStore(store_path)
    md = store.export_markdown()

    if output:
        output = output.expanduser().resolve()
        if output.exists():
            _log.warning("Overwriting existing file at %s", output)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown exported to {output}")
    else:
        typer.echo(md)


# ---------------------------------------------------------------------------
# Utility helpers – reminders & validation
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> datetime:  # noqa: D401 – small helper
    """Return naive *datetime* for ISO date (YYYY-MM-DD)."""

    return datetime.strptime(date_str, "%Y-%m-%d")


def _within_hours(target: datetime, *, hours: int) -> bool:
    """Return *True* if *target* datetime is within *hours* from *now*."""

    now = datetime.utcnow()
    delta = target - now
    return 0 <= delta.total_seconds() <= hours * 3600


# ---------------------------------------------------------------------------
# HTML generation helper
# ---------------------------------------------------------------------------


def generate_kb_html(tutorials: List[Tutorial], knowledge: List[KnowledgeEntry]) -> str:
    """Return **stand-alone HTML** string for knowledge-base preview.

    The output is a self-contained page with a search input filtering a list of
    tutorials (📘) and benchmark/knowledge entries (📊).
    """

    html_parts: List[str] = [
        "<!doctype html>",
        "<html lang='en'>",
        "<meta charset='utf-8'>",
        "<title>Developer Knowledge Base</title>",
        "<style>body{font-family:system-ui;margin:2rem}input{width:100%;padding:0.5rem;margin-bottom:1rem}</style>",
        "<h1>Developer Knowledge Base</h1>",
        "<input placeholder='Search…' oninput='f(this.value)'>",
        "<ul id='list'>",
    ]

    def _li(label: str, url: str | None = None) -> str:
        link = f"<a href='{url}' target='_blank'>{label}</a>" if url else label
        return f"<li>{link}</li>"

    for t in tutorials:
        html_parts.append(_li(f"📘 Tutorial: {t.title}", t.recording_url))
    for k in knowledge:
        html_parts.append(_li(f"📊 Benchmark: {k.title}", k.path))

    html_parts.extend(
        [
            "</ul>",
            (
                "<script>function f(q){q=q.toLowerCase();"  # simple JS filter
                "for(const li of document.querySelectorAll('#list li')){"  # noqa: E501
                "li.style.display=li.textContent.toLowerCase().includes(q)?'':'none'}}</script>"
            ),
            "</html>",
        ]
    )

    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# Reminder sender
# ---------------------------------------------------------------------------


def send_reminders(*, ahead_hours: int = 24, store_path: Path | str = _DEFAULT_FILE) -> List[OfficeHour]:
    """Return *OfficeHour* sessions starting within *ahead_hours* (UTC)."""

    store = DeveloperSupportStore(store_path)
    upcoming: List[OfficeHour] = []
    for oh in store._load():
        if isinstance(oh, OfficeHour):
            # Parse date + time (assume HH:MM in 24h)
            try:
                dt = datetime.strptime(f"{oh.date} {oh.start_time}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue  # skip malformed
            if _within_hours(dt, hours=ahead_hours):
                upcoming.append(oh)
    return upcoming


# ---------------------------------------------------------------------------
# CLI commands – engineer registry, reminders, kb preview
# ---------------------------------------------------------------------------


@app.command()
def engineer(
    name: str = typer.Argument(..., help="Full name"),
    email: str | None = typer.Option(None, "--email", "-e", help="E-mail address"),
    handle: str | None = typer.Option(None, "--handle", "-H", help="Chat handle e.g. @alice"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Optional notes"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Add an **authorised engineer** allowed to host office hours."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeveloperSupportStore(store_path)
    store.append(AuthorisedEngineer(name=name, email=email, handle=handle, notes=notes))


@app.command()
def remind(
    ahead_hours: int = typer.Option(24, "--hours", "-a", min=1, help="Look-ahead window in hours"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Print upcoming office-hour sessions within *ahead_hours*."""

    setup_logging("DEBUG" if verbose else "INFO")
    upcoming = send_reminders(ahead_hours=ahead_hours, store_path=store_path)

    if not upcoming:
        typer.echo(f"✅ No office-hour sessions in the next {ahead_hours}h.")
        raise typer.Exit()

    typer.echo(f"🔔 Office-hour sessions within {ahead_hours}h:\n")
    for oh in upcoming:
        typer.echo(f"• {oh.date} {oh.start_time} – {oh.engineer}: {oh.summary or 'No summary'}")


@app.command()
def kb_preview(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write HTML to file"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Generate a **simple HTML** knowledge-base index with live search."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = DeveloperSupportStore(store_path)

    tutorials = [r for r in store._load() if isinstance(r, Tutorial)]
    knowledge = [r for r in store._load() if isinstance(r, KnowledgeEntry)]

    doc = generate_kb_html(tutorials, knowledge)

    if output:
        output = output.expanduser().resolve()
        output.write_text(doc, encoding="utf-8")
        typer.echo(f"🌐 Knowledge base HTML written to {output}")
    else:
        typer.echo(doc)


if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter