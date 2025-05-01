from __future__ import annotations

"""Diff Mode (ACT) – Context-aware diffing & application.

This module exposes an *assistant-commit-tool* (ACT) style workflow:

1. **Compute** a diff between *original* and *modified* text.
2. **Preview** the diff with syntax colouring (optional).
3. **Apply** the diff to the file system through :pyfunc:`src.patch_apply.apply_patch_set`.

Compared to generic `git diff`, the helper understands *token budget* and can
truncate hunks to keep assistant prompts concise (only include *N* context
lines instead of full files).

CLI example
-----------
```
$ python -m src.diff_mode compute path/to/file.py <new_content.py > changes.diff
$ python -m src.diff_mode apply --patch-file changes.diff --yes
```

Design goals
~~~~~~~~~~~~
* **Lower I/O** – by default includes 3 context lines (configurable) similar to
  unified diff `-U3`.
* **Developer Review** – integrates with :pymod:`src.diff_review_standards` to
  block suspicious patches unless `--force` is provided.
* **Batch Mode** – supports multi-file patches; delegates to
  :pyfunc:`src.patch_apply.apply_patch_set` for atomic writes.
"""

from pathlib import Path
import sys
import difflib
import typer
from typing import List

from .logger import get_logger, setup_logging
from .diff_review_standards import lint_diff
from .patch_apply import apply_patch_set

__all__ = [
    "compute_diff",
    "apply_diff",
    "app",
]

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def compute_diff(original: str | List[str], modified: str | List[str], *, fromfile: str = "a/file", tofile: str = "b/file", context: int = 3) -> str:
    """Return unified diff string with *context* lines."""

    if isinstance(original, str):
        original = original.splitlines(keepends=True)
    if isinstance(modified, str):
        modified = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(original, modified, fromfile=fromfile, tofile=tofile, lineterm="", n=context)
    return "\n".join(diff)


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="ACT – diff compute/preview/apply")


@app.command()
def compute(
    file: Path = typer.Argument(..., help="Path to original file"),
    new_file: Path | None = typer.Option(None, "--new", help="File with modified content (defaults to STDIN)"),
    context: int = typer.Option(3, "-U", "--context", help="Context lines (default 3)"),
):
    """Compute diff between *file* and *new_file* or STDIN and print to STDOUT."""

    original_text = file.read_text()
    if new_file:
        modified_text = new_file.read_text()
    else:
        modified_text = sys.stdin.read()

    diff = compute_diff(original_text, modified_text, fromfile=str(file), tofile=str(file), context=context)
    print(diff)


@app.command()
def apply(
    patch_file: Path = typer.Argument(..., help="Unified diff file ('-' for STDIN)"),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository root"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation & lint checks"),
    force: bool = typer.Option(False, "--force", help="Apply even when linter blocks"),
    backup: bool = typer.Option(False, "--backup", help="Create .bak backups before overwrite"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Apply a diff patch after optional linter approval."""

    setup_logging("DEBUG" if verbose else "INFO")

    diff_text = sys.stdin.read() if str(patch_file) == "-" else patch_file.read_text()

    if not yes:
        issues = lint_diff(diff_text)
        if issues and not force:
            _log.error("Patch blocked by linter:\n%s", "\n".join(f"- {i}" for i in issues))
            raise typer.Exit(code=1)
        if issues:
            typer.secho("⚠ Linter issues detected", fg="yellow")
            for i in issues:
                typer.echo(f"- {i}")
        confirm = typer.confirm("Apply patch?", default=False)
        if not confirm:
            raise typer.Exit(code=0)

    modified = apply_patch_set(repo, diff_text, dry_run=False, create_backup=backup)
    typer.secho(f"Applied patch to {len(modified)} file(s)", fg="green")


if __name__ == "__main__":  # pragma: no cover
    app()