from __future__ import annotations

"""Model Delegation Logic – "Think" then "Do" pattern.

This helper dispatches *reasoning heavy* ("think") stages to a **large / remote**
model (e.g. OpenAI GPT-4) while executing *lightweight* or *follow-up* ("do")
steps on a **smaller / local** model (e.g. Ollama Llama-3).  The goal is to
achieve *energy proportionality* – reserving expensive resources only when
necessary.

High-level API
--------------
>>> from src.model_delegation import delegated_chat
>>> result = delegated_chat([
...     {"role": "user", "content": "Generate a Python function to compute PI"},
... ])

The function automatically runs the **planning** phase on the *think_provider*
(default: ``openai``) and the **execution** phase on the *do_provider* (default:
``ollama``).  Providers can be overridden per-call.

Design choices
~~~~~~~~~~~~~~
* **Stateless** – no global state besides environment variables used by the
  underlying providers.
* **Composable** – built on :pyfunc:`src.model_interface.chat` therefore inherits
  retry, logging and provider abstraction.
* **Explainability** – returns a *tuple* ``(assistant_content, meta)`` where
  ``meta`` captures both responses and token usage (when available) for audits.

Environment variables
~~~~~~~~~~~~~~~~~~~~~
* ``THINK_MODEL`` – default model name for the *think* provider.
* ``DO_MODEL`` – default model name for the *do* provider.

"""

from typing import List, Dict, Any, Tuple
import os
from .model_interface import chat as _chat
from .logger import get_logger

__all__ = [
    "delegated_chat",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Core helper
# ---------------------------------------------------------------------------


def _default(value: str | None, fallback: str) -> str:
    return value if value else fallback


def delegated_chat(
    messages: List[Dict[str, str]],
    *,
    think_provider: str | None = None,
    do_provider: str | None = None,
    think_model: str | None = None,
    do_model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """Run a *two-step* chat completion ("think" ➜ "do").

    Parameters
    ----------
    messages
        Standard OpenAI-style messages array.
    think_provider / do_provider
        Provider identifiers recognised by :pyfunc:`src.model_interface.chat`.
    think_model / do_model
        Model names specific to the chosen providers.
    temperature, max_tokens
        Forwarded to both provider calls.

    Returns
    -------
    tuple
        ``(assistant_content, meta)`` where *meta* is a dict holding both raw
        provider responses and basic telemetry.
    """

    # ------------------
    # THINK PHASE
    # ------------------
    _think_provider = _default(think_provider, os.getenv("THINK_PROVIDER", "openai"))
    _think_model = _default(think_model, os.getenv("THINK_MODEL", "gpt-4o"))

    _log.debug("[THINK] provider=%s model=%s", _think_provider, _think_model)

    analysis_prompt = (
        "You are an expert software engineer. Given the following user request, "
        "draft a high-level plan or pseudo-code. Focus on reasoning, edge cases "
        "and pitfalls. Do NOT write the final answer – only plan the work."
    )
    think_messages = [
        {"role": "system", "content": analysis_prompt},
        *messages,
    ]
    plan = _chat(
        think_messages,
        provider=_think_provider,
        model=_think_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # ------------------
    # DO PHASE
    # ------------------
    _do_provider = _default(do_provider, os.getenv("DO_PROVIDER", "ollama"))
    _do_model = _default(do_model, os.getenv("DO_MODEL", "llama3"))

    _log.debug("[DO] provider=%s model=%s", _do_provider, _do_model)

    execution_prompt = (
        "Using the following plan, produce the final answer in the requested format. "
        "Plan:\n" + plan
    )
    do_messages = [
        {"role": "system", "content": execution_prompt},
        *messages,
    ]

    answer = _chat(
        do_messages,
        provider=_do_provider,
        model=_do_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    meta: Dict[str, Any] = {
        "plan": plan,
        "think_provider": _think_provider,
        "do_provider": _do_provider,
        "think_model": _think_model,
        "do_model": _do_model,
    }

    return answer, meta