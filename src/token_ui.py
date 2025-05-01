from __future__ import annotations

"""Token-aware UI – live token counter & budget warnings.

This module provides a minimal *terminal* interface that shows **live** token
counts while the user types a prompt.  It leverages the lightweight
:pyfunc:`src.token_estimator.estimate_tokens` helper and outputs warnings when
the prompt exceeds configurable thresholds.

Usage (CLI) – interactive prompt:
---------------------------------
    $ python -m src.token_ui --max-tokens 4096

Press *Enter* twice to finish input.  The final prompt is printed to STDOUT.

Teams can embed the :func:`stream_user_input` generator into *TUI* or *web* apps
for richer experiences.  The implementation deliberately avoids *curses* or
other heavy frameworks to stay dependency-free.
"""

import sys
import typer
from typing import Generator

from .token_estimator import estimate_tokens
from .logger import get_logger, setup_logging

__all__ = [
    "stream_user_input",
    "app",
]

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Core generator – yields cumulative user input
# ---------------------------------------------------------------------------

def stream_user_input(stdin: typer.FileText = typer.FileText("-")) -> Generator[str, None, None]:
    """Yield cumulative lines entered by the user until two consecutive newlines.

    Works both for *interactive* stdin and piped input.  Each yielded *value* is
    the **full** text so far (not just the delta) so callers can recompute token
    counts.
    """

    buffer_lines: list[str] = []
    consecutive_empty = 0
    _prompt = "→ " if stdin.isatty() else ""

    while True:
        line = stdin.readline()
        if not line:  # EOF (e.g. piped input)
            break
        if stdin.isatty():
            # If TTY, we have already consumed the line via input() earlier.
            pass
        buffer_lines.append(line)
        if line.strip() == "":
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
        else:
            consecutive_empty = 0
        yield "".join(buffer_lines)
        _prompt = "… "


# ---------------------------------------------------------------------------
# Token-efficiency coaching
# ---------------------------------------------------------------------------

def _coaching_tips(text: str) -> list[str]:
    """Return simple heuristics to reduce *token* count of *text*.

    The suggestions are purely string-based to avoid heavyweight NLP deps.
    """

    tips: list[str] = []

    # Tip 1 – encourage bullet reduction when too many lines
    lines = text.splitlines()
    if len(lines) > 20:
        tips.append("Condense long lists into shorter bullet points or remove redundancies.")

    # Tip 2 – remove excessive whitespace
    if any(len(ln.strip()) == 0 for ln in lines):
        tips.append("Remove empty lines to reduce overhead tokens.")

    # Tip 3 – shorten examples
    if "example" in text.lower() and len(text) > 1000:
        tips.append("Consider shortening illustrative examples or referencing them externally.")

    # Tip 4 – rephrase verbose phrases
    if "in order to" in text:
        tips.append("Replace phrases like 'in order to' with 'to'.")

    return tips


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Live token counter for prompt drafting")


@app.command()
def interactive(
    max_tokens: int = typer.Option(4096, help="Model token limit for warnings"),
    show_energy: bool = typer.Option(
        True,
        "--show-energy/--no-show-energy",
        help="Display estimated energy consumption alongside token count.",
    ),
    remote: bool = typer.Option(
        False,
        "--remote/--local",
        help="Set to --remote when inference will run in the cloud (higher kWh per token).",
    ),
    coach: bool = typer.Option(
        False,
        "--coach/--no-coach",
        help="Enable token-efficiency coaching tips when prompt grows large.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Start an interactive session that counts tokens and optionally shows energy impact.

    The **energy estimation** is a *rule-of-thumb* based on heuristics used in
    :pymod:`src.success_metrics`: ~1e-7 kWh per token for **local** execution
    and 5e-7 kWh for **remote/cloud** calls. The values are *approximate* and
    intended to raise *awareness* rather than provide scientific accuracy.
    """

    setup_logging("DEBUG" if verbose else "INFO")

    kwh_per_token = 5e-7 if remote else 1e-7

    typer.secho("Enter your prompt. Press ⏎ twice to finish.\n", fg="cyan")
    buffer: str = ""

    while True:
        try:
            line = input()
        except EOFError:
            break
        buffer += line + "\n"

        # -----------------------------------------------
        # Metrics – tokens & energy footprint (estimate)
        # -----------------------------------------------
        tokens = estimate_tokens(buffer)
        percent = int(tokens / max_tokens * 100)

        if show_energy:
            energy_kwh = tokens * kwh_per_token
            energy_msg = f" 🌱≈{energy_kwh:.6f} kWh"
        else:
            energy_msg = ""

        # -------------------------
        # Status / budget warnings
        # -------------------------
        if tokens > max_tokens:
            typer.secho(f"⚠ {tokens} tokens ({percent}% of limit){energy_msg} – exceeds budget!", fg="red")
        elif tokens > max_tokens * 0.9:
            typer.secho(f"⚠ {tokens} tokens ({percent}% of limit){energy_msg}", fg="yellow")
        else:
            typer.secho(f"✓ {tokens} tokens{energy_msg}", fg="green")

        # -------------------------------------------------
        # Coaching – suggest ways to shorten the prompt
        # -------------------------------------------------
        if coach and tokens > max_tokens * 0.75:
            _tips = _coaching_tips(buffer)
            for tip in _tips:
                typer.secho(f"💡 {tip}", fg="blue")

        # -------------------------
        # Termination – double ⏎
        # -------------------------
        if line.strip() == "":  # user pressed Enter on empty line
            if buffer.rstrip("\n").endswith("\n\n"):
                break

    # Output final prompt (without trailing newlines) so caller can pipe
    sys.stdout.write(buffer.rstrip("\n"))


if __name__ == "__main__":  # pragma: no cover
    app()  # pylint: disable=no-value-for-parameter