from __future__ import annotations

"""GitHub Pages deployment helper (Step 1.11).

This module automates the initial *GitHub Pages* skeleton for the repository –
as per the theory prompt:

1. Create a `docs/index.md` welcome page linking to existing resources.
2. Ensure there is a `docs/README.md` (acts as landing page for GitHub file
   browser) – we *generate or update* a minimal variant.
3. Optionally generate a GitHub Actions workflow at
   `.github/workflows/pages.yml` that publishes the *docs/* directory to Pages.

Design notes
------------
* Mirrors the approach used in :pymod:`src.standardization` – **preview first**
  unless `--write` is provided.
* Uses a simple :class:`FileSpec` dataclass to carry file content & path.
* Focuses on *static* assets only; no runtime dependencies.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List
import textwrap
import json

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "FileSpec",
    "generate_index_md",
    "generate_readme_md",
    "generate_workflow",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileSpec:
    """Container describing a file to be written/previewed."""

    path: Path
    content: str

    def as_dict(self) -> Dict[str, Any]:
        return {"path": str(self.path), "content": self.content}


# ---------------------------------------------------------------------------
# Template generators
# ---------------------------------------------------------------------------

def generate_index_md() -> str:
    """Return the default *index.md* markdown string."""

    return textwrap.dedent(
        """\
        # Welcome to the AI-Assisted Coding Documentation

        This site provides guidelines, references, and onboarding resources for using
        AI-driven tools effectively in development workflows.

        - [Development Guidelines](./ai_coding_guidelines.md)
        - [Onboarding Guide](./onboarding.md)

        ---
        Generated automatically from the latest source code and documentation.
        """
    )


def generate_readme_md() -> str:
    """Return a minimal `docs/README.md` with navigation links."""

    return textwrap.dedent(
        """\
        # Documentation folder

        This directory is published to **GitHub Pages**. Edit markdown files here and
        push to the `main` branch to update the public site.

        - [📚 Site Home](./index.md)
        - [🛠 Development Guidelines](./ai_coding_guidelines.md)
        - [🚀 Onboarding](./onboarding.md)
        """
    )


_WORKFLOW_YML = textwrap.dedent(
    """\
    name: Deploy GitHub Pages

    on:
      push:
        branches:
          - main

    permissions:
      contents: read
      pages: write
      id-token: write

    jobs:
      deploy:
        runs-on: ubuntu-latest
        steps:
          - name: Checkout
            uses: actions/checkout@v4

          - name: Setup Pages
            uses: actions/configure-pages@v3

          - name: Upload artifact
            uses: actions/upload-pages-artifact@v2
            with:
              path: docs

          - name: Deploy to GitHub Pages
            uses: actions/deploy-pages@v2
    """
)


def generate_workflow() -> str:
    """Return the GitHub Actions workflow YAML string."""

    return _WORKFLOW_YML


# ---------------------------------------------------------------------------
# Helpers producing FileSpec instances
# ---------------------------------------------------------------------------

def _file_specs(repo_root: Path | str, include_workflow: bool) -> List[FileSpec]:
    root = Path(repo_root).resolve()

    specs = [
        FileSpec(root / "docs" / "index.md", generate_index_md()),
        FileSpec(root / "docs" / "README.md", generate_readme_md()),
    ]

    if include_workflow:
        specs.append(FileSpec(root / ".github" / "workflows" / "pages.yml", generate_workflow()))

    _log.debug("Prepared %d file specs (workflow=%s)", len(specs), include_workflow)
    return specs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate GitHub Pages scaffolding (Step 1.11)")


@app.command()
def all(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    workflow: bool = typer.Option(True, "--workflow/--no-workflow", help="Include GitHub Actions workflow"),
    write: bool = typer.Option(False, "--write", help="Write files to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *index.md*, *README.md* and optionally the workflow file."""

    setup_logging("DEBUG" if verbose else "INFO")

    specs = _file_specs(repo_path, include_workflow=workflow)
    _output(specs, write, force)


@app.command()
def index(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write file to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
):
    """Generate `docs/index.md` only."""

    spec = FileSpec(Path(repo_path).resolve() / "docs" / "index.md", generate_index_md())
    _output([spec], write, force)


@app.command()
def workflow(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write file to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
):
    """Generate `.github/workflows/pages.yml` only."""

    spec = FileSpec(Path(repo_path).resolve() / ".github" / "workflows" / "pages.yml", generate_workflow())
    _output([spec], write, force)


# ---------------------------------------------------------------------------
# Internal I/O helpers
# ---------------------------------------------------------------------------

def _output(specs: List[FileSpec], write: bool, force: bool) -> None:  # noqa: D401 – imperative mood not required
    """Write or preview *specs*."""

    for spec in specs:
        if write:
            if spec.path.exists() and not force:
                _log.warning("Skipping existing %s (use --force to overwrite)", spec.path)
                continue
            spec.path.parent.mkdir(parents=True, exist_ok=True)
            spec.path.write_text(spec.content, encoding="utf-8")
            typer.echo(f"✅ {spec.path.relative_to(Path.cwd())} written")
        else:
            header = f"----- {spec.path.relative_to(Path.cwd())} -----"
            typer.echo(header)
            typer.echo(spec.content.rstrip())
            typer.echo("-" * len(header))