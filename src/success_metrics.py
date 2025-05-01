from __future__ import annotations

"""Success metrics collection utilities.

This module operationalises *Step 1.6 Success Criteria* from the theory→code
specification.

It offers:

1. **Event dataclasses** mirroring the three KPIs – *Efficiency*, *Accuracy*,
   *Adoption*.
2. A lightweight **JSON-Lines store** for append-only metric logging that works
   in both local and CI environments.
3. Simple **aggregation helpers** producing a summary dictionary ready for
   dashboards or CLI inspection.
4. A **Typer CLI** – "`python -m src.success_metrics …`" – for ad-hoc recording
   and reporting without extra scripts.

The implementation purposefully avoids heavy analytics frameworks to keep the
core package dependency-free beyond the existing project stack (``Typer`` &
``rich`` are already included).

Usage example
-------------
>>> from src.success_metrics import MetricsStore, EfficiencyEvent
>>> store = MetricsStore()  # uses ./.success_metrics.jsonl by default
>>> store.append_event(EfficiencyEvent(baseline_time=120, improved_time=80))
>>> print(store.aggregate())
{"efficiency": {"events": 1, "total_time_saved": 40.0, "average_time_saved": 40.0}, ...}
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import typer

from .logger import get_logger, setup_logging
from src.cli_docs import generate_docs, write_docs_file

__all__ = [
    "EfficiencyEvent",
    "AccuracyEvent",
    "AdoptionEvent",
    "EnergyEvent",
    "LocalOperationEvent",
    "OverrideEvent",
    "ConsentReaffirmationEvent",
    "AuditReadinessEvent",
    "SustainabilityAwarenessEvent",
    "EmissionSavingEvent",
    "FirstSessionCompletionEvent",
    "TimeToFirstCommitEvent",
    "RetentionWeekOneEvent",
    "FeatureAdoptionEvent",
    "NpsEvent",
    "SignupEvent",
    "UpgradeEvent",
    "SmeTeamAdoptionEvent",
    "PlatformDiversityEvent",
    "MetricsStore",
]

_log = get_logger(__name__)

_DEFAULT_STORE_PATH = Path(os.getenv("SUCCESS_METRICS_FILE", ".success_metrics.jsonl"))

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------


# Allow default field even when subclasses add required params
@dataclass(kw_only=True)
class BaseEvent:  # noqa: D101 – self-documenting via subclasses
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property
    def type(self) -> str:
        return self.__class__.__name__

    def to_json(self) -> str:
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


@dataclass
class EfficiencyEvent(BaseEvent):
    """Represents an *Efficiency* measurement.

    Parameters
    ----------
    baseline_time:
        Time in **seconds** required for the baseline process
        (e.g. manual code review).
    improved_time:
        Time in **seconds** using the LLM-assisted workflow.
    """

    baseline_time: float
    improved_time: float

    @property
    def time_saved(self) -> float:
        return max(self.baseline_time - self.improved_time, 0.0)


@dataclass
class AccuracyEvent(BaseEvent):
    """Represents an *Accuracy* measurement.

    Parameters
    ----------
    diff_accuracy:
        Quality score of LLM-generated diff, typically ranging 0-1.
    """

    diff_accuracy: float


@dataclass
class AdoptionEvent(BaseEvent):
    """Represents an *Adoption* measurement.

    Parameters
    ----------
    feedback:
        Free-form text or categorical label capturing developer feedback.
    successful_onboarding:
        Optional flag indicating whether onboarding was successful.
    """

    feedback: str
    successful_onboarding: bool | None = None


# ---------------------------------------------------------------------------
# Green computing KPI – energy impact
# ---------------------------------------------------------------------------


@dataclass
class EnergyEvent(BaseEvent):
    """Capture the *approximate* ecological footprint of an LLM operation.

    The values **do not** aim for scientific precision but provide a *relative
    indicator* to compare different optimisation strategies; they are good
    enough to surface regressions and guide local-first improvements.

    Parameters
    ----------
    tokens:
        Total number of prompt **and** response tokens.
    energy_kwh:
        Rough energy consumption in *kilowatt-hours* attributed to the
        operation.  Defaults to ``tokens * 1e-7`` for *local inference* and
        ``tokens * 5e-7`` for *remote/cloud* calls – see
        :pymod:`src.offline_awareness` for the heuristics.
    local_execution:
        ``True`` when inference happened exclusively on the developer machine
        (e.g. via *Ollama*); ``False`` when cloud compute was involved.
    """

    tokens: int
    energy_kwh: float
    local_execution: bool


# ---------------------------------------------------------------------------
# Step 3.8 – New KPI event dataclasses
# ---------------------------------------------------------------------------


@dataclass
class LocalOperationEvent(BaseEvent):
    """Record whether an operation executed entirely locally.

    This metric supports the *Local-only operation success rate* KPI
    (target **>90%**).

    Parameters
    ----------
    local_operation_success:
        ``True`` when no remote service was contacted; ``False`` otherwise.
    """

    local_operation_success: bool


@dataclass
class OverrideEvent(BaseEvent):
    """Capture whether the user **overrode** an AI suggestion.

    KPI reference: *User override of AI suggestions* (target **≥20%** HITL
    activity).  Each suggestion should emit one :class:`OverrideEvent` with
    the *override* flag set accordingly so a ratio can be calculated.
    """

    override: bool


@dataclass
class ConsentReaffirmationEvent(BaseEvent):
    """Track consent reaffirmation occurrences.

    KPI reference: *Consent reaffirmation events* – at least one per *feature
    tier*.  The *feature_tier* attribute allows granular aggregation.
    """

    feature_tier: str


@dataclass
class AuditReadinessEvent(BaseEvent):
    """Record outcome of a cross-jurisdiction audit.

    KPI reference: *Cross-jurisdiction audit readiness* (target **100% pass
    rate**).
    """

    passed: bool


@dataclass
class SustainabilityAwarenessEvent(BaseEvent):
    """Record feedback about sustainability awareness.

    A user is considered *aware* when they explicitly report that the tooling
    helped them realise energy / ecological implications (e.g. via an in-app
    prompt).  A boolean flag keeps the data model simple and allows us to
    aggregate the *percentage of users reporting increased consciousness* – the
    target KPI is **≥80%**.

    Parameters
    ----------
    aware:
        ``True`` if the user reported increased awareness; ``False`` otherwise.
    comment:
        Optional free-form text with additional feedback.
    """

    aware: bool
    comment: str | None = None


@dataclass
class EmissionSavingEvent(BaseEvent):
    """Capture the *percentage emission savings* achieved by running locally.

    Each task that can be executed on the developer machine instead of the
    cloud emits one :class:`EmissionSavingEvent` so we can calculate the *mean
    saving per user, per month* – KPI target **≥50%**.

    Parameters
    ----------
    saving_pct:
        Percentage emission saving compared to the cloud baseline (0-100).
    """

    saving_pct: float


# ---------------------------------------------------------------------------
# Step 5.7 – Additional KPI event dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FirstSessionCompletionEvent(BaseEvent):
    """Record whether the onboarding *wizard* was completed.

    KPI reference: *First session completion* – target **≥80%**.
    """

    completed: bool


@dataclass
class TimeToFirstCommitEvent(BaseEvent):
    """Duration (in seconds) from installation to first Git commit.

    KPI reference: *Time-to-first-commit* – target **<10 min** (600 s).
    """

    duration_seconds: float

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60


@dataclass
class RetentionWeekOneEvent(BaseEvent):
    """Record whether a user is still active one week after onboarding.

    KPI reference: *Retention after 1 week* – target **≥65%**.
    """

    retained: bool


@dataclass
class FeatureAdoptionEvent(BaseEvent):
    """Capture opt-in *advanced UX tool* adoption.

    KPI reference: *Feature adoption rate* – target **≥50%**.
    """

    adopted: bool


@dataclass
class NpsEvent(BaseEvent):
    """Net Promoter Score entry (0-10).

    A *promoter* is a score of 9-10, *passive* 7-8, *detractor* 0-6.  The
    aggregate NPS is **(*promoters* − *detractors*) / total × 100** and the
    target is **≥45**.
    """

    score: int


# ---------------------------------------------------------------------------
# Step 6.6 – New KPI events (education & growth KPIs)
# ---------------------------------------------------------------------------


@dataclass
class SignupEvent(BaseEvent):
    """Record creation of a *new account*.

    Parameters
    ----------
    is_edu:
        ``True`` if the account uses an educational domain/email and counts
        towards the *EDU sign-up rate* KPI (target ≥15% of all new accounts).
    """

    is_edu: bool


@dataclass
class UpgradeEvent(BaseEvent):
    """Capture a *Free → Paid* upgrade event.

    Parameters
    ----------
    within_30_days:
        ``True`` when the upgrade happened within the first 30 days after
        sign-up. Used to track the KPI *Free → Paid upgrade rate*
        (target ≥10% within 30 days).
    """

    within_30_days: bool


@dataclass
class SmeTeamAdoptionEvent(BaseEvent):
    """Record *SME team* adoption.

    Parameters
    ----------
    seats:
        Number of seats the team subscribed to (3–10 marks an SME team).  The
        KPI goal is *50 teams in 90 days*; each event represents **one** team
        adoption.
    """

    seats: int


@dataclass
class PlatformDiversityEvent(BaseEvent):
    """Track usage across operating systems.

    Parameters
    ----------
    os_name:
        Normalised operating system label (e.g. ``"macOS"``, ``"Windows"``,
        ``"Linux"``).  The KPI *Platform diversity* expects ≥20% non-macOS
        usage six months post-launch.
    """

    os_name: str


# ---------------------------------------------------------------------------
# Metrics store – append-only JSONL file
# ---------------------------------------------------------------------------


class MetricsStore:
    """Persistent storage & aggregation helper for success metrics."""

    def __init__(self, path: str | Path = _DEFAULT_STORE_PATH) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Metrics store initialised at %s", self.path)

    # -----------------
    # Public methods
    # -----------------

    def append_event(self, event: BaseEvent) -> None:
        """Append *event* to the JSON-Lines log."""

        line = event.to_json()
        # Touch the file first to avoid FileNotFoundError on some platforms
        if not self.path.exists():
            self.path.touch()

        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _log.info("Recorded %s", event.type)

    def load_events(self) -> List[BaseEvent]:
        """Return all events from disk as dataclass instances."""

        if not self.path.exists():
            return []

        events: List[BaseEvent] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                evt_type = data.pop("type", None)
                if evt_type == "EfficiencyEvent":
                    events.append(EfficiencyEvent(**data))
                elif evt_type == "AccuracyEvent":
                    events.append(AccuracyEvent(**data))
                elif evt_type == "AdoptionEvent":
                    events.append(AdoptionEvent(**data))
                elif evt_type == "EnergyEvent":
                    events.append(EnergyEvent(**data))
                elif evt_type == "LocalOperationEvent":
                    events.append(LocalOperationEvent(**data))
                elif evt_type == "OverrideEvent":
                    events.append(OverrideEvent(**data))
                elif evt_type == "ConsentReaffirmationEvent":
                    events.append(ConsentReaffirmationEvent(**data))
                elif evt_type == "AuditReadinessEvent":
                    events.append(AuditReadinessEvent(**data))
                elif evt_type == "SustainabilityAwarenessEvent":
                    events.append(SustainabilityAwarenessEvent(**data))
                elif evt_type == "EmissionSavingEvent":
                    events.append(EmissionSavingEvent(**data))
                elif evt_type == "FirstSessionCompletionEvent":
                    events.append(FirstSessionCompletionEvent(**data))
                elif evt_type == "TimeToFirstCommitEvent":
                    events.append(TimeToFirstCommitEvent(**data))
                elif evt_type == "RetentionWeekOneEvent":
                    events.append(RetentionWeekOneEvent(**data))
                elif evt_type == "FeatureAdoptionEvent":
                    events.append(FeatureAdoptionEvent(**data))
                elif evt_type == "NpsEvent":
                    events.append(NpsEvent(**data))
                elif evt_type == "SignupEvent":
                    events.append(SignupEvent(**data))
                elif evt_type == "UpgradeEvent":
                    events.append(UpgradeEvent(**data))
                elif evt_type == "SmeTeamAdoptionEvent":
                    events.append(SmeTeamAdoptionEvent(**data))
                elif evt_type == "PlatformDiversityEvent":
                    events.append(PlatformDiversityEvent(**data))
        return events

    def aggregate(self) -> Dict[str, Any]:
        """Compute aggregate statistics for each metric category."""

        eff_events: List[EfficiencyEvent] = []
        acc_events: List[AccuracyEvent] = []
        adp_events: List[AdoptionEvent] = []
        energy_events: List[EnergyEvent] = []
        loc_events: List[LocalOperationEvent] = []
        ov_events: List[OverrideEvent] = []
        con_events: List[ConsentReaffirmationEvent] = []
        aud_events: List[AuditReadinessEvent] = []
        sus_events: List[SustainabilityAwarenessEvent] = []
        emi_events: List[EmissionSavingEvent] = []
        fs_events: List[FirstSessionCompletionEvent] = []
        ttfc_events: List[TimeToFirstCommitEvent] = []
        ret_events: List[RetentionWeekOneEvent] = []
        fad_events: List[FeatureAdoptionEvent] = []
        nps_events: List[NpsEvent] = []
        signup_events: List[SignupEvent] = []
        upgrade_events: List[UpgradeEvent] = []
        sme_events: List[SmeTeamAdoptionEvent] = []
        platform_events: List[PlatformDiversityEvent] = []
        for e in self.load_events():
            if isinstance(e, EfficiencyEvent):
                eff_events.append(e)
            elif isinstance(e, AccuracyEvent):
                acc_events.append(e)
            elif isinstance(e, AdoptionEvent):
                adp_events.append(e)
            elif isinstance(e, EnergyEvent):
                energy_events.append(e)
            elif isinstance(e, LocalOperationEvent):
                loc_events.append(e)
            elif isinstance(e, OverrideEvent):
                ov_events.append(e)
            elif isinstance(e, ConsentReaffirmationEvent):
                con_events.append(e)
            elif isinstance(e, AuditReadinessEvent):
                aud_events.append(e)
            elif isinstance(e, SustainabilityAwarenessEvent):
                sus_events.append(e)
            elif isinstance(e, EmissionSavingEvent):
                emi_events.append(e)
            elif isinstance(e, FirstSessionCompletionEvent):
                fs_events.append(e)
            elif isinstance(e, TimeToFirstCommitEvent):
                ttfc_events.append(e)
            elif isinstance(e, RetentionWeekOneEvent):
                ret_events.append(e)
            elif isinstance(e, FeatureAdoptionEvent):
                fad_events.append(e)
            elif isinstance(e, NpsEvent):
                nps_events.append(e)
            elif isinstance(e, SignupEvent):
                signup_events.append(e)
            elif isinstance(e, UpgradeEvent):
                upgrade_events.append(e)
            elif isinstance(e, SmeTeamAdoptionEvent):
                sme_events.append(e)
            elif isinstance(e, PlatformDiversityEvent):
                platform_events.append(e)

        summary: Dict[str, Any] = {}

        # Efficiency aggregation
        if eff_events:
            total_saved = sum(e.time_saved for e in eff_events)
            avg_saved = total_saved / len(eff_events)
            summary["efficiency"] = {
                "events": len(eff_events),
                "total_time_saved": round(total_saved, 2),
                "average_time_saved": round(avg_saved, 2),
            }

        # Accuracy aggregation
        if acc_events:
            avg_acc = sum(e.diff_accuracy for e in acc_events) / len(acc_events)
            summary["accuracy"] = {
                "events": len(acc_events),
                "average_diff_accuracy": round(avg_acc, 4),
            }

        # Adoption aggregation
        if adp_events:
            successes = sum(1 for e in adp_events if e.successful_onboarding)
            summary["adoption"] = {
                "events": len(adp_events),
                "successful_onboardings": successes,
            }

        # Energy / ecological footprint aggregation
        if energy_events:
            total_tokens = sum(e.tokens for e in energy_events)
            total_kwh = sum(e.energy_kwh for e in energy_events)
            avg_kwh = total_kwh / len(energy_events)
            local_ops = sum(1 for e in energy_events if e.local_execution)
            summary["energy_footprint"] = {
                "events": len(energy_events),
                "total_tokens": total_tokens,
                "total_kwh": round(total_kwh, 6),
                "average_kwh": round(avg_kwh, 6),
                "local_execution_ratio": round(local_ops / len(energy_events) * 100, 2),
            }

        # Local-only operation KPI
        if loc_events:
            local_successes = sum(1 for e in loc_events if e.local_operation_success)
            success_rate = local_successes / len(loc_events) * 100
            summary["local_only_operation"] = {
                "events": len(loc_events),
                "local_successes": local_successes,
                "success_rate_pct": round(success_rate, 2),
            }

        # Override KPI – human-in-the-loop activity
        if ov_events:
            overrides = sum(1 for e in ov_events if e.override)
            override_rate = overrides / len(ov_events) * 100
            summary["override_activity"] = {
                "events": len(ov_events),
                "overrides": overrides,
                "override_rate_pct": round(override_rate, 2),
            }

        # Consent reaffirmation counts per tier
        if con_events:
            tier_counts: Dict[str, int] = {}
            for e in con_events:
                tier_counts[e.feature_tier] = tier_counts.get(e.feature_tier, 0) + 1
            summary["consent_reaffirmation"] = tier_counts

        # Audit readiness KPI
        if aud_events:
            passes = sum(1 for e in aud_events if e.passed)
            pass_rate = passes / len(aud_events) * 100
            summary["audit_readiness"] = {
                "events": len(aud_events),
                "passes": passes,
                "pass_rate_pct": round(pass_rate, 2),
            }

        # Sustainability awareness KPI
        if sus_events:
            aware = sum(1 for e in sus_events if e.aware)
            summary["sustainability_awareness"] = {
                "events": len(sus_events),
                "aware_count": aware,
                "aware_rate_pct": round(aware / len(sus_events) * 100, 2),
            }

        # Emission savings KPI
        if emi_events:
            avg_saving = sum(e.saving_pct for e in emi_events) / len(emi_events)
            summary["emission_savings"] = {
                "events": len(emi_events),
                "average_saving_pct": round(avg_saving, 2),
            }

        # First session completion KPI
        if fs_events:
            completions = sum(1 for e in fs_events if e.completed)
            summary["first_session_completion"] = {
                "events": len(fs_events),
                "completions": completions,
                "completion_rate_pct": round(completions / len(fs_events) * 100, 2),
            }

        # Time-to-first-commit KPI
        if ttfc_events:
            avg_seconds = sum(e.duration_seconds for e in ttfc_events) / len(ttfc_events)
            summary["time_to_first_commit"] = {
                "events": len(ttfc_events),
                "average_seconds": round(avg_seconds, 1),
                "average_minutes": round(avg_seconds / 60, 2),
            }

        # Retention after week one KPI
        if ret_events:
            retained = sum(1 for e in ret_events if e.retained)
            summary["retention_week_one"] = {
                "events": len(ret_events),
                "retained": retained,
                "retention_rate_pct": round(retained / len(ret_events) * 100, 2),
            }

        # Feature adoption KPI
        if fad_events:
            adopted = sum(1 for e in fad_events if e.adopted)
            summary["feature_adoption"] = {
                "events": len(fad_events),
                "adopted": adopted,
                "adoption_rate_pct": round(adopted / len(fad_events) * 100, 2),
            }

        # Net Promoter Score KPI
        if nps_events:
            promoters = sum(1 for e in nps_events if e.score >= 9)
            detractors = sum(1 for e in nps_events if e.score <= 6)
            nps = (promoters - detractors) / len(nps_events) * 100
            avg_score = sum(e.score for e in nps_events) / len(nps_events)
            summary["nps"] = {
                "events": len(nps_events),
                "average_score": round(avg_score, 2),
                "nps": round(nps, 2),
            }

        # Signup KPI – EDU sign-up rate
        if signup_events:
            edu_signups = sum(1 for e in signup_events if e.is_edu)
            edu_rate = edu_signups / len(signup_events) * 100
            summary["signup"] = {
                "events": len(signup_events),
                "edu_signups": edu_signups,
                "edu_rate_pct": round(edu_rate, 2),
            }

        # Upgrade KPI – free→paid within 30 days
        if upgrade_events:
            within_30 = sum(1 for e in upgrade_events if e.within_30_days)
            upgrade_rate = within_30 / len(upgrade_events) * 100
            summary["upgrade"] = {
                "events": len(upgrade_events),
                "within_30_days": within_30,
                "upgrade_rate_pct": round(upgrade_rate, 2),
            }

        # SME team adoption KPI
        if sme_events:
            teams = len(sme_events)
            total_seats = sum(e.seats for e in sme_events)
            avg_seats = total_seats / teams
            summary["sme_team_adoption"] = {
                "teams": teams,
                "total_seats": total_seats,
                "average_seats_per_team": round(avg_seats, 2),
            }

        # Platform diversity KPI
        if platform_events:
            non_macos = sum(1 for e in platform_events if e.os_name.lower() != "macos")
            diversity_rate = non_macos / len(platform_events) * 100
            summary["platform_diversity"] = {
                "events": len(platform_events),
                "non_macos_users": non_macos,
                "diversity_rate_pct": round(diversity_rate, 2),
            }

        return summary


# ---------------------------------------------------------------------------
# CLI interface (typer) – kept minimal to prevent bloating main CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Record and inspect success metrics (step 1.6).")


@app.command()
def record_efficiency(
    baseline_time: float = typer.Argument(..., help="Baseline time (seconds)."),
    improved_time: float = typer.Argument(..., help="Improved time (seconds)."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record an *Efficiency* event."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(EfficiencyEvent(baseline_time=baseline_time, improved_time=improved_time))


@app.command()
def record_accuracy(
    diff_accuracy: float = typer.Argument(..., help="Diff accuracy score 0-1."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record an *Accuracy* event."""

    if not 0 <= diff_accuracy <= 1:
        raise typer.BadParameter("diff_accuracy must be between 0 and 1")

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(AccuracyEvent(diff_accuracy=diff_accuracy))


