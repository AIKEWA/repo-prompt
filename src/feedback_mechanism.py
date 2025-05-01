from __future__ import annotations

"""Feedback loop utilities for step 1.7 of the implementation roadmap.

This module collects and aggregates qualitative user feedback via
three channels:

1. Weekly developer surveys.
2. Git diff annotations authored by users (commit-level feedback).
3. Issue tracker suggestions (bug/feature requests).

The implementation mirrors :pymod:`src.success_metrics` in spirit but keeps
the concerns separate: *success_metrics* captures quantitative KPIs,
while *feedback_mechanism* focuses on qualitative insights.

Why JSON-Lines?
---------------
* Append-only and stream-friendly – safe for concurrent writes (CI).
* Diff-able in Git for auditability.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List
import re

import typer
from git import Repo, InvalidGitRepositoryError, NoSuchPathError  # type: ignore

from .logger import get_logger, setup_logging

__all__ = [
    "DeveloperSurvey",
    "DiffAnnotation",
    "IssueSuggestion",
    "UserControlFeedback",
    "WizardSurvey",
    "TooltipVote",
    "FeedbackStore",
    "EnergySnapshot",
    "ModelTaskSuggestion",
]

_log = get_logger(__name__)

_DEFAULT_FILE = Path(os.getenv("FEEDBACK_FILE", ".feedback.jsonl"))

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------------------
# Dataclasses – individual feedback types
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class BaseFeedback:
    """Base class adding ``created_at`` metadata and JSON serialisation."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property
    def type(self) -> str:
        return self.__class__.__name__

    # ---------------------------------------------------------------------
    # Serialisation helpers
    # ---------------------------------------------------------------------

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


@dataclass
class DeveloperSurvey(BaseFeedback):
    """Weekly developer sentiment survey.

    Parameters
    ----------
    week_start:
        The Monday ISO date (YYYY-MM-DD) representing the survey week.
    satisfaction:
        Numerical satisfaction score 0-10.
    comments:
        Optional free-form comments.
    """

    week_start: str
    satisfaction: int
    comments: str | None = None

    # -------------------
    # Validation
    # -------------------

    def __post_init__(self) -> None:  # noqa: D401 – imperative mood
        # Validate ISO date
        try:
            date.fromisoformat(self.week_start)
        except ValueError as exc:
            raise ValueError("week_start must be ISO date YYYY-MM-DD") from exc
        if not 0 <= self.satisfaction <= 10:
            raise ValueError("satisfaction must be between 0 and 10")


@dataclass
class DiffAnnotation(BaseFeedback):
    """Free-form comment attached to a Git diff.

    Parameters
    ----------
    commit_range:
        The diff spec e.g. 'HEAD~1..HEAD' or commit SHA.
    author:
        Name or identifier of the person leaving the annotation.
    comment:
        Review note, bug notice, suggestion etc.
    """

    commit_range: str
    author: str
    comment: str


@dataclass
class IssueSuggestion(BaseFeedback):
    """Bug report or feature suggestion captured from issue tracker.

    Parameters
    ----------
    issue_type:
        One of ``bug``, ``feature`` or ``other``.
    description:
        Textual description of the suggestion.
    reported_by:
        Optional reporter name or identifier.
    status:
        Optional status indicator – ``open``, ``acknowledged``, ``resolved`` …
    """

    issue_type: str  # "bug" | "feature" | "other"
    description: str
    reported_by: str | None = None
    status: str | None = None


# New user control qualitative feedback – Step 3.9


@dataclass
class UserControlFeedback(BaseFeedback):
    """Qualitative rating of *sense of control* and *navigation ease*.

    Added to support **3.9 Feedback Loops and Iterative Refinement** where we
    measure how users *feel* about their control over the application and how
    easy the consent & privacy controls are to navigate.

    Parameters
    ----------
    control_score:
        Numerical score 1-5 capturing perceived *sense of control* (Likert).
    navigation_score:
        Numerical score 1-5 for *ease of navigating data controls*.
    comments:
        Optional free-text elaboration or suggestions.
    """

    control_score: int  # 1-5 Likert scale
    navigation_score: int  # 1-5 Likert scale
    comments: str | None = None

    def __post_init__(self) -> None:  # noqa: D401 – imperative style
        for field_name, val in (
            ("control_score", self.control_score),
            ("navigation_score", self.navigation_score),
        ):
            if not 1 <= val <= 5:
                raise ValueError(f"{field_name} must be 1-5 Likert value")


