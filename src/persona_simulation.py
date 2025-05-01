from __future__ import annotations

"""persona_simulation.py – Phase 3c: Persona Chaining & Scenario Simulation 🤖🪄

This module builds upon *src.community_platform* & *src.ethics_certification*
by enabling **persona chaining** (combine multiple templates into a composite
role) and providing **live ethics audit simulations** via an LLM.

Highlights
~~~~~~~~~~
* ``chain`` command – merge 2-N personas into a *composite* persona stored in
  ``.personas/`` for reuse (no external network calls).
* ``audit`` command – run a GPT simulation that evaluates a persona (single or
  composite) in a supplied *scenario* and prints the model's analysis.
* Uses :pyfunc:`src.model_interface.chat` for provider-agnostic backend.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Dict
import json

import typer

from .logger import get_logger, setup_logging
from .community_platform import (
    PersonaTemplate,
    load_persona,
    create_persona,
    list_personas,
)
from .model_interface import chat as _chat

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. Persona chaining                                                         #
###############################################################################


def _find_persona_files(names: List[str]) -> List[Path]:  # noqa: D401
    """Return list of matching persona files for *names* (first match per name)."""

    files: List[Path] = []
    repo_dir = Path(".personas")
    for n in names:
        matches = [p for p in repo_dir.glob("*.json") if p.stem.startswith(n)]
        if not matches:
            raise FileNotFoundError(f"Persona '{n}' not found in {repo_dir}/")
        files.append(matches[0])
    return files


def combine_personas(names: List[str], *, overwrite: bool = False) -> PersonaTemplate:
    """Return *composite* PersonaTemplate by merging metadata of *names*."""

    files = _find_persona_files(names)
    templates = [load_persona(p) for p in files]

    comp_name = "chain_" + "_".join(t.name for t in templates)
    if len(comp_name) > 60:
        comp_name = comp_name[:57] + "..."

    comp_values: List[str] = []
    for t in templates:
        comp_values.extend([v for v in (t.values or []) if v not in comp_values])

    comp_desc_lines = [
        "Composite persona created by chaining the following templates:",
    ]
    for t in templates:
        comp_desc_lines.append(f"- {t.role} ({t.name}): {t.description}")

    composite = PersonaTemplate(
        name=comp_name,
        role="CompositePersona",
        description="\n".join(comp_desc_lines),
        values=comp_values,
        tags=["composite", *names],
    )

    # Persist ----------------------------------------------------------------
    path = create_persona(composite)
    _log.info("Composite persona written to %s", path)
    return composite

###############################################################################
# 2. Scenario simulation (live ethics audit)                                  #
###############################################################################


_DEFAULT_SCENARIO = (
    "You are participating in a live ethics audit. Analyse how the persona would "
    "handle a high-stakes decision impacting data privacy, inclusivity and "
    "environmental sustainability. Provide step-by-step reasoning followed by "
    "a pass/fail verdict and recommendations."
)


def run_simulation(persona: PersonaTemplate, scenario: str = _DEFAULT_SCENARIO, *, provider: str | None = None, model: str | None = None) -> str:  # noqa: D401
    """Return LLM response evaluating *persona* on *scenario*."""

    system_prompt = (
        "You are an AI ethics auditor evaluating the following persona:\n" + persona.description
    )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": scenario},
    ]

    response = _chat(messages, provider=provider, model=model)
    return response

###############################################################################
# 3. Typer CLI                                                                #
###############################################################################

app = typer.Typer(add_completion=False, help="Persona chaining & simulation")


@app.command()
def chain(  # noqa: D401 – CLI entrypoint
    names: List[str] = typer.Argument(..., help="List of persona names to combine"),
    overwrite: bool = typer.Option(False, "--overwrite", "-f", help="Overwrite existing composite persona"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Create a *composite* persona from multiple existing templates."""

    if verbose:
        setup_logging("DEBUG")

    try:
        composite = combine_personas(names, overwrite=overwrite)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo(f"✅ Composite persona '{composite.name}' created.")


@app.command()
def audit(  # noqa: D401 – CLI entrypoint
    persona: str = typer.Argument(..., help="Persona name (single or composite)"),
    scenario: str = typer.Option(_DEFAULT_SCENARIO, "--scenario", "-s", help="Audit scenario text"),
    provider: str | None = typer.Option(None, "--provider", help="LLM provider override"),
    model: str | None = typer.Option(None, "--model", help="Model override e.g. gpt-4o"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run live ethics audit simulation for *persona* under *scenario*."""

    if verbose:
        setup_logging("DEBUG")

    try:
        tmpl = load_persona(_find_persona_files([persona])[0])
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo("Running ethics audit… (this can take a few seconds)")
    try:
        response = run_simulation(tmpl, scenario, provider=provider, model=model)
    except Exception as exc:
        typer.secho(f"LLM call failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo("\n--- Audit Report ---\n")
    typer.echo(response)


if __name__ == "__main__":  # pragma: no cover
    app()