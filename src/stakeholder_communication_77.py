# new file
from __future__ import annotations

"""stakeholder_communication_77.py – Step 7.7 Stakeholder Communication 📣⚙️

Brings *7.7 Stakeholder Communication* theory to life.

The module outputs **markdown** artefacts via a CLI so non-developers can
consume them easily:

1. **Prompt Library wiki page** – Standards, Templates, Governance.
2. **Town-hall demo outline** – Highlights KPIs (time saved, accuracy).
3. **Prompt Clinics schedule** – Monthly training calendar.

Example
~~~~~~~
$ python -m src.stakeholder_communication_77 wiki -o docs/wiki/prompt_library.md
$ python -m src.stakeholder_communication_77 demo --date 2025-05-09
$ python -m src.stakeholder_communication_77 clinic --months 9 -o comms/clinics_q4.md

Security & Ethics
~~~~~~~~~~~~~~~~~
* Pure markdown – no network traffic, no PII.
* KPI aggregation uses anonymised data from :pymod:`src.success_metrics`.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
import textwrap

import typer

from .logger import get_logger, setup_logging
from .success_metrics import MetricsStore, _DEFAULT_STORE_PATH

__all__ = [
    "generate_wiki_section_markdown",
    "generate_town_hall_demo_markdown",
    "generate_clinic_schedule_markdown",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. Prompt Library – wiki section                                         ###
###############################################################################


def generate_wiki_section_markdown() -> str:  # noqa: D401 – imperative style
    """Return markdown for **Prompt Library – Standards, Templates, Governance**."""

    md = textwrap.dedent(
        f"""
        # 📚 Prompt Library – Standards, Templates, Governance

        _Last updated: {datetime.utcnow().strftime(ISO_FMT)}_

        | Section | Purpose |
        |---|---|
        | **Standards** | Define formatting, naming, and context conventions for every prompt. |
        | **Templates** | Provide reusable scaffolds to minimise engineering time. |
        | **Governance** | Describe approval workflow, versioning, ownership. |

        ## 1. Standards
        1. **Naming** – *PascalCase* IDs prefixed by domain (`CodeFix_LowRisk`).
        2. **Context Block** – Begin with `Context:` ≤ 50 tokens.
        3. **Clarity** – Use imperative sentences, avoid ambiguity.
        4. **Safety Tags** – Place `# REVIEW:` beside lines requiring SME checks.

        ## 2. Templates
        Store templates in `prompts/` with YAML front-matter:

        ```yaml
        ---
        id: CodeReview_Guided
        version: 1.0.0
        owner: frontend-team
        ---
        Context: {{code_diff}}
        Instruction: Review the diff, identify bugs, suggest unit tests.
        ```

        > 📝 Replace placeholders (e.g. `{{code_diff}}`) via orchestration layer.

        ## 3. Governance
        1. **Change Proposal** – Submit PR, highlight changes with `# DISCUSS:`.
        2. **Approvers** – Two Prompt Strategists + one Domain Engineer.
        3. **Versioning** – *Patch* = wording, *Minor* = behaviour, *Major* = structure.
        4. **Audit Trail** – CI appends SHA & timestamp to YAML metadata.
        """
    ).strip() + "\n"

    _log.debug("Generated wiki section (%d chars)", len(md))
    return md

###############################################################################
# 2. Town-hall demo outline                                                ###
###############################################################################


def _aggregate_kpis(store: MetricsStore) -> Dict[str, float]:
    """Aggregate minimal KPI set for the demo slide."""

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


def generate_town_hall_demo_markdown(*, date: str | None = None, metrics_path: Path | str = _DEFAULT_STORE_PATH) -> str:  # noqa: D401
    """Return markdown outline for the **town-hall demo**.

    Parameters
    ----------
    date:
        Optional date (YYYY-MM-DD). Defaults to the next Friday.
    metrics_path:
        Path to metrics JSONL.
    """

    # Determine demo date
    if date:
        try:
            demo_dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("date must be YYYY-MM-DD") from exc
    else:
        today = datetime.utcnow()
        days_until_fri = (4 - today.weekday()) % 7  # Monday = 0
        demo_dt = today + timedelta(days=days_until_fri)

    kpi = _aggregate_kpis(MetricsStore(metrics_path))

    md = textwrap.dedent(
        f"""
        # 🏛️ Town-Hall Demo – Prompt Orchestration Impact

        _Demo date: {demo_dt.strftime('%Y-%m-%d')}_

        ## 1. Welcome & Agenda (5 min)
        * Quick recap of prompt strategy goals.

        ## 2. KPI Snapshot (10 min)
        | Metric | Value |
        |---|---:|
        | **Efficiency events** | {kpi['eff_events']} |
        | **Σ Time saved** | {kpi['total_time_saved']:.1f}s |
        | **Avg time saved / event** | {kpi['avg_time_saved']:.1f}s |
        | **Accuracy events** | {kpi['acc_events']} |
        | **Avg diff accuracy** | {kpi['avg_accuracy']:.2%} |

        ## 3. Live Walk-through (15 min)
        * Showcase Prompt Library & orchestration.
        * Demonstrate real-time metrics logging.

        ## 4. Q&A (15 min)
        * Collect feedback, discuss next steps.

        ## 5. Closing (5 min)
        * Announce upcoming **Prompt Clinic**.
        * Encourage contributions to Prompt Library.
        """
    ).strip() + "\n"

    _log.debug("Generated demo outline (%d chars)", len(md))
    return md

###############################################################################
# 3. Prompt Clinics schedule                                               ###
###############################################################################


def generate_clinic_schedule_markdown(*, months: int = 6, start: str | None = None) -> str:  # noqa: D401
    """Return markdown table of upcoming **Prompt Clinics**.

    Parameters
    ----------
    months:
        Number of months to list.
    start:
        First month (YYYY-MM). Defaults to current month.
    """

    if months <= 0:
        raise ValueError("months must be > 0")

    # Determine initial month
    if start:
        try:
            first_dt = datetime.strptime(start, "%Y-%m")
        except ValueError as exc:
            raise ValueError("start must be YYYY-MM") from exc
    else:
        now = datetime.utcnow()
        first_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    lines: List[str] = [
        f"# 🗓️ Prompt Clinics Schedule ({months} months)",
        "",
        "| # | Month | Focus | Facilitators | Notes |",
        "|---:|---|---|---|---|",
    ]

    for idx in range(months):
        month_dt = (first_dt + timedelta(days=idx * 31)).replace(day=1)
        label = month_dt.strftime("%Y-%m")
        lines.append(
            f"| {idx + 1} | {label} | _Prompt optimisation_ | _Prompt Strategists_ | |"
        )

    md = "\n".join(lines) + "\n"
    _log.debug("Generated clinics schedule (%d chars)", len(md))
    return md

###############################################################################
# 4. Typer CLI                                                             ###
###############################################################################

app = typer.Typer(add_completion=False, help="Step 7.7 Stakeholder Communication utilities")


def _write(path: Path | str, content: str, overwrite: bool) -> None:
    """Write *content* to *path* with overwrite check."""

    path = Path(path).expanduser().resolve()
    if path.exists() and not overwrite:
        typer.echo("❌ File exists – use --overwrite to replace.")
        raise typer.Exit(1)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    typer.echo(f"✅ Written → {path.relative_to(Path.cwd())}")


@app.command()
def wiki(
    output: Path | None = typer.Option(None, "--output", "-o", help="Markdown output path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace file if exists"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the Prompt Library wiki page."""

    setup_logging("DEBUG" if verbose else "INFO")
    md = generate_wiki_section_markdown()

    if output:
        _write(output, md, overwrite)
    else:
        typer.echo(md)


@app.command()
def demo(
    date: str = typer.Option(None, "--date", "-d", help="Demo date YYYY-MM-DD"),
    metrics_file: Path = typer.Option(_DEFAULT_STORE_PATH, "--metrics", help="Custom metrics JSONL"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Markdown output path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace file if exists"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the town-hall demo outline."""

    setup_logging("DEBUG" if verbose else "INFO")
    md = generate_town_hall_demo_markdown(date=date, metrics_path=metrics_file)

    if output:
        _write(output, md, overwrite)
    else:
        typer.echo(md)


@app.command()
def clinic(
    months: int = typer.Option(6, "--months", "-m", help="Number of months to list"),
    start: str = typer.Option(None, "--start", "-s", help="Start month YYYY-MM"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Markdown output path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace file if exists"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the Prompt Clinics schedule."""

    setup_logging("DEBUG" if verbose else "INFO")
    md = generate_clinic_schedule_markdown(months=months, start=start)

    if output:
        _write(output, md, overwrite)
    else:
        typer.echo(md)


if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter