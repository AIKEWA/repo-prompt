from __future__ import annotations

"""Utility to compute and apply unified diff patches for text files.

This is a lightweight wrapper around `difflib` producing traditional unified
format patches compatible with `patch` command, but intentionally avoids shell
invocation to stay cross-platform and safe in serverless setups.
"""

import difflib
from pathlib import Path
from typing import List, Tuple
from .logger import get_logger

_log = get_logger(__name__)

def unified_diff(original: str | List[str], modified: str | List[str], fromfile: str = "a/file", tofile: str = "b/file", n: int = 3) -> str:
    """Return a unified diff string between two text inputs."""
    if isinstance(original, str):
        original = original.splitlines(keepends=True)
    if isinstance(modified, str):
        modified = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(original, modified, fromfile=fromfile, tofile=tofile, lineterm="", n=n)
    return "\n".join(diff)


# FEEDBACK: Provide apply_patch function?

# -----------------------
# Patch application util
# -----------------------

def apply_unified_patch(original_text: str, patch_str: str) -> str:
    """Apply a unified diff patch to `original_text` and return modified text.

    This is a pure-Python implementation that walks through the patch hunks
    produced by :func:`unified_diff`. It supports additions and deletions but
    does **not** handle file mode or rename headers.

    Parameters
    ----------
    original_text
        The full original content of the file.
    patch_str
        A unified diff string that should be applied.
    """

    import io

    original_lines = original_text.splitlines(keepends=True)
    patched_lines: list[str] = []

    diff = patch_str.splitlines()
    # Skip diff header lines starting with --- and +++
    i = 0
    while i < len(diff) and diff[i].startswith("---"):
        i += 1
    if i < len(diff) and diff[i].startswith("+++"):
        i += 1

    ptr = 0  # pointer into original_lines

    while i < len(diff):
        hunk_header = diff[i]
        if not hunk_header.startswith("@@"):
            raise ValueError(f"Unexpected diff format at line {i}: {hunk_header}")

        # Parse hunk header @@ -l,s +l,s @@
        import re

        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", hunk_header)
        if not m:
            # Allow minimal header like "@@" which indicates full-file addition/deletion
            if hunk_header.strip() == "@@":
                old_start = ptr
                old_len = 0
            else:
                raise ValueError(f"Malformed hunk header: {hunk_header}")
        else:
            old_start = int(m.group(1)) - 1  # convert to 0-idx
            old_len = int(m.group(2) or 1)

        # Add unchanged lines before hunk
        patched_lines.extend(original_lines[ptr:old_start])
        ptr = old_start

        i += 1
        # Process hunk body
        while i < len(diff) and not diff[i].startswith("@@"):
            line = diff[i]
            if line.startswith(" "):  # context line
                patched_lines.append(original_lines[ptr])
                ptr += 1
            elif line.startswith("-"):  # deletion
                ptr += 1
            elif line.startswith("+"):  # addition
                patched_lines.append(line[1:] + "\n")
            else:
                raise ValueError(f"Invalid hunk line: {line}")
            i += 1

    # Append remaining lines
    patched_lines.extend(original_lines[ptr:])

    _log.debug("Patch applied successfully")
    return "".join(patched_lines)