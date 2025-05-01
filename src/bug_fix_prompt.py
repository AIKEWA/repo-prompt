"""Selective bug-fix prompt generator (Use Case: *Selective bug fix prompt*).

This helper streamlines the process of crafting **focused** LLM prompts for
bug-fixing tasks.  Given a natural-language bug description it leverages the
:pymod:`src.context_builder.ContextBuilder` to retrieve the *most relevant*
code snippets so that the large-language-model receives **just enough**
context – reducing token usage and cognitive overhead.

The resulting prompt can be either **printed** for manual copy-paste or, when a
valid API key is present, **sent** directly to the configured LLM provider via
:pymod:`src.model_interface.chat` to request a patch/diff.

Key Features
------------
1. **Context narrowing** – integrates ContextBuilder with token budgeting.
2. **Prompt template** – produces a ready-to-use markdown prompt instructing
   the model to return a unified diff.
3. **Optional execution** – with the `--send` flag the prompt is dispatched to
   the model and the assistant's response is streamed.

Security Considerations
~~~~~~~~~~~~~~~~~~~~~~~
* Only reads source files – no code execution.
* Sanitises user bug description before embedding in prompt.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import List, Dict

import typer

from .context_builder import ContextBuilder, Snippet
from .token_estimator import estimate_tokens, budget_remaining
from .model_interface import chat as _chat
from .logger import get_logger, setup_logging

__all__ = [
    "build_bugfix_prompt",
    "send_prompt",
    "app",
]

_log = get_logger(__name__)

_DEFAULT_MODEL = "gpt-3.5-turbo"
_DEFAULT_MAX_PROMPT_TOKENS = 6000

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


_PROMPT_HEADER = """You are an experienced software engineer.\n"""
_PROMPT_INSTRUCTIONS = (
    "Analyse the following bug description and the provided code snippets. "
    "Return a unified **diff** that fixes the bug with minimal changes. "
    "Use ```diff``` fences and include file paths."
)


def _format_snippet(s: Snippet) -> str:
    """Return a markdown representation of *Snippet* `s`."""

    rel_path = s.path
    header = f"### {rel_path} (lines {s.start}-{s.end})"
    code_block = f"```{rel_path.suffix.lstrip('.')}\n{s.text}\n```"
    return f"{header}\n{code_block}"


def build_bugfix_prompt(
    description: str,
    repo_root: Path | str = Path("."),
    *,
    k: int = 7,
    max_prompt_tokens: int = _DEFAULT_MAX_PROMPT_TOKENS,
) -> str:
    """Return a markdown prompt for fixing a bug described by *description*."""

    repo_root = Path(repo_root).resolve()
    builder = ContextBuilder(repo_root)

    snippets = builder.select_snippets(description, k=k, max_tokens=max_prompt_tokens // 2)

    _log.info("Selected %d snippets (total ~%d tokens)", len(snippets), sum(estimate_tokens(s.text) for s in snippets))

    parts: List[str] = [
        _PROMPT_HEADER,
        f"**Bug Description**:\n{html.escape(description)}\n",
        _PROMPT_INSTRUCTIONS,
        "\n---\n",
    ]

    parts.extend(_format_snippet(s) for s in snippets)

    prompt = "\n\n".join(parts)

    tokens = estimate_tokens(prompt)
    if tokens > max_prompt_tokens:
        _log.warning("Prompt length %d tokens exceeds %d – consider lowering k", tokens, max_prompt_tokens)

    return prompt


# ---------------------------------------------------------------------------
# Optional LLM call
# ---------------------------------------------------------------------------


def send_prompt(prompt: str, *, provider: str | None = None, model: str = _DEFAULT_MODEL) -> str:
    """Send *prompt* to configured LLM provider and return assistant content."""

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": "You are an AI coding assistant."},
        {"role": "user", "content": prompt},
    ]

    return _chat(messages, provider=provider, model=model)


# ---------------------------------------------------------------------------
# Typer CLI wrapper
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate focused bug-fix prompts and optionally send them to an LLM.")


@app.command()
def prompt(
    description: str = typer.Argument(..., help="Natural-language bug description"),
    repo_path: Path = typer.Option(Path("."), "--repo", help="Repository root (default cwd)"),
    k: int = typer.Option(7, "--k", help="Number of relevant snippets to include"),
    max_tokens: int = typer.Option(_DEFAULT_MAX_PROMPT_TOKENS, "--max-tokens", help="Max tokens for prompt"),
    send: bool = typer.Option(False, "--send", help="Send the prompt to the LLM"),
    provider: str | None = typer.Option(None, "--provider", help="LLM provider (overrides $LLM_PROVIDER)"),
    model: str = typer.Option(_DEFAULT_MODEL, "--model", help="Model name"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI helper – build prompt and optionally send to model."""

    setup_logging("DEBUG" if verbose else "INFO")

    prompt_text = build_bugfix_prompt(description, repo_root=repo_path, k=k, max_prompt_tokens=max_tokens)

    if not send:
        typer.echo(prompt_text)
    else:
        try:
            response = send_prompt(prompt_text, provider=provider, model=model)
        except Exception as exc:
            _log.error("LLM request failed: %s", exc)
            raise typer.Exit(code=1)

        typer.echo("\n--- LLM Response ---\n")
        typer.echo(response)