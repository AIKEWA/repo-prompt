"""Real-world environment analyzer.

This module extracts local development environment specifics to be embedded into
LLM prompts or telemetry. It is the *code translation* of the theoretical step
«1.2 Analyze Real-World Context» from the project spec.

Usage example
-------------
```python
from pathlib import Path
from context_analyzer import analyze_context
ctx = analyze_context(Path.cwd())
print(ctx)
```

The output is a dict ready for JSON or XML serialization containing the keys
``environment``, ``needs`` and ``constraints``.

Security notes
--------------
The analyzer purposely avoids collecting sensitive or personal data. Remote URL
sanitization replaces potential credentials with placeholders.
"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import sys

from git import Repo  # type: ignore

from .logger import get_logger

_log = get_logger(__name__)

# -----------------------
# Public API
# -----------------------


def analyze_context(repo_path: str | Path) -> Dict[str, Any]:
    """Return a structured description of the local dev environment.

    Parameters
    ----------
    repo_path:
        Path to a Git repository whose state should be factored into the
        context. The function tolerates non-git directories by omitting Git
        fields.
    """

    _log.debug("Analyzing environment for %s", repo_path)

    environment = _gather_env_details()
    git_info = _gather_git_details(repo_path)
    environment.update(git_info)

    # Static interpretation of *needs* and *constraints* based on the spec.
    needs = [
        "Streamlined LLM integration for multi-file editing",
        "Enhanced commit workflows",
        "Privacy in enterprise settings",
    ]

    constraints = [
        "Model latency",
        "Learning curve for prompt structuring",
        "Team onboarding",
    ]

    context: Dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": environment,
        "needs": needs,
        "constraints": constraints,
    }

    _log.debug("Context produced: %s", context)
    return context


# -----------------------
# Internal helpers
# -----------------------


def _gather_env_details() -> Dict[str, Any]:
    """Collect OS, Python and shell details."""

    return {
        "os": {
            "platform": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "shell": os.getenv("SHELL", "unknown"),
        # Additional workflow details in line with the spec (macOS, terminal-centric workflows)
        "terminal": {
            "program": os.getenv("TERM_PROGRAM", "unknown"),
            "interactive": sys.stdout.isatty(),
        },
    }


def _gather_git_details(repo_path: str | Path) -> Dict[str, Any]:
    """Describe Git repository status, if applicable."""

    p = Path(repo_path)
    if not (p / ".git").exists():
        _log.warning("%s is not a Git repository – skipping git context", p)
        return {}

    repo = Repo(str(p))

    def _sanitize_remote(url: str) -> str:
        # Strip potential credentials from HTTP(S) URLs
        if "@" in url and (url.startswith("http://") or url.startswith("https://")):
            credential_part, rest = url.split("@", 1)
            # keep protocol ("https://") and rest path
            protocol = credential_part.split("//", 1)[0] + "//"
            return protocol + rest
        return url

    remotes = {_r.name: _sanitize_remote(_r.url) for _r in repo.remotes}

    status = {
        "active_branch": repo.active_branch.name if not repo.head.is_detached else "DETACHED_HEAD",
        "is_dirty": repo.is_dirty(),
        "untracked_files": bool(repo.untracked_files),
        "latest_commit": repo.head.commit.hexsha[:7],
    }

    return {
        "git": {
            "remotes": remotes,
            "status": status,
        }
    } 