"""carbon_scheduler.py – Carbon-aware prompt scheduling (Step 4.6 v2)

This module consults real-time *grid intensity* APIs (✳ ElectricityMap
preferred) to decide **whether** a heavy operation like LLM inference should be
*deferred* until the electricity mix is cleaner.

API support
-----------
* **ElectricityMap** – requires an API token via the ``GRID_API_TOKEN`` env var.
  Endpoint: ``https://api.electricitymap.org/v3/carbon-intensity/latest``
* **WattTime** – planned (not yet implemented).

Usage
~~~~~
>>> from src.carbon_scheduler import delay_if_dirty
>>> delay_if_dirty(threshold=350)  # blocks until grid ≤ 350 gCO₂/kWh or timeout

When the API is unreachable or no token is configured, the helper *fails
open* and returns immediately.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx

from .logger import get_logger, setup_logging

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & configuration
# ---------------------------------------------------------------------------

_ELECTRICITYMAP_URL = "https://api.electricitymap.org/v3/carbon-intensity/latest"
_DEFAULT_ZONE = os.getenv("GRID_ZONE", "US-CAL")  # override for locale


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_current_intensity(*, zone: str = _DEFAULT_ZONE, token: str | None = None) -> Optional[float]:
    """Return latest grid intensity in **gCO₂/kWh** or *None* on failure."""

    token = token or os.getenv("GRID_API_TOKEN")
    if not token:
        _log.debug("GRID_API_TOKEN not set – skipping intensity lookup")
        return None

    url = f"{_ELECTRICITYMAP_URL}?zone={zone}"
    headers = {"auth-token": token}

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            intensity = data["carbonIntensity"]  # gCO2eq/kWh
            _log.debug("Grid intensity for %s: %.1f gCO₂/kWh", zone, intensity)
            return float(intensity)
    except Exception as exc:  # noqa: BLE001 – best-effort only
        _log.debug("Grid intensity lookup failed: %s", exc, exc_info=False)
        return None


def delay_if_dirty(*, threshold: float = 400.0, max_wait: int = 3600, poll_interval: int = 300, zone: str = _DEFAULT_ZONE) -> None:  # noqa: D401
    """Block the caller when *current* grid intensity exceeds *threshold*.

    The function polls the ElectricityMap API every *poll_interval* seconds up
    to *max_wait* seconds.  If the intensity stays *above* the threshold the
    function returns after the timeout so as not to hang indefinitely.
    """

    intensity = get_current_intensity(zone=zone)
    if intensity is None:
        return  # fail open

    if intensity <= threshold:
        return  # clean enough

    start = datetime.utcnow()
    deadline = start + timedelta(seconds=max_wait)
    _log.info("Grid intensity %.0f gCO₂/kWh above threshold %.0f. Deferring heavy operation (max %d s)", intensity, threshold, max_wait)

    while intensity is not None and intensity > threshold and datetime.utcnow() < deadline:
        sleep_s = min(poll_interval, int((deadline - datetime.utcnow()).total_seconds()))
        if sleep_s <= 0:
            break
        _log.debug("Sleeping %d s before next intensity check", sleep_s)
        time.sleep(sleep_s)
        intensity = get_current_intensity(zone=zone)

    if intensity is not None and intensity > threshold:
        _log.warning("Proceeding despite high intensity (%.0f gCO₂/kWh) after max_wait=%d s", intensity, max_wait)
    else:
        _log.info("Resuming – grid intensity now %.0f gCO₂/kWh", intensity or -1)