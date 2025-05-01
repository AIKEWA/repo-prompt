from __future__ import annotations

"""Test skeleton generator based on repository introspection.

This module addresses *Use Case 2* from the project spec: *Generating
comprehensive test coverage using Codemap-suggested files*.

It uses :pymod:`src.codemaps` to detect Python source files in a repository and
identifies missing test modules following the naming convention
``tests/test_<module>.py``.

When executed as a script it can optionally **write** stub test files that
contain boilerplate `pytest` test functions ready for developers to fill in.

Security considerations
----------------------
* No dynamic code execution – only file I/O.
* Respects existing tests; will not overwrite already present files unless
  ``--force`` flag is provided.
"""

from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Iterable
import textwrap
import sys

from .codemaps import map_repository
from .logger import get_logger

_log = get_logger(__name__)

# -----------------------------
# Public data structures
# -----------------------------

@dataclass
class TestSuggestion:
    """Represents a missing test file and potential skeleton content."""

    source_path: Path  # original python module
    suggested_test_path: Path  # e.g. tests/test_<module>.py
    stub_content: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------
# Core helpers
# -----------------------------

def _default_stub(module_name: str) -> str:
    """Return boilerplate pytest stub for *module_name*."""

    return textwrap.dedent(
        f'''"""Auto-generated test stub for `{module_name}`.

        Fill in real tests and remove this docstring once complete.
        """

import pytest  # noqa: F401  # FEEDBACK: remove if unused


def test_placeholder():
    # REVIEW: Replace with real assertions
    assert False, "Not implemented yet"
'''
    )


def suggest_tests(repo_root: Path | str) -> List[TestSuggestion]:
    """Return a list of :class:`TestSuggestion` for *repo_root*.

    Detection logic:
    * Include every ``.py`` file under *repo_root* **except** those inside the
      ``tests`` directory or starting with ``__`` (dunder modules).
    * A corresponding test is expected at ``tests/test_<module>.py`` where
      ``<module>`` is the file stem.
    * If that file does not exist → create a suggestion.
    """

    root = Path(repo_root).resolve()
    cm = map_repository(root)

    suggestions: List[TestSuggestion] = []

    # Collect python files from codemap
    def _walk(nodes: Iterable):
        for n in nodes:
            from src.codemaps import FileNode, DirNode  # local import to avoid cycles
            if isinstance(n, FileNode):
                if n.path.suffix == ".py" and "tests" not in n.path.parts:
                    if n.path.stem.startswith("__"):
                        continue
                    yield Path(n.path)
            else:  # DirNode
                yield from _walk(n.children)

    for py_file in _walk([cm.root_node]):
        rel = py_file.relative_to(root)
        # map to tests dir
        test_path = root / "tests" / f"test_{py_file.stem}.py"
        if not test_path.exists():
            stub = _default_stub(py_file.stem)
            suggestions.append(TestSuggestion(py_file, test_path, stub))

    _log.info("%d test stubs suggested", len(suggestions))
    return suggestions


# -----------------------------
# CLI entry point
# -----------------------------

def _write_stub(path: Path, content: str, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        _log.warning("Skipping existing %s (use --force to overwrite)", path)
        return
    path.write_text(content, encoding="utf-8")
    _log.info("Stub written to %s", path)


def main(argv: list[str] | None = None):
    import argparse, json

    parser = argparse.ArgumentParser(description="Suggest or generate pytest stubs")
    parser.add_argument("path", type=Path, help="Repository root path")
    parser.add_argument("--write", action="store_true", help="Write stub files to disk")
    parser.add_argument("--force", action="store_true", help="Overwrite existing stubs")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human text")
    args = parser.parse_args(argv)

    suggestions = suggest_tests(args.path)

    if args.write:
        for s in suggestions:
            _write_stub(s.suggested_test_path, s.stub_content, args.force)

    if args.json:
        print(json.dumps([s.as_dict() for s in suggestions], indent=2))
    else:
        for s in suggestions:
            print(f"{s.suggested_test_path} ← tests for {s.source_path}")


if __name__ == "__main__":
    main(sys.argv[1:]) 