from __future__ import annotations

"""Pull-request review assistant using LLM commentary.

This implements *Use Case 3* from the project specification: *Enhancing PR
review quality with embedded commit diffs + LLM commentary*.

The module exposes :func:`summarize_diff` which:

1. Extracts a Git diff for a given *commit range* (default ``HEAD~1..HEAD``).
2. Feeds the diff to an LLM with a review prompt.
3. Returns the assistant's feedback so it can be embedded into a PR or saved as
   review notes.

Design goals
------------
* **Minimal API surface** – one main function + CLI wrapper.
* **Safety** – diff size is truncated if it exceeds a configurable token
  budget.  Users are warned via log.
* **Observability** – structured logs and return data make the integration
  friendly for CI workflows.

Dependencies
------------
* :pypi:`GitPython` for diff extraction.
* Internal :pymod:`src.model_interface` for LLM access.
"""

from pathlib import Path
from typing import List, Dict, Any
import os

from git import Repo  # type: ignore

from .logger import get_logger
from .model_interface import openai_chat
from .token_estimator import estimate_tokens, budget_remaining

_log = get_logger(__name__)

_MAX_PROMPT_TOKENS = int(os.getenv("REVIEW_MAX_PROMPT_TOKENS", "6000"))


# -----------------------------
# Public API
# -----------------------------

def summarize_diff(
    repo_path: Path | str = ".",
    commit_range: str = "HEAD~1..HEAD",
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.1,
) -> str:
    """Return LLM commentary for *commit_range* inside *repo_path*.

    Parameters
    ----------
    repo_path:
        Local Git repository path.
    commit_range:
        Range syntax understood by ``git diff`` (e.g. ``main..feature``).
    model, temperature:
        Forwarded to :func:`src.model_interface.openai_chat`.
    """

    repo = Repo(Path(repo_path))

    _log.info("Generating diff for %s", commit_range)
    diff_text = repo.git.diff(commit_range, unified=3)
    if not diff_text.strip():
        _log.warning("Diff is empty – nothing to review")
        return "No changes detected in diff range."  # early exit

    token_count = estimate_tokens(diff_text)
    if token_count > _MAX_PROMPT_TOKENS:
        # naive truncation: keep last lines (recent changes), could be improved
        _log.warning(
            "Diff token count %d exceeds %d – truncating",
            token_count,
            _MAX_PROMPT_TOKENS,
        )
        # keep roughly allowed tokens worth of characters (approx 4 chars/token)
        max_chars = _MAX_PROMPT_TOKENS * 4
        diff_text = diff_text[-max_chars:]

    system_prompt = """You are a meticulous senior software engineer tasked with reviewing pull-requests.
Provide a concise summary of changes, point out potential bugs, security issues, and suggest improvements.
Respond in markdown bullet-points."""

    user_prompt = f"""Here is the diff to review:
```diff
{diff_text}
```
"""

    _log.debug("Sending diff (%d tokens) to LLM", estimate_tokens(user_prompt))

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = openai_chat(messages, model=model, temperature=temperature)
    except Exception as exc:
        _log.error("LLM request failed: %s", exc)
        raise

    return response


# -----------------------------
# CLI wrapper (Typer sub-app)
# -----------------------------

# CLI is added dynamically in src.__main__ to avoid Typer import overhead here.

def _cli(repo_path: Path, commit_range: str, model: str, verbose: bool):
    from .logger import setup_logging

    setup_logging("DEBUG" if verbose else "INFO")

    content = summarize_diff(repo_path, commit_range, model)
    import sys

    sys.stdout.write("\n--- LLM Review ---\n\n")
    sys.stdout.write(content + "\n") 