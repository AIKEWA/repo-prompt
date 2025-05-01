from __future__ import annotations

"""Static analyzer for detecting naming convention issues in Python files.

This module addresses *Use Case 1* from the project spec: *Refactoring a large
Python repo with consistent naming conventions*.

It focuses on **detection** first – generating a structured report of
inconsistent identifiers so humans (or later automated refactor steps) can
apply fixes safely.

Why detection-only?  Fully–automatic renaming across a multi-file repo quickly
runs into edge-cases (imports, dynamic attributes, ``__getattr__`` hooks,
reflection).  By separating the *what* (violations) from the *how* (applying a
rename) we keep blast-radius low and let teams decide whether to:

* manually adjust the names,
* pipe the report into a migration tool like *rope* or *libcst*, or
* iterate with an LLM for diff-based patches.

# DESIGN

* Parses the AST of every ``.py`` file.
* Checks **functions**, **classes** and **variables** at module level.
* Ignores dunder (``__init__``) & private (``_name``) conventions.
* Flags mismatches against two naming styles:
  * ``snake_case`` – recommended for functions & variables.
  * ``PascalCase`` – recommended for classes.

The report is returned as a list of ``Violation`` dataclass instances and can
be serialized to JSON for downstream integration (e.g. CI annotations).

The module is dependency-free (uses stdlib ``ast`` only).

"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Iterable, Dict, Any
import ast
import re

from .logger import get_logger

_log = get_logger(__name__)


# -----------------------------
# Public data structures
# -----------------------------

@dataclass
class Violation:
    path: Path  # file where violation occurred
    lineno: int
    identifier: str
    kind: str  # "function" | "class" | "variable"
    expected: str  # expected naming style hint

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------
# Naming helpers
# -----------------------------

_SNAKE_REGEX = re.compile(r"^[a-z_][a-z0-9_]*$")
_PASCAL_REGEX = re.compile(r"^[A-Z][a-zA-Z0-9]+$")


def _is_snake(name: str) -> bool:
    return bool(_SNAKE_REGEX.fullmatch(name))


def _is_pascal(name: str) -> bool:
    return bool(_PASCAL_REGEX.fullmatch(name))


def _check_identifier(name: str, kind: str) -> str | None:
    """Return expectation message if *name* violates *kind* convention."""
    if name.startswith("__") and name.endswith("__"):
        return None  # dunder names are exempt
    if name.startswith("_"):
        return None  # private names – project may choose to ignore

    if kind == "class" and not _is_pascal(name):
        return "PascalCase"
    if kind in {"function", "variable"} and not _is_snake(name):
        return "snake_case"
    return None


# -----------------------------
# Core API
# -----------------------------

def analyze_file(path: Path) -> List[Violation]:
    """Analyze a single Python file and return naming violations."""
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _log.warning("Skipping non-utf8 file %s", path)
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        _log.error("Failed to parse %s – %s", path, exc)
        return []

    violations: List[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            expected = _check_identifier(node.name, "function")
            if expected:
                violations.append(Violation(path, node.lineno, node.name, "function", expected))
        elif isinstance(node, ast.AsyncFunctionDef):
            expected = _check_identifier(node.name, "function")
            if expected:
                violations.append(Violation(path, node.lineno, node.name, "function", expected))
        elif isinstance(node, ast.ClassDef):
            expected = _check_identifier(node.name, "class")
            if expected:
                violations.append(Violation(path, node.lineno, node.name, "class", expected))
        elif isinstance(node, ast.Assign):
            # collect targets at module level only (parent Module)
            if isinstance(node.parent, ast.Module):  # type: ignore[attr-defined]
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        expected = _check_identifier(tgt.id, "variable")
                        if expected:
                            violations.append(
                                Violation(path, tgt.lineno, tgt.id, "variable", expected)
                            )

    return violations


# Monkey-patching walk to include parent back-ref for variable check
# (we avoid external libs; minimal overhead).

def _attach_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]


# Patch analyze_file to call _attach_parents before walk
_old_parse = ast.parse

def _patched_parse(source: str, filename: str = "<unknown>") -> ast.AST:
    tree = _old_parse(source, filename=filename)
    _attach_parents(tree)
    return tree

ast.parse = _patched_parse  # type: ignore[assignment]


def analyze_repository(root: Path) -> List[Violation]:
    """Analyze *root* recursively and return all naming violations."""
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    py_files: Iterable[Path] = root.rglob("*.py")

    all_violations: List[Violation] = []
    for f in py_files:
        all_violations.extend(analyze_file(f))

    _log.info("Found %d naming violations", len(all_violations))
    return all_violations


# -----------------------------
# Command-line helper
# -----------------------------

if __name__ == "__main__":  # manual usage as script
    import argparse, json

    p = argparse.ArgumentParser(description="Detect naming convention issues across a repo")
    p.add_argument("path", type=Path, help="Path to repository root")
    p.add_argument("--json", action="store_true", help="Output JSON instead of human text")
    args = p.parse_args()

    vios = analyze_repository(args.path)
    if args.json:
        print(json.dumps([v.as_dict() for v in vios], indent=2))
    else:
        for v in vios:
            print(f"{v.path}:{v.lineno}: {v.kind} '{v.identifier}' should be {v.expected}") 