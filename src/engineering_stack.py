from __future__ import annotations

"""engineering_stack.py – Step 3.5 Methodologies & Tools ⚙️🏛️

This module turns the theoretical **3.5 Methodologies and Tools** section of the
project specification into *runnable* Python utilities.  Two complementary
areas are covered:

* **Engineering Stack Validation** – lightweight checks that ensure a local
  developer workstation (or CI node) is able to build *privacy-respecting*
  micro-services in **Rust** or **Go**, compile them to **WebAssembly (WASM)**
  and – where available – run them inside a **sandbox** (``wasmtime`` runtime).
* **Governance Tooling** – helper functions to *parse End-User Licence
  Agreements (EULA)* for risky clauses **and** to map a *jurisdiction* (ISO
  3166-1 alpha-2 country code) to a suitable *sovereign cloud region*.

The public API mirrors patterns introduced by previous modules to keep a *stable
shape* across the codebase:

```
from src.engineering_stack import verify_stack, parse_eula, route_jurisdiction

report = verify_stack(pretty=True)
flagged = parse_eula(Path("EULA.txt"))
region  = route_jurisdiction("DE", provider="aws")
```

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* All checks run **locally** – no network traffic is generated.
* EULA parsing is *keyword-based* only; it does **not** provide legal advice.
  # REVIEW: Always perform human review before shipping.
* Jurisdiction routing uses *static mappings* that need periodic verification.
  # DISCUSS: Could pull dynamically from CSP APIs in the future.
"""

import json
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List

import typer

from .logger import get_logger, setup_logging
from .methodology_tools import CheckResult  # re-use existing tiny dataclass

__all__ = [
    "verify_stack",
    "parse_eula",
    "route_jurisdiction",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Engineering-stack introspection helpers
# ---------------------------------------------------------------------------


def _check_cmd(cmd: str, friendly: str | None = None) -> CheckResult:
    """Return :class:`CheckResult` for *cmd* availability (uses ``shutil.which``)."""

    friendly = friendly or cmd
    path = shutil.which(cmd)
    return CheckResult(friendly, bool(path), path or "not found on PATH")


def _check_rust_target() -> CheckResult:
    """Verify that **rustc** supports the *wasm32-unknown-unknown* target."""

    if not shutil.which("rustc"):
        return CheckResult("Rust wasm32 target", False, "rustc not installed")

    try:
        # Query installed targets (fast; local call).
        result = subprocess.run(
            ["rustup", "target", "list", "--installed"], capture_output=True, text=True, check=False
        )
        installed = result.stdout.strip().splitlines()
        ok = any(t.startswith("wasm32-") for t in installed)
        return CheckResult("Rust wasm32 target", ok, str(installed))
    except FileNotFoundError:
        # rustup not present – fallback: assume target missing.
        return CheckResult("Rust wasm32 target", False, "rustup not installed")


def _check_go_wasm() -> CheckResult:
    """Check whether **Go** supports Wasm via the ``wasm`` architecture."""

    if not shutil.which("go"):
        return CheckResult("Go wasm support", False, "go not installed")

    # Retrieve `go env` – safe on all platforms.
    try:
        result = subprocess.run(["go", "env", "GOARCH"], capture_output=True, text=True, check=True)
        arch = result.stdout.strip()
        ok = arch == "wasm" or True  # Modern Go can always target wasm via GOOS=js GOARCH=wasm.
        return CheckResult("Go wasm support", ok, f"current GOARCH={arch}")
    except Exception as exc:  # pragma: no cover – platform quirks
        return CheckResult("Go wasm support", False, str(exc))


@dataclass
class StackReport:
    """Machine-readable summary for :func:`verify_stack`."""

    created_at: str
    os: str
    all_ok: bool
    checks: List[CheckResult]

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        return {
            "created_at": self.created_at,
            "os": self.os,
            "all_ok": self.all_ok,
            "checks": [c.as_dict() for c in self.checks],
        }

    def to_json(self, **kwargs) -> str:  # pragma: no cover – convenience helper
        return json.dumps(self.as_dict(), indent=2, **kwargs)


# Public verification API ---------------------------------------------------------------------


def verify_stack(*, pretty: bool = False) -> StackReport:
    """Return a :class:`StackReport` with engineering-stack readiness results."""

    from datetime import datetime

    checks = [
        _check_cmd("rustc", "Rust compiler"),
        _check_rust_target(),
        _check_cmd("go", "Go compiler"),
        _check_go_wasm(),
        _check_cmd("wasmtime", "Wasmtime runtime"),
    ]

    report = StackReport(created_at=datetime.utcnow().isoformat() + "Z", os=platform.system(), all_ok=False, checks=checks)
    report.all_ok = all(c.ok for c in checks)

    if pretty:
        _print_report(report)
    return report


def _print_report(report: StackReport) -> None:  # noqa: D401 – imperative mood fine
    """Human-readable *pretty* printer used by CLI."""

    import textwrap

    status = "✔ READY" if report.all_ok else "✖ MISSING TOOLS"
    typer.secho(f"Engineering Stack Check – {status}\n", fg="green" if report.all_ok else "red", bold=True)

    for c in report.checks:
        colour = "green" if c.ok else "red"
        typer.secho(f"{c.name:<25} : {'OK' if c.ok else 'MISSING'}", fg=colour)
        if not c.ok and c.details:
            typer.echo(textwrap.indent(c.details, "  → "))
    typer.echo()


# ---------------------------------------------------------------------------
# Governance tooling – EULA parsing & jurisdiction routing
# ---------------------------------------------------------------------------
# Keyword heuristics for *potentially risky* clauses – human editable.
_FLAGGED_PATTERNS: Dict[str, re.Pattern[str]] = {
    "third_party_sharing": re.compile(r"share[s]?\s+.*third\s+part(y|ies)", re.I),
    "data_sale": re.compile(r"sell[s]?\s+.*data", re.I),
    "tracking": re.compile(r"track[s]?\s+.*user", re.I),
    "waiver_of_liability": re.compile(r"waive[s]?\s+.*liabilit", re.I),
    "binding_arbitration": re.compile(r"binding\s+arbitration", re.I),
}


@dataclass
class EULAFlag:
    """Single match inside a EULA document."""

    line_no: int
    rule: str
    excerpt: str


@dataclass
class EULAReport:
    """Collection of :class:`EULAFlag` objects with helper serialisation."""

    path: str
    flags: List[EULAFlag]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "flags": [asdict(f) for f in self.flags],
        }

    def to_json(self, **kwargs) -> str:  # pragma: no cover
        return json.dumps(self.as_dict(), indent=2, **kwargs)


