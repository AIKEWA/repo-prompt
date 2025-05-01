"""
real_world_usage_context.py – Step 5.2 Analyze Real-World Context 🧑This module turns the *5.2 Analyze Real-World Context* theory block into **executable** Python code that captures the *human* side of shipping AI-assisted tooling.

Focus
-----
* Target audience: **macOS developers** using large language models (LLMs) for coding, debugging & documentation.
* Surfaced pain points (from the spec):
  1. **Copy-paste fatigue** between IDE ↔︎ chat windows.
  2. **Unpredictable / unreviewable AI changes.**
  3. **Initial confusion** when onboarding to advanced features such as *CodeMaps* & regex filters.

The analyser maps those *qualitative* insights to **concrete, actionable recommendations** that reference existing helper
modules in the code-base (e.g. :pymod:`src.diff_mode`, :pymod:`src.granular_review`).  The output is a structured
``dict`` so it can be embedded into prompts, dashboards or CI checks.

Security/Ethics
~~~~~~~~~~~~~~~
* Runs *locally* only – no network calls or telemetry collection.
* Does **not** inspect user code. All heuristics are transparent & auditable.

Example CLI
-----------
```bash
python -m src.real_world_usage_context report --pretty
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "PainPoint",
    "analyze_usage_context",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enumerations & data structures
# ---------------------------------------------------------------------------


class PainPoint(str, Enum):
    """Supported user-reported pain-points.

    Extend the list when new qualitative feedback emerges.
    """

    COPY_PASTE_FATIGUE = "copy_paste_fatigue"
    UNREVIEWABLE_CHANGES = "unreviewable_ai_changes"
    FEATURE_CONFUSION = "advanced_feature_confusion"


@dataclass
class Recommendation:
    """Represents a *single* actionable recommendation."""

    pain_point: PainPoint
    message: str
    related_modules: List[str]

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return {
            "pain_point": self.pain_point.value,
            "message": self.message,
            "related_modules": self.related_modules,
        }


# Static mapping ⇒ keeps logic simple & auditable
_PAIN_POINT_RECOMMENDATIONS: Dict[PainPoint, Recommendation] = {
    PainPoint.COPY_PASTE_FATIGUE: Recommendation(
        pain_point=PainPoint.COPY_PASTE_FATIGUE,
        message=(
            "Embed the LLM directly into the editor or use *Context Builder* + *CodeMaps* to reduce manual copy/paste. "
            "Consider a keyboard shortcut that pipes the *current file* or *selected diff* to the chat interface."
        ),
        related_modules=[
            "context_builder",
            "codemaps",
            "token_ui",
        ],
    ),
    PainPoint.UNREVIEWABLE_CHANGES: Recommendation(
        pain_point=PainPoint.UNREVIEWABLE_CHANGES,
        message=(
            "Enable *preview* and *approval* workflows before applying AI-generated patches. "
            "Leverage the `diff_mode` + `granular_review` helpers or gate changes behind CI checks (e.g. `ci_sustainability_gate`)."
        ),
        related_modules=[
            "diff_mode",
            "granular_review",
            "patch_apply",
            "ci_sustainability_gate",
        ],
    ),
    PainPoint.FEATURE_CONFUSION: Recommendation(
        pain_point=PainPoint.FEATURE_CONFUSION,
        message=(
            "Provide interactive tutorials or tooltips for *CodeMaps* & regex filters. "
            "Generate onboarding docs via `ux_guidelines` and ensure discoverability inside the IDE (⌘⇧P → *AI: Show Help*)."
        ),
        related_modules=[
            "ux_guidelines",
            "codemaps",
            "training_support",
        ],
    ),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_usage_context(*, include: List[str] | None = None) -> Dict[str, Any]:
    """Return structured *pain-point* analysis for Mac LLM developers.

    Parameters
    ----------
    include:
        Optional list of pain-point **names** to *limit* the analysis. When
        *None* (default) all supported pain-points are considered.

    Returns
    -------
    Dict[str, Any]
        JSON-serialisable structure that lists pain-points and recommendations.
    """

    selected: List[PainPoint]
    if include is None:
        selected = list(PainPoint)
    else:
        selected = []
        for name in include:
            try:
                selected.append(PainPoint(name))
            except ValueError:
                _log.warning("Unknown pain-point '%s' – skipping", name)
                continue

    _log.debug("Analyzing pain-points: %s", [p.value for p in selected])

    recommendations = [
        _PAIN_POINT_RECOMMENDATIONS[p].as_dict() for p in selected if p in _PAIN_POINT_RECOMMENDATIONS
    ]

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_base": "mac_llm_developer",
        "pain_points": [p.value for p in selected],
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Typer CLI – quick standalone usage
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=False,
    help="5.2 Real-World Usage Context analyser – maps developer pain-points to recommendations.",
)


@app.command()
def report(
    include: List[str] = typer.Option(
        None,
        "--include",
        "-i",
        help="Comma-separated pain-point names to analyse (default: all).",
    ),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty human-readable output"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a **pain-point report** for the given *include* list."""

    setup_logging("DEBUG" if verbose else "INFO")

    include_list = [i.strip() for i in include] if include else None

    data = analyze_usage_context(include=include_list)

    if json_output:
        typer.echo(json.dumps(data, indent=2))
    elif pretty:
        _pretty_print(data)
    else:
        # default: compact JSON one-liner (useful for scripting)
        typer.echo(json.dumps(data))


# ---------------------------------------------------------------------------
# Helpers – human-friendly pretty printer
# ---------------------------------------------------------------------------


def _pretty_print(data: Dict[str, Any]) -> None:  # noqa: D401 – imperative mood not necessary
    """Print *data* in a more readable table form."""

    typer.echo("📌 Pain-point analysis (macOS developer context)\n")

    for rec in data.get("recommendations", []):
        typer.echo(f"• {rec['pain_point']}: {rec['message']}")
        if rec["related_modules"]:
            mods = ", ".join(rec["related_modules"])
            typer.echo(f"  ↪ related modules: {mods}\n")


# ---------------------------------------------------------------------------
# Self-test entry-point (manual) – ``python -m src.real_world_usage_context report --pretty``
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()