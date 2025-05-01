from __future__ import annotations

"""Granular Review UX – checkbox-style per-edit preview.

This utility converts a *multi-file unified diff* into an **interactive**
terminal checklist, allowing reviewers to approve **each hunk** individually
before applying.  It integrates with :pymod:`src.diff_patch` &
:pyfunc:`src.patch_apply.apply_patch_set`.

Why?
-----
Reduces *repeat cycles* by letting humans cherry-pick safe changes and quickly
bounce back suggestions for risky ones.

Implementation constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~
* Pure *Typer* + *InquirerPy* (optional dependency) – falls back to simple Y/N
  prompts when the library is unavailable.
* Avoids heavy TUI frameworks to stay lean.
"""

from pathlib import Path
from typing import List, Dict
import sys
import re
import typer

from .diff_patch import apply_unified_patch, unified_diff
from .patch_apply import split_diff_by_file, apply_patch_set
from .logger import get_logger, setup_logging

try:
    from InquirerPy import inquirer  # type: ignore
except ImportError:  # graceful fallback
    inquirer = None  # type: ignore

__all__ = [
    "interactive_review",
    "app",
]

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Interactive review helper
# ---------------------------------------------------------------------------

def _prompt_choice(message: str) -> bool:
    if inquirer:
        return inquirer.confirm(message, default=True).execute()
    return typer.confirm(message, default=True)


def interactive_review(patch_str: str, repo_root: Path | str = ".") -> List[str]:
    """Present each *hunk* to the user for approval before applying.

    Returns list of files that were modified.
    """

    repo_root = Path(repo_root)
    file_patches = split_diff_by_file(patch_str)
    approved_patches: Dict[str, str] = {}

    for path, diff in file_patches.items():
        _log.info("Reviewing %s", path)
        hunks = re.split(r"(^@@.*?@@$)", diff, flags=re.M)
        # hunks list alternates between header+body blocks, we rejoin pairs
        combined: List[str] = []
        for i in range(1, len(hunks), 2):
            combined.append(hunks[i] + hunks[i + 1])

        approved_hunks: List[str] = []
        for hunk in combined:
            print("\n" + hunk)
            if _prompt_choice("Apply this hunk?"):
                approved_hunks.append(hunk)

        if approved_hunks:
            header = "\n".join(diff.splitlines()[:2])  # keep --- +++ lines
            approved_patches[path] = header + "\n" + "\n".join(approved_hunks)

    if not approved_patches:
        _log.info("No changes approved – exiting")
        return []

    combined_patch = "\n".join(approved_patches.values())
    modified = apply_patch_set(repo_root, combined_patch, dry_run=False, create_backup=True)
    return modified


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Granular review of patch hunks")


@app.command()
def review(
    patch_file: Path = typer.Argument(..., help="Unified diff to review ('-' for STDIN)"),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run interactive checklist review for *patch_file*."""

    setup_logging("DEBUG" if verbose else "INFO")

    patch_str = sys.stdin.read() if str(patch_file) == "-" else patch_file.read_text()
    modified = interactive_review(patch_str, repo)
    typer.secho(f"Patched {len(modified)} files", fg="green")


if __name__ == "__main__":
    app()