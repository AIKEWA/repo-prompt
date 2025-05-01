from __future__ import annotations

"""Codemaps utilities for mapping codebase structure to prompt payloads.

This module provides helper functions and a main `CodeMap` class that can scan a
code repository and build an in-memory representation of files, directories, and
code snippets relevant for context-limited LLM prompts.

It is intentionally lightweight and dependency-free beyond the Python standard
library, so it can be reused in serverless contexts.

# REVIEW: Expand functionality for binary file detection
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional
import re
import json
import textwrap
import typer

__all__ = ["CodeMap", "FileNode", "DirNode", "map_repository"]


@dataclass
class FileNode:
    """Represents a single file in the repository tree."""

    path: Path
    language: Optional[str] = None
    size: int = 0

    def as_dict(self) -> dict:
        return {
            "type": "file",
            "path": str(self.path),
            "language": self.language,
            "size": self.size,
        }


@dataclass
class DirNode:
    """Represents a directory containing files and/or other directories."""

    path: Path
    children: List["DirNode | FileNode"] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "type": "directory",
            "path": str(self.path),
            "children": [child.as_dict() for child in self.children],
        }


class CodeMap:
    """Builds and stores a tree representing the repository structure."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"{self.root} is not a directory")
        self.root_node: DirNode = DirNode(self.root)

    # FEEDBACK: Should we include file content hashing here for diff detection?

    def build(
        self,
        *,
        exclude_pattern: str | None = None,
        include_pattern: str | None = None,
    ) -> "CodeMap":
        """Populate :pyattr:`root_node` with repository contents.

        Parameters
        ----------
        exclude_pattern
            Optional *regular expression* that – if it **matches** the full
            path – causes a file or directory to be skipped.  Handy for
            excluding generated artefacts such as ``\.git`` or ``build``
            folders.
        include_pattern
            Optional *regular expression* that must match the full path in
            order for a *file* to be included.  Directories are always walked
            but they will be pruned from the final JSON if they end up empty
            (because all of their children were filtered).  When
            *include_pattern* is *None* all files are considered.
        """

        regex_excl = re.compile(exclude_pattern) if exclude_pattern else None
        regex_incl = re.compile(include_pattern) if include_pattern else None

        for path in self.root.rglob("*"):
            # 1) Skip anything matching the *exclude* regex first.
            if regex_excl and regex_excl.search(str(path)):
                continue

            # 2) Directories are always created so the tree structure is
            #    preserved, even if they may end up empty after applying the
            #    *include* filter to their children.
            relative = path.relative_to(self.root)
            if path.is_dir():
                self._ensure_dir(relative)
                continue

            # 3) For *files* we additionally check the *include* pattern.
            if regex_incl and not regex_incl.search(str(path)):
                continue

            self._add_file(relative)

        return self

    def to_json(self, **kwargs) -> str:
        """Serialize the code map to JSON."""
        return json.dumps(self.root_node.as_dict(), **kwargs)

    # -----------------
    # Internal helpers
    # -----------------

    def _ensure_dir(self, relative: Path) -> DirNode:
        parts = relative.parts
        node = self.root_node
        for part in parts:
            # locate or create that subdir node
            next_dir = next((c for c in node.children if isinstance(c, DirNode) and c.path.name == part), None)
            if next_dir is None:
                new_path = node.path / part
                next_dir = DirNode(new_path)
                node.children.append(next_dir)
            node = next_dir
        return node

    def _add_file(self, relative: Path) -> None:
        dir_node = self._ensure_dir(relative.parent) if relative.parent != Path('.') else self.root_node
        file_path = self.root / relative
        language = file_path.suffix.lstrip('.')
        size = file_path.stat().st_size
        dir_node.children.append(FileNode(file_path, language, size))


# Utility function wrapper

def map_repository(root: str | Path, **kwargs) -> CodeMap:
    """Convenience wrapper to build a CodeMap in one call."""
    return CodeMap(root).build(**kwargs)


# Typer CLI app (lazy import to keep core logic lightweight when used as library)
app = typer.Typer(add_completion=False, help="CodeMap inspection utilities – helpful before large multi-file edits.")


