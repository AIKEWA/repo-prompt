"""
Large-scale identifier refactoring helper (Use Case: *Large refactors across files*).

This module provides a **cognitive-aware** workflow for renaming an identifier
across an entire Python repository while *minimising working-memory load* for
humans.  It leverages :pymod:`src.codemaps` to build an in-memory representation
of the project, visualises the impacted files, and then generates a *single
multi-file diff* that can be reviewed or applied via
:pymod:`src.patch_apply.apply_patch_set`.

Key features
------------
1. **CodeMap visualisation** – quickly see where the identifier occurs.
2. **Preview mode** – output a unified diff for inspection / PR creation.
3. **Apply mode** – patch the repository in-place with optional backups.

Limitations
~~~~~~~~~~~
* The replacement uses a *regex word-boundary* search which is **syntax-agnostic**.
  False-positives inside strings or comments may occur.  For complex refactors
  consider AST-based tools.  This helper aims for *80 % quick wins*.

Security considerations
~~~~~~~~~~~~~~~~~~~~~~~
* Only text processing – no dynamic code execution.
* Backups can be enabled (`--backup`) to safeguard against unwanted changes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import typer

from .codemaps import map_repository
from .diff_patch import unified_diff
from .patch_apply import apply_patch_set
from .logger import get_logger, setup_logging

__all__ = [
    "preview_refactor",
    "apply_refactor",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_candidate_files(repo_root: Path) -> List[Path]:
    """Return a list of *Python* files within *repo_root* using CodeMap.

    Leveraging :pymod:`src.codemaps` keeps this in line with the broader repo
    visualisation strategy and avoids duplicate walking logic.
    """

    cm = map_repository(repo_root, include_pattern=r"\.py$")

    paths: List[Path] = []

    def _walk(nodes):  # nested helper
        from src.codemaps import FileNode, DirNode  # local import to avoid cycles

        for n in nodes:
            if isinstance(n, FileNode):
                paths.append(Path(n.path))
            elif isinstance(n, DirNode):
                _walk(n.children)

    _walk([cm.root_node])
    return paths


def _replace_identifier(text: str, old: str, new: str) -> str:
    """Return *text* where **whole-word** occurrences of *old* are replaced by *new*."""

    pattern = re.compile(rf"\b{re.escape(old)}\b")
    return pattern.sub(new, text)


def _build_refactor_patch(repo_root: Path, old: str, new: str) -> str:
    """Generate a *unified diff* covering all replacements across the repo."""

    patches: List[str] = []
    for file_path in _collect_candidate_files(repo_root):
        try:
            original = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            _log.debug("Skipping non-utf-8 file %s", file_path)
            continue

        modified = _replace_identifier(original, old, new)
        if original == modified:
            continue  # no change needed

        diff = unified_diff(
            original,
            modified,
            fromfile=f"a/{file_path.relative_to(repo_root)}",
            tofile=f"b/{file_path.relative_to(repo_root)}",
        )
        patches.append(diff)

    return "\n".join(patches)


# ---------------------------------------------------------------------------
# Public API helpers (callable from other modules)
# ---------------------------------------------------------------------------


def preview_refactor(repo_root: Path | str, old: str, new: str) -> str:
    """Return the diff that *would* be applied when renaming *old* → *new*."""

    repo_root = Path(repo_root).resolve()
    return _build_refactor_patch(repo_root, old, new)


def apply_refactor(
    repo_root: Path | str,
    old: str,
    new: str,
    *,
    dry_run: bool = True,
    backup: bool = False,
) -> List[str]:
    """Preview (*dry_run=True*) or apply the identifier rename across the repo."""

    repo_root = Path(repo_root).resolve()
    patch_text = _build_refactor_patch(repo_root, old, new)
    if not patch_text.strip():
        _log.info("No occurrences of '%s' found – nothing to do", old)
        return []

    return apply_patch_set(repo_root, patch_text, dry_run=dry_run, create_backup=backup)


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Rename an identifier across the project with diff preview/apply.")


@app.command()
def rename(
    old: str = typer.Argument(..., help="Current identifier name (exact, case-sensitive)"),
    new: str = typer.Argument(..., help="Desired new identifier"),
    repo_path: Path = typer.Option(Path("."), "--repo", help="Repository root (default cwd)"),
    apply: bool = typer.Option(False, "--apply", help="Write changes instead of preview"),
    backup: bool = typer.Option(False, "--backup", help="Create *.bak files before overwriting"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable summary"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI wrapper around :func:`apply_refactor`.

    Example::

        # Preview diff
        python -m src.large_refactor rename foo bar --repo .

        # Apply with backups
        python -m src.large_refactor rename old_func new_func --apply --backup
    """

    setup_logging("DEBUG" if verbose else "INFO")

    repo_path = repo_path.resolve()
    if not repo_path.is_dir():
        typer.echo(f"Error: {repo_path} is not a directory", err=True)
        raise typer.Exit(code=1)

    if not apply:
        diff = preview_refactor(repo_path, old, new)
        if diff:
            typer.echo(diff)
        else:
            typer.echo("No changes necessary – identifier not found.")
    else:
        modified = apply_refactor(repo_path, old, new, dry_run=False, backup=backup)
        if json_output:
            import json, sys

            json.dump({"modified": modified}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            typer.echo(f"{len(modified)} file(s) updated.")