from __future__ import annotations

"""Automated changelog generator (optional Step – *Standardised Change Log*).

This module assembles a markdown changelog from Git commit history.  It offers
**two modes**:

1. *Conventional* – uses commit messages directly (supports Conventional Commits
   parsing for grouping).
2. *LLM-assisted* – summarises commits via `openai_chat` when an API key is
   available.  The fallback ensures the command always works even offline.

Public API
~~~~~~~~~~~
* :func:`generate_changelog` – returns a markdown string.
* CLI – ``python -m src.changelog [options]``

The implementation aligns with the existing architecture (logging, GitPython
usage, Typer CLI embedding via ``src.__main__``).
"""

from pathlib import Path
from typing import List, Dict
from collections import defaultdict
import os
import re
from datetime import datetime

from git import Repo  # type: ignore

from .logger import get_logger
from .model_interface import openai_chat
from .feedback_mechanism import FeedbackStore, IssueSuggestion  # type: ignore

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONVENTIONAL_RE = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|chore)(?:\([^)]*\))?:\s*(.*)", re.IGNORECASE)


def _group_commits(commits: List[str]) -> Dict[str, List[str]]:
    """Group commit messages by Conventional Commits *type*."""

    groups: Dict[str, List[str]] = defaultdict(list)
    for msg in commits:
        m = _CONVENTIONAL_RE.match(msg)
        if m:
            groups[m.group(1).lower()].append(m.group(2).strip())
        else:
            groups["other"].append(msg.strip())
    return groups


_SYSTEM_PROMPT = (
    "You are an expert release manager. Create a concise, well-formatted markdown changelog "
    "from the following commit messages. Group similar changes and use bullet points. "
    "Do NOT invent features – only summarise what is present."
)


def _collect_top_requests(store: FeedbackStore, start_dt: datetime, end_dt: datetime, top_n: int = 3) -> List[IssueSuggestion]:
    """Return *top_n* IssueSuggestions in the given datetime interval (inclusive).

    *Top* is defined by order of occurrence (first created) but could be
    enhanced in the future (e.g. reaction counts).
    """

    issues = [
        ev for ev in store._load_events()
        if isinstance(ev, IssueSuggestion)
           and start_dt <= datetime.fromisoformat(ev.created_at.rstrip("Z")) <= end_dt
    ]
    # sort by created_at
    issues.sort(key=lambda i: i.created_at)
    return issues[:top_n]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_changelog(
    repo_path: Path | str = Path("."),
    from_ref: str | None = None,
    to_ref: str = "HEAD",
    llm: bool = False,
    model: str = "gpt-3.5-turbo",
    feedback_store: Path | None = None,
) -> str:
    """Return a markdown changelog for *from_ref..to_ref* (inclusive).

    Parameters
    ----------
    repo_path:
        Git repository root.
    from_ref:
        Starting revision (exclusive).  If *None*, uses the last git tag.
    to_ref:
        Ending revision (inclusive), default ``HEAD``.
    llm:
        If *True* and an API key is present, summarise via OpenAI chat.
    model:
        Model name for LLM summarisation.
    feedback_store:
        Path to the feedback store.
    """

    try:
        repo = Repo(Path(repo_path))
    except Exception as exc:
        from git import InvalidGitRepositoryError, NoSuchPathError  # type: ignore

        if isinstance(exc, (InvalidGitRepositoryError, NoSuchPathError)):
            raise RuntimeError("No Git repository detected. Please initialise one with 'git init' in your project folder.") from exc
        raise

    if from_ref is None:
        # fallback to the latest tag if available
        tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime)
        from_ref = tags[-1].name if tags else "HEAD~20"  # last 20 commits as fallback
        _log.info("Using %s as starting ref", from_ref)

    rev_range = f"{from_ref}..{to_ref}"
    _log.info("Collecting commits in range %s", rev_range)

    commits = [
        c.message.split("\n", 1)[0]  # first line (subject)
        for c in repo.iter_commits(rev_range)
    ]
    commits.reverse()  # chronological order

    if not commits:
        _log.warning("No commits found in range %s", rev_range)
        return "### Changelog\n\n_No changes_"

    if llm and os.getenv("OPENAI_API_KEY"):
        _log.info("Generating LLM-assisted changelog (%d commits)", len(commits))
        user_prompt = "\n".join(f"- {m}" for m in commits)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        summary = openai_chat(messages, model=model)
        return summary

    # conventional grouping fallback
    grouped = _group_commits(commits)
    md_parts: List[str] = ["### Changelog", ""]
    order = ["feat", "fix", "docs", "refactor", "perf", "test", "chore", "style", "other"]
    for kind in order:
        items = grouped.get(kind)
        if not items:
            continue
        header = kind.capitalize() if kind != "feat" else "Features"
        md_parts.append(f"#### {header}")
        md_parts.extend(f"- {item}" for item in items)
        md_parts.append("")

    # Integrate top 3 improvement requests if feedback store specified
    if feedback_store is not None:
        store = FeedbackStore(feedback_store)
        # Use commit date range for approximate period
        start_dt = repo.commit(from_ref).committed_datetime
        end_dt = repo.commit(to_ref).committed_datetime
        top_reqs = _collect_top_requests(store, start_dt, end_dt)
        if top_reqs:
            md_parts.append("### Top improvement requests (feedback)")
            for req in top_reqs:
                md_parts.append(f"- {req.description} ({req.issue_type}) – status: {req.status or 'open'}")
            md_parts.append("")

    return "\n".join(md_parts).rstrip()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, sys

    p = argparse.ArgumentParser(description="Generate markdown changelog from git history")
    p.add_argument("--repo", type=Path, default=Path("."), help="Git repository path")
    p.add_argument("--from", dest="from_ref", help="Start revision (exclusive). Defaults to last tag.")
    p.add_argument("--to", dest="to_ref", default="HEAD", help="End revision (inclusive)")
    p.add_argument("--llm", action="store_true", help="Use OpenAI summarisation if key present")
    p.add_argument("--model", default="gpt-3.5-turbo", help="OpenAI model name")
    args = p.parse_args()

    from .logger import setup_logging

    setup_logging()
    md = generate_changelog(args.repo, args.from_ref, args.to_ref, args.llm, args.model)
    sys.stdout.write(md + "\n") 