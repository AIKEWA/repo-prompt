"""Light-weight helpers for interacting with Git repositories.

While :pymod:`git` (GitPython) offers a rich API, this wrapper exposes a
minimal surface tailored for the Repo-Prompt workflow:

* staging files touched by an LLM patch
* committing changes with a conventional message template
* creating temporary feature branches for safe experimentation

All functions are defensive – they raise on unexpected states rather than
silently discarding errors – and emit structured logs for observability.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from git import Repo, Actor  # type: ignore

from .logger import get_logger

_log = get_logger(__name__)

__all__ = [
    "ensure_clean_worktree",
    "stage_and_commit",
    "create_feature_branch",
]


def ensure_clean_worktree(repo_path: str | Path) -> None:
    """Raise ``RuntimeError`` if the repository is not in a clean state.

    A *clean* work-tree means no uncommitted changes or untracked files that
    could be unintentionally overwritten by an LLM-generated patch.
    """

    repo = Repo(Path(repo_path))
    if repo.is_dirty(untracked_files=True):
        raise RuntimeError(
            "Git work-tree has uncommitted changes. Commit or stash them "
            "before running the edit command."
        )


def create_feature_branch(repo_path: str | Path, name: str | None = None) -> str:
    """Create and checkout a new feature branch derived from ``main`` (or current).

    Parameters
    ----------
    repo_path:
        Path to the Git repository.
    name:
        Optional branch name. A timestamp-based fallback will be generated if
        *None*.

    Returns
    -------
    str
        The name of the newly created branch.
    """

    from datetime import datetime
    repo = Repo(Path(repo_path))

    target_name = name or f"llm-patch/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    if target_name in repo.heads:
        raise ValueError(f"Branch {target_name!r} already exists")

    _log.info("Creating feature branch %s", target_name)
    new_branch = repo.create_head(target_name)
    new_branch.checkout()
    return target_name


def stage_and_commit(repo_path: str | Path, files: List[Path], message: str) -> str:
    """Stage *files* and commit with *message*.

    The *author* and *committer* identities default to the locally configured
    Git settings but can be overridden via the ``GIT_AUTHOR_NAME`` /
    ``GIT_AUTHOR_EMAIL`` environment variables for CI workflows.

    Returns the hexsha of the created commit.
    """

    repo = Repo(Path(repo_path))

    # Convert to relative POSIX paths expected by GitPython
    rel_paths = [str(p.relative_to(repo.working_tree_dir)) for p in files]
    if not rel_paths:
        raise ValueError("Nothing to commit – no files provided")

    # Stage
    _log.debug("Staging files: %s", rel_paths)
    repo.index.add(rel_paths)

    # Commit
    _log.info("Creating commit: %s", message.split("\n", 1)[0])
    author = Actor.from_environment()
    commit = repo.index.commit(message, author=author, committer=author)
    return commit.hexsha