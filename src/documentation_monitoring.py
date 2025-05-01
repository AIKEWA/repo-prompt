"""
Documentation & Monitoring utilities (Step 2.7).

This module complements ``success_metrics`` and ``feedback_mechanism`` by
adding **immutable logs** for prompt sessions and diff‐application events –
both prerequisites for reliable *post-hoc* analysis of LLM assisted coding
workflows.

Why a dedicated file?
---------------------
Whilst :pymod:`src.success_metrics` already captures high-level KPIs such as
*Efficiency* and *Accuracy*, the underlying *raw events* (prompt requests,
diffs actually applied to the repo, etc.) are valuable on their own.  They:

* enable drill-down investigations when a KPI spikes,
* provide training data for future model evaluation, and
* satisfy **audit** & **compliance** requirements.

Key features
============
* Append-only **JSON-Lines** store – safe for concurrent writes and friendly
  to version control.
* Minimal **Typer** CLI – one-liners for manual inspection and ad-hoc export.
* SHA-256 *redaction* helper to avoid leaking full prompt contents while still
  allowing grouping by *prompt hash*.
* Summary helper that **merges** results from ``success_metrics`` &
  ``feedback_mechanism`` so that *all* KPIs mentioned in the theory prompt are
  accessible via a single command.

Example
-------
>>> from src.documentation_monitoring import SessionStore, PromptSessionEvent
>>> store = SessionStore()
>>> store.append(PromptSessionEvent(prompt="Explain binary search", model="gpt-3.5-turbo", prompt_tokens=21, completion_tokens=42))
>>> print(store.aggregate()["prompt_sessions"])
{"events": 1, "avg_total_tokens": 63, "avg_latency_ms": 0}
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from .logger import get_logger, setup_logging
from .success_metrics import MetricsStore
from .feedback_mechanism import FeedbackStore

__all__ = [
    "PromptSessionEvent",
    "DiffAppliedEvent",
    "SessionStore",
    "summary",
]

_log = get_logger(__name__)

_DEFAULT_FILE = Path(os.getenv("SESSION_LOG_FILE", ".prompt_sessions.jsonl"))
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _BaseEvent:
    """Common metadata & JSON serialisation plumage."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property
    def type(self) -> str:
        return self.__class__.__name__

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


@dataclass
class PromptSessionEvent(_BaseEvent):
    """Single prompt/completion interaction with an LLM provider.

    Parameters
    ----------
    prompt:
        Raw prompt *string* or *None*.  If redaction is enabled the prompt is
        replaced by a SHA-256 hash to avoid leaking sensitive user data.
    model:
        Model identifier e.g. ``gpt-4o``.
    provider:
        Provider name (``openai``, ``ollama`` …).  Can be *auto-filled* by
        caller.
    prompt_tokens / completion_tokens:
        Token counts as reported by the provider.  *Optional* because not all
        APIs expose token usage.
    latency_ms:
        Wall-clock latency in **milliseconds** as measured by the client.
    """

    prompt: Optional[str]
    model: str
    provider: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    # FEEDBACK: Consider adding cost metrics (USD) here.

    # -------------------
    # Post-init redaction
    # -------------------

    def __post_init__(self) -> None:  # noqa: D401
        if self.prompt is not None and len(self.prompt) > 2000:  # pragma: no cover
            # Prevent gigantic JSON lines – store hash instead.
            self.prompt = f"sha256:{hashlib.sha256(self.prompt.encode()).hexdigest()}"


@dataclass
class DiffAppliedEvent(_BaseEvent):
    """Metadata about a diff that was *applied* to the codebase.

    Parameters
    ----------
    diff_hash:
        SHA-256 of the diff content ‑ useful for de-duplication.
    files_modified:
        Number of files touched by the diff.
    chars_added / chars_removed:
        Totals derived from diff parsing – **not** LOC.
    applied_by:
        Human or automation actor who authorised the patch.
    success:
        Whether the patch was applied without merge/reject conflicts.
    """

    diff_hash: str
    files_modified: int
    chars_added: int
    chars_removed: int
    applied_by: str | None = None
    success: bool = True


# ---------------------------------------------------------------------------
# Store – append-only JSONL
# ---------------------------------------------------------------------------


