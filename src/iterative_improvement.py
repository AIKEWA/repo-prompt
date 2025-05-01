from __future__ import annotations

"""iterative_improvement.py – Step 4.9 Feedback & Iteration helpers 🌀

This *stand-alone* module plugs the remaining **Step 4.9** items into the
existing Repo-Prompt architecture without touching core files:

1. ✉️  *Anonymous energy reports* – Developers can **opt-in** to attach a
   coarse-grained overview of their recent *EnergyEvent*s whenever they submit
   qualitative feedback.  The helper aggregates the last *N* hours of energy
   usage and stores the snapshot in the common :class:`src.feedback_mechanism.FeedbackStore`.
2. 🛠️  *Model⇄Task suggestions* – Community members can propose *better* model
   choices for a given task.  The dataclass is persisted in the same JSON-Lines
   store so higher-level analytics can mine the suggestions.

The implementation intentionally refrains from *remote network calls*.  Should
an organisation wish to *send* the snapshots to a telemetry backend they can
hook into the public :func:`gather_energy_snapshot` helper and process the
returned payload accordingly.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Any

import typer

from .success_metrics import MetricsStore, EnergyEvent
from .feedback_mechanism import FeedbackStore, BaseFeedback
from .logger import get_logger, setup_logging

__all__ = [
    "EnergySnapshot",
    "ModelTaskSuggestion",
    "gather_energy_snapshot",
    "store_energy_snapshot",
    "improve_compact_model_capabilities",
    "compress_prompt",
    "schedule_based_on_usage",
    "app",
]

_log = get_logger(__name__)

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Dataclasses – stored in the *feedback* JSONL alongside other qualitative data
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class EnergySnapshot(BaseFeedback):
    """Aggregate view of recent :class:`src.success_metrics.EnergyEvent`s.

    Parameters
    ----------
    window_hours:
        Look-back window used for the aggregation.
    events:
        Number of :class:`EnergyEvent`s considered.
    total_kwh:
        Sum of *energy_kwh* across the window.
    local_pct:
        Percentage of events that executed *locally* (0-100).
    """

    window_hours: int
    events: int
    total_kwh: float
    local_pct: float


@dataclass(kw_only=True)
class ModelTaskSuggestion(BaseFeedback):
    """Community-driven proposal to use an *alternative* model for a task.

    Parameters
    ----------
    task:
        Short identifier of the activity (e.g. "code-generation", "unit-test")
    current_model:
        Model currently used for that task.
    suggested_model:
        Proposed *better* model – could be smaller/faster/cheaper.
    rationale:
        Optional free-form justification or empirical data.
    """

    task: str
    current_model: str
    suggested_model: str
    rationale: str | None = None


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _select_energy_events(store: MetricsStore, *, window_hours: int) -> List[EnergyEvent]:
    """Return *EnergyEvent*s within the last *window_hours*."""

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    events: List[EnergyEvent] = []
    for ev in store.load_events():
        if isinstance(ev, EnergyEvent):
            # `created_at` stored in ISO_FMT (UTC, trailing Z)
            ts = datetime.strptime(ev.created_at, ISO_FMT).replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                events.append(ev)
    return events


def gather_energy_snapshot(*, window_hours: int = 24, metrics_path: Path | str | None = None) -> EnergySnapshot:
    """Compute an :class:`EnergySnapshot` for the given look-back window."""

    mstore = MetricsStore(metrics_path) if metrics_path else MetricsStore()
    events = _select_energy_events(mstore, window_hours=window_hours)

    total_kwh = sum(ev.energy_kwh for ev in events)
    local_events = sum(1 for ev in events if ev.local_execution)
    local_pct: float = 0.0
    if events:
        local_pct = round(100 * local_events / len(events), 2)
    snapshot = EnergySnapshot(
        window_hours=window_hours,
        events=len(events),
        total_kwh=round(total_kwh, 6),
        local_pct=local_pct,
    )
    return snapshot


def store_energy_snapshot(snapshot: EnergySnapshot, *, feedback_path: Path | str | None = None) -> None:
    """Append *snapshot* to the std. feedback store (respects opt-in flag)."""

    store = FeedbackStore(feedback_path) if feedback_path else FeedbackStore()
    store.append(snapshot)


# ---------------------------------------------------------------------------
# Typer CLI – entry-point `python -m src.iterative_improvement …`
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Step 4.9 utilities – energy snapshots & model suggestions")


@app.command()
def energy(
    window_hours: int = typer.Option(24, "--hours", help="Aggregation window (look-back) in hours"),
    opt_in: bool = typer.Option(False, "--opt-in", help="Explicitly allow storage of the snapshot"),
    metrics_file: Path | None = typer.Option(None, "--metrics", help="Custom success_metrics JSONL file"),
    store_path: Path | None = typer.Option(None, "--store", help="Feedback JSONL path (default .feedback.jsonl)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate **and optionally persist** an *EnergySnapshot*.

    When *--opt-in* is **not** supplied, the snapshot is only **printed** to
    STDOUT.  This fulfils the *privacy-by-default* stance – data is captured
    locally and *shared* only with explicit consent.
    """

    setup_logging("DEBUG" if verbose else "INFO")

    snapshot = gather_energy_snapshot(window_hours=window_hours, metrics_path=metrics_file)

    if not opt_in:
        # Privacy-first – do not persist
        typer.echo(snapshot.to_json())
        _log.info("Energy snapshot generated (not persisted, opt-in flag missing)")
        raise typer.Exit()

    store_energy_snapshot(snapshot, feedback_path=store_path)
    typer.echo("✔ Energy snapshot stored in feedback log")


