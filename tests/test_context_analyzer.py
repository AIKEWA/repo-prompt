import os
import sys
from pathlib import Path

# Ensure project root is on sys.path **before** importing project modules
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.context_analyzer import analyze_context

import pytest


@pytest.fixture
def dummy_git_repo(tmp_path: Path):
    """Create a temporary git repository with a remote URL containing credentials."""
    from git import Repo
    repo = Repo.init(tmp_path)
    # Create initial commit
    (tmp_path / "README.md").write_text("hello")
    repo.index.add(["README.md"])
    repo.index.commit("init")

    # Add a remote that contains creds which should be sanitized
    repo.create_remote("origin", url="https://user:password@example.com/repo.git")
    yield tmp_path


def test_analyze_context_keys(dummy_git_repo: Path):
    ctx = analyze_context(dummy_git_repo)

    # Top-level keys
    assert {"timestamp", "environment", "needs", "constraints"} <= ctx.keys()

    # Environment details should include os, python, shell, terminal
    env = ctx["environment"]
    for k in ("os", "python", "shell", "terminal"):
        assert k in env



def test_remote_url_sanitization(dummy_git_repo: Path):
    ctx = analyze_context(dummy_git_repo)
    remotes = ctx["environment"]["git"]["remotes"]
    origin_url = remotes["origin"]

    # Should not contain credentials
    assert "user:password" not in origin_url
    assert origin_url.startswith("https://") 