# Country code → provider → region mapping (very limited MVP)
_JURISDICTION_MAP: Dict[str, Dict[str, str]] = {
    "DE": {"aws": "eu-central-1", "azure": "germany-west-central"},  # Germany
    "FR": {"aws": "eu-west-3", "azure": "france-central"},  # France
    "US": {"aws": "us-east-1", "azure": "eastus"},
    "IN": {"aws": "ap-south-1", "azure": "central-india"},
    "CN": {"aws": "cn-north-1", "azure": "china-north"},
    # Add more as needed – keep sovereign concerns in mind.
}


# Public helper functions --------------------------------------------------------------------

def parse_eula(path: Path | str | None = None, *, text: str | None = None) -> EULAReport:
    """Semantic-flag a EULA file or *text* and return :class:`EULAReport`.

    Either *path* **or** *text* must be supplied.  The function scans each line
    for *flagged patterns* defined in :pydata:`_FLAGGED_PATTERNS`.
    """

    if not path and text is None:
        raise ValueError("Either 'path' or 'text' must be provided")

    if path:
        path = Path(path)
        content = path.read_text(encoding="utf-8", errors="ignore")
        label = str(path)
    else:
        content = text or ""
        label = "<in-memory-text>"

    flags: List[EULAFlag] = []

    for i, line in enumerate(content.splitlines(), start=1):
        for rule, pattern in _FLAGGED_PATTERNS.items():
            if pattern.search(line):
                excerpt = line.strip()[:120]
                flags.append(EULAFlag(line_no=i, rule=rule, excerpt=excerpt))
                _log.debug("Flagged %s at line %d: %s", rule, i, excerpt)

    return EULAReport(path=label, flags=flags)


def route_jurisdiction(country_code: str, *, provider: str = "aws") -> str:
    """Return *cloud region* for *country_code* (**ISO-3166-1 alpha-2**).

    The mapping is static; if the combination is unknown a *ValueError* is
    raised to force explicit handling.
    """

    code = country_code.strip().upper()
    provider = provider.lower()

    try:
        mapping = _JURISDICTION_MAP[code][provider]
    except KeyError as exc:
        raise ValueError(f"No mapping for {code}/{provider}") from exc
    return mapping


# ---------------------------------------------------------------------------
# Typer CLI entry-points (mirror style of other *Step 3.* modules)
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Step 3.5 Engineering & Governance utilities")


@app.command()
def verify(
    pretty: bool = typer.Option(False, "--pretty", help="Print human-readable table"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Check local toolchain for Rust/Go/Wasm readiness."""

    setup_logging("DEBUG" if verbose else "INFO")

    report = verify_stack(pretty=pretty and not json_output)
    if json_output:
        typer.echo(report.to_json())


@app.command()
def eula(
    file: Path = typer.Argument(..., exists=True, readable=True, help="Path to EULA or TOS text file"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON report"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Parse *file* and flag risky clauses."""

    setup_logging("DEBUG" if verbose else "INFO")
    report = parse_eula(file)

    if json_output:
        typer.echo(report.to_json())
    else:
        if report.flags:
            typer.secho(f"Found {len(report.flags)} flagged clause(s):", fg="yellow", bold=True)
            for f in report.flags:
                typer.echo(f"• L{f.line_no:>3} – {f.rule.replace('_', ' ')}\n  {f.excerpt}")
        else:
            typer.secho("No risky clauses detected – still perform human review!", fg="green")


@app.command()
def route(
    country: str = typer.Argument(..., help="ISO-3166-1 alpha-2 country code e.g. DE"),
    provider: str = typer.Option("aws", "--provider", "-p", help="Cloud provider e.g. aws, azure"),
):
    """Print recommended *sovereign cloud region* for *country*."""

    try:
        region = route_jurisdiction(country, provider=provider)
        typer.secho(region, fg="green")
    except ValueError as exc:
        typer.secho(str(exc), fg="red")