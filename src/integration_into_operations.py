from __future__ import annotations

"""integration_into_operations.py – Step 7.8 Integration into Operations 🔗⚙️

This module operationalises **Step 7.8 – Integration into Operations**.
It cements *prompt engineering* artefacts (templates, literacy, decisions)
as **first-class DevOps assets** so that product engineering teams can
plan, track, and audit them just like code.

The implementation provides three lightweight subsystems:

1. **Sprint Story Registry** (``.prompt_stories.jsonl``) – Treat changes to
   prompt templates as backlog items that can be picked up in regular
   sprints.  Each record captures the *who/what/why* of an update.
2. **Prompt Literacy Tracker** (``.prompt_literacy.jsonl``) – Log onboarding
   sessions and periodic assessments so *prompt literacy* becomes a
   measurable performance indicator.
3. **AI Decision Audit Log** (``.ai_audit_log.jsonl``) – Append-only log that
   records *every* prompt→response pair hash together with the acting user so
   GDPR, HIPAA, and similar regulations have a **traceable provenance chain**.

Design principles
=================
* **Local-only**: Pure file IO – no outbound network calls; encrypt/hash PII.
* **Append-only JSONL**: Aligns with stores introduced in earlier steps to
  guarantee auditability without complex databases.
* **Minimal dependencies**: Relies solely on the project's existing stack
  (``Typer``, ``rich``).  Cryptographic hashes are provided by stdlib
  :pymod:`hashlib`.
* **CLI-first UX**: Non-Python stakeholders can interact via
  ``python -m src.integration_into_operations …`` commands.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import typer

from .logger import get_logger, setup_logging
from .prompt_ops_framework import PromptTemplate, load_template, validate_template

__all__ = [
    # Data models
    "SprintStory",
    "PromptLiteracyRecord",
    "AiDecisionAuditEntry",
    # Stores
    "SprintStoryStore",
    "PromptLiteracyStore",
    "AuditLogStore",
    # CLI application
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. Data models                                                              #
###############################################################################


@dataclass(slots=True)
class _BaseRecord:  # noqa: D401 – simple value holder
    """Shared metadata + JSON serialisation helper."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # -------------------------
    # Serialisation helpers
    # -------------------------

    def to_json(self) -> str:  # noqa: D401 – imperative style ok
        data = asdict(self)
        data["type"] = self.__class__.__name__
        return json.dumps(data, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 1.1 – Sprint story                                                         #
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SprintStory(_BaseRecord):
    """Represents a *backlog item* for a prompt template update.

    Parameters
    ----------
    template_name:
        Identifier of the affected prompt template.
    from_version:
        The *current* version at the moment the story was raised.
    to_version:
        Target version after the update is completed.
    description:
        Short explanation why the update is required (bug, optimisation, etc.).
    story_points:
        Optional scrum story-point estimate.
    status:
        Kanban status – ``todo`` | ``in-progress`` | ``done``.
    assignee:
        Optional engineer responsible for the story.
    """

    template_name: str
    from_version: str
    to_version: str
    description: str
    story_points: int | None = None
    status: str = "todo"
    assignee: str | None = None


# ---------------------------------------------------------------------------
# 1.2 – Prompt literacy record                                               #
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PromptLiteracyRecord(_BaseRecord):
    """Capture a *prompt literacy* session or assessment.

    Parameters
    ----------
    participant:
        Developer or team-lead identifier (hashed or pseudonymised).
    session_date:
        ISO date ``YYYY-MM-DD`` of the training session.
    score:
        Optional evaluation score (0-10) measuring literacy proficiency.
    topics:
        Optional bullet list of covered topics.
    duration_min:
        Session duration in minutes.
    """

    participant: str
    session_date: str
    score: int | None = None
    topics: List[str] | None = None
    duration_min: int | None = None


# ---------------------------------------------------------------------------
# 1.3 – AI decision audit entry                                              #
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AiDecisionAuditEntry(_BaseRecord):
    """Traceable record of an LLM decision for compliance audits.

    Parameters
    ----------
    template_name:
        Prompt template used to generate the decision.
    prompt_version:
        Version of the template.
    input_hash:
        SHA-256 hash of the *input payload* (prevents PII leakage).
    output_hash:
        SHA-256 hash of the model output.
    user_hash:
        *Salted* hash referencing the end-user (non-reversible pseudonym).
    compliance_tags:
        Regulations this entry is relevant for (e.g. ``["GDPR", "HIPAA"]``).
    decision_id:
        Deterministic ID (first 12 chars of *input_hash*).
    """

    template_name: str
    prompt_version: str
    input_hash: str
    output_hash: str
    user_hash: str
    compliance_tags: Sequence[str]
    decision_id: str = field(init=False)

    # -------------------------
    # Post-init helpers
    # -------------------------

    def __post_init__(self) -> None:  # noqa: D401 – imperative ok
        self.decision_id = self.input_hash[:12]


###############################################################################
# 2. Append-only JSONL stores                                                #
###############################################################################


class _JsonlStore:  # noqa: D101 – internal helper base
    """Lightweight append-only JSONL store."""

    def __init__(self, path: Path | str) -> None:  # noqa: D401
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Store initialised at %s", self.path)

    # ------------------------------------------------------------------
    # Public helper methods
    # ------------------------------------------------------------------

    def append(self, record: _BaseRecord) -> None:  # noqa: D401 – imperative
        """Serialise *record* and append a JSON line."""

        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        _log.info("Recorded %s (%s)", record.__class__.__name__, getattr(record, "created_at", "?"))

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                _log.warning("Skipping invalid JSON: %.40s…", ln)
        return out


# -----------------------------
# Concrete stores
# -----------------------------

_DEFAULT_STORY_FILE = Path(os.getenv("PROMPT_STORY_FILE", ".prompt_stories.jsonl"))
_DEFAULT_LITERACY_FILE = Path(os.getenv("PROMPT_LITERACY_FILE", ".prompt_literacy.jsonl"))
_DEFAULT_AUDIT_FILE = Path(os.getenv("AI_AUDIT_LOG_FILE", ".ai_audit_log.jsonl"))


class SprintStoryStore(_JsonlStore):  # noqa: D101 – concrete store
    """Store for :class:`SprintStory` objects."""

    def __init__(self, path: Path | str = _DEFAULT_STORY_FILE):
        super().__init__(path)

    # -----------------
    # Query helpers
    # -----------------

    def list(self, status: str | None = None) -> List[SprintStory]:  # noqa: D401
        items: List[SprintStory] = []
        for d in self._load():
            if status is None or d.get("status") == status:
                items.append(SprintStory(**d))
        return items


class PromptLiteracyStore(_JsonlStore):  # noqa: D101 – concrete store
    """Store for :class:`PromptLiteracyRecord` objects."""

    def __init__(self, path: Path | str = _DEFAULT_LITERACY_FILE):
        super().__init__(path)

    def aggregate_scores(self) -> Dict[str, float]:  # noqa: D401 – imperative 
        """Return *average* literacy score per participant."""

        scores: Dict[str, List[int]] = {}
        for d in self._load():
            if (score := d.get("score")) is not None:
                scores.setdefault(d["participant"], []).append(score)

        return {p: sum(vals) / len(vals) for p, vals in scores.items() if vals}


class AuditLogStore(_JsonlStore):  # noqa: D101 – concrete store
    """Store for :class:`AiDecisionAuditEntry` records."""

    def __init__(self, path: Path | str = _DEFAULT_AUDIT_FILE):
        super().__init__(path)

    def filter(self, *, tag: str | None = None) -> List[AiDecisionAuditEntry]:  # noqa: D401
        """Return all entries (optionally filtered by *compliance tag*)."""

        elems: List[AiDecisionAuditEntry] = []
        for d in self._load():
            if tag is None or tag in d.get("compliance_tags", []):
                elems.append(AiDecisionAuditEntry(**d))
        return elems


###############################################################################
# 3. Helper utilities                                                        #
###############################################################################


def _sha256(text: str) -> str:  # noqa: D401 – local helper
    return hashlib.sha256(text.encode()).hexdigest()


def record_decision(
    template: PromptTemplate,
    *,
    user_identifier: str,
    input_payload: str,
    output_payload: str,
    compliance_tags: Sequence[str] | None = None,
    store: AuditLogStore | None = None,
) -> AiDecisionAuditEntry:  # noqa: D401 – imperative
    """Create & persist an :class:`AiDecisionAuditEntry` and return it.

    All *payloads* and *user_identifier* values are **hashed** to avoid
    persisting raw potentially sensitive data.  The caller supplies a unique
    salted *user_identifier* – e.g., the **SCIM user ID** + a project salt –
    so GDPR obligations around *pseudonymisation* are respected.
    """

    validate_template(template)  # quick sanity check – # FEEDBACK: extend validation

    entry = AiDecisionAuditEntry(
        template_name=template.name,
        prompt_version=template.version,
        input_hash=_sha256(input_payload),
        output_hash=_sha256(output_payload),
        user_hash=_sha256(user_identifier),
        compliance_tags=list(compliance_tags or []),
    )

    (store or AuditLogStore()).append(entry)
    return entry


###############################################################################
# 4. Typer CLI                                                               #
###############################################################################


app = typer.Typer(add_completion=False, help="Integration into Ops toolkit (step 7.8)")


# -----------------
# Sprint stories
# -----------------


@app.command("story-add")
def cli_story_add(  # noqa: D401 – CLI wrapper
    template: str = typer.Argument(..., help="Prompt template name"),
    from_version: str = typer.Option(..., "--from", help="Current version"),
    to_version: str = typer.Option(..., "--to", help="Target version"),
    description: str = typer.Option("", "--desc", "-d", help="Story description"),
    points: int | None = typer.Option(None, "--points", "-p", help="Story-point estimate"),
    assignee: str | None = typer.Option(None, "--assignee", "-a", help="Owner"),
    store_path: Path = typer.Option(_DEFAULT_STORY_FILE, "--store", help="Custom story JSONL path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs"),
):
    """Create a *sprint story* for a prompt update."""

    setup_logging("DEBUG" if verbose else "INFO")

    story = SprintStory(
        template_name=template,
        from_version=from_version,
        to_version=to_version,
        description=description,
        story_points=points,
        assignee=assignee,
    )

    SprintStoryStore(store_path).append(story)
    typer.echo(f"✅ Story recorded for {template} {from_version}→{to_version}")


@app.command("story-list")
def cli_story_list(  # noqa: D401 – CLI wrapper
    status: str = typer.Option(None, "--status", "-s", help="Filter by status (todo/in-progress/done)"),
    store_path: Path = typer.Option(_DEFAULT_STORY_FILE, "--store", help="Story JSONL path"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List stories (optionally filtered by *status*)."""

    setup_logging("DEBUG" if verbose else "INFO")
    stories = SprintStoryStore(store_path).list(status=status)

    if json_output:
        json.dump([asdict(s) for s in stories], typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        if not stories:
            typer.echo("No stories found.")
            raise typer.Exit()

        def _row(s: SprintStory) -> str:  # noqa: D401 – inline helper
            pts = s.story_points if s.story_points is not None else "-"
            return f"| {s.created_at} | {s.template_name}@{s.from_version}→{s.to_version} | {pts} | {s.status} | {s.assignee or '-'} | "

        header = "| Created | Template | SP | Status | Assignee |\n|---|---|---|---|---|"
        typer.echo(header)
        for st in stories:
            typer.echo(_row(st))


# -----------------
# Prompt literacy
# -----------------


@app.command("literacy-record")
def cli_literacy_record(  # noqa: D401 – CLI wrapper
    participant: str = typer.Argument(..., help="Participant identifier (hashed or pseudonym)"),
    score: int | None = typer.Option(None, "--score", "-s", help="Assessment score 0-10"),
    topics: str | None = typer.Option(None, "--topics", "-t", help="Comma-separated topics"),
    duration: int | None = typer.Option(None, "--duration", "-m", help="Duration in minutes"),
    session_date: str = typer.Option(lambda: datetime.utcnow().strftime("%Y-%m-%d"), "--date", "-d", help="Session date YYYY-MM-DD"),
    store_path: Path = typer.Option(_DEFAULT_LITERACY_FILE, "--store", help="Literacy JSONL path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *prompt literacy* session."""

    setup_logging("DEBUG" if verbose else "INFO")
    rec = PromptLiteracyRecord(
        participant=participant,
        session_date=session_date,
        score=score,
        topics=[t.strip() for t in topics.split(",")] if topics else None,
        duration_min=duration,
    )
    PromptLiteracyStore(store_path).append(rec)
    typer.echo("✅ Prompt literacy record stored")


@app.command("literacy-scores")
def cli_literacy_scores(  # noqa: D401 – CLI wrapper
    store_path: Path = typer.Option(_DEFAULT_LITERACY_FILE, "--store", help="Literacy JSONL path"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print *average literacy scores* per participant."""

    setup_logging("DEBUG" if verbose else "INFO")
    agg = PromptLiteracyStore(store_path).aggregate_scores()

    if json_output:
        json.dump(agg, typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        if not agg:
            typer.echo("No scores available.")
            raise typer.Exit()

        typer.echo("# 📊 Average Prompt Literacy Scores\n")
        typer.echo("| Participant | Avg Score |\n|---|---:|")
        for part, sc in sorted(agg.items(), key=lambda kv: kv[0]):
            typer.echo(f"| {part} | {sc:.2f} |")


# -----------------
# Audit log
# -----------------


@app.command("audit-log")
def cli_audit_log(  # noqa: D401 – CLI wrapper
    tag: str = typer.Option(None, "--tag", "-t", help="Filter by compliance tag (GDPR/HIPAA/…)"),
    store_path: Path = typer.Option(_DEFAULT_AUDIT_FILE, "--store", help="Audit log JSONL path"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List audit log entries (optionally filtered by *tag*)."""

    setup_logging("DEBUG" if verbose else "INFO")
    entries = AuditLogStore(store_path).filter(tag=tag)

    if json_output:
        json.dump([asdict(e) for e in entries], typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        if not entries:
            typer.echo("No entries found.")
            raise typer.Exit()

        typer.echo("# 🗄️ AI Decision Audit Log\n")
        typer.echo("| Time | Template | Version | Decision-ID | Tags |\n|---|---|---|---|---|")
        for e in entries:
            tags = ",".join(e.compliance_tags)
            typer.echo(f"| {e.created_at} | {e.template_name} | {e.prompt_version} | {e.decision_id} | {tags} |")


###############################################################################
# 5. Module CLI Entrypoint                                                   #
###############################################################################


# Allow `python -m src.integration_into_operations …`
if __name__ == "__main__":  # pragma: no cover – direct execution convenience
    app()