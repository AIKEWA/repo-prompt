from __future__ import annotations

"""human_agent_alignment.py – Step 7.3 Human–Agent Alignment Toolkit 🧭📏

This module operationalises **7.3 – Human–Agent Alignment Toolkit** from the
project specification.  It introduces:

* A **metadata schema** for alignment-oriented prompts covering the six core
  dimensions (*knowledge, autonomy, operations, reputation, ethics,
  engagement*).  The schema aligns with the YAML example from the spec.
* A lightweight **feedback store** that records *alignment ratings* so that
  users can score how well model outputs matched their expectations.
* A *pilot-test helper* that measures the shift in **developer satisfaction**
  before and after alignment-aware prompts are introduced (re-using the
  existing :pymod:`src.feedback_mechanism` survey events).
* A small **Typer CLI** so that non-Python stakeholders can:
  * generate YAML stubs for new alignment metadata (`meta` command),
  * record alignment ratings interactively (`rate` command),
  * inspect basic statistics (`stats` command), and
  * run the pilot test (`pilot` command).

The module is *pure Python* and relies solely on standard-library modules
plus the already-present third-party dependency :pypi:`typer`.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import json

import typer

from .feedback_mechanism import (
    ISO_FMT,
    BaseFeedback,
    DeveloperSurvey,
    FeedbackStore,
)
from .logger import get_logger, setup_logging

__all__ = [
    "AlignmentMetadata",
    "AlignmentRating",
    "AlignmentFeedbackStore",
    "compute_satisfaction_shift",
    "app",
]

_log = get_logger(__name__)

###############################################################################
# 1. Metadata schema                                                          #
###############################################################################


@dataclass
class AlignmentMetadata:  # noqa: D101 – simple value holder
    """Metadata block attached to an **alignment-aware prompt**.

    Mirrors the YAML example provided in the specification.
    """

    id: str
    intent: str
    ethics_guardrails: str
    autonomy: str
    compliance_tag: str

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return asdict(self)

    def to_json(self, *, indent: int | None = 2) -> str:  # noqa: D401 – imperative
        """Return *pretty* JSON representation."""

        return json.dumps(self.as_dict(), indent=indent, ensure_ascii=False) + "\n"

    def to_yaml(self) -> str:  # noqa: D401 – imperative tone ok
        """Return a minimal YAML representation.

        We replicate the *hand-rolled* emitter style from
        :pymod:`src.prompt_ops_framework` to avoid extra dependencies.
        """

        lines: List[str] = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in self.as_dict().items()]
        return "\n".join(lines) + "\n"

###############################################################################
# 2. Alignment rating events                                                  #
###############################################################################


@dataclass
class AlignmentRating(BaseFeedback):  # noqa: D101 – value object
    """User rating of *how aligned* an LLM response felt.

    Parameters
    ----------
    prompt_id:
        Identifier of the prompt template that produced the answer being rated.
    score:
        Likert-style rating (1-5) where **5 == perfectly aligned**.
    comments:
        Optional free-form clarification.
    """

    prompt_id: str
    score: int  # 1-5 Likert scale
    comments: str | None = None

    def __post_init__(self) -> None:  # noqa: D401 – immediate validation
        if not 1 <= self.score <= 5:
            raise ValueError("score must be 1-5 Likert value")

###############################################################################
# 3. Persistence helper                                                       #
###############################################################################


class AlignmentFeedbackStore:
    """Append-only JSON-Lines store for :class:`AlignmentRating` events."""

    _DEFAULT_FILE = Path(".alignment_feedback.jsonl")

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:  # noqa: D401
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Alignment feedback store at %s", self.path)

    # -----------------------------
    # Public API
    # -----------------------------

    def append(self, rating: AlignmentRating) -> None:  # noqa: D401 – imperative
        """Persist *rating* as a single JSON-Line."""

        line = rating.to_json()
        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _log.info("Recorded alignment rating for %s", rating.prompt_id)

    def _load_events(self) -> List[AlignmentRating]:  # noqa: D401
        """Return *all* events from the backing file."""

        if not self.path.exists():
            return []

        events: List[AlignmentRating] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                # Filter out the automatically injected "type" key to avoid
                # double initialisation issues when re-creating dataclass.
                data.pop("type", None)
                events.append(AlignmentRating(**data))
        return events

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    def aggregate(self) -> Dict[str, Any]:  # noqa: D401
        """Return simple aggregate statistics (count & average)."""

        evs = self._load_events()
        if not evs:
            return {"events": 0}

        avg = sum(ev.score for ev in evs) / len(evs)
        return {
            "events": len(evs),
            "average_score": round(avg, 2),
        }

###############################################################################
# 4. Pilot-test helper                                                        #
###############################################################################


def compute_satisfaction_shift(
    feedback_store_path: Path = Path(".feedback.jsonl"),
    alignment_store_path: Path = Path(".alignment_feedback.jsonl"),
) -> Dict[str, Any]:  # noqa: D401 – imperative tone ok
    """Compute the Δ in dev satisfaction before vs *after* alignment adoption.

    The first recorded :class:`AlignmentRating` timestamp is used as the
    **cut-off point**.  All :class:`src.feedback_mechanism.DeveloperSurvey`
    events dated *strictly before* this moment form the *baseline*; those on
    or after become the *post-alignment* bucket.
    """

    fb_store = FeedbackStore(feedback_store_path)
    align_store = AlignmentFeedbackStore(alignment_store_path)

    align_events = align_store._load_events()
    if not align_events:
        raise RuntimeError("No alignment ratings found – cannot compute shift")

    # Earliest alignment rating marks adoption moment
    first_align_dt = min(datetime.strptime(ev.created_at, ISO_FMT) for ev in align_events)

    # Collect developer survey events
    surveys: List[DeveloperSurvey] = [
        ev for ev in fb_store._load_events() if isinstance(ev, DeveloperSurvey)
    ]

    before = [s for s in surveys if datetime.strptime(s.created_at, ISO_FMT) < first_align_dt]
    after = [s for s in surveys if datetime.strptime(s.created_at, ISO_FMT) >= first_align_dt]

    def _avg(seq: List[DeveloperSurvey] | None) -> float | None:  # noqa: D401
        if not seq:
            return None
        return sum(s.satisfaction for s in seq) / len(seq)

    result: Dict[str, Any] = {
        "baseline_surveys": len(before),
        "post_alignment_surveys": len(after),
        "baseline_avg": round(_avg(before), 2) if before else None,
        "post_alignment_avg": round(_avg(after), 2) if after else None,
    }

    if result["baseline_avg"] is not None and result["post_alignment_avg"] is not None:
        result["delta"] = round(result["post_alignment_avg"] - result["baseline_avg"], 2)

    return result

###############################################################################
# 5. Typer CLI                                                                #
###############################################################################


app = typer.Typer(add_completion=False, help="Human–Agent Alignment Toolkit (step 7.3)")


@app.command()
def meta(
    id: str = typer.Argument(..., help="Unique metadata identifier"),
    intent: str = typer.Option(..., "--intent", "-i", help="Prompt intent"),
    ethics_guardrails: str = typer.Option(..., "--ethics", "-e", help="Ethics guardrails statement"),
    autonomy: str = typer.Option(..., "--autonomy", "-a", help="Autonomy constraints for the agent"),
    compliance_tag: str = typer.Option("versioned, reviewed", "--tag", "-t", help="Compliance tag(s)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write YAML to file instead of stdout"),
):
    """Generate a YAML metadata stub for an alignment-aware prompt."""

    md = AlignmentMetadata(
        id=id,
        intent=intent,
        ethics_guardrails=ethics_guardrails,
        autonomy=autonomy,
        compliance_tag=compliance_tag,
    )
    yaml_text = md.to_yaml()

    if output:
        output.write_text(yaml_text, encoding="utf-8")
        _log.info("Metadata written to %s", output)
    else:
        typer.echo(yaml_text)


@app.command()
def rate(
    prompt_id: str = typer.Argument(..., help="Prompt identifier being rated"),
    score: int = typer.Option(..., "--score", "-s", help="Alignment score 1-5"),
    comments: str | None = typer.Option(None, "--comments", "-c", help="Optional free-form comments"),
    store_path: Path = typer.Option(AlignmentFeedbackStore._DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs"),
):
    """Record an alignment rating event (1-5 Likert scale)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = AlignmentFeedbackStore(store_path)
    store.append(AlignmentRating(prompt_id=prompt_id, score=score, comments=comments))