def _tree(node: DirNode | FileNode, indent: int = 0) -> str:
    """Return a *human-readable* tree view of *node* (recursive)."""

    prefix = "│   " * (indent - 1) + ("├── " if indent else "") if indent else ""
    if isinstance(node, FileNode):
        return f"{prefix}{node.path.name}\n"

    lines: List[str] = [f"{prefix}{node.path.name}/\n"]
    child_count = len(node.children)
    for i, child in enumerate(sorted(node.children, key=lambda c: c.path.name)):
        is_last = i == child_count - 1
        sub_prefix = "    " if is_last else "│   "
        # Recursively build – adjust indent to keep branch lines correct
        sub_tree = _tree(child, indent + 1)
        # Replace leading branch glyphs depending on *is_last*
        if indent >= 0 and sub_tree:
            first_line_end = sub_tree.find("\n")
            if first_line_end != -1:
                branch = "└── " if is_last else "├── "
                sub_tree = branch + sub_tree[first_line_end - len(child.path.name) - 1 :]
        # Prepend indent spaces
        lines.append(textwrap.indent(sub_tree, "    " * indent))
    return "".join(lines)


@app.command()
def scan(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root to map"),
    include_regex: str | None = typer.Option(None, "--include-regex", help="Include file paths matching pattern"),
    exclude_regex: str | None = typer.Option(None, "--exclude-regex", help="Exclude file/directory paths"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of tree view"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a repository CodeMap and print a **tree view** or JSON.

    This command supports daily developer workflows by quickly showing where
    a change might have cascading effects – recommended *before* large
    multi-file edits or refactors.
    """

    from .logger import setup_logging, get_logger  # local import to avoid overhead

    setup_logging("DEBUG" if verbose else "INFO")
    log = get_logger(__name__)

    cm = map_repository(repo_path, include_pattern=include_regex, exclude_pattern=exclude_regex)

    if json_output:
        typer.echo(cm.to_json(indent=2))
    else:
        typer.echo(f"CodeMap for {repo_path.resolve()}\n")
        tree_view = _tree(cm.root_node)
        typer.echo(tree_view)
        log.info("%d child nodes mapped", len(cm.root_node.children))

# ---------------------------------------------------------------------------
# Human-readable guide – quick onboarding with CodeMaps
# ---------------------------------------------------------------------------

# The *guide* command prints a concise markdown reference that explains **why**
# CodeMaps are useful and **how** to leverage them for day-to-day navigation of
# large repositories.  This is referenced from the *Integration into Standard
# Practice* section (Step 2.14) to act as an *entry point* for juniors who are
# onboarding to the project.


@app.command()
def guide():  # pragma: no cover – simple output helper
    """Print a markdown quick-start guide for using CodeMaps.

    The output can be copied into onboarding docs (or viewed directly via
    `python -m src.codemaps guide`).  Keeping it close to the implementation
    ensures the information stays up-to-date with feature changes.
    """

    md = (
        "# 🗺️ CodeMaps Quick-Start\n\n"
        "CodeMaps help you build a *mental model* of an unfamiliar codebase by\n"
        "turning the directory tree into a searchable JSON map.  Use the CLI\n"
        "commands below to explore and filter the repository while staying\n"
        "within LLM token limits.\n\n"
        "```bash\n"
        "# List the full structure (human-readable tree)\n"
        "python -m src.codemaps scan .\n\n"
        "# Show only Python source files, output JSON for tooling\n"
        "python -m src.codemaps scan --include-regex '\\.(py)$' --json\n\n"
        "# Visualise the tree inside VS Code\n"
        "python -m src.codemaps scan . | code -\n"
        "```\n\n"
        "**Next steps for juniors**:\n"
        "1. Pick a sub-module you're interested in and run `--include-regex` to\n"
        "   zoom in.\n"
        "2. Use the *Context Builder* (`python -m src.context_builder search`)\n"
        "   with the paths you found to extract relevant snippets.\n"
        "3. When submitting your first PR, reference CodeMaps in the description\n"
        "   so reviewers know which areas you touched.\n"
    )

    typer.echo(md)