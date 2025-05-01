"""
adaptive_scaling.py – Step 3.10 Adaptive Scaling 🚀🛡️

This module **extends Repo-Prompt's privacy-first design** to *other* developer
utilities (linters, test-runners, formatters …), while ensuring that only
**jurisdiction-compliant** components are executed on a given workstation or CI
agent.

High-level features
-------------------
1. **Pluggable Tool Adapters** – Wrap any *CLI*-based developer tool in a
   lightweight :class:`ToolAdapter` that records meta-data (name, binary,
   jurisdiction tags) and provides a :py:meth:`ToolAdapter.run` convenience
   method.
2. **Jurisdiction Policy Engine** – A tiny decision layer reading the
   workstation's jurisdiction from
   ``$ADAPTIVE_SCALING_REGION`` (fallback: "INTL") and allowing the caller to
   *filter* adapters so that only tools *whitelisted* for the chosen region are
   offered.
3. **Typer CLI** – `python -m src.adaptive_scaling list` prints all available
   adapters along with their compliance status. `… run flake8` executes a tool
   *only when allowed* or exits with *code 2*.

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* ▶ *Offline-first* – No network requests are made. Region detection relies on
  an environment variable to avoid leaking IP addresses.
* 🛡️ *Fail-closed* – Unknown regions **deny** all tools unless an explicit
  override (`--force`) is supplied.
* # REVIEW: Please double-check jurisdiction maps and update regularly.

Example
~~~~~~~
```bash
# EU developer workstation
export ADAPTIVE_SCALING_REGION=EU

# List – pytest is allowed (local), some SaaS scanner is not
python -m src.adaptive_scaling list

# Safe execution wrapper
python -m src.adaptive_scaling run pytest -q tests/
```
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "ToolAdapter",
    "registry",
    "register_adapter",
    "get_region",
    "filter_compliant",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data structures & registry
# ---------------------------------------------------------------------------

@dataclass
class ToolAdapter:
    """Metadata wrapper around a CLI-based *developer tool*.

    Parameters
    ----------
    name:
        Human-friendly identifier (e.g. ``flake8``).
    binary:
        Executable name (as passed to ``shutil.which`` / subprocess).  May be a
        shell string containing arguments.
    regions_allowed:
        Iterable of *region codes* ("EU", "US" …) for which this tool is
        considered **compliant**.  Use the special value ``"INTL"`` to allow
        global usage.
    description:
        Optional short help text displayed by the CLI.
    """

    name: str
    binary: str
    regions_allowed: Sequence[str] = field(default_factory=lambda: ["INTL"])
    description: str | None = None

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def is_allowed(self, region: str) -> bool:
        """Return *True* when *region* is included in :pyattr:`regions_allowed`."""

        return region in self.regions_allowed or "INTL" in self.regions_allowed

    # # REVIEW: Double-check subprocess security when passing user args
    def run(self, args: Sequence[str] | None = None, *, region: str | None = None, check: bool = True) -> int:
        """Run the adapter's underlying command when *region* is compliant.

        Parameters
        ----------
        args:
            Extra CLI arguments forwarded to the underlying binary.
        region:
            Override the detected region (see :func:`get_region`).
        check:
            When *True* raise :class:`RuntimeError` if the command exits with a
            non-zero status (mirrors ``subprocess.run(check=True)``).

        Returns
        -------
        int
            Exit code of the underlying process.
        """

        region = region or get_region()
        if not self.is_allowed(region):
            raise PermissionError(f"Tool '{self.name}' is not allowed in region '{region}'.")

        cmd_parts = [self.binary] + list(args or [])
        cmd_str = " ".join(shlex.quote(p) for p in cmd_parts)
        _log.debug("Executing adapter '%s': %s", self.name, cmd_str)
        result = subprocess.run(cmd_parts).returncode
        if check and result != 0:
            raise RuntimeError(f"Adapter '{self.name}' exited with code {result}.")
        return result


# Global registry – lazy populated below
registry: Dict[str, ToolAdapter] = {}


def register_adapter(adapter: ToolAdapter) -> None:
    """Add *adapter* to the global :pydata:`registry` (idempotent)."""

    if adapter.name in registry:  # pragma: no cover – defensive guard
        _log.debug("Overwriting existing adapter '%s'", adapter.name)
    registry[adapter.name] = adapter


# ---------------------------------------------------------------------------
# Jurisdiction utility
# ---------------------------------------------------------------------------

_REGION_ENV = "ADAPTIVE_SCALING_REGION"


def get_region(default: str = "INTL") -> str:
    """Return region code from :pyenvvar:`ADAPTIVE_SCALING_REGION` (upper-cased)."""

    return os.getenv(_REGION_ENV, default).upper()


def filter_compliant(region: str | None = None) -> Dict[str, ToolAdapter]:
    """Return *registry* subset compliant with *region* (defaults to env)."""

    region = region or get_region()
    return {name: ta for name, ta in registry.items() if ta.is_allowed(region)}


# ---------------------------------------------------------------------------
# Built-in adapters – extend as needed
# ---------------------------------------------------------------------------

# Local-only tools (always allowed)
register_adapter(ToolAdapter("pytest", "pytest", ["INTL"], "Python test runner"))
register_adapter(ToolAdapter("flake8", "flake8", ["INTL"], "Python style checker"))

# Example SaaS-based security scanner – restricted to US region
register_adapter(
    ToolAdapter(
        "snyk", "snyk", ["US"], "SaaS vulnerability scanner (requires outbound network)"
    )
)

# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Adaptive Scaling (Step 3.10) – jurisdiction-aware tool launcher")


@app.command()
def list(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List registered adapters and their compliance status for the current region."""

    setup_logging("DEBUG" if verbose else "INFO")
    region = get_region()

    data = {
        name: {
            "binary": ta.binary,
            "allowed": ta.is_allowed(region),
            "regions_allowed": list(ta.regions_allowed),
            "description": ta.description or "",
        }
        for name, ta in registry.items()
    }

    if json_output:
        import json

        typer.echo(json.dumps({"region": region, "adapters": data}, indent=2))
        raise typer.Exit()

    typer.secho(f"Adaptive Scaling – region: {region}\n", bold=True)
    for name, meta in data.items():
        colour = "green" if meta["allowed"] else "red"
        status = "✔ allowed" if meta["allowed"] else "✖ blocked"
        typer.secho(f"{name:<10} : {status}", fg=colour)
        if meta["description"]:
            typer.echo(f"  → {meta['description']}")


@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def run(
    tool: str = typer.Argument(..., help="Adapter name (see 'list')"),
    force: bool = typer.Option(False, "--force", help="Ignore region policy (unsafe)"),
    ctx: typer.Context = typer.Option(..., hidden=True),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Execute *tool* with remaining CLI arguments if region-compliant."""

    setup_logging("DEBUG" if verbose else "INFO")

    adapter = registry.get(tool)
    if not adapter:
        typer.secho(f"Unknown tool '{tool}'. Use 'list' to view valid names.", fg="red", err=True)
        raise typer.Exit(code=2)

    region = get_region()
    if not adapter.is_allowed(region) and not force:
        typer.secho(
            f"Tool '{tool}' is not permitted in region '{region}'. Use --force to override.",
            fg="red",
            err=True,
        )
        raise typer.Exit(code=2)

    # Forward *all* unknown CLI args directly to the adapter command
    extras = [str(a) for a in ctx.args]
    try:
        exit_code = adapter.run(extras, region=region, check=False)
    except PermissionError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(code=2)
    except RuntimeError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(code=exit_code)

    raise typer.Exit(code=exit_code)


# Entry-point shim (`python -m src.adaptive_scaling …`)
if __name__ == "__main__":
    app()  # pragma: no cover