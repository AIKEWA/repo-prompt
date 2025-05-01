"""Cognitive primer generator – maps Repo Prompt features to human cognition.

This module fulfils *Step 2.6 – Onboard developers with a cognitive primer* by
producing a concise markdown document that explains **how** Repo Prompt mirrors
human *selective attention* and *working-memory* processes.  The primer helps
new team members quickly internalise why utilities such as *Context Builder*
and *CodeMap* exist and how they integrate into daily workflows.

CLI usage examples
------------------
1. Preview primer in terminal (default)::

       python -m src.cognitive_primer show

2. Write to *docs/cognitive_primer.md* (create dirs if needed)::

       python -m src.cognitive_primer write --path docs/primer.md

Internally the module is dependency-free except for :pypi:`typer` which is
already used elsewhere in the codebase.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

import typer

__all__ = [
    "generate_primer",
    "app",
]


# ---------------------------------------------------------------------------
# Markdown generator
# ---------------------------------------------------------------------------


def _sections() -> List[str]:
    """Return static primer section strings (kept here for easy edits)."""

    return [
        "## 1 Why another tooling layer?",
        "Human brains excel at pattern recognition yet struggle with *large*\n"
        "working-memory loads (≈ ~7 ± 2 items).  Modern codebases contain≈\n"
        "thousands of files – cognitive overload is inevitable.  *Repo Prompt*\n"
        "bridges that gap by turning *selective attention* and *long-term\n"
        "memory* concepts into automation primitives (Context Builder,\n"
        "CodeMap, …).",
        "",
        "## 2 Selective attention → Context Builder",
        "Just like humans skim only the *relevant* paragraphs when reading,\n"
        "`ContextBuilder.select_snippets()` extracts <=*k* high-scoring\n"
        "snippets so Large Language Models receive *just enough* context to be\n"
        "useful – no more, no less.",
        "",
        "## 3 Spatial memory → CodeMap",
        "Developers remember *where* things live (\"the utils folder\",\n"
        "\"models.py\").  `CodeMap` serialises that spatial memory into JSON\n"
        "or a tree view so cognitive effort can be spent on reasoning rather\n"
        "than navigation.",
        "",
        "## 4 Working-memory unload → Apply-mode",
        "Applying LLM-generated diffs in one atomic operation ensures humans\n"
        "need to review only the *delta* instead of re-implementing the patch\n"
        "manually – saving scarce *attention bandwidth*.",
        "",
        "## 5 Daily workflow integration",
        "1. Search with **presets** – `python -m src.context_builder.search --preset python`\n"
        "2. Visualise impact – `python -m src.codemaps scan --include-regex \\.(py)$`\n"
        "3. Generate diff & review – `python -m src.patch_apply --patch-file`",
        "",
        "## 6 Key take-aways",
        "* *Automation augments*, it does not replace expertise.\n"
        "* Keep token budgets low – smaller prompts == faster iterations.\n"
        "* Treat LLMs as collaborators: verify, test, iterate.",
    ]


def generate_primer() -> str:  # noqa: D401 – imperative mood not required
    """Return a markdown string of the cognitive primer."""

    lines: List[str] = [
        "# Cognitive Primer – Repo Prompt & Human Attention",
        "",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
    ]
    lines.extend(_sections())
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate or write the cognitive primer document.")


@app.command()
def show():
    """Print primer markdown to STDOUT."""

    typer.echo(generate_primer())


@app.command()
def write(
    path: Path = typer.Option(Path("docs/cognitive_primer.md"), "--path", "-p", help="Output markdown path"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if exists"),
):
    """Write primer markdown to *path* (default *docs/cognitive_primer.md*)."""

    path = path.expanduser()
    if path.exists() and not force:
        typer.echo(f"Error: {path} exists – use --force to overwrite", err=True)
        raise typer.Exit(code=1)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_primer(), encoding="utf-8")
    typer.echo(f"Primer written to {path.resolve()}")