class SessionStore:
    """Append-only storage for *_BaseEvent* descendants."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Session store initialised at %s", self.path)

    # -----------------
    # Public API
    # -----------------

    def append(self, event: _BaseEvent) -> None:
        """Serialise *event* to disk."""

        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_json() + "\n")
        _log.info("Recorded %s", event.type)

    def load_events(self) -> List[_BaseEvent]:
        """Return all events as dataclass instances."""

        if not self.path.exists():
            return []

        events: List[_BaseEvent] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                evt_type = data.pop("type", None)
                if evt_type == "PromptSessionEvent":
                    events.append(PromptSessionEvent(**data))
                elif evt_type == "DiffAppliedEvent":
                    events.append(DiffAppliedEvent(**data))
        return events

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    def aggregate(self) -> Dict[str, Any]:
        """Compute simple aggregates for stored events."""

        prompt_events: List[PromptSessionEvent] = []
        diff_events: List[DiffAppliedEvent] = []
        for e in self.load_events():
            if isinstance(e, PromptSessionEvent):
                prompt_events.append(e)
            elif isinstance(e, DiffAppliedEvent):
                diff_events.append(e)

        summary: Dict[str, Any] = {}

        # Prompt sessions
        if prompt_events:
            total_tokens = [
                (e.prompt_tokens or 0) + (e.completion_tokens or 0) for e in prompt_events
            ]
            avg_tokens = sum(total_tokens) / len(total_tokens) if total_tokens else 0
            avg_latency = (
                sum(e.latency_ms or 0 for e in prompt_events) / len(prompt_events)
            )
            summary["prompt_sessions"] = {
                "events": len(prompt_events),
                "avg_total_tokens": round(avg_tokens, 2),
                "avg_latency_ms": round(avg_latency, 2),
            }

        # Diff stats
        if diff_events:
            success_rate = (
                sum(1 for e in diff_events if e.success) / len(diff_events)
            )
            summary["diffs"] = {
                "events": len(diff_events),
                "success_rate": round(success_rate * 100, 1),
                "files_modified_total": sum(e.files_modified for e in diff_events),
            }

        return summary


# ---------------------------------------------------------------------------
# High-level KPI summary that *merges* other stores
# ---------------------------------------------------------------------------


def _combine_kpis() -> Dict[str, Any]:
    """Return a **single** dictionary combining all KPI sources."""

    sess_summary = SessionStore().aggregate()
    metrics_summary = MetricsStore().aggregate()
    feedback_summary = FeedbackStore().aggregate()

    combined = {
        **sess_summary,
        **metrics_summary,
    }

    # Subjective load captured via developer *satisfaction* scores.
    if "developer_surveys" in feedback_summary:
        combined["developer_load"] = feedback_summary["developer_surveys"]

    return combined


# ---------------------------------------------------------------------------
# Typer CLI – minimal surface for manual ops & CI pipelines
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Log prompt sessions & diff events and inspect KPI summary (step 2.7).")


# -----------------
# Prompt logging
# -----------------


@app.command()
def prompt(
    prompt: str = typer.Argument(..., help="Prompt string (will be SHA-256 hashed if >2k chars)"),
    model: str = typer.Option(..., "--model", "-m", help="Model identifier e.g. gpt-4o"),
    provider: str | None = typer.Option(None, "--provider", "-p", help="LLM provider name"),
    prompt_tokens: int | None = typer.Option(None, "--prompt-tokens", help="Prompt token count"),
    completion_tokens: int | None = typer.Option(None, "--completion-tokens", help="Completion token count"),
    latency_ms: float | None = typer.Option(None, "--latency-ms", help="End-to-end latency in ms"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *PromptSessionEvent*."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = SessionStore(store_path)
    store.append(
        PromptSessionEvent(
            prompt=prompt,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
    )


# -----------------
# Diff logging
# -----------------


@app.command()
def diff(
    diff_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to unified diff file"),
    applied_by: str | None = typer.Option(None, "--by", help="Actor applying the diff"),
    success: bool = typer.Option(True, "--success/--failure", help="Did patch apply cleanly?"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *DiffAppliedEvent* for *diff_file*."""

    setup_logging("DEBUG" if verbose else "INFO")
    diff_text = diff_file.read_text(encoding="utf-8")
    files_modified = diff_text.count("\n+++ ")
    chars_added = sum(len(ln) for ln in diff_text.splitlines() if ln.startswith("+"))
    chars_removed = sum(len(ln) for ln in diff_text.splitlines() if ln.startswith("-"))
    diff_hash = hashlib.sha256(diff_text.encode()).hexdigest()

    store = SessionStore(store_path)
    store.append(
        DiffAppliedEvent(
            diff_hash=diff_hash,
            files_modified=files_modified,
            chars_added=chars_added,
            chars_removed=chars_removed,
            applied_by=applied_by,
            success=success,
        )
    )


# -----------------
# KPI summary
# -----------------


@app.command()
def summary(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print combined KPI summary from *all* stores (sessions, metrics, feedback)."""

    setup_logging("DEBUG" if verbose else "INFO")
    combined = _combine_kpis()

    if json_output:
        json.dump(combined, typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        if not combined:
            typer.echo("No data recorded yet.")
            raise typer.Exit(code=1)
        # Render human friendly output
        if "prompt_sessions" in combined:
            ps = combined["prompt_sessions"]
            typer.echo(
                f"📝 Prompts: {ps['events']} sessions – avg {ps['avg_total_tokens']} tokens, "
                f"{ps['avg_latency_ms']} ms latency"
            )
        if "efficiency" in combined:
            eff = combined["efficiency"]
            typer.echo(
                f"⚡ Time-saved: {eff['average_time_saved']}s avg across {eff['events']} events (Σ {eff['total_time_saved']}s)"
            )
        if "accuracy" in combined:
            acc = combined["accuracy"]
            typer.echo(
                f"🎯 Diff accuracy: {acc['average_diff_accuracy']*100:.1f}% avg across {acc['events']} events"
            )
        if "developer_load" in combined:
            dl = combined["developer_load"]
            typer.echo(
                f"🙂 Dev satisfaction: {dl['average_satisfaction']}/10 avg across {dl['events']} surveys"
            )


# Allow "python -m src.documentation_monitoring …"
if __name__ == "__main__":
    app()