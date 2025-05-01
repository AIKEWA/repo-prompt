from __future__ import annotations

"""Context Builder – selective attention utility (Step 2.1).

This module operationalises the theoretical *Context Builder* concept which
plays the role of *selective attention* in human cognition.  Given a textual
**query** (e.g. a bug report or feature description) and a code repository it
returns **focused snippets** that are most relevant to that query.  Those
snippets can then be embedded into an LLM prompt to provide *just the right
amount* of context without exceeding token budgets.

Key characteristics
-------------------
* **Light-weight** – relies on the Python standard library only.
* **Token-aware** – uses :pymod:`src.token_estimator` to keep the generated
  snippets within a configurable budget.
* **Pluggable ranking** – ships with a naïve *keyword frequency* scorer but the
  :class:`ContextBuilder` class exposes a `score_fn` hook so that teams can
  inject more advanced models (BM25 / embeddings) without changing call-sites.
* **CLI** – `python -m src.context_builder search "memory leak" --k 7` prints a
  JSON list of the top-7 snippets.

Security notes
~~~~~~~~~~~~~~
* Files larger than *max_bytes* are skipped to avoid loading huge binaries.
* Only UTF-8 decodable files are processed; binary blobs are ignored.
* Paths can be *include/exclude* filtered via regular expressions similar to
  :pymod:`src.codemaps`.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence
import json
import re
import textwrap

import typer

from .logger import get_logger, setup_logging
from .token_estimator import estimate_tokens

__all__ = [
    "Snippet",
    "select_snippets",
    "ContextBuilder",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Snippet:
    """Represents a code snippet relevant to a query."""

    path: Path
    start: int  # 1-indexed line number of first line (inclusive)
    end: int  # 1-indexed line number of last line (inclusive)
    text: str
    score: float

    # -------------------------------
    # Serialisation helpers
    # -------------------------------

    def as_dict(self) -> Dict[str, str | int | float]:  # pragma: no cover – simple
        return {
            "path": str(self.path),
            "start": self.start,
            "end": self.end,
            "score": round(self.score, 4),
            "text": self.text,
        }


# ---------------------------------------------------------------------------
# Public helper function (stateless)
# ---------------------------------------------------------------------------


def _default_score_fn(query_tokens: Sequence[str], haystack: str) -> float:
    """Return a *very* naïve relevance score (token frequency).

    The implementation counts how often any *query token* appears in the
    *haystack* (case-insensitive) normalized by haystack length.
    """

    if not haystack:
        return 0.0

    lower_haystack = haystack.lower()
    hits = sum(lower_haystack.count(t) for t in query_tokens)
    return hits / max(len(lower_haystack), 1)


# ---------------------------------------------------------------------------
# Context Builder class
# ---------------------------------------------------------------------------


class ContextBuilder:
    """Encapsulates scanning, scoring and snippet extraction logic."""

    def __init__(
        self,
        root: str | Path,
        *,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        max_bytes: int = 200_000,
        snippet_radius: int = 5,
        score_fn: Callable[[Sequence[str], str], float] | None = None,
    ) -> None:
        """Create a *ContextBuilder* for *root* repository path.

        Parameters
        ----------
        root:
            Repository root path (file system directory).
        include_pattern / exclude_pattern:
            Optional regular expressions to filter file *paths* (not content).
            *Exclude* is applied **first**, *include* second (mirrors
            :func:`src.codemaps.CodeMap.build`).
        max_bytes:
            Upper bound for file size.  Anything larger is skipped for
            performance and to avoid loading binaries accidentally.
        snippet_radius:
            Number of context lines *before* and *after* each match included in
            the snippet.
        score_fn:
            Custom relevance scoring function.  Receives the tokenised *query*
            and the *candidate text* (full file content).  Defaults to a simple
            token frequency scorer.
        """

        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"{self.root} is not a directory")

        self.include_re = re.compile(include_pattern) if include_pattern else None
        self.exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
        self.max_bytes = max_bytes
        self.snippet_radius = max(0, snippet_radius)
        self.score_fn = score_fn or _default_score_fn

        _log.debug("ContextBuilder initialised for %s", self.root)

    # -------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------

    def select_snippets(
        self,
        query: str,
        *,
        k: int = 5,
        max_tokens: int | None = None,
        min_score: float = 0.0,
    ) -> List[Snippet]:
        """Return up to *k* highest-scoring snippets for *query*.

        *min_score* can be used to filter out weak matches.  When *max_tokens*
        is set the snippet texts are truncated so that the *total* token count
        of the returned list does **not** exceed that limit (best-effort).
        """

        query_tokens = [t.lower() for t in re.findall(r"\w+", query) if t]
        if not query_tokens:
            raise ValueError("Query must contain at least one alphanumeric token")

        candidate_snippets: List[Snippet] = []

        for file_path in self._iter_files():
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:  # skip binaries
                _log.debug("Skipping binary %s", file_path)
                continue
            score = self.score_fn(query_tokens, text)
            if score <= 0:
                continue

            # naive snippet extraction: first occurrence + radius
            lower_text = text.lower()
            first_idx = min((lower_text.find(tok) for tok in query_tokens if tok in lower_text), default=-1)
            if first_idx == -1:
                continue  # shouldn't happen given score > 0 but safeguard

            start_line = text.count("\n", 0, first_idx) + 1  # 1-indexed
            lines = text.splitlines()
            beg = max(0, start_line - 1 - self.snippet_radius)
            end = min(len(lines), start_line - 1 + self.snippet_radius + 1)
            snippet_text = "\n".join(lines[beg:end])
            snippet = Snippet(path=file_path, start=beg + 1, end=end, text=snippet_text, score=score)
            candidate_snippets.append(snippet)

        # --------------------
        # Sort & top-k select
        # --------------------
        candidate_snippets.sort(key=lambda s: s.score, reverse=True)
        selected = [s for s in candidate_snippets if s.score >= min_score][:k]

        # -----------------------------
        # Token budget post-processing
        # -----------------------------
        if max_tokens is not None:
            selected = _apply_token_budget(selected, max_tokens)

        return selected

    # -------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------

    def _iter_files(self) -> Iterable[Path]:
        """Yield file system paths filtered by include/exclude patterns."""

        for p in self.root.rglob("*"):
            if p.is_dir():
                continue
            if p.stat().st_size > self.max_bytes:
                _log.debug("Skipping large file %s (%.1f KB)", p, p.stat().st_size / 1024)
                continue
            rel = p.relative_to(self.root)
            if self.exclude_re and self.exclude_re.search(str(rel)):
                _log.debug("Excluding %s via exclude_pattern", rel)
                continue
            if self.include_re and not self.include_re.search(str(rel)):
                continue
            yield p


# ---------------------------------------------------------------------------
# Helper – token budget enforcement
# ---------------------------------------------------------------------------


def _apply_token_budget(snippets: List[Snippet], budget: int) -> List[Snippet]:
    """Return a copy of *snippets* truncated so that total tokens ≤ *budget*."""

    result: List[Snippet] = []
    tokens_used = 0
    for snip in snippets:
        tokens = estimate_tokens(snip.text)
        if tokens_used + tokens <= budget:
            result.append(snip)
            tokens_used += tokens
        else:
            # try to fit a truncated version of the snippet if possible
            remaining = budget - tokens_used
            if remaining <= 0:
                break
            # simple rule: cut off lines until we fit
            lines = snip.text.splitlines()
            new_text: str = ""
            while lines and estimate_tokens("\n".join(lines)) > remaining:
                lines.pop()
            if lines:
                new_text = "\n".join(lines)
                result.append(
                    Snippet(
                        path=snip.path,
                        start=snip.start,
                        end=snip.start + len(lines) - 1,
                        text=new_text,
                        score=snip.score,
                    )
                )
                break  # budget exhausted
    return result


def select_snippets(
    query: str,
    root: str | Path = ".",
    **kwargs,
):
    """Stateless helper that instantiates :class:`ContextBuilder` and delegates.

    This function exists so callers can *quickly* retrieve context without
    having to manage a ``ContextBuilder`` instance.  It mirrors the parameters
    of :meth:`ContextBuilder.select_snippets` except that the *repository root*
    is passed separately.
    """

    builder = ContextBuilder(root)
    return builder.select_snippets(query, **kwargs)


# ---------------------------------------------------------------------------
# CLI interface (Typer)
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Selective attention builder – find relevant code snippets")

# Built-in include/exclude pattern presets that teams can reuse via the `--preset` CLI flag.
# Keys are *human-readable* names; values are 2-tuples of
#     (include_regex | None, exclude_regex | None)
#
# These defaults purposefully keep the patterns simple – projects are encouraged
# to extend them via a wrapper config or by forking this list.
_PRESET_FILTERS: Dict[str, tuple[str | None, str | None]] = {
    # Generic Python repository – ignore virtualenvs & tests but scan *.py
    "python": (r"\.py$", r"(^|/)\.venv/|(^|/)tests?/"),
    # Production application code only (src/ folder)
    "prod_py": (r"^src/.*\.py$", r"(^|/)tests?/|(^|/)docs?/"),
    # Documentation focus – markdown & rst docs
    "docs": (r"\.(md|rst)$", None),
}


def _resolve_preset(name: str) -> tuple[str | None, str | None]:
    """Return `(include_regex, exclude_regex)` for *name* preset.

    Raises
    ------
    KeyError
        If the preset name is unknown.
    """

    try:
        return _PRESET_FILTERS[name]
    except KeyError as exc:  # pragma: no cover – validation happens in CLI
        raise KeyError(f"Unknown preset '{name}'. Available: {', '.join(_PRESET_FILTERS)}") from exc


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language or keyword query"),
    repo_path: Path = typer.Option(Path("."), "--repo", help="Repository root to scan"),
    k: int = typer.Option(5, "--k", help="Number of snippets to return"),
    max_tokens: int | None = typer.Option(None, "--max-tokens", help="Total token budget"),
    include_regex: str | None = typer.Option(None, "--include-regex", help="File path include filter"),
    exclude_regex: str | None = typer.Option(None, "--exclude-regex", help="File path exclude filter"),
    preset: str | None = typer.Option(None, "--preset", help="Use built-in filter preset instead of regex"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI wrapper around :meth:`ContextBuilder.select_snippets`.

    When *preset* is provided, its configured *include*/*exclude* patterns
    override the explicit `--include-regex` / `--exclude-regex` options.
    """

    setup_logging("DEBUG" if verbose else "INFO")

    # Determine filters – preset overrides explicit regex flags for convenience
    if preset is not None:
        try:
            include_regex, exclude_regex = _resolve_preset(preset)
        except KeyError as exc:
            raise typer.BadParameter(str(exc)) from exc

    builder = ContextBuilder(
        repo_path,
        include_pattern=include_regex,
        exclude_pattern=exclude_regex,
    )

    snippets = builder.select_snippets(query, k=k, max_tokens=max_tokens)

    if json_output:
        json.dump([s.as_dict() for s in snippets], typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        for snip in snippets:
            header = f"{snip.path}:{snip.start}-{snip.end}  (score={snip.score:.4f})"
            typer.secho(header, fg="green")
            typer.echo(textwrap.indent(snip.text, "| "))
            typer.echo("")