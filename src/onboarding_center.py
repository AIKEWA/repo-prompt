from __future__ import annotations

"""onboarding_center.py – Phase 3d: Onboarding & Interactive Tutorials 📚

Provides **CLI-based interactive lessons** that guide developers through key
RepoPrompt concepts (e.g. *ethics*, *prompt ops*).  Progress can optionally be
sent to a webhook for LMS tracking.  Lessons link out to browser playgrounds
such as *JupyterLite* for hands-on experimentation.
"""

from pathlib import Path
from typing import Dict, List, Any
import json
import time
import sys
import webbrowser
import requests  # safe to import – used elsewhere in project
import typer

from .logger import get_logger, setup_logging

_log = get_logger(__name__)

###############################################################################
# 1. Lesson registry                                                          #
###############################################################################


LessonStep = Dict[str, Any]


def _ethics_lesson() -> List[LessonStep]:  # noqa: D401 – factory helper
    """Return scripted steps for the *ethics* lesson."""

    return [
        {
            "title": "Welcome to the Ethics Primer",
            "content": (
                "In this lesson you'll learn how RepoPrompt ensures responsible AI "
                "development. You will review key principles and complete short "
                "quizzes to check understanding."
            ),
        },
        {
            "title": "Principle 1 – Inclusivity",
            "content": (
                "RepoPrompt personas are designed to respect cultural diversity. "
                "\nQuestion: Should prompts be localised for different user bases? (y/n)"
            ),
            "quiz": "y",
        },
        {
            "title": "Principle 2 – Transparency",
            "content": (
                "Explainability is key. All templates include a description field.\n"
                "Question: Is it acceptable to omit the description? (y/n)"
            ),
            "quiz": "n",
        },
        {
            "title": "Hands-on playground",
            "content": (
                "Open the JupyterLite playground to inspect a persona YAML file."
            ),
            "action": "open",
            "url": "https://jupyterlite.github.io/demo/repl/index.html?path=persona_demo.ipynb",
        },
        {
            "title": "Congrats 🎉",
            "content": "You've completed the ethics lesson!",
        },
    ]


LESSONS: Dict[str, List[LessonStep]] = {
    "ethics": _ethics_lesson(),
}

###############################################################################
# 2. Core helpers                                                             #
###############################################################################


def _send_webhook(url: str, payload: Dict[str, Any]) -> None:  # noqa: D401
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as exc:  # pragma: no cover – network failures
        _log.warning("Webhook POST failed: %s", exc)


###############################################################################
# 3. Typer CLI                                                                #
###############################################################################

app = typer.Typer(add_completion=False, help="Interactive onboarding centre")


@app.command()
def list():  # noqa: D401 – CLI entrypoint
    """List available lesson *slugs*."""

    for slug in LESSONS:
        typer.echo(f"- {slug}")


@app.command()
def learn(  # noqa: D401 – CLI entrypoint
    lesson: str = typer.Argument(..., help="Lesson slug – run 'list' to view"),
    webhook_url: str | None = typer.Option(None, "--webhook", help="POST progress updates to this URL"),
    open_links: bool = typer.Option(False, "--open", "-o", help="Auto-open external URLs"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run interactive *lesson* with optional webhook progress reporting."""

    if verbose:
        setup_logging("DEBUG")

    steps = LESSONS.get(lesson)
    if not steps:
        typer.secho(f"Lesson '{lesson}' not found. Use 'list' to see options.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"📚 Starting lesson: {lesson}\n", fg=typer.colors.GREEN)

    for idx, step in enumerate(steps, 1):
        typer.secho(f"Step {idx}/{len(steps)} – {step['title']}", fg=typer.colors.CYAN)
        typer.echo(step["content"])

        # Quiz --------------------------------------------------------------
        if (answer := step.get("quiz")) is not None:
            user = typer.prompt("Your answer (y/n)").strip().lower()
            correct = user == answer.lower()
            typer.secho("Correct!" if correct else "Incorrect.", fg=typer.colors.GREEN if correct else typer.colors.RED)
        # Action (e.g. open browser) ---------------------------------------
        if step.get("action") == "open":
            url = step["url"]
            typer.echo(f"Opening {url} …")
            if open_links:
                webbrowser.open(url, new=2)
        typer.echo("")

        # Webhook -----------------------------------------------------------
        if webhook_url:
            _send_webhook(
                webhook_url,
                {
                    "lesson": lesson,
                    "step": idx,
                    "title": step["title"],
                    "timestamp": time.time(),
                },
            )

    typer.secho("🏁 Lesson completed!", fg=typer.colors.GREEN)

    if webhook_url:
        _send_webhook(webhook_url, {"lesson": lesson, "status": "completed", "timestamp": time.time()})


if __name__ == "__main__":  # pragma: no cover
    app()