# 5.8 Post-Wizard survey & tooltip micro-interaction feedback
# ---------------------------------------------------------------------------

@dataclass
class WizardSurvey(BaseFeedback):
    """Rating gathered *after* the onboarding wizard completes.

    Parameters
    ----------
    wizard_version:
        Semantic version or short hash identifying the wizard build.
    rating:
        1-5 Likert score answering "How helpful was the wizard?".
    comments:
        Optional free-form feedback.
    """

    wizard_version: str
    rating: int  # 1-5 Likert scale
    comments: str | None = None

    def __post_init__(self) -> None:  # noqa: D401 – immediate validation
        if not 1 <= self.rating <= 5:
            raise ValueError("rating must be 1-5 Likert value")
        # Very lax version pattern to not be overly strict in early phases
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.wizard_version):
            raise ValueError("wizard_version must be alphanum/hash style identifier")


@dataclass
class TooltipVote(BaseFeedback):
    """Binary *Was this helpful?* vote attached to a tooltip/popover.

    Parameters
    ----------
    tooltip_id:
        Stable identifier of the UI tooltip (e.g. ``"wizard_step_1_context"``).
    helpful:
        ``True`` when the user selected *Yes*; ``False`` for *No*.
    comments:
        Optional clarification why the tooltip was (not) helpful.
    """

    tooltip_id: str
    helpful: bool
    comments: str | None = None

    def __post_init__(self) -> None:  # noqa: D401 – validation
        if not self.tooltip_id or len(self.tooltip_id) > 100:
            raise ValueError("tooltip_id must be 1-100 chars")


# ---------------------------------------------------------------------------
# Step 4.9 – expose new event dataclasses for * import convenience
# ---------------------------------------------------------------------------

try:
    from .iterative_improvement import EnergySnapshot, ModelTaskSuggestion  # type: ignore
except (ModuleNotFoundError, ImportError):  # pragma: no cover – iterative module optional during bootstrap or circular
    # Provide dummies to avoid import errors; real classes imported lazily in _load_events
    EnergySnapshot = ModelTaskSuggestion = None  # type: ignore


# ---------------------------------------------------------------------------
# Persistence – append-only JSON-Lines store
# ---------------------------------------------------------------------------


