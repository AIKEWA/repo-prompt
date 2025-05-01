from __future__ import annotations

"""Selective Context Builder – AST-informed static analysis wrapper.

This module builds on :pymod:`src.context_builder` but enhances relevance
ranking by inspecting **Abstract Syntax Trees** (AST) of Python files.  The
approach quickly filters candidate files *before* full-text scoring, reducing
I/O and inference footprint.

Key idea
~~~~~~~~
If a query token matches **identifiers** (function / class / variable names) in
a module's AST we consider that file a *strong* candidate.  We therefore assign
it an *identifier boost* so that such files surface first.

API is kept identical to :class:`src.context_builder.ContextBuilder` so existing
call-sites can swap imports with minimal changes:

>>> from src.selective_context_builder import ContextBuilder
>>> cb = ContextBuilder(root=".")
>>> snippets = cb.select_snippets("database connection leak")

Implementation details
----------------------
* The custom :func:`ast_score_fn` delegates to the original `_default_score_fn`
  for baseline token frequency but adds a boost when identifiers overlap.
* Uses *std lib* only – no extra dependencies.
* Skips files that fail to parse (syntax errors or non-Python).
"""

from pathlib import Path
from typing import Sequence
import ast
import re

from .context_builder import ContextBuilder as _BaseBuilder, _default_score_fn
from .logger import get_logger

_log = get_logger(__name__)

__all__ = [
    "ContextBuilder",
]


# ---------------------------------------------------------------------------
# AST-augmented scoring function
# ---------------------------------------------------------------------------

def _extract_identifiers(source: str) -> set[str]:
    """Return set of *identifier strings* (names) in *source* Python text."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name.lower())
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id.lower())
    return names


def ast_score_fn(query_tokens: Sequence[str], haystack: str) -> float:
    """Score = baseline + identifier_boost.

    *identifier_boost* is ``+1`` when *any* token matches an identifier.
    """

    baseline = _default_score_fn(query_tokens, haystack)
    if baseline == 0:
        return 0.0

    identifiers = _extract_identifiers(haystack)
    if not identifiers:
        return baseline

    if any(tok in identifiers for tok in query_tokens):
        return baseline + 1.0  # simple additive boost
    return baseline


# ---------------------------------------------------------------------------
# Public builder re-export with default score_fn wired-in
# ---------------------------------------------------------------------------

class ContextBuilder(_BaseBuilder):
    """Drop-in replacement with AST-based relevance boosting."""

    def __init__(self, root: str | Path, **kwargs):
        super().__init__(root, score_fn=ast_score_fn, **kwargs)