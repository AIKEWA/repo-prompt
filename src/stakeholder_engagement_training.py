# new file
from __future__ import annotations

"""stakeholder_engagement_training.py – Step 8.5 Stakeholder Engagement & Training 🎯🧑‍🤝‍🧑

This module operationalises **Step 8.5 – Stakeholder Engagement & Training** from the
Theory→Code execution framework.

Objectives addressed
====================
1. **Communication** – Publish roadmap & outcome artefacts via tech blogs and town-hall
   slide outlines.
2. **Enablement** – Register *PromptOps* training sessions and produce **CIP 101**
   learning modules.
3. **Sandbox onboarding** – Track browser-based *prompt-editing* sandboxes for new
   engineers.

Design
------
* Mirrors the append-only JSON-Lines approach used by other Step modules (e.g.
  :pymod:`src.stakeholder_training`).
* Provides **Typer CLI** so non-developers can record items or generate finished
  markdown documents without touching the codebase.
* All operations are **local-only**; there are no outbound network calls and no
  personal data is persisted.

Example usage
~~~~~~~~~~~~~
```console
# Add a roadmap entry
python -m src.stakeholder_engagement_training roadmap add "Q2 2025 AI Roadmap" --audience "All engineers" \
    --summary "Major PromptOps upgrades" --quarter 2025-Q2

# Generate the quarterly roadmap blog post
python -m src.stakeholder_engagement_training roadmap markdown --quarter 2025-Q2 -o docs/blog/q2_roadmap.md

# Record a PromptOps training session
python -m src.stakeholder_engagement_training training add --title "PromptOps 101 – Intro" --level beginner

# Create starter CIP 101 module markdown
python -m src.stakeholder_engagement_training cip markdown -o docs/cip_101.md
```

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* Pure markdown generation; **no** external API invocations.
* Records intentionally exclude PII and store only public metadata.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import textwrap

import typer

from .logger import get_logger, setup_logging
from .success_metrics import MetricsStore, _DEFAULT_STORE_PATH

__all__ = [
    "RoadmapEntry",
    "TownHall",
    "TrainingSession",
    "PromptSandbox",
    "EngagementStore",
    "generate_roadmap_markdown",
    "generate_town_hall_outline",
    "generate_cip_101_markdown",
    "generate_sandbox_readme",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Dataclass primitives
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _BaseRecord:
    """Shared metadata and JSON serialisation helper."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # -------------------
    # Helper properties
    # -------------------

    @property
    def type(self) -> str:  # noqa: D401 – property naming OK
        return self.__class__.__name__

    # -------------------
    # Serialisation
    # -------------------

    def to_json(self) -> str:  # noqa: D401 – imperative fine
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


@dataclass
class RoadmapEntry(_BaseRecord):
    """Represents a *roadmap* or *outcome* announcement.

    Parameters
    ----------
    title:
        Short headline for the blog / wiki article.
    quarter:
        Fiscal or calendar quarter (e.g. "2025-Q2").
    audience:
        Intended readership ("All engineers", "Stakeholders").
    summary:
        One-sentence summary.
    link:
        Optional URL or repo path to the full article.
    """

    title: str
    quarter: str
    audience: str
    summary: str
    link: str | None = None


@dataclass
class TownHall(_BaseRecord):
    """Metadata for an *engineering town-hall* event."""

    title: str
    date: str  # YYYY-MM-DD
    location: str | None = None
    summary: str | None = None


@dataclass
class TrainingSession(_BaseRecord):
    """Represents a **PromptOps** training session."""

    title: str
    level: str | None = None  # beginner | intermediate | advanced
    date: str | None = None  # YYYY-MM-DD
    duration_min: int | None = None
    recording_url: str | None = None

    def __post_init__(self) -> None:  # noqa: D401 – lifecycle ok
        if self.date is None:
            self.date = datetime.utcnow().strftime("%Y-%m-%d")


@dataclass
class PromptSandbox(_BaseRecord):
    """Tracks a *browser-accessible prompt-editing sandbox* instance."""

    url: str
    owner: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# JSON-Lines store
# ---------------------------------------------------------------------------


