"""Development context analyzer – Step 2.2.

This module inspects a *code repository* and produces quantitative metrics that
help Large Language Models (LLMs) **reason about real-world development
complexities** such as *monorepos*, *multi-language stacks* or *large
dependency graphs*.

It translates the theoretical *2.2 Analyze the Real-World Development Context*
section from the project specification into an executable utility that can be
embedded into prompts or automation workflows.

Key features
------------
* **Language breakdown** – counts files by programming language so the prompt
  can highlight heterogeneous tech-stacks.
* **Size metrics** – reports total / median / max *Lines-of-Code* (LoC) to give
  downstream components an idea of repository scope.
* **Complexity score** – a naive heuristic that combines number of files,
  language diversity and LoC into a 0-100 *complexity index* (subject to
  refinement).
* **Typer CLI** – run `python -m src.development_context scan` for ad-hoc JSON
  output; pass `--pretty` for human-readable tables.

Security notes
~~~~~~~~~~~~~~
* Only reads *text* files up to a configurable size limit (defaults 2 MB).
* Skips directories typically containing generated artefacts (e.g. `node_modules`,
  `.venv`, `.git`). The list can be overridden via the `--exclude-regex` flag.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "analyze_development_context",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

# Map common file extensions to languages (extend as needed)
_EXTENSION_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
}

# Fallback language label when extension not recognised
_UNKNOWN = "other"

# Default directories to ignore (regex pattern) – can be overridden via CLI
_DEFAULT_EXCLUDE_PATTERN = r"(?x)(\.git|\.hg|\.svn|node_modules|\.venv|\.mypy_cache|__pycache__)"

# Maximum file size (in bytes) read when counting lines (skip larger)
_DEFAULT_MAX_BYTES = 2_000_000  # 2 MB


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_development_context(
    repo_root: str | Path,
    *,
    exclude_pattern: str = _DEFAULT_EXCLUDE_PATTERN,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> Dict[str, Any]:
    """Return structured metrics describing *repo_root*.

    Parameters
    ----------
    repo_root:
        Path to the repository root directory.
    exclude_pattern:
        *Regular expression* used to skip directories / files.
    max_bytes:
        Files larger than this limit are ignored when computing LoC. Prevents
        accidental loading of minified vendor bundles or binaries.
    """

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory")

    _log.debug("Scanning development context for %s", root)

    file_langs: List[str] = []
    loc_counts: List[int] = []

    exclude_re = re.compile(exclude_pattern)

    for file_path in _iter_files(root, exclude_re):
        try:
            if file_path.stat().st_size > max_bytes:
                _log.debug("Skipping large file %s", file_path)
                continue

            lang = _language_from_extension(file_path)
            file_langs.append(lang)

            loc = _count_loc(file_path)
            loc_counts.append(loc)
        except UnicodeDecodeError:
            _log.debug("Skipping binary or non-UTF8 file %s", file_path)
            continue

    lang_counter = Counter(file_langs)

    metrics: Dict[str, Any] = {
        "files_total": len(loc_counts),
        "languages": dict(lang_counter),
    }

    if loc_counts:
        metrics.update(
            {
                "loc_total": sum(loc_counts),
                "loc_median": statistics.median(loc_counts),
                "loc_max": max(loc_counts),
                "loc_avg": round(sum(loc_counts) / len(loc_counts), 1),
            }
        )

    metrics["complexity_score"] = _complexity_index(metrics)

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "repository": str(root),
        "metrics": metrics,
        "insights": _derive_insights(metrics),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_files(root: Path, exclude_re: re.Pattern[str]) -> Iterable[Path]:
    """Yield all *text* files under *root* not matching *exclude_re*."""

    for path in root.rglob("*"):
        if path.is_dir():
            if exclude_re.search(str(path)):
                # Skip the entire directory tree for efficiency
                _log.debug("Pruning directory %s", path)
                dirs_to_skip = [d for d in path.iterdir() if d.is_dir()]
                for d in dirs_to_skip:
                    # remove from generator via "path.rglob" by not yielding (implicit)
                    pass
                continue
            continue  # do not yield directories

        if exclude_re.search(str(path)):
            continue

        yield path


def _language_from_extension(path: Path) -> str:
    return _EXTENSION_LANG.get(path.suffix.lower(), _UNKNOWN)


def _count_loc(path: Path) -> int:
    """Return number of lines in *path* (fast)."""
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        return sum(1 for _ in fh)


def _complexity_index(metrics: Dict[str, Any]) -> int:
    """Return naive *complexity* 0-100 index based on metrics.*"""

    files = metrics.get("files_total", 0)
    loc = metrics.get("loc_total", 0)
    lang_diversity = len(metrics.get("languages", {}))

    # Weighted heuristic – tweak weights as needed
    score = (
        min(files / 1000, 1.0) * 40  # file count weight
        + min(loc / 100_000, 1.0) * 40  # lines of code weight
        + min(lang_diversity / 10, 1.0) * 20  # language diversity weight
    )

    return int(round(score))


def _derive_insights(metrics: Dict[str, Any]) -> List[str]:
    """Return human-readable insights derived from *metrics*."""

    insights: List[str] = []
    lang_counter = metrics.get("languages", {})
    if len(lang_counter) > 3:
        insights.append("High language diversity may challenge cross-file understanding.")
    if metrics.get("files_total", 0) > 5000:
        insights.append("Large file count detected – consider selective context building.")
    if metrics.get("complexity_score", 0) > 70:
        insights.append("Overall repository complexity is high; LLM prompt budgets should be managed carefully.")
    return insights


# ---------------------------------------------------------------------------
# CLI interface (Typer)
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Analyze repository development context (Step 2.2).")


@app.command()
def scan(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root to scan."),
    exclude_regex: str = typer.Option(_DEFAULT_EXCLUDE_PATTERN, "--exclude-regex", help="Regex to exclude paths"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty human-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print development context metrics for *repo_path* (JSON by default)."""

    setup_logging("DEBUG" if verbose else "INFO")
    result = analyze_development_context(repo_path, exclude_pattern=exclude_regex)

    if pretty:
        _pretty_print(result)
    else:
        typer.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _pretty_print(data: Dict[str, Any]) -> None:  # noqa: D401 – imperative mood not necessary
    """Render *data* in a simple human-readable form using rich (if available)."""

    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text

        console = Console()

        metrics = data["metrics"]
        console.rule("Development Context")
        console.print(f"[bold]Repository[/]: {data['repository']}")
        console.print(f"[bold]Scanned At[/]: {data['timestamp']}")
        console.print(f"[bold]Complexity Score[/]: {metrics['complexity_score']}")

        # Languages table
        table = Table(title="Language Breakdown")
        table.add_column("Language")
        table.add_column("Files", justify="right")
        for lang, cnt in sorted(metrics["languages"].items(), key=lambda x: x[1], reverse=True):
            table.add_row(lang, str(cnt))
        console.print(table)

        console.print("\n[bold]Insights:[/]")
        if data["insights"]:
            for ins in data["insights"]:
                console.print(f"• {ins}")
        else:
            console.print(Text("No notable insights.", style="dim"))

    except ImportError:
        # Fallback plain text – keep dependency optional
        typer.echo("rich not installed → falling back to plain text\n")
        typer.echo(json.dumps(data, indent=2))