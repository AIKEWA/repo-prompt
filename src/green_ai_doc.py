"""green_ai_doc.py – Green AI Coding onboarding guide (Step 4.7)

This module generates a **Green AI Coding** onboarding document that helps new
contributors understand the *sustainability* features built into the
AI-assisted coding workflow:

* Local-first LLM execution & model quantisation
* Real-time **token counter** with energy tool-tips (see :pymod:`src.token_ui`)
* Carbon-aware scheduling (:pymod:`src.carbon_scheduler`)
* Success metrics & energy KPIs (:pymod:`src.success_metrics`)

It mirrors the API of :pymod:`src.standardization` so teams can add the guide
via a simple CLI call:

```bash
python -m src.green_ai_doc --output docs/green_ai_onboarding.md
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import textwrap

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "generate_green_ai_doc",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Markdown template
# ---------------------------------------------------------------------------

_GREEN_AI_DOC = textwrap.dedent(
    """\
    # 🌱 Green AI Coding – Onboarding Guide

    Welcome to the team's sustainability initiative! This quick-start guide
    introduces the *green* features embedded in our AI-assisted coding stack
    so you can contribute without increasing the project's carbon footprint.

    ## Why Green AI?
    Large Language Models (LLMs) can be energy-intensive. By adopting
    **local-first inference**, **carbon-aware scheduling**, and **transparent
    energy metrics**, we ensure that productivity gains do **not** come at the
    expense of the planet.

    ---

    ## 1. Local-first LLM execution
    1. Install [Ollama](https://ollama.ai/) or another on-device inference
       runtime (see *Step 2.9* of the main docs).
    2. Export `FORCE_LOCAL_LLM=1` to prefer local models. When a cloud call is
       unavoidable, the workflow records an *EnergyEvent* so we can offset the
       impact.

    ```bash
    export FORCE_LOCAL_LLM=1  # set in your shell profile
    ```

    ## 2. Real-time token & energy feedback
    Use the interactive token counter:

    ```bash
    python -m src.token_ui interactive --max-tokens 8192 --remote
    ```

    Every prompt shows an *approximate* kWh number next to the token count.
    Compare **remote** vs **local** runs to see the savings!

    ## 3. Carbon-aware scheduling
    Delay heavy jobs until the electricity grid is cleaner:

    ```python
    from src.carbon_scheduler import delay_if_dirty
    delay_if_dirty(threshold=350)  # gCO₂/kWh
    ```

    ## 4. Track your savings
    The `success_metrics` CLI aggregates energy data:

    ```bash
    python -m src.success_metrics summary
    ```

    Look for the 🌱 *Energy* section to monitor your personal footprint.

    ## 5. Further reading
    * [Carbon Aware SDK](https://carbon-aware-computing.io/)
    * [Efficient Prompt Engineering](https://arxiv.org/abs/2403.12345)
    * Internal doc: *Energy KPI dashboard* (Confluence » Sustainability)

    ---
    *Generated automatically via `python -m src.green_ai_doc`.*
    """
)

# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def generate_green_ai_doc() -> str:
    """Return the Green AI onboarding markdown string."""

    return _GREEN_AI_DOC

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate Green AI onboarding doc (Step 4.7)")

@app.command()
def generate(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Path to write markdown (stdout if omitted)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print or write the onboarding guide."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = generate_green_ai_doc()

    if output:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✅ Green AI doc written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)

if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter