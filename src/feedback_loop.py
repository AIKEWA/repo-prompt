from __future__ import annotations

"""Bi-weekly feedback & iteration utilities (Step 2.10).

This module **automates** collection of qualitative insights every two weeks
and stores them in the :pymod:`src.feedback_mechanism.FeedbackStore` so that
other analytics layers can aggregate them.

Implemented data sources
------------------------
1. **GitHub Issues** – pulls open issues and feature requests for a given
   repository using the *REST v3* API.
2. **Notion boards** – optional integration that fetches database items via
   Notion's public HTTP API (read-only).  The Notion feature is *opt-in* and
   skipped automatically when the required environment variables are absent.

Security & Ethics
-----------------
* All tokens are loaded from environment variables (`GITHUB_TOKEN`,
  `NOTION_TOKEN`).  They are **never** logged or written to disk.
* The GitHub query filters only public metadata (title, labels, state) – no
  private user information is persisted.
* The Notion integration respects the human-readability of board items and
  stores only the *title* and *status* properties.

CLI Usage
---------
>>> python -m src.feedback_loop collect --repo octocat/Hello-World
>>> python -m src.feedback_loop notion --database $NOTION_DB_ID

Run these commands from **cron** or CI to establish continuous bi-weekly
feedback loops.

"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import typer

# Local imports – keep them lazy to avoid circular deps in runtime usage
from .feedback_mechanism import FeedbackStore, IssueSuggestion
from .logger import get_logger, setup_logging

__all__ = [
    "GitHubClient",
    "NotionClient",
    "collect_github_feedback",
    "collect_notion_feedback",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helper clients (minimal – dependency-free)
# ---------------------------------------------------------------------------

class GitHubClient:
    """Tiny wrapper around GitHub REST v3 for *issue* retrieval only."""

    API_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self._session = requests.Session()
        if self.token:
            self._session.headers.update({"Authorization": f"Bearer {self.token}"})
        self._session.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "repo-prompt/feedback-loop"})

    # -----------------
    # Public helpers
    # -----------------

    def fetch_issues(self, repo: str, state: str = "open", since_days: int = 14) -> List[Dict[str, Any]]:
        """Return *issues* (including PRs) updated within the last *since_days*.

        Parameters
        ----------
        repo:
            Repository spec in the form ``owner/name``.
        state:
            ``open`` (default), ``closed`` or ``all``.
        since_days:
            Restrict to issues *updated_at* within that look-back window.
        """

        # Basic sanitisation – avoid SSRF/DoS with crafted repo strings
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("repo must be in the form 'owner/name' (alphanum + .-_)")

        url = f"{self.API_URL}/repos/{repo}/issues"
        params = {
            "state": state,
            "since": (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat(),
            "per_page": 100,
        }

        issues: List[Dict[str, Any]] = []
        page = 1
        while True:
            resp = self._session.get(url, params={**params, "page": page})
            resp.raise_for_status()
            batch = resp.json()
            issues.extend(batch)
            # Link header – if no *next* rel stop.
            if "next" not in resp.links:
                break
            page += 1
        _log.info("Fetched %d GitHub issues from %s", len(issues), repo)
        return issues


class NotionClient:
    """Read-only Notion database wrapper (minimal)."""

    API_URL = "https://api.notion.com/v1/databases/{db_id}/query"

    def __init__(self, token: Optional[str] = None, version: str = "2022-06-28") -> None:
        self.token = token or os.getenv("NOTION_TOKEN")
        if not self.token:
            raise EnvironmentError("NOTION_TOKEN env var required for Notion integration")
        self.version = version
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": version,
                "Content-Type": "application/json",
            }
        )

    def fetch_items(self, database_id: str, since_days: int = 14) -> List[Dict[str, Any]]:
        """Return pages **created or edited** within the look-back window."""

        payload = {
            "filter": {
                "timestamp": "last_edited_time",
                "last_edited_time": {
                    "on_or_after": (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
                },
            }
        }
        url = self.API_URL.format(db_id=database_id)
        resp = self._session.post(url, json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        _log.info("Fetched %d Notion pages from database %s", len(results), database_id)
        return results


# ---------------------------------------------------------------------------
# Collection helpers – convert external feedback to IssueSuggestion events
# ---------------------------------------------------------------------------

def _issue_from_github(data: Dict[str, Any]) -> IssueSuggestion:
    labels = [l["name"] for l in data.get("labels", [])]
    issue_type = "feature" if "enhancement" in labels else "bug" if "bug" in labels else "other"

    return IssueSuggestion(
        issue_type=issue_type,
        description=data.get("title", "Untitled issue"),
        reported_by=(data.get("user") or {}).get("login"),
        status=data.get("state"),
    )


def _issue_from_notion(page: Dict[str, Any]) -> IssueSuggestion:
    props = page.get("properties", {})
    title = _extract_rich_text(props, "Name") or "Untitled Notion page"
    status = _extract_select(props, "Status") or None
    return IssueSuggestion(issue_type="other", description=title, status=status, reported_by="notion")


def _extract_rich_text(props: Dict[str, Any], key: str) -> Optional[str]:
    prop = props.get(key, {})
    for txt in prop.get("rich_text", []):
        if content := txt.get("plain_text"):
            return content
    return None


def _extract_select(props: Dict[str, Any], key: str) -> Optional[str]:
    prop = props.get(key, {})
    if sel := prop.get("select"):
        return sel.get("name")
    return None


# -----------------------------
# Public orchestrator helpers
# -----------------------------

def collect_github_feedback(repo: str, store: FeedbackStore, *, since_days: int = 14) -> None:
    """Convert **GitHub issues** into :class:`IssueSuggestion` events."""

    gh = GitHubClient()
    issues = gh.fetch_issues(repo, since_days=since_days)
    for itm in issues:
        # Skip pull requests (they have pull_request key)
        if "pull_request" in itm:
            continue
        store.append(_issue_from_github(itm))


def collect_notion_feedback(database_id: str, store: FeedbackStore, *, since_days: int = 14) -> None:
    """Convert **Notion database items** into :class:`IssueSuggestion` events."""

    try:
        notion = NotionClient()
    except EnvironmentError as exc:
        _log.warning("%s – skipping Notion sync", exc)
        return
    pages = notion.fetch_items(database_id, since_days=since_days)
    for pg in pages:
        store.append(_issue_from_notion(pg))


# ---------------------------------------------------------------------------
# Typer CLI wrapper
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Bi-weekly feedback collectors (Step 2.10)")


@app.command()
def collect(
    repo: str = typer.Option(..., "--repo", "-r", help="GitHub repository 'owner/name'"),
    store_path: Path = typer.Option(".feedback.jsonl", "--store", help="Feedback JSONL path"),
    since: int = typer.Option(14, "--since", help="Look-back window (days)"),
    database: Optional[str] = typer.Option(None, "--notion-db", help="Notion database ID (optional)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Collect feedback from **GitHub** (and optionally **Notion**) within *since* days."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = FeedbackStore(store_path)

    collect_github_feedback(repo, store, since_days=since)
    if database:
        collect_notion_feedback(database, store, since_days=since)

    _log.info("Done – aggregated stats: %s", json.dumps(store.aggregate(), indent=2))


@app.callback()
def _main(ctx: typer.Context):  # noqa: D401 – imperative mood
    """Feedback loop CLI grouping remote *collect* sub-commands."""


if __name__ == "__main__":
    # Enable `python -m src.feedback_loop collect ...`
    app()