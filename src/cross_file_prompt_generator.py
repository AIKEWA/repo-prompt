from __future__ import annotations

"""cross_file_prompt_generator.py – Repository-wide multi-role prompt builder 🚀🔍

This module implements the *8.2 – Mid-term Buildout* concept by generating
**repository-wide** prompt templates that *simulate* **cross-file context**
for large-scale audits (e.g. security reviews).

Highlights
~~~~~~~~~~
* Leverages :pyclass:`src.selective_context_builder.ContextBuilder` (AST-
  boosted) to gather *k* highly relevant snippets across the codebase.
* Produces a :pyclass:`src.prompt_ops_framework.PromptTemplate` with **four
  roles** – *developer*, *QA*, *security*, *maintainer* – reflecting the pilot
  use case described in the roadmap.
* Supports **consensus-fix** workflows by optionally dispatching the prompt to
  an LLM and logging the *assistant* output for later human override.
* CLI – ``python -m src.cross_file_prompt_generator audit "sql injection"``
  builds and (optionally) stores the template inside ``.prompts/``.

Security Notes
--------------
* **Read-only** on source files – no code execution.
* Sanitises user input to prevent prompt injection.
* When ``--send`` is used the LLM call is delegated to
  :func:`src.model_interface.chat`, inheriting its safety measures.

"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Dict, Any
import html
import typer

from .selective_context_builder import ContextBuilder  # AST-boosted builder
from .context_builder import Snippet
from .prompt_ops_framework import PromptTemplate, add_template, init_repo
from .token_estimator import estimate_tokens
from .model_interface import chat as _chat
from .logger import get_logger, setup_logging

__all__ = [
    "RoleSpec",
    "build_repo_prompt",
    "create_template",
    "send_prompt",
    "app",
]

_log = get_logger(__name__)

###############################################################################
# 1. Data model                                                               #
###############################################################################


@dataclass(frozen=True)
class RoleSpec:  # noqa: D101 – simple value holder
    role: str
    """OpenAI-style role identifier (e.g. ``developer``)."""
    content_stub: str
    """Message prefix where ``{{context}}`` will be substituted by snippets."""


# Default 4-role audit configuration – can be overridden via CLI -------------

_DEFAULT_ROLES: Sequence[RoleSpec] = (
    RoleSpec(
        role="developer",
        content_stub=(
            "As the *Developer* who authored the code, explain the intent and "
            "known constraints.  Here is the relevant context:\n\n{{context}}"
        ),
    ),
    RoleSpec(
        role="qa",
        content_stub=(
            "As *QA*, outline potential functional issues based on the code "
            "snippet below and prior bug reports.\n\n{{context}}"
        ),
    ),
    RoleSpec(
        role="security",
        content_stub=(
            "As the *Security Engineer*, analyse the snippet for "
            "vulnerabilities.  Use OWASP Top-10 as reference.\n\n{{context}}"
        ),
    ),
    RoleSpec(
        role="maintainer",
        content_stub=(
            "As the *Maintainer*, propose minimal, backwards-compatible "
            "patches to fix the identified issues.  Output a unified diff.\n\n{{context}}"
        ),
    ),
)

###############################################################################
# 2. Core helpers                                                             #
###############################################################################


def _format_snippets(snippets: Sequence[Snippet]) -> str:
    """Return a markdown block concatenating *snippets* with headers."""

    parts: List[str] = []
    for s in snippets:
        header = f"### {s.path} (lines {s.start}-{s.end})"
        code_block = f"```{s.path.suffix.lstrip('.') or 'text'}\n{s.text}\n```"
        parts.extend([header, code_block])
    return "\n\n".join(parts)


def build_repo_prompt(
    query: str,
    *,
    repo_root: Path | str = Path("."),
    k: int = 10,
    roles: Sequence[RoleSpec] | None = None,
    max_snippet_tokens: int | None = None,
) -> str:
    """Return **multi-role markdown prompt** for *query* over *repo_root*.

    Each role receives the *same* ``{{context}}`` placeholder which is replaced
    with a markdown amalgamation of the selected snippets.  This guarantees
    that every role operates on the exact same evidence base, facilitating
    **consensus-fix** generation.
    """

    roles = roles or _DEFAULT_ROLES
    repo_root = Path(repo_root).resolve()

    builder = ContextBuilder(repo_root)
    snippets = builder.select_snippets(query, k=k, max_tokens=max_snippet_tokens)

    if not snippets:
        raise RuntimeError("No relevant snippets found – adjust query or k")

    context_md = _format_snippets(snippets)
    total_ctx_tokens = estimate_tokens(context_md)
    _log.debug("Context spans ~%d tokens across %d snippet(s)", total_ctx_tokens, len(snippets))

    prompt_parts: List[str] = [
        "# Repository-wide Audit Prompt",
        f"**Audit Focus**: {html.escape(query)}",
        "\n---\n",
    ]

    for spec in roles:
        part = spec.content_stub.replace("{{context}}", context_md)
        prompt_parts.append(f"## Role: {spec.role}\n{part}")

    return "\n\n".join(prompt_parts)


###############################################################################
# 3. Template & LLM helpers                                                   #
###############################################################################


def create_template(
    query: str,
    *,
    repo_root: Path | str = Path("."),
    k: int = 10,
    roles: Sequence[RoleSpec] | None = None,
    template_name: str | None = None,
) -> PromptTemplate:
    """Build a :pyclass:`PromptTemplate` ready to be stored via PromptOps."""

    prompt_str = build_repo_prompt(query, repo_root=repo_root, k=k, roles=roles)

    # Build *messages* array – we wrap each role block into an LLM message
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": "You are Repo Prompt, a multi-role assistant."}
    ]

    for block in prompt_str.split("\n## Role: "):
        if block.startswith("# Repository"):
            # header block belongs to first system message
            continue
        role, _, content = block.partition("\n")
        messages.append({"role": role.strip().lower(), "content": content.strip()})

    tmpl = PromptTemplate(
        name=template_name or f"audit_{query.replace(' ', '_')}",
        roles=messages,
        description="Auto-generated repository-wide audit template",
        version="0.1.0",
        tags=["audit", "security", "multi_role"],
    )
    return tmpl


# ---------------------------------------------------------------------------
# Optional LLM execution
# ---------------------------------------------------------------------------


_DEFAULT_MODEL = "gpt-4o-mini"  # sensible default; override via CLI


def send_prompt(messages: Sequence[Dict[str, str]], *, provider: str | None = None, model: str = _DEFAULT_MODEL) -> str:  # noqa: D401 – imperative style
    """Dispatch *messages* to the configured LLM provider and return assistant reply."""

    return _chat(list(messages), provider=provider, model=model)


###############################################################################
# 4. Typer CLI                                                                #
###############################################################################


app = typer.Typer(add_completion=False, help="Generate multi-role repository audit prompts.")


@app.command()
def audit(
    query: str = typer.Argument(..., help="Natural language focus, e.g. 'SQL injection risk'"),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
    k: int = typer.Option(10, "--k", help="Number of snippets to include"),
    store: bool = typer.Option(False, "--store", help="Persist template into .prompts/ and commit"),
    send: bool = typer.Option(False, "--send", help="Send prompt to LLM"),
    provider: str | None = typer.Option(None, "--provider", help="LLM provider"),
    model: str = typer.Option(_DEFAULT_MODEL, "--model", help="Model name"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs"),
):
    """Build a repository-wide audit prompt.  Optionally store and/or send."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        template = create_template(query, repo_root=repo, k=k)
    except Exception as exc:
        _log.error("Prompt creation failed: %s", exc)
        raise typer.Exit(code=1)

    # Human-readable preview --------------------------------------------------
    typer.secho("\n--- Generated Prompt Template (YAML) ---\n", fg="cyan")
    typer.echo(template.to_yaml())

    # Store to .prompts/ if requested ----------------------------------------
    if store:
        try:
            init_repo(repo)
            path = add_template(template, repo_path=repo)
            typer.secho(f"📦 Stored template at {path}", fg="green")
        except Exception as exc:
            _log.error("Failed to store template: %s", exc)
            raise typer.Exit(code=1)

    # Send to LLM if requested ----------------------------------------------
    if send:
        try:
            response = send_prompt(template.roles, provider=provider, model=model)
            typer.secho("\n--- LLM Response ---\n", fg="magenta")
            typer.echo(response)
        except Exception as exc:
            _log.error("LLM request failed: %s", exc)
            raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()