class FeedbackStore:
    """Persistent storage & aggregation helper for qualitative feedback."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Feedback store initialised at %s", self.path)

    # -----------------
    # Public API
    # -----------------

    def append(self, feedback: BaseFeedback) -> None:
        """Append *feedback* to the JSON-Lines log."""

        line = feedback.to_json()
        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _log.info("Recorded %s", feedback.type)

    # ------------------------------------------------------------------
    # Loading & aggregation helpers
    # ------------------------------------------------------------------

    def _load_events(self) -> List[BaseFeedback]:
        if not self.path.exists():
            return []

        events: List[BaseFeedback] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                evt_type = data.pop("type", None)
                if evt_type == "DeveloperSurvey":
                    events.append(DeveloperSurvey(**data))
                elif evt_type == "DiffAnnotation":
                    events.append(DiffAnnotation(**data))
                elif evt_type == "IssueSuggestion":
                    events.append(IssueSuggestion(**data))
                elif evt_type == "UserControlFeedback":
                    events.append(UserControlFeedback(**data))
                elif evt_type == "EnergySnapshot":
                    events.append(EnergySnapshot(**data))
                elif evt_type == "ModelTaskSuggestion":
                    events.append(ModelTaskSuggestion(**data))
                # STEP 5.8 additions
                elif evt_type == "WizardSurvey":
                    events.append(WizardSurvey(**data))
                elif evt_type == "TooltipVote":
                    events.append(TooltipVote(**data))
        return events

    def aggregate(self) -> Dict[str, Any]:
        """Compute simple aggregate statistics for stored feedback."""

        surveys: List[DeveloperSurvey] = []
        diffs: List[DiffAnnotation] = []
        issues: List[IssueSuggestion] = []
        control_fb: List[UserControlFeedback] = []
        energy_snaps: List["EnergySnapshot"] = []  # type: ignore
        suggestions: List["ModelTaskSuggestion"] = []  # type: ignore
        wizard_surveys: List[WizardSurvey] = []
        tooltip_votes: List[TooltipVote] = []

        for ev in self._load_events():
            if isinstance(ev, DeveloperSurvey):
                surveys.append(ev)
            elif isinstance(ev, DiffAnnotation):
                diffs.append(ev)
            elif isinstance(ev, IssueSuggestion):
                issues.append(ev)
            elif isinstance(ev, UserControlFeedback):
                control_fb.append(ev)
            elif isinstance(ev, WizardSurvey):
                wizard_surveys.append(ev)
            elif isinstance(ev, TooltipVote):
                tooltip_votes.append(ev)
            else:
                # Lazy match new events by class name to avoid import cycles
                if ev.__class__.__name__ == "EnergySnapshot":
                    energy_snaps.append(ev)  # type: ignore
                elif ev.__class__.__name__ == "ModelTaskSuggestion":
                    suggestions.append(ev)  # type: ignore

        summary: Dict[str, Any] = {}

        if surveys:
            avg_sat = sum(s.satisfaction for s in surveys) / len(surveys)
            summary["developer_surveys"] = {
                "events": len(surveys),
                "average_satisfaction": round(avg_sat, 2),
            }
        if diffs:
            summary["diff_annotations"] = {
                "events": len(diffs),
            }
        if issues:
            open_or_ack = sum(
                1 for i in issues if i.status in (None, "open", "acknowledged")
            )
            summary["issue_suggestions"] = {
                "events": len(issues),
                "open_or_ack": open_or_ack,
            }

        if control_fb:
            avg_control = sum(f.control_score for f in control_fb) / len(control_fb)
            avg_nav = sum(f.navigation_score for f in control_fb) / len(control_fb)
            summary["user_control"] = {
                "events": len(control_fb),
                "average_control": round(avg_control, 2),
                "average_navigation": round(avg_nav, 2),
            }

        if energy_snaps:
            total_kwh = sum(es.total_kwh for es in energy_snaps)
            summary["energy_snapshots"] = {
                "events": len(energy_snaps),
                "total_kwh": round(total_kwh, 3),
            }

        if suggestions:
            summary["model_suggestions"] = {
                "events": len(suggestions),
            }

        # 5.8 aggregations
        if wizard_surveys:
            avg_rating = sum(ws.rating for ws in wizard_surveys) / len(wizard_surveys)
            summary["wizard_surveys"] = {
                "events": len(wizard_surveys),
                "average_rating": round(avg_rating, 2),
            }
        if tooltip_votes:
            helpful_total = sum(1 for tv in tooltip_votes if tv.helpful)
            summary["tooltip_votes"] = {
                "events": len(tooltip_votes),
                "helpful_pct": round(100 * helpful_total / len(tooltip_votes), 1),
            }

        return summary


# ---------------------------------------------------------------------------
# Typer CLI – lightweight wrapper for shell/CI usage
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Record and inspect qualitative feedback (step 1.7).")


@app.command()
def survey(
    week_start: str = typer.Argument(..., help="Week start YYYY-MM-DD (Monday ISO)"),
    satisfaction: int = typer.Argument(..., help="Satisfaction score 0-10"),
    comments: str | None = typer.Option(None, "--comments", "-c", help="Optional comments"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a weekly developer survey."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    store.append(
        DeveloperSurvey(week_start=week_start, satisfaction=satisfaction, comments=comments)
    )


@app.command()
def annotate_diff(
    commit_range: str = typer.Argument(..., help="Commit range or SHA"),
    author: str = typer.Argument(..., help="Reviewer name"),
    comment: str = typer.Argument(..., help="Annotation text"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Attach feedback to a Git diff."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    store.append(
        DiffAnnotation(commit_range=commit_range, author=author, comment=comment)
    )


@app.command()
def issue(
    issue_type: str = typer.Argument(..., help="bug|feature|other"),
    description: str = typer.Argument(..., help="Issue description"),
    reported_by: str | None = typer.Option(None, "--by", help="Reporter"),
    status: str | None = typer.Option("open", "--status", help="Issue status"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Log a bug or feature suggestion."""

    setup_logging("DEBUG" if verbose else "INFO")
    if issue_type not in {"bug", "feature", "other"}:
        raise typer.BadParameter("issue_type must be bug|feature|other")
    store = FeedbackStore(store_path)
    store.append(
        IssueSuggestion(
            issue_type=issue_type,
            description=description,
            reported_by=reported_by,
            status=status,
        )
    )


