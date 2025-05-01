from __future__ import annotations

"""Training & Communication resource tracker.

This module operationalises *Step 1.9 Training and Communication* from the
Theory→Code execution spec.  It provides a lightweight registry for the three
required deliverables:

1. **Internal documentation** – use-case templates stored in the repository or
   an internal knowledge base.
2. **Short training videos** – e.g. screencasts demonstrating *Codemap* usage
   or XML diffing workflows.
3. **Real-time comms channels** – Slack / Microsoft Teams channels for support
   and announcements.

The implementation mirrors the JSON-Lines approach used across the codebase
(`success_metrics`, `feedback_mechanism`) to ensure **append-only** audit trails
that play nicely with Git.

CLI usage examples
------------------
Register a new video and list a summary::

    python -m src.training_comm video "Codemap & XML diffing" \
        --url "https://videos.internal.example/codemaps.mp4" \
        --description "5-minute overview"

    python -m src.training_comm summary --json

"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "DocTemplate",
    "TrainingVideo",
    "CommChannel",
    "TrainingStore",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

_DEFAULT_FILE = Path(os.getenv("TRAINING_FILE", ".training_resources.jsonl"))
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(kw_only=True)
class BaseResource:
    """Base dataclass adding *created_at* metadata and JSON serialisation."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property
    def type(self) -> str:  # noqa: D401 – imperative mood not required for property
        return self.__class__.__name__

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Concrete resource types
# ---------------------------------------------------------------------------


@dataclass
class DocTemplate(BaseResource):
    """Represents an *internal documentation template*.

    Parameters
    ----------
    name:
        Human-readable template name, e.g. "Codemap Usage Guide".
    path:
        Relative or absolute file system path (or wiki slug) where the template lives.
    description:
        Optional free-form description of the template purpose / audience.
    version:
        Optional semantic version ("1.0") or Git commit SHA for traceability.
    """

    name: str
    path: str
    description: str | None = None
    version: str | None = None


@dataclass
class TrainingVideo(BaseResource):
    """Represents a *training video* deliverable.

    Parameters
    ----------
    title:
        Video title.
    url:
        HTTP/S or internal storage URL.
    description:
        Optional short summary.
    duration_sec:
        Optional length of the video in seconds.
    tags:
        Optional comma-separated list of tags / topics.
    """

    title: str
    url: str
    description: str | None = None
    duration_sec: int | None = None
    tags: str | None = None  # simple CSV for now


@dataclass
class CommChannel(BaseResource):
    """Represents a *real-time communication channel*.

    Parameters
    ----------
    platform:
        "Slack", "Teams" …
    name:
        Channel or team name, e.g. "#ai-coding-support".
    invite_url:
        Optional invite / deep link URL.
    description:
        Optional description of channel purpose.
    """

    platform: str
    name: str
    invite_url: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# JSON-Lines store
# ---------------------------------------------------------------------------


class TrainingStore:
    """Persistent storage & aggregation helper for training resources."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Training store initialised at %s", self.path)

    # --------------
    # CRUD helpers
    # --------------

    def append(self, resource: BaseResource) -> None:  # noqa: D401 – imperative mood not required
        """Append *resource* to the JSONL store."""

        line = resource.to_json()
        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _log.info("Recorded %s", resource.type)

    # ------------------------------
    # Loading / aggregation helpers
    # ------------------------------

    def _load(self) -> List[BaseResource]:
        if not self.path.exists():
            return []

        resources: List[BaseResource] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                r_type = data.pop("type", None)
                if r_type == "DocTemplate":
                    resources.append(DocTemplate(**data))
                elif r_type == "TrainingVideo":
                    resources.append(TrainingVideo(**data))
                elif r_type == "CommChannel":
                    resources.append(CommChannel(**data))
        return resources

    def aggregate(self) -> Dict[str, Any]:
        """Return simple counts per resource type."""

        docs: List[DocTemplate] = []
        videos: List[TrainingVideo] = []
        channels: List[CommChannel] = []
        for r in self._load():
            if isinstance(r, DocTemplate):
                docs.append(r)
            elif isinstance(r, TrainingVideo):
                videos.append(r)
            elif isinstance(r, CommChannel):
                channels.append(r)

        return {
            "doc_templates": len(docs),
            "training_videos": len(videos),
            "comm_channels": len(channels),
        }


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------


app = typer.Typer(add_completion=False, help="Register and report training resources (Step 1.9)")


@app.command()
def doc(
    name: str = typer.Argument(..., help="Template name"),
    path: str = typer.Argument(..., help="File path or wiki slug"),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional description"),
    version: str | None = typer.Option(None, "--version", "-v", help="Template version/commit"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register an *internal documentation* template."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingStore(store_path)
    store.append(DocTemplate(name=name, path=path, description=description, version=version))


@app.command()
def video(
    title: str = typer.Argument(..., help="Video title"),
    url: str = typer.Option(..., "--url", "-u", help="Video URL"),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional description"),
    duration: int | None = typer.Option(None, "--duration", "-t", help="Length in seconds"),
    tags: str | None = typer.Option(None, "--tags", help="CSV tags"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a *training video* entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingStore(store_path)
    store.append(TrainingVideo(title=title, url=url, description=description, duration_sec=duration, tags=tags))


@app.command()
def channel(
    platform: str = typer.Argument(..., help="Platform e.g. Slack, Teams"),
    name: str = typer.Argument(..., help="Channel name"),
    invite_url: str | None = typer.Option(None, "--invite-url", "-i", help="Invite/deep link URL"),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional description"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a *real-time communication channel*."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingStore(store_path)
    store.append(CommChannel(platform=platform, name=name, invite_url=invite_url, description=description))


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Print a quick count summary of all resources."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingStore(store_path)
    agg = store.aggregate()

    if json_output:
        import sys as _sys, json as _json

        _json.dump(agg, _sys.stdout, indent=2)
        _sys.stdout.write("\n")
    else:
        typer.echo("# Training & Communication Overview\n")
        typer.echo(f"📄 Doc templates:   {agg['doc_templates']}")
        typer.echo(f"🎬 Training videos: {agg['training_videos']}")
        typer.echo(f"💬 Channels:        {agg['comm_channels']}")


@app.command()
def export(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Export resources to a markdown reference sheet."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = TrainingStore(store_path)
    res = store._load()

    if not res:
        typer.echo("No resources recorded.")
        raise typer.Exit(code=1)

    lines: List[str] = ["# Training & Communication Resources", ""]
    docs = [r for r in res if isinstance(r, DocTemplate)]
    videos = [r for r in res if isinstance(r, TrainingVideo)]
    channels = [r for r in res if isinstance(r, CommChannel)]

    if docs:
        lines.append("## Documentation Templates\n")
        for d in docs:
            lines.append(f"* **{d.name}** – {d.path}{' – ' + d.description if d.description else ''}")
        lines.append("")

    if videos:
        lines.append("## Training Videos\n")
        for v in videos:
            dur = f" ({v.duration_sec}s)" if v.duration_sec else ""
            lines.append(f"* **{v.title}** – {v.url}{dur}{' – ' + v.description if v.description else ''}")
        lines.append("")

    if channels:
        lines.append("## Communication Channels\n")
        for c in channels:
            lines.append(f"* **{c.platform} – {c.name}**{': ' + c.invite_url if c.invite_url else ''}{' – ' + c.description if c.description else ''}")
        lines.append("")

    md = "\n".join(lines).rstrip() + "\n"

    if output:
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown written to {output}")
    else:
        typer.echo(md)


# Allow `python -m src.training_comm …`
if __name__ == "__main__":  # pragma: no cover – entry point guard
    app() 