@app.command()
def stats(
    store_path: Path = typer.Option(AlignmentFeedbackStore._DEFAULT_FILE, "--store", help="JSONL store path"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """Display aggregate statistics for alignment ratings."""

    agg = AlignmentFeedbackStore(store_path).aggregate()
    if json_output:
        typer.echo(json.dumps(agg))
    else:
        typer.echo(
            f"🧭 Alignment ratings: {agg.get('events', 0)} events, "
            f"avg score {agg.get('average_score', 'N/A')} / 5"
        )


@app.command()
def pilot(
    feedback_store: Path = typer.Option(Path(".feedback.jsonl"), "--feedback-store", help="Qualitative feedback JSONL"),
    alignment_store: Path = typer.Option(AlignmentFeedbackStore._DEFAULT_FILE, "--alignment-store", help="Alignment JSONL"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """Measure developer-satisfaction Δ before/after alignment adoption."""

    res = compute_satisfaction_shift(feedback_store, alignment_store)
    if json_output:
        typer.echo(json.dumps(res))
    else:
        typer.echo("📊 Pilot Test Results")
        typer.echo(
            f"Baseline satisfaction ({res['baseline_surveys']} surveys): {res['baseline_avg']}"
        )
        typer.echo(
            f"Post-alignment ({res['post_alignment_surveys']} surveys): {res['post_alignment_avg']}"
        )
        if "delta" in res:
            typer.echo(f"Δ satisfaction: {res['delta']}")


# ---------------------------------------------------------------------------
# Entry point                                                                 #
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover – manual execution helper
    app()