from __future__ import annotations

"""Docstring completeness audit utility.

This module fulfils the *Docstring Completeness Audit* enhancement idea from the
spec.  It statically analyses Python files and reports where **module**,
**class**, **function**, and **method** docstrings are missing or empty.

Design principles
-----------------
* **Read-only**: no mutations; perfect for CI gating.
* **Coverage granularity**: distinguishes between module-level, class-level and
  function-level docstrings so teams can prioritise.
* **Extensible**: additional rules (e.g. minimum length, param docs) can be
  added without changing the public API.

Public API
~~~~~~~~~~
* :func:`audit_file` – return list of :class:`MissingDoc` for one file.
* :func:`audit_repository` – recurse through a repo.
* CLI – ``python -m src.docstring_audit <path> [--json]``

Security considerations
~~~~~~~~~~~~~~~~~~~~~~~
* Pure AST parsing; no runtime import / execution of project files.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Iterable
import ast

from .logger import get_logger

_log = get_logger(__name__)


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class MissingDoc:
    path: Path  # file path
    lineno: int  # where definition starts (module uses 1)
    kind: str  # module | class | function | method
    qualname: str  # qualified name ("MyCls.method" etc.)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------
# Internal helpers
# -----------------------------

def _has_docstring(node: ast.AST) -> bool:
    return bool(ast.get_docstring(node, clean=False))


def audit_file(path: Path) -> List[MissingDoc]:
    """Return missing-docstring records for *path* (Python file)."""

    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _log.warning("Skipping non-utf8 file %s", path)
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        _log.error("Syntax error in %s: %s", path, exc)
        return []

    missing: List[MissingDoc] = []

    # Module docstring
    if not _has_docstring(tree):
        missing.append(MissingDoc(path, 1, "module", path.stem))

    # Walk classes / functions
    class Stack(list):
        """Utility to track enclosing class names for qualname."""

    cls_stack: Stack[str] = Stack()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            qualname = ".".join([*cls_stack, node.name])
            if not _has_docstring(node):
                missing.append(MissingDoc(path, node.lineno, "class", qualname))
            cls_stack.append(node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_qn = f"{qualname}.{child.name}"
                    if not _has_docstring(child):
                        missing.append(MissingDoc(path, child.lineno, "method", method_qn))
            cls_stack.pop()
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not isinstance(
            node.parent, ast.ClassDef  # type: ignore[attr-defined]
        ):
            if not _has_docstring(node):
                missing.append(
                    MissingDoc(path, node.lineno, "function", node.name)
                )

    return sorted(missing, key=lambda m: (m.path, m.lineno))


# Attach parent refs for class/method detection
_old_parse = ast.parse


def _patched_parse(source: str, filename: str = "<unknown>") -> ast.AST:
    tree = _old_parse(source, filename=filename)
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]
    return tree

ast.parse = _patched_parse  # type: ignore[assignment]


def audit_repository(root: Path) -> List[MissingDoc]:
    """Recursively audit all ``*.py`` files under *root*."""

    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    results: List[MissingDoc] = []
    for file in root.rglob("*.py"):
        # Skip tests; docstrings optional there
        if "tests" in file.parts:
            continue
        results.extend(audit_file(file))

    _log.info("Found %d missing docstrings", len(results))
    return results


# -----------------------------
# CLI entry point
# -----------------------------

if __name__ == "__main__":
    import argparse, json, sys

    p = argparse.ArgumentParser(description="Docstring completeness audit")
    p.add_argument("path", type=Path, help="Repository root path")
    p.add_argument("--json", action="store_true", help="Output report as JSON")
    args = p.parse_args()

    missings = audit_repository(args.path)

    if args.json:
        json.dump([m.as_dict() for m in missings], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for m in missings:
            print(f"{m.path}:{m.lineno}: missing {m.kind} docstring for {m.qualname}") 