"""telemetry_tracker.py – Unified telemetry & emissions logging (Step 4.6 Phase 2)

This helper introduces **first-class integration** with the :pypi:`codecarbon` library
so that each *action* (e.g. LLM inference, data processing) can record its
approximate *carbon footprint*.

Goals
-----
* **Zero-dependency fallback** – When *CodeCarbon* is **not** installed the
  context manager degrades gracefully, still emitting *event skeletons* so
  downstream aggregators can operate on a *consistent* schema.
* **Append-only JSONL** – Logs are written to ``.telemetry.jsonl`` (configurable
  via the ``TELEMETRY_FILE`` env variable) to align with the *success metrics*
  store already used elsewhere in the codebase.
* **Low overhead** – ``measure_power_secs`` is set to 1 second which is
  accurate enough for our purposes while keeping performance impact minimal.

Example
~~~~~~~
>>> from src.telemetry_tracker import track_emissions
>>> with track_emissions("safe_chat"):
...     _ = chat_fn(prompt)

An event similar to the following will be appended to the log on exit:
```json
{"ts":"2024-06-12T14:55:23Z","component":"safe_chat","emissions_kg":0.00042}
```
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .logger import get_logger

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Runtime availability checks
# ---------------------------------------------------------------------------

try:
    from codecarbon import EmissionsTracker  # type: ignore

    _CODECARBON_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover – intentionally light-weight
    _CODECARBON_AVAILABLE = False

# ---------------------------------------------------------------------------
# Public context manager
# ---------------------------------------------------------------------------

_DEFAULT_LOG = Path(os.getenv("TELEMETRY_FILE", ".telemetry.jsonl")).expanduser()


@contextmanager
def track_emissions(component: str, *, log_path: Path | str | None = None) -> Iterator[None]:  # noqa: D401 – imperative
    """Yield a context that records *CodeCarbon* emissions against *component*.

    Parameters
    ----------
    component:
        Human-readable label for the tracked action – e.g. ``"safe_chat"``.
    log_path:
        Optional override path for the JSONL log file (defaults to
        ``$TELEMETRY_FILE`` env var or ``.telemetry.jsonl``).
    """

    path = Path(log_path or _DEFAULT_LOG)
    path.parent.mkdir(parents=True, exist_ok=True)

    tracker: Optional["EmissionsTracker"] = None
    if _CODECARBON_AVAILABLE:
        # Lazy import avoids cost when telemetry disabled
        tracker = EmissionsTracker(
            project_name="RepoPrompt",
            measure_power_secs=1,
            save_to_file=False,  # we handle persistence ourselves
            log_level="error",  # silence verbose output
        )
        tracker.start()
        _log.debug("CodeCarbon tracker started for %s", component)

    try:
        yield  # control returns to caller's code block
    finally:
        emissions_kg: float | None = None
        if tracker is not None:  # pragma: no branch – explicit for clarity
            emissions_kg = tracker.stop()
            _log.debug("CodeCarbon tracker stopped – %.6f kg", emissions_kg)

        # Even when CodeCarbon unavailable we write a *stub* so that the event
        # stream stays continuous (value ``null`` signals missing measurement).
        _write_event(path, {
            "ts": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": component,
            "emissions_kg": emissions_kg,
        })


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_event(path: Path, payload: dict) -> None:
    """Append *payload* as compact JSON to *path* (one event per line)."""

    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception as exc:  # noqa: BLE001 – failure should not crash caller
        _log.debug("Failed to write telemetry event: %s", exc, exc_info=False)