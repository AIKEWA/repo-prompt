from __future__ import annotations

"""Multi-file diff parser & applier.

This module compliments :pymod:`src.diff_patch` by adding **repository-level**
patch application utilities – a missing piece required by *Step 1.5 –
Implementation Plan* ("Result Preview" & "Change Application").

Key features
------------
1. **Split unified patches** that span multiple files into per-file chunks.
2. **Dry-run preview** – print coloured output showing which files would be
   modified without touching disk.
3. **Apply patches** atomically (best-effort) with optional backup creation so
   changes can be rolled back.

The implementation purposefully avoids external dependencies – it builds upon
:pyfunc:`src.diff_patch.apply_unified_patch` for the heavy lifting.

Example usage (library):
    >>> from pathlib import Path
    >>> from src.patch_apply import apply_patch_set
    >>> diff_text = Path("changes.diff").read_text()
    >>> report = apply_patch_set(Path("./repo"), diff_text, dry_run=True)

Command-line usage:
    $ python -m src.patch_apply --patch-file changes.diff --apply

"""

from pathlib import Path
from typing import Dict, List
import sys

from .diff_patch import apply_unified_patch
from .logger import get_logger, setup_logging

__all__ = [
    "split_diff_by_file",
    "apply_patch_set",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Patch parsing helpers
# ---------------------------------------------------------------------------

def _strip_prefix(path: str) -> str:
    """Return *path* stripped of leading ``a/`` or ``b/`` prefixes."""
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def split_diff_by_file(patch_str: str) -> Dict[str, str]:
    """Split a *multi-file* unified diff string into per-file patches.

    Parameters
    ----------
    patch_str:
        A unified diff (e.g. produced by ``git diff``) possibly containing
        multiple file sections.

    Returns
    -------
    dict
        Mapping of *relative file path* → *full diff block for that file*.
    """

    file_patches: Dict[str, List[str]] = {}
    current_path: str | None = None
    current_lines: List[str] = []

    lines = patch_str.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- ") and (i + 1) < len(lines) and lines[i + 1].startswith("+++ "):
            # New file diff starts – flush previous
            if current_path is not None:
                file_patches[current_path] = "\n".join(current_lines)
                current_lines = []
            # Extract paths from header
            from_path = line[4:].strip()
            to_path = lines[i + 1][4:].strip()

            # Prefer *to_path* (b/) when file exists, else *from_path*
            header_path = _strip_prefix(to_path if to_path != "/dev/null" else from_path)
            current_path = header_path if header_path != "/dev/null" else _strip_prefix(from_path)

            # Start accumulating with header lines
            current_lines.append(line)
            current_lines.append(lines[i + 1])
            i += 2
            continue
        # Regular diff content
        if current_path is not None:
            current_lines.append(line)
        i += 1
    # Flush last file
    if current_path is not None and current_lines:
        file_patches[current_path] = "\n".join(current_lines)

    return file_patches


# ---------------------------------------------------------------------------
# Public apply function
# ---------------------------------------------------------------------------

def apply_patch_set(
    repo_path: Path | str,
    patch_str: str,
    *,
    dry_run: bool = True,
    create_backup: bool = False,
    encoding: str = "utf-8",
) -> List[str]:
    """Apply a multi-file *patch_str* to *repo_path*.

    Parameters
    ----------
    repo_path:
        Repository (or project) root directory.
    patch_str:
        Unified diff covering one or more files.
    dry_run:
        If *True* (default) the function performs a **preview only** and does
        **not** write changes.  Set to *False* to perform the write.
    create_backup:
        When *True* a ``.bak`` sibling file is written *before* mutating the
        original file. Ignored when *dry_run* is *True*.
    encoding:
        File encoding (default UTF-8).

    Returns
    -------
    list[str]
        List of file paths (relative to *repo_path*) that would be / were
        modified.
    """

    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        raise ValueError(f"{repo_path} is not a directory")

    file_patches = split_diff_by_file(patch_str)
    modified: List[str] = []

    for rel_path, single_patch in file_patches.items():
        target = repo_path / rel_path
        orig_text = ""
        if target.exists():
            orig_text = target.read_text(encoding=encoding)
        else:
            _log.info("Creating new file %s", rel_path)

        try:
            new_text = apply_unified_patch(orig_text, single_patch)
        except Exception as exc:
            _log.error("Failed to apply patch for %s: %s", rel_path, exc)
            raise

        modified.append(rel_path)
        if dry_run:
            _log.debug("[DRY-RUN] %s would be updated (∆ %d chars)", rel_path, len(new_text) - len(orig_text))
            continue

        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)
        if create_backup and target.exists():
            backup_path = target.with_suffix(target.suffix + ".bak")
            target.replace(backup_path)
            _log.debug("Backup written to %s", backup_path)

        target.write_text(new_text, encoding=encoding)
        _log.info("Patched %s (%d bytes)", rel_path, len(new_text.encode(encoding)))

    return modified


# ---------------------------------------------------------------------------
# CLI entry-point – lightweight to avoid extra deps
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, textwrap, json

    parser = argparse.ArgumentParser(description="Preview or apply a unified diff to the local repository")
    parser.add_argument("--patch-file", type=Path, required=False, default=None, help="Path to diff file. Reads stdin if omitted or '-' ")
    parser.add_argument("--repo-path", type=Path, default=Path("."), help="Repository root (default current dir)")
    parser.add_argument("--apply", action="store_true", help="Actually write changes. Otherwise dry-run preview.")
    parser.add_argument("--backup", action="store_true", help="Create *.bak backups before overwriting")
    parser.add_argument("--json", action="store_true", help="Output JSON summary instead of human text")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    setup_logging("DEBUG" if args.verbose else "INFO")

    if args.patch_file is None or str(args.patch_file) == "-":
        diff_text = sys.stdin.read()
    else:
        diff_text = Path(args.patch_file).read_text()

    result = apply_patch_set(args.repo_path, diff_text, dry_run=not args.apply, create_backup=args.backup)

    if args.json:
        json.dump({"modified": result, "dry_run": not args.apply}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        mode = "would be" if not args.apply else "were"
        if result:
            print(f"{len(result)} file(s) {mode} modified:")
            for p in result:
                print("  •", p)
        else:
            print("No files matched the patch – nothing to do") 