@app.command()
def suggest(
    task: str = typer.Argument(..., help="Task identifier (e.g. 'code-review')"),
    current_model: str = typer.Argument(..., help="Model currently in use"),
    suggested_model: str = typer.Argument(..., help="Proposed alternative model"),
    rationale: str | None = typer.Option(None, "--why", help="Optional justification"),
    store_path: Path | None = typer.Option(None, "--store", help="Feedback JSONL path (default .feedback.jsonl)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *ModelTaskSuggestion* in the feedback store."""

    setup_logging("DEBUG" if verbose else "INFO")
    suggestion = ModelTaskSuggestion(
        task=task,
        current_model=current_model,
        suggested_model=suggested_model,
        rationale=rationale,
    )
    store = FeedbackStore(store_path) if store_path else FeedbackStore()
    store.append(suggestion)
    typer.echo("✔ Suggestion recorded – thank you for contributing! 💡")


# ---------------------------------------------------------------------------
# Iteration Focus – placeholder helpers (Step 4.9 roadmap)  # REVIEW
# ---------------------------------------------------------------------------


def improve_compact_model_capabilities(model_name: str, *, dataset_path: Path | str, epochs: int = 1) -> None:  # noqa: D401
    """Fine-tune a *compact* model to enhance downstream task accuracy.

    This is a **placeholder** implementation – the real fine-tuning pipeline
    depends on the ML framework (🤗 Transformers, llama-cpp-python …).  We
    expose the function here so downstream scripts can *import* a canonical
    entry-point once the infra is ready.

    Parameters
    ----------
    model_name:
        Identifier of the compact base model to be fine-tuned.
    dataset_path:
        Path to the training dataset (JSONL / Parquet / arrow).
    epochs:
        Number of fine-tuning epochs.
    """

    _log.warning("improve_compact_model_capabilities() is not yet implemented – PRs welcome!")


def compress_prompt(prompt: str, *, strategy: str = "semantic") -> str:  # noqa: D401
    """Return a *compressed* version of *prompt* according to *strategy*.

    Strategies may include *semantic hashing*, *keyword extraction* or
    *token-level pruning*.  Currently a no-op placeholder.
    """

    _log.debug("compress_prompt(%s) called with strategy=%s", prompt[:30], strategy)
    # TODO: implement compression algo – see Step 4.9 spec
    return prompt  # unchanged for now


def schedule_based_on_usage(profile: dict[str, Any]) -> None:  # noqa: D401
    """Refine background task scheduling using real-world *profile* data.

    The *profile* dict may contain keys like ``active_hours``, ``heavy_tasks``
    frequency etc.  For now the function only logs the call so we can wire it
    up in integration tests.
    """

    _log.info("schedule_based_on_usage profile keys: %s", list(profile.keys()))
    # Actual scheduling delegation would probably call src.adaptive_scaling / carbon_scheduler

# Allow `python -m src.iterative_improvement …`
if __name__ == "__main__":  # pragma: no cover
    app()