@app.command()
def control(
    control_score: int = typer.Argument(..., help="Sense of control rating 1-5"),
    navigation_score: int = typer.Argument(..., help="Data control navigation rating 1-5"),
    comments: str | None = typer.Option(None, "--comments", "-c", help="Optional comments"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record *UserControlFeedback* (Step 3.9 qualitative metric)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    store.append(
        UserControlFeedback(
            control_score=control_score,
            navigation_score=navigation_score,
            comments=comments,
        )
    )


@app.command()
def wizard(
    wizard_version: str = typer.Argument(..., help="Wizard build/version identifier"),
    rating: int = typer.Argument(..., help="Helpfulness rating 1-5"),
    comments: str | None = typer.Option(None, "--comments", "-c", help="Optional comments"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *post-wizard* helpfulness survey (Step 5.8)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    store.append(WizardSurvey(wizard_version=wizard_version, rating=rating, comments=comments))


@app.command()
def tooltip(
    tooltip_id: str = typer.Argument(..., help="Tooltip identifier"),
    helpful: bool = typer.Option(True, "--helpful/--not-helpful", help="Was the tooltip helpful?"),
    comments: str | None = typer.Option(None, "--comments", "-c", help="Optional comments"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a binary *Was this helpful?* vote for a tooltip (Step 5.8)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    store.append(TooltipVote(tooltip_id=tooltip_id, helpful=helpful, comments=comments))


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show aggregated feedback summary."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    agg = store.aggregate()

    if json_output:
        import json as _json, sys as _sys

        _json.dump(agg, _sys.stdout, indent=2)
        _sys.stdout.write("\n")
    else:
        if not agg:
            typer.echo("No feedback recorded yet.")
            raise typer.Exit(code=1)
        if "developer_surveys" in agg:
            ds = agg["developer_surveys"]
            typer.echo(
                f"📝 Surveys: {ds['events']} events, avg satisfaction {ds['average_satisfaction']}/10"
            )
        if "diff_annotations" in agg:
            da = agg["diff_annotations"]
            typer.echo(f"🗂️ Diff Annotations: {da['events']} comments")
        if "issue_suggestions" in agg:
            isg = agg["issue_suggestions"]
            typer.echo(
                f"🐞/💡 Issues: {isg['events']} total, {isg['open_or_ack']} open/ack"
            )


# ---------------------------------------------------------------------------
# Analysis / reports helpers (Option A & C)
# ---------------------------------------------------------------------------


def _weekly_export(store: "FeedbackStore") -> str:
    """Return a markdown report of the last ISO week worth of feedback."""

    from datetime import timedelta

    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday())  # current week Monday
    last_monday = monday - timedelta(days=7)

    surveys = [
        ev for ev in store._load_events()
        if isinstance(ev, DeveloperSurvey) and date.fromisoformat(ev.week_start) >= last_monday
    ]
    issues = [
        ev for ev in store._load_events()
        if isinstance(ev, IssueSuggestion) and datetime.fromisoformat(ev.created_at[:-1]).date() >= last_monday
    ]

    lines: List[str] = ["# Weekly Feedback Report", ""]
    lines.append(f"Period: {last_monday} ➜ {monday - timedelta(days=1)}")
    lines.append("")

    if surveys:
        avg_sat = sum(s.satisfaction for s in surveys) / len(surveys)
        lines.append(f"## Developer Satisfaction – avg {avg_sat:.2f}/10 from {len(surveys)} surveys")
        lines.append("")
    else:
        lines.append("No surveys recorded last week.")

    if issues:
        lines.append("## Reported improvement requests")
        for i, iss in enumerate(sorted(issues, key=lambda x: x.created_at)[:10], 1):
            lines.append(f"{i}. {iss.description} ({iss.issue_type}) – status: {iss.status or 'open'}")
    else:
        lines.append("No new improvement requests last week.")

    return "\n".join(lines)


def _build_heatmap(
    store: "FeedbackStore",
    repo_path: Path,
    top_n: int = 10,
    *,
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
) -> List[tuple[str, int]]:
    """Return list of ``(file_path, count)`` tuples for most commented files.

    Parameters
    ----------
    include_pattern
        Optional regular expression – only paths **matching** this pattern are
        counted.  Useful to limit the heat map to ``^src/`` or similar scopes.
    exclude_pattern
        Optional regular expression – paths **matching** this pattern are
        *ignored*.  Takes precedence over *include_pattern* when both match.
    """

    regex_incl = re.compile(include_pattern) if include_pattern else None
    regex_excl = re.compile(exclude_pattern) if exclude_pattern else None

    try:
        repo = Repo(str(repo_path))
        use_git = True
    except (InvalidGitRepositoryError, NoSuchPathError):
        # Fallback to non-Git mode – still produce heat map by heuristics
        use_git = False

    counts: Dict[str, int] = {}
    for ev in store._load_events():
        if not isinstance(ev, DiffAnnotation):
            continue

        file_candidates: List[str] = []

        if use_git:
            try:
                diff_output = repo.git.diff(ev.commit_range, name_only=True)
                file_candidates = diff_output.splitlines()
            except Exception:
                # ignore invalid ranges
                pass
        else:
            # heuristic: treat commit_range string as space-delimited file paths
            file_candidates = [p for p in ev.commit_range.split() if "/" in p or "." in p]

        for path in file_candidates:
            # Apply filters
            if regex_excl and regex_excl.search(path):
                continue
            if regex_incl and not regex_incl.search(path):
                continue

            counts[path] = counts.get(path, 0) + 1

    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:top_n]


# ---------------------------------------------------------------------------
# Additional CLI commands
# ---------------------------------------------------------------------------


@app.command()
def export(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file instead of stdout"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a weekly markdown report of feedback data (Option A)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    report_md = _weekly_export(store)

    if output:
        output.write_text(report_md, encoding="utf-8")
        typer.echo(f"Report written to {output}")
    else:
        typer.echo(report_md)


@app.command()
def heatmap(
    repo_path: Path = typer.Argument(".", exists=True, file_okay=False, help="Git repo for diff lookup"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL file"),
    top: int = typer.Option(10, "--top", help="Number of top files to show"),
    include_regex: str | None = typer.Option(
        None,
        "--include-regex",
        help="Only consider file paths matching this regex inside the heat map",
    ),
    exclude_regex: str | None = typer.Option(
        None,
        "--exclude-regex",
        help="Ignore file paths matching this regex inside the heat map",
    ),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a heat map of frequently annotated files (Option C)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)
    try:
        data = _build_heatmap(
            store,
            repo_path,
            top,
            include_pattern=include_regex,
            exclude_pattern=exclude_regex,
        )
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    if json_output:
        import json as _json, sys as _sys

        _json.dump(dict(data), _sys.stdout, indent=2)
        _sys.stdout.write("\n")
    else:
        if not data:
            typer.echo("No diff annotations found.")
            raise typer.Exit(code=1)
        typer.echo("# Diff Annotation Heat Map\n")
        for path, cnt in data:
            bar = "█" * min(cnt, 20)
            typer.echo(f"{path}: {cnt} {bar}")


# Allow "python -m src.feedback_mechanism …"
if __name__ == "__main__":
    app()