_DEFAULT_FILE = Path(os.getenv("STAKEHOLDER_ENGAGEMENT_85_FILE", ".stakeholder_engagement_8_5.jsonl"))


class EngagementStore:
    """Append-only storage & aggregation for Step 8.5 artefacts."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Engagement store initialised at %s", self.path)

    # -------------------
    # CRUD helpers
    # -------------------

    def append(self, record: _BaseRecord) -> None:  # noqa: D401 – imperative fine
        """Serialise *record* to disk (append-only)."""

        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        _log.info("Recorded %s", record.type)

    def _load(self) -> List[_BaseRecord]:
        if not self.path.exists():
            return []

        records: List[_BaseRecord] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                r_type = data.pop("type", None)
                if r_type == "RoadmapEntry":
                    records.append(RoadmapEntry(**data))
                elif r_type == "TownHall":
                    records.append(TownHall(**data))
                elif r_type == "TrainingSession":
                    records.append(TrainingSession(**data))
                elif r_type == "PromptSandbox":
                    records.append(PromptSandbox(**data))
        return records

    # -------------------
    # Aggregations & exports
    # -------------------

    def aggregate(self) -> Dict[str, Any]:  # noqa: D401
        roadmap = 0
        townhalls = 0
        trainings = 0
        sandboxes = 0
        for r in self._load():
            if isinstance(r, RoadmapEntry):
                roadmap += 1
            elif isinstance(r, TownHall):
                townhalls += 1
            elif isinstance(r, TrainingSession):
                trainings += 1
            elif isinstance(r, PromptSandbox):
                sandboxes += 1
        return {
            "roadmap_entries": roadmap,
            "town_halls": townhalls,
            "training_sessions": trainings,
            "sandboxes": sandboxes,
        }

    def filter_by_quarter(self, quarter: str) -> List[RoadmapEntry]:
        return [r for r in self._load() if isinstance(r, RoadmapEntry) and r.quarter == quarter]


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------


def generate_roadmap_markdown(*, quarter: str, store: EngagementStore | None = None) -> str:  # noqa: D401
    """Return markdown **tech-blog** post for *quarter* roadmap/outcomes."""

    if store is None:
        store = EngagementStore()

    entries = store.filter_by_quarter(quarter)
    if not entries:
        _log.warning("No roadmap entries found for %s", quarter)

    md_lines: List[str] = [
        f"# 🚀 Engineering Roadmap & Outcomes – {quarter}",
        "",
        f"_Published: {datetime.utcnow().strftime(ISO_FMT)}_",
        "",
        "## Highlights\n",
    ]

    for e in entries:
        md_lines.append(f"* **{e.title}** – {e.summary}  ")
        md_lines.append(f"  Audience: {e.audience}" + (f" • [Read more]({e.link})" if e.link else ""))
    md_lines.append("")

    md_lines.extend(
        [
            "## Looking ahead\n",
            "We will continue to iterate on PromptOps and developer enablement,",
            "incorporating feedback from town-halls and CIP 101 sessions.",
        ]
    )

    md = "\n".join(md_lines).strip() + "\n"
    _log.debug("Generated roadmap markdown (%d chars)", len(md))
    return md


# --------------------
# Town-hall outline
# --------------------


def _aggregate_kpis(store: MetricsStore) -> Dict[str, float]:
    """Aggregate minimal KPI set for slides – mirrors src.stakeholder_communication_77."""

    agg = store.aggregate()
    eff = agg.get("efficiency", {})
    acc = agg.get("accuracy", {})
    return {
        "eff_events": eff.get("events", 0),
        "total_time_saved": eff.get("total_time_saved", 0.0),
        "avg_time_saved": eff.get("average_time_saved", 0.0),
        "acc_events": acc.get("events", 0),
        "avg_accuracy": acc.get("average_accuracy", acc.get("diff_accuracy_avg", 0.0)),
    }


def generate_town_hall_outline(*, date: str | None = None, metrics_path: Path | str = _DEFAULT_STORE_PATH) -> str:  # noqa: D401
    """Return markdown outline for an *engineering town-hall*."""

    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    kpi = _aggregate_kpis(MetricsStore(metrics_path))

    md = textwrap.dedent(
        f"""
        # 🏛️ Engineering Town-Hall – PromptOps Updates

        _Date: {date}_

        ## KPI Snapshot
        | Metric | Value |
        |---|---:|
        | **Efficiency events** | {kpi['eff_events']} |
        | **Σ Time saved** | {kpi['total_time_saved']:.1f}s |
        | **Avg time saved / event** | {kpi['avg_time_saved']:.1f}s |
        | **Accuracy events** | {kpi['acc_events']} |
        | **Avg diff accuracy** | {kpi['avg_accuracy']:.2%} |

        ## Agenda
        1. Roadmap recap & wins 👏
        2. Live PromptOps demo 🚀
        3. Q&A and feedback collection 💬

        ## Next Steps
        * Schedule **CIP 101** deep-dive.
        * Launch new prompt-editing sandbox for onboarding.
        """
    ).strip() + "\n"

    _log.debug("Generated town-hall outline (%d chars)", len(md))
    return md


# --------------------
# CIP 101 markdown
# --------------------


def generate_cip_101_markdown() -> str:  # noqa: D401 – imperative
    """Return starter markdown for **CIP 101 – PromptOps Fundamentals**."""

    md = textwrap.dedent(
        f"""
        # 🎓 CIP 101 – PromptOps Fundamentals

        _Last updated: {datetime.utcnow().strftime(ISO_FMT)}_

        ## Overview
        **CIP 101** introduces engineers to *PromptOps* – the end-to-end workflow
        for managing and deploying prompts at scale.

        | Module | Topics |
        |---|---|
        | 1. Foundation | Prompt anatomy, governance, safety tags |
        | 2. Tooling | Prompt Library, version control, CI checks |
        | 3. Deployment | Orchestration, latency optimisation, rollback |
        | 4. Ethics & Security | Bias mitigation, secrets handling |

        ## Learning Objectives
        1. Understand the life-cycle of a production prompt.
        2. Apply *safety tags* (`# REVIEW:`, `# DISCUSS:`) effectively.
        3. Use the Prompt Library CLI to create, test, and publish prompts.
        4. Evaluate prompts using success metrics and feedback loops.

        ## Hands-on Lab – Your First Prompt
        Follow the steps below in the *prompt-editing sandbox*:

        1. Duplicate the **HelloDiff** template.
        2. Replace the *Context* section with your own code diff.
        3. Run `prompt-cli test --prompt HelloDiff` and inspect metrics.
        4. Submit for review with `prompt-cli submit HelloDiff`.

        > 💡 **Tip:** Add `# TODO:` beside lines you wish to discuss with peers.
        """
    ).strip() + "\n"

    _log.debug("Generated CIP 101 markdown (%d chars)", len(md))
    return md


# --------------------
# Sandbox README
# --------------------


def generate_sandbox_readme(*, url: str, owner: str | None = None) -> str:  # noqa: D401
    """Return README snippet for a *prompt-editing sandbox* instance."""

    owner_info = f"Owned by **{owner}**." if owner else ""
    md = textwrap.dedent(
        f"""
        # 🏖️ Prompt-Editing Sandbox

        {owner_info}

        Access the sandbox at: <{url}>

        ## Getting Started
        1. Open the link above in your browser.
        2. Sign in with your company SSO.
        3. Click **New Prompt** to start experimenting.

        ## Next Steps
        * Complete the *CIP 101 Hands-on Lab*.
        * Share prompts with peers using the *Share* → *Team* menu.
        * Join the #promptops channel for support.
        """
    ).strip() + "\n"

    _log.debug("Generated sandbox README (%d chars)", len(md))
    return md


# ---------------------------------------------------------------------------
# Typer CLI – entry points
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Step 8.5 – Stakeholder Engagement & Training")

# ---------------
# Roadmap group
# ---------------


_roadmap_app = typer.Typer(name="roadmap", help="Record or generate roadmap artefacts")
app.add_typer(_roadmap_app)


@_roadmap_app.command("add")
def cli_roadmap_add(
    title: str = typer.Argument(..., help="Headline for the roadmap entry"),
    quarter: str = typer.Option("2025-Q2", "--quarter", "-q", help="Quarter e.g. 2025-Q2"),
    audience: str = typer.Option("All engineers", "--audience", "-a", help="Target audience"),
    summary: str = typer.Option(..., "--summary", "-s", help="Short summary"),
    link: str | None = typer.Option(None, "--link", "-l", help="Optional URL or path"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *roadmap/outcome* entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = EngagementStore(store_path)
    store.append(RoadmapEntry(title=title, quarter=quarter, audience=audience, summary=summary, link=link))


@_roadmap_app.command("markdown")
def cli_roadmap_markdown(
    quarter: str = typer.Option(..., "--quarter", "-q", help="Quarter e.g. 2025-Q2"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a **tech-blog** markdown post for *quarter*."""

    setup_logging("DEBUG" if verbose else "INFO")
    md = generate_roadmap_markdown(quarter=quarter, store=EngagementStore(store_path))

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown written to {output}")
    else:
        typer.echo(md)


