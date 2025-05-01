from __future__ import annotations

"""Abstraction layer for model inference APIs.

Currently provides a basic wrapper around `OpenAI` chat completion endpoint.
Extendable to support local models or other vendors.
"""

import os
# Ensure .env variables loaded before use
from dotenv import load_dotenv
load_dotenv()
from typing import List, Dict, Any

import requests
import httpx
from .logger import get_logger

# REVIEW: Might switch to openai official lib for streaming support

_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Default Ollama endpoint (local HTTP API)
_OLLAMA_API_URL = f"{os.getenv('OLLAMA_HOST', 'http://localhost:11434')}/api/chat"

_log = get_logger(__name__)

__all__ = [
    "openai_chat",
    "openai_chat_async",
    "ollama_chat",
    "chat",
]

# ---------------------------------------------------------------------------
# Provider-specific helpers
# ---------------------------------------------------------------------------

def openai_chat(messages: List[Dict[str, str]], model: str = "gpt-3.5-turbo", temperature: float = 0.2, max_tokens: int | None = None, **kwargs) -> str:
    """Send chat completion request and return assistant message content."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable not set")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        **({"max_tokens": max_tokens} if max_tokens is not None else {}),
        **kwargs,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    response = requests.post(_OPENAI_API_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


async def openai_chat_async(
    messages: List[Dict[str, str]],
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.2,
    max_tokens: int | None = None,
    **kwargs,
) -> str:
    """Async variant of :func:`openai_chat` using httpx."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable not set")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        **({"max_tokens": max_tokens} if max_tokens is not None else {}),
        **kwargs,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_OPENAI_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        _log.debug("Tokens used (approx): %s", data.get("usage"))
        return data["choices"][0]["message"]["content"]


def ollama_chat(
    messages: List[Dict[str, str]],
    model: str = "llama3",
    temperature: float = 0.2,
    max_tokens: int | None = None,
    **kwargs,
) -> str:
    """Minimal wrapper for the Ollama HTTP API.

    Ollama's chat endpoint expects a *single* prompt string rather than the
    OpenAI-style ``messages`` array.  We therefore flatten the conversation
    into a plain text prompt with role prefixes.  This approach is adequate
    for prototyping and *experimentation* but may require richer formatting for
    production use.
    """

    prompt_parts = []
    for msg in messages:
        role = msg.get("role") or "user"
        prompt_parts.append(f"[{role}]\n{msg.get('content', '')}")

    prompt = "\n\n".join(prompt_parts)

    payload: dict[str, str | float | int | None] = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
    }

    if max_tokens is not None:
        payload["num_predict"] = max_tokens

    try:
        resp = requests.post(_OLLAMA_API_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError("Could not connect to the Ollama API at " f"{_OLLAMA_API_URL}. Is the daemon running?") from exc


# ---------------------------------------------------------------------------
# Provider-agnostic façade
# ---------------------------------------------------------------------------

def chat(
    messages: List[Dict[str, str]],
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
) -> str:
    """Return LLM response from *provider*.

    The helper chooses an implementation backend based on either the explicit
    *provider* argument **or** the ``LLM_PROVIDER`` environment variable (falls
    back to ``openai``).  This function enables **quick switching** between
    providers during *iteration* and can be used by higher-level modules
    without hard-coding a dependency on OpenAI.
    """

    provider = provider or os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        return openai_chat(messages, model=model or "gpt-3.5-turbo", **kwargs)
    if provider == "ollama":
        return ollama_chat(messages, model=model or "llama3", **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")