@app.command()
def record_adoption(
    feedback: str = typer.Argument(..., help="Developer feedback or event description."),
    successful: bool = typer.Option(None, "--success/--no-success", help="Was onboarding successful?"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record an *Adoption* event."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(AdoptionEvent(feedback=feedback, successful_onboarding=successful))


@app.command()
def record_energy(
    tokens: int = typer.Argument(..., help="Total prompt + response tokens"),
    local_execution: bool = typer.Option(True, "--local/--remote", help="Was execution local?"),
    energy_kwh: float | None = typer.Option(None, "--kwh", help="Override energy consumption (kWh)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record an *Energy* KPI event.

    Useful when token counts and locality information are available from CI
    logs or external instrumentation but outside the :func:`offline_awareness.safe_chat`
    helper.
    """

    setup_logging("DEBUG" if verbose else "INFO")

    if energy_kwh is None:
        kwh_per_token = 1e-7 if local_execution else 5e-7
        energy_kwh = tokens * kwh_per_token

    store = MetricsStore(store_path)
    store.append_event(EnergyEvent(tokens=tokens, energy_kwh=energy_kwh, local_execution=local_execution))


@app.command()
def record_local_operation(
    local_success: bool = typer.Argument(..., help="Set to 1/true if operation was local-only."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record *Local-only operation* KPI event."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(LocalOperationEvent(local_operation_success=local_success))


@app.command()
def record_override(
    override: bool = typer.Argument(..., help="Whether the user overrode the AI suggestion."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record HITL *override* KPI event."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(OverrideEvent(override=override))


@app.command()
def record_consent(
    feature_tier: str = typer.Argument(..., help="Identifier of the feature tier for which consent was reaffirmed."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record *consent reaffirmation* event."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(ConsentReaffirmationEvent(feature_tier=feature_tier))


@app.command()
def record_audit(
    passed: bool = typer.Argument(..., help="Pass status of the cross-jurisdiction audit (true / false)."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record *cross-jurisdiction audit* outcome."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(AuditReadinessEvent(passed=passed))


@app.command()
def record_sustainability(
    aware: bool = typer.Argument(..., help="Did the user report increased sustainability awareness? (true/false)"),
    comment: str | None = typer.Option(None, "--comment", help="Optional free-form text."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record *sustainability awareness* event."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(SustainabilityAwarenessEvent(aware=aware, comment=comment))


@app.command()
def record_emission(
    saving_pct: float = typer.Argument(..., help="Percent emission saving vs cloud baseline (0-100)."),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record percentage emission saving from local execution."""
    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(EmissionSavingEvent(saving_pct=saving_pct))


@app.command(name="session-complete")
def record_session_completion(
    completed: bool = typer.Argument(..., help="Did the user finish the onboarding wizard? (true/false)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record first session (wizard) completion."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(FirstSessionCompletionEvent(completed=completed))


@app.command(name="ttfc")
def record_time_to_first_commit(
    duration_seconds: float = typer.Argument(..., help="Time from install to first commit (seconds)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record *time-to-first-commit* metric (seconds)."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(TimeToFirstCommitEvent(duration_seconds=duration_seconds))


@app.command(name="retention")
def record_retention_week_one(
    retained: bool = typer.Argument(..., help="Is the user still active after one week? (true/false)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record retention status after one week."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(RetentionWeekOneEvent(retained=retained))


@app.command(name="feature-adoption")
def record_feature_adoption(
    adopted: bool = typer.Argument(..., help="Has the user enabled advanced UX tools? (true/false)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record opt-in adoption of advanced UX features."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(FeatureAdoptionEvent(adopted=adopted))


@app.command(name="nps")
def record_nps(
    score: int = typer.Argument(..., help="Net Promoter Score response (0-10)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a Net Promoter Score vote."""

    if not 0 <= score <= 10:
        raise typer.BadParameter("Score must be between 0 and 10")

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(NpsEvent(score=score))


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show aggregated metrics summary."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    agg = store.aggregate()

    if json_output:
        import json as _json, sys as _sys

        _json.dump(agg, _sys.stdout, indent=2)
        _sys.stdout.write("\n")
    else:
        if not agg:
            typer.echo("No metrics recorded yet.")
            raise typer.Exit(code=1)
        if "efficiency" in agg:
            eff = agg["efficiency"]
            typer.echo(f"⚡ Efficiency: {eff['average_time_saved']}s avg saved across {eff['events']} events (Σ {eff['total_time_saved']}s)")
        if "accuracy" in agg:
            acc = agg["accuracy"]
            typer.echo(f"🎯 Accuracy: {acc['average_diff_accuracy']*100:.1f}% avg across {acc['events']} events")
        if "adoption" in agg:
            adp = agg["adoption"]
            typer.echo(f"🤝 Adoption: {adp['successful_onboardings']} successes / {adp['events']} events")
        if "local_only_operation" in agg:
            loc = agg["local_only_operation"]
            typer.echo(
                f"🏠 Local-only: {loc['success_rate_pct']:.1f}% success across {loc['events']} events"
            )
        if "override_activity" in agg:
            ov = agg["override_activity"]
            typer.echo(
                f"✋ Overrides: {ov['override_rate_pct']:.1f}% overrides across {ov['events']} events"
            )
        if "consent_reaffirmation" in agg:
            con = agg["consent_reaffirmation"]
            tiers = ", ".join(f"{tier}: {cnt}" for tier, cnt in con.items())
            typer.echo(f"🔐 Consent reaffirmations – {tiers}")
        if "audit_readiness" in agg:
            aud = agg["audit_readiness"]
            typer.echo(
                f"📜 Audit: {aud['pass_rate_pct']:.1f}% pass rate ({aud['passes']}/{aud['events']} events)"
            )
        if "energy_footprint" in agg:
            energy = agg["energy_footprint"]
            typer.echo(f"🌱 Energy: {energy['average_kwh']:.6f} kWh avg across {energy['events']} events")
        if "sustainability_awareness" in agg:
            sus = agg["sustainability_awareness"]
            typer.echo(f"🌱 Sustainability: {sus['aware_rate_pct']:.1f}% aware across {sus['events']} events")
        if "emission_savings" in agg:
            emi = agg["emission_savings"]
            typer.echo(f"🌱 Emission: {emi['average_saving_pct']:.1f}% avg across {emi['events']} events")
        if "first_session_completion" in agg:
            fs = agg["first_session_completion"]
            typer.echo(f"🌱 First session completion: {fs['completion_rate_pct']:.1f}% across {fs['events']} events")
        if "time_to_first_commit" in agg:
            ttfc = agg["time_to_first_commit"]
            typer.echo(f"🌱 Time to first commit: {ttfc['average_minutes']:.2f} min avg across {ttfc['events']} events")
        if "retention_week_one" in agg:
            ret = agg["retention_week_one"]
            typer.echo(f"🔄 Retention week one: {ret['retention_rate_pct']:.1f}% across {ret['events']} events")
        if "feature_adoption" in agg:
            fad = agg["feature_adoption"]
            typer.echo(f"🌱 Feature adoption: {fad['adoption_rate_pct']:.1f}% across {fad['events']} events")
        if "nps" in agg:
            nps = agg["nps"]
            typer.echo(f"🌱 Net Promoter Score: {nps['nps']:.1f}% across {nps['events']} events")

        # Step 6.6 KPIs
        if "signup" in agg:
            su = agg["signup"]
            typer.echo(
                f"📝 Sign-ups: {su['edu_rate_pct']:.1f}% EDU ({su['edu_signups']}/{su['events']} events)"
            )
        if "upgrade" in agg:
            up = agg["upgrade"]
            typer.echo(
                f"💳 Upgrades: {up['upgrade_rate_pct']:.1f}% within 30 days ({up['within_30_days']}/{up['events']} events)"
            )
        if "sme_team_adoption" in agg:
            sme = agg["sme_team_adoption"]
            typer.echo(
                f"👥 SME Teams: {sme['teams']} teams, avg {sme['average_seats_per_team']} seats (Σ {sme['total_seats']})"
            )
        if "platform_diversity" in agg:
            pd = agg["platform_diversity"]
            typer.echo(
                f"🖥️ Platform diversity: {pd['diversity_rate_pct']:.1f}% non-macOS across {pd['events']} users"
            )


# ---------------------------------------------------------------------------
# Step 6.6 – CLI helpers
# ---------------------------------------------------------------------------


@app.command(name="signup")
def record_signup(
    is_edu: bool = typer.Argument(..., help="Is the sign-up from an EDU domain? (true/false)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a new account sign-up."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(SignupEvent(is_edu=is_edu))


@app.command(name="upgrade")
def record_upgrade(
    within_30_days: bool = typer.Argument(..., help="Did upgrade happen within 30 days? (true/false)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a Free → Paid upgrade."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(UpgradeEvent(within_30_days=within_30_days))


@app.command(name="sme-team")
def record_sme_team(
    seats: int = typer.Argument(..., help="Number of seats (3–10) for the SME team"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record adoption by an SME team (3–10 seats)."""

    if not 3 <= seats <= 10:
        raise typer.BadParameter("SME teams must have between 3 and 10 seats")

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(SmeTeamAdoptionEvent(seats=seats))


@app.command(name="platform")
def record_platform_diversity(
    os_name: str = typer.Argument(..., help="Operating system name (macOS/Windows/Linux/etc.)"),
    store_path: Path = typer.Option(_DEFAULT_STORE_PATH, "--store", help="Metrics JSONL file."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record platform (OS) usage for diversity KPI."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = MetricsStore(store_path)
    store.append_event(PlatformDiversityEvent(os_name=os_name))


# Allow "python -m src.success_metrics …"
if __name__ == "__main__":
    app()

# Get markdown string
md = generate_docs(app)
print(md[:300])          # preview

# Persist to file (e.g., for README or docs site)
write_docs_file(app, Path("docs/CLI_REFERENCE.md"))