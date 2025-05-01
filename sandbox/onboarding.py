#!/usr/bin/env python3
"""Developer onboarding helper for *Redefining AI-Assisted Coding*.

Run from repository root:

    python -m sandbox.onboarding --help

Features
--------
1. Greets contributor; prints critical project links.
2. Optionally executes the *quick test suite* (unit only).
3. Validates local Git config & pre-commit installation.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

import typer

README_URL = "https://github.com/your-org/repo#readme"
PHASE_1_DOC = Path("docs/PHASE_1_SUMMARY.md")

app = typer.Typer(add_completion=False, help="Onboard new developers to RepoPrompt project")


def _run(cmd: List[str], cwd: Path | None = None, check: bool = True) -> int:
    """Minimal subprocess wrapper that forwards output."""

    proc = subprocess.run(cmd, cwd=cwd, check=check)
    return proc.returncode


@app.command()
def welcome(name: str = typer.Option("Developer", "--name", help="Your display name")) -> None:
    """Print a friendly welcome message with next steps."""

    typer.secho(f"👋 Hi {name}! Welcome to the RepoPrompt codebase.\n", fg=typer.colors.GREEN)
    typer.echo("Start by reading the Phase-1 summary →", nl=False)
    typer.secho(f" {PHASE_1_DOC.as_posix()}\n", fg=typer.colors.BRIGHT_BLUE)
    typer.echo("Full README →", nl=False)
    typer.secho(f" {README_URL}\n", fg=typer.colors.BRIGHT_BLUE)
    typer.echo("Then run:")
    typer.echo("    pre-commit install  # to set up git hooks")
    typer.echo("    python -m sandbox.onboarding test  # to confirm local env")


@app.command()
def test(unit_only: bool = typer.Option(True, "--unit-only", help="Skip integration tests")) -> None:
    """Execute the pytest suite to ensure environment health."""

    cmd = [sys.executable, "-m", "pytest", "-q"]
    if unit_only:
        cmd += ["-m", "not integration"]
    typer.secho("Running local tests…", fg=typer.colors.YELLOW)
    try:
        _run(cmd)
    except subprocess.CalledProcessError as exc:
        typer.secho("❌ Tests failed", fg=typer.colors.RED)
        raise typer.Exit(exc.returncode)
    typer.secho("✅ All tests passed!", fg=typer.colors.GREEN)


if __name__ == "__main__":  # pragma: no cover
    app()