# ---------------
# Town-hall group
# ---------------


_town_app = typer.Typer(name="townhall", help="Generate town-hall outlines")
app.add_typer(_town_app)


@_town_app.command("outline")
def cli_townhall_outline(
    date: str | None = typer.Option(None, "--date", "-d", help="Date YYYY-MM-DD"),
    metrics_file: Path = typer.Option(_DEFAULT_STORE_PATH, "--metrics", help="Metrics JSONL"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate markdown outline for a town-hall event."""

    setup_logging("DEBUG" if verbose else "INFO")
    md = generate_town_hall_outline(date=date, metrics_path=metrics_file)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown written to {output}")
    else:
        typer.echo(md)


# ---------------
# Training group
# ---------------


_training_app = typer.Typer(name="training", help="Record PromptOps training sessions")
app.add_typer(_training_app)


@_training_app.command("add")
def cli_training_add(
    title: str = typer.Argument(..., help="Training title"),
    level: str | None = typer.Option("beginner", "--level", "-l", help="Level: beginner|intermediate|advanced"),
    date: str | None = typer.Option(None, "--date", "-d", help="YYYY-MM-DD"),
    duration: int | None = typer.Option(None, "--duration", "-t", help="Duration in minutes"),
    recording_url: str | None = typer.Option(None, "--recording-url", "-r", help="Recording or slides URL"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a *PromptOps* training session."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = EngagementStore(store_path)
    store.append(TrainingSession(title=title, level=level, date=date, duration_min=duration, recording_url=recording_url))


# ---------------
# CIP group
# ---------------


_cip_app = typer.Typer(name="cip", help="Generate CIP 101 materials")
app.add_typer(_cip_app)


@_cip_app.command("markdown")
def cli_cip_markdown(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate starter **CIP 101 – PromptOps Fundamentals** markdown."""

    setup_logging("DEBUG" if verbose else "INFO")
    md = generate_cip_101_markdown()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown written to {output}")
    else:
        typer.echo(md)


# ---------------
# Sandbox group
# ---------------


_sandbox_app = typer.Typer(name="sandbox", help="Record or document prompt sandboxes")
app.add_typer(_sandbox_app)


@_sandbox_app.command("add")
def cli_sandbox_add(
    url: str = typer.Argument(..., help="Sandbox URL"),
    owner: str | None = typer.Option(None, "--owner", "-o", help="Sandbox owner"),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional description"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record a prompt-editing sandbox instance."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = EngagementStore(store_path)
    store.append(PromptSandbox(url=url, owner=owner, description=description))


@_sandbox_app.command("readme")
def cli_sandbox_readme(
    url: str = typer.Argument(..., help="Sandbox URL"),
    owner: str | None = typer.Option(None, "--owner", "-o", help="Owner"),
    output: Path | None = typer.Option(None, "--output", "-f", help="Write markdown to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a README snippet for a sandbox instance."""

    setup_logging("DEBUG" if verbose else "INFO")
    md = generate_sandbox_readme(url=url, owner=owner)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown written to {output}")
    else:
        typer.echo(md)


# ---------------------------------------------------------------------------
# Hint entry-point – `python -m src.stakeholder_engagement_training`          #
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter