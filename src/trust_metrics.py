from __future__ import annotations

"""trust_metrics.py – Step 3.6 Step-by-Step Implementation Plan 🕊️📈

This module operationalises the **3.6 Step-by-Step Implementation Plan**
from the project specification.  It focuses on **user trust** by providing
three complementary building blocks:

1. **Trust Metric Evaluation** – lightweight heuristics that calculate
   *Transparency*, *Consent Frequency* and *HITL Adoption* scores based on
   local artefacts (consent registry, interaction logs).
2. **Modular Processing Layer** – a *local-first* helper
   :func:`process_request` that routes data either to a **local agent** or –
   *only after explicit opt-in* – to a **remote network layer**.  The decision
   is fully transparent and emits structured events for auditing.
3. **CLI Utilities** – a tiny Typer-powered interface to inspect metrics,
   process sample data and toggle the remote layer for debugging.

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* All metrics are derived from **local** files – *no outbound traffic*.
* Remote processing is guarded by :class:`src.data_sovereignty.ConsentManager`.
* Interaction events are appended to ``~/.trust_log.jsonl`` (chmod 600).
  # REVIEW: Log file location & retention policy – adjust in production.
"""

import json
import os
import sys
import contextlib  # Added for suppress usage
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from .data_sovereignty import ConsentManager
from .logger import get_logger, setup_logging

__all__ = [
    "TrustMetric",
    "TrustReport",
    "evaluate_trust",
    "process_request",
    "app",
]

_log = get_logger(__name__)
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TrustMetric:  # noqa: D101 – simple value holder
    name: str
    score: int  # 0-100 heuristics
    details: str | None = None

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return asdict(self)


@dataclass
class TrustReport:  # noqa: D101 – documented in module docstring
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(_ISO_FMT))
    total_score: int = 0
    metrics: List[TrustMetric] = field(default_factory=list)

    # ---------------- Serialisation helpers ----------------
    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – helper only
        return {
            "created_at": self.created_at,
            "total_score": self.total_score,
            "metrics": [m.as_dict() for m in self.metrics],
        }

    def to_json(self) -> str:  # pragma: no cover – helper only
        return json.dumps(self.as_dict(), indent=2) + "\n"


# ---------------------------------------------------------------------------
# Logging helpers – interaction audit trail
# ---------------------------------------------------------------------------

_TRUST_LOG = Path(os.getenv("TRUST_LOG_PATH", Path.home() / ".trust_log.jsonl")).expanduser()

# Ensure the log exists (chmod 600) – keep within module init for simplicity.
_TRUST_LOG.parent.mkdir(parents=True, exist_ok=True)
if not _TRUST_LOG.exists():
    _TRUST_LOG.touch(mode=0o600)


def _log_event(event: Dict[str, Any]) -> None:
    """Append *event* as JSON line to the trust log (best-effort)."""

    try:
        with _TRUST_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, separators=(",", ":")) + "\n")
    except Exception as exc:  # pragma: no cover – IO errors are non-fatal
        _log.warning("Failed to write trust event: %s", exc)


# ---------------------------------------------------------------------------
# Heuristic metric helpers
# ---------------------------------------------------------------------------

_CONSENT_PATH = Path.home() / ".consent.json"


def _transparency_score() -> TrustMetric:
    """Return *Transparency* metric based on local vs remote processing ratio."""

    local_cnt = 0
    remote_cnt = 0
    for line in _TRUST_LOG.read_text().splitlines():
        with contextlib.suppress(Exception):
            data = json.loads(line)
            if data.get("event") == "process":
                if data.get("mode") == "local":
                    local_cnt += 1
                elif data.get("mode") == "remote":
                    remote_cnt += 1
    total = local_cnt + remote_cnt
    if total == 0:
        return TrustMetric("Transparency", 0, "No processing events recorded yet")
    score = int(100 * local_cnt / total)
    return TrustMetric("Transparency", score, f"{local_cnt}/{total} local operations")


def _consent_frequency_score() -> TrustMetric:
    """Return *Consent Frequency* metric based on consent registry entries."""

    if not _CONSENT_PATH.exists():
        return TrustMetric("Consent Frequency", 0, "Consent registry not initialised")

    try:
        data = json.loads(_CONSENT_PATH.read_text())
    except json.JSONDecodeError:  # pragma: no cover – corruption handling
        return TrustMetric("Consent Frequency", 0, "Consent registry corrupted")

    total_actions = len(data)
    allowed_actions = sum(1 for v in data.values() if v)
    if total_actions == 0:
        return TrustMetric("Consent Frequency", 0, "No consent prompts recorded")
    score = int(100 * allowed_actions / total_actions)
    return TrustMetric("Consent Frequency", score, f"{allowed_actions}/{total_actions} allowed")


def _hitl_adoption_score() -> TrustMetric:
    """Return *HITL Adoption* based on recorded *hitl* events."""

    hitl_cnt = 0
    total_cnt = 0
    for line in _TRUST_LOG.read_text().splitlines():
        with contextlib.suppress(Exception):
            data = json.loads(line)
            if data.get("event") == "hitl":
                hitl_cnt += 1
            if data.get("event") in {"hitl", "process"}:
                total_cnt += 1
    if total_cnt == 0:
        return TrustMetric("HITL Adoption", 0, "No interactive events recorded")
    score = int(100 * hitl_cnt / total_cnt)
    return TrustMetric("HITL Adoption", score, f"{hitl_cnt}/{total_cnt} interactive")


# ---------------------------------------------------------------------------
# Public Evaluation API
# ---------------------------------------------------------------------------

def evaluate_trust() -> TrustReport:
    """Calculate trust metrics and return :class:`TrustReport`."""

    metrics = [_transparency_score(), _consent_frequency_score(), _hitl_adoption_score()]
    total = int(sum(m.score for m in metrics) / len(metrics))
    return TrustReport(total_score=total, metrics=metrics)


# ---------------------------------------------------------------------------
# Modular processing helper – local-first routing
# ---------------------------------------------------------------------------

_REMOTE_TOGGLE_ENV = "ENABLE_REMOTE_PROCESSING"


def process_request(data: str, *, provider: str | None = None, consent_mgr: Optional[ConsentManager] = None) -> str:
    """Process *data* using *local* agent or – with consent – remote provider.

    Parameters
    ----------
    data:
        Arbitrary text payload.
    provider:
        Optional remote provider identifier (example: "openai").  Ignored when
        remote processing is disabled.
    consent_mgr:
        Optional :class:`ConsentManager` instance (dependency injection for
        tests / CLI).

    Returns
    -------
    str
        Response string (echo for local agent demonstration).
    """

    mgr = consent_mgr or ConsentManager()
    remote_enabled = os.getenv(_REMOTE_TOGGLE_ENV, "0").lower() in {"1", "true", "yes"}

    # Decide processing mode
    mode = "local"
    if remote_enabled:
        if mgr.request("remote_processing", "Send data to remote provider?", auto_deny=True):
            mode = "remote"
        else:
            _log.info("Remote processing denied – falling back to local agent")

    # ----------------------------------------
    # 1️⃣ Local agent – stub implementation
    # ----------------------------------------
    if mode == "local":
        response = data[::-1]  # simple placeholder – reverse string
    else:
        response = _remote_call_stub(data, provider=provider)

    # Audit event
    _log_event({
        "ts": datetime.utcnow().strftime(_ISO_FMT),
        "event": "process",
        "mode": mode,
        "provider": provider,
    })
    return response


def _remote_call_stub(payload: str, *, provider: str | None = None) -> str:  # noqa: D401 – imperative fine
    """Placeholder remote request (echoes payload upper-case)."""

    # # DISCUSS: Replace with real HTTP call in production
    _log.debug("Simulating remote call to %s with %s bytes", provider or "unknown", len(payload))
    return payload.upper()


# ---------------------------------------------------------------------------
# Typer CLI – trust metrics + processing demo
# ---------------------------------------------------------------------------

app = typer.Typer(add_help_option=True, no_args_is_help=True, pretty_exceptions_show_locals=False)


@app.command()
def metrics(json_output: bool = typer.Option(False, "--json", help="Emit JSON report"), verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Print transparency, consent and HITL metrics."""

    setup_logging("DEBUG" if verbose else "INFO")
    report = evaluate_trust()
    if json_output:
        typer.echo(report.to_json())
    else:
        _pretty_print(report)


@app.command()
def process(
    payload: str = typer.Argument(..., help="Payload string to process"),
    remote: bool = typer.Option(False, "--remote", help="Enable remote processing (sets env)")
):
    """Demo processing of *payload* using local-first routing."""

    if remote:
        os.environ[_REMOTE_TOGGLE_ENV] = "1"
    response = process_request(payload)
    typer.echo(response)


# ---------------------------------------------------------------------------
# Helper – human-readable pretty printer
# ---------------------------------------------------------------------------


def _pretty_print(report: TrustReport) -> None:  # noqa: D401 – imperative fine
    import textwrap

    typer.secho("\nUser Trust Metrics – Aggregate %d%%\n" % report.total_score, bold=True)
    for m in report.metrics:
        colour = "green" if m.score >= 80 else "yellow" if m.score >= 50 else "red"
        typer.secho(f"{m.name:<20}: {m.score:3d}%", fg=colour)
        if m.details:
            typer.echo(textwrap.indent(m.details, "  → "))
    typer.echo()


# Entry-point for `python -m src.trust_metrics` -------------------------------------------------
if __name__ == "__main__":  # pragma: no cover – manual CLI usage
    app()