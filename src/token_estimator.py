from __future__ import annotations

"""Token estimation helpers leveraging the `tiktoken` library.

The functions defined here provide fast approximations of token usage for
arbitrary strings or code fragments, enabling preflight checks before
submitting prompts to token-limited LLMs.

These are NOT exact counts but closely approximate for GPT-3.5 and GPT-4
families with the cl100k_base encoding.
"""

from functools import lru_cache
from typing import List, Sequence, Mapping

import tiktoken

_DEFAULT_MODEL = "gpt-3.5-turbo"

# REVIEW: expose model as argument or config?


@lru_cache(maxsize=4)
def _encoding_for_model(model: str = _DEFAULT_MODEL) -> tiktoken.Encoding:  # type: ignore
    """Cached encoding retrieval."""

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str, model: str = _DEFAULT_MODEL) -> int:
    """Return the approximate number of tokens in `text`."""

    enc = _encoding_for_model(model)
    return len(enc.encode(text, disallowed_special=set()))


def budget_remaining(context: str, max_tokens: int, model: str = _DEFAULT_MODEL) -> int:
    """How many tokens remain if `context` were sent with `max_tokens` limit."""
    return max_tokens - estimate_tokens(context, model) 