from __future__ import annotations

"""stakeholder_communication_plan.py – Step 6.7 Stakeholder Communication Plan 📣📝

This module operationalises the *6.7 Stakeholder Communication Plan* section
by translating the high-level outline into tangible, production-ready helpers.

It focuses on two communication vectors:

1. **Internal** – *Weekly sprint schedule* that lists adoption KPIs and a space
   for iterative discount tier experiments.
2. **External** – Ready-to-publish artefacts supporting the pricing roll-out:
   * Pricing FAQ markdown update
   * Dev-community AMA outline (Reddit, Discord, Dev.to)
   * Blog/LinkedIn post titled **"Why We're Opening Up"**

All artefacts can be rendered via a **Typer CLI** so non-developer stakeholders
(marketing, customer success) can generate or preview them without touching
Python code:

```console
# Preview a 6-week sprint schedule (stdout)
python -m src.stakeholder_communication_plan internal schedule --start 2025-01-06 --weeks 6

# Write FAQ update to docs/faq_pricing.md
python -m src.stakeholder_communication_plan external faq --output docs/faq_pricing.md

# Export Reddit AMA outline
python -m src.stakeholder_communication_plan external ama --platform reddit --output comms/reddit_ama.md

# Publish the blog post
python -m src.stakeholder_communication_plan external blog --output docs/blog/why_opening_up.md --overwrite
```

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* Produced artefacts are *markdown files* – **no network traffic**.
* Templates include placeholders only – *no sensitive data* is embedded.
* Encourages transparent pricing communication and community engagement.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import List
import textwrap
import typer

from .logger import get_logger, setup_logging

__all__ = [
    # Internal helpers
    "generate_sprint_schedule_markdown",
    # External helpers
    "generate_pricing_faq_markdown",
    "generate_ama_outline_markdown",
    "generate_blog_post_markdown",
    # Typer entry-point
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. INTERNAL – WEEKLY SPRINT SCHEDULE                                       ###
###############################################################################

def _week_range(start: datetime, week_idx: int) -> str:  # noqa: D401 – imperative
    """Return *YYYY-MM-DD* → *YYYY-MM-DD* label for *week_idx* starting at *start*."""

    monday = start + timedelta(weeks=week_idx)
    sunday = monday + timedelta(days=6)
    return f"{monday.date()} → {sunday.date()}"


def generate_sprint_schedule_markdown(*, start: str | None = None, weeks: int = 4) -> str:  # noqa: D401
    """Return markdown table outlining the **weekly sprint schedule**.

    Parameters
    ----------
    start:
        ISO date (Monday) that marks the first sprint. Defaults to the upcoming
        Monday when *None*.
    weeks:
        Number of sprint rows to generate (default: 4).
    """

    if weeks <= 0:
        raise ValueError("weeks must be > 0")

    if start:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
        except ValueError as exc:  # pragma: no cover – basic validation
            raise ValueError("start must be YYYY-MM-DD") from exc
    else:
        today = datetime.utcnow()
        # Find next Monday
        days_ahead = (7 - today.weekday()) % 7
        start_dt = (today + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)

    lines: List[str] = [
        f"# 📅 Internal Sprint Schedule ({weeks} weeks)",
        "",
        "| Week | Date Range | Adoption KPI Focus | Discount Tier Experiment | Notes |",
        "|---:|---|---|---|---|",
    ]

    for idx in range(weeks):
        date_rng = _week_range(start_dt, idx)
        lines.append(f"| {idx + 1} | {date_rng} | _e.g. DAU, active installs_ | _e.g. –10% tier_ | |")

    md = "\n".join(lines) + "\n"
    _log.debug("Generated sprint schedule (len=%d chars)", len(md))
    return md

###############################################################################
# 2. EXTERNAL – FAQ, AMA & BLOG POST                                        ###
###############################################################################


def generate_pricing_faq_markdown() -> str:  # noqa: D401 – imperative
    """Return markdown **Pricing FAQ** update section."""

    md = textwrap.dedent(
        f"""
        ## 💸 Pricing FAQ – Update ({datetime.utcnow().strftime(ISO_FMT)})

        **Q: Why are we introducing new discount tiers?**
        > We aim to make our AI tooling more accessible while rewarding early adopters and community contributors.

        **Q: How do the weekly iterations work?**
        > Each week we evaluate adoption KPIs (e.g. new active users, churn) and adjust the discount tiers accordingly.\
        > It's part of an **evidence-based pricing** methodology that balances sustainability with accessibility.

        **Q: Will my current plan change?**
        > Existing subscriptions remain untouched. You can opt-in to a new tier anytime via *Settings → Billing*.
        """
    ).strip() + "\n"

    _log.debug("Generated Pricing FAQ (len=%d chars)", len(md))
    return md


def generate_ama_outline_markdown(*, platform: str = "reddit") -> str:  # noqa: D401
    """Return markdown outline for **developer community AMA** on *platform*."""

    platform_title = platform.capitalize()
    md = textwrap.dedent(
        f"""
        # 🙋‍♂️ {platform_title} AMA – Pricing & Open-Up Strategy

        | Detail | Info |
        |---|---|
        | **Date** | {datetime.utcnow().strftime('%Y-%m-%d')} (TBD) |
        | **Time** | 16:00 UTC (TBD) |
        | **Hosts** | Product & Engineering leads |
        | **Topics** | Discount tiers • Roadmap • Community feedback |

        ## Agenda
        1. Welcome & quick project recap (5min)
        2. "Why we're opening up" – strategy overview (10min)
        3. Live Q&A (40min)
        4. Closing & next steps (5min)

        > 🤝 **Code of Conduct** – Be respectful, constructive, and on-topic.
        """
    ).strip() + "\n"

    _log.debug("Generated %s AMA outline (len=%d chars)", platform, len(md))
    return md


def generate_blog_post_markdown() -> str:  # noqa: D401 – imperative
    """Return markdown draft for the **Why We're Opening Up** blog/LinkedIn post."""

    md = textwrap.dedent(
        """
        # Why We're Opening Up – Making AI Tools Accessible for All

        *Published on {date} by the AI-Assisted Coding Team*

        ---
        > In the spirit of transparency and community-driven development, we're excited to announce a new pricing structure that lowers the barrier to entry and invites broader collaboration.

        ## 1. The Journey So Far
        Over the past year, we've witnessed incredible adoption of our offline-first AI toolchain. Yet, we've also heard feedback that cost can be a hurdle for independent developers and emerging markets.

        ## 2. Evidence-Based Pricing
        Starting this month, we'll iterate on **weekly discount tiers** backed by real-time adoption KPIs. This agile approach enables us to fine-tune pricing based on actual usage and community impact.

        ## 3. Community Engagement
        Transparency doesn't stop at pricing. Join our upcoming **AMA sessions** on Reddit, Discord, and Dev.to where we'll discuss the roadmap and gather your input.

        ## 4. What's Next
        We'll publish regular updates, share metrics publicly, and continue refining our offerings. Your feedback shapes the future—let's build it together!

        — The AI-Assisted Coding Team
        """.format(date=datetime.utcnow().strftime("%Y-%m-%d"))
    ).strip() + "\n"

    _log.debug("Generated blog post draft (len=%d chars)", len(md))
    return md

###############################################################################
# 3. TYPER CLI – expose helpers to non-dev stakeholders                      ###
###############################################################################

app = typer.Typer(add_completion=False, help="Step 6.7 – Stakeholder Communication Plan utilities")

# ---------------- Internal commands ----------------------------------------
internal_app = typer.Typer(help="Internal communication artefacts")
app.add_typer(internal_app, name="internal")


@internal_app.command("schedule")
def _cmd_schedule(
    start: str = typer.Option(None, "--start", help="Sprint start date (Monday) YYYY-MM-DD"),
    weeks: int = typer.Option(4, "--weeks", help="Number of sprints to generate"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a markdown **weekly sprint schedule** table."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_sprint_schedule_markdown(start=start, weeks=weeks)
    if output:
        output = output.expanduser().resolve()
        if output.exists() and not overwrite:
            raise FileExistsError(f"{output} already exists – use --overwrite to replace")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✅ Sprint schedule written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)


# ---------------- External commands ----------------------------------------
external_app = typer.Typer(help="External communication artefacts")
app.add_typer(external_app, name="external")


@external_app.command("faq")
def _cmd_faq(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the **Pricing FAQ** markdown snippet."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_pricing_faq_markdown()
    if output:
        output = output.expanduser().resolve()
        if output.exists() and not overwrite:
            raise FileExistsError(f"{output} already exists – use --overwrite to replace")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✅ FAQ written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)


@external_app.command("ama")
def _cmd_ama(
    platform: str = typer.Option("reddit", "--platform", "-p", help="Platform label (reddit|discord|devto)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate **AMA outline** for a developer community platform."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_ama_outline_markdown(platform=platform)
    if output:
        output = output.expanduser().resolve()
        if output.exists() and not overwrite:
            raise FileExistsError(f"{output} already exists – use --overwrite to replace")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✅ AMA outline written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)


@external_app.command("blog")
def _cmd_blog_post(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate **Why We're Opening Up** blog/LinkedIn draft."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_blog_post_markdown()
    if output:
        output = output.expanduser().resolve()
        if output.exists() and not overwrite:
            raise FileExistsError(f"{output} already exists – use --overwrite to replace")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✅ Blog post written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)


if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter