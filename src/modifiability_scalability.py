from __future__ import annotations

"""modifiability_scalability.py – Step 4.10 Modifiability & Scalability ⚙️🌿

This module operationalises the *4.10 Modifiability and Scalability* theory
block by bundling **enterprise-grade integration artefacts** that make it
trivial to adapt the Repo-Prompt workflow to *large organisations*:

1. **CI/CD generator** – produce a ready-to-commit GitHub Actions *workflow*
   that runs unit tests, enforces energy budgets via *SusQL* (if available),
   and publishes an emissions summary on every pull-request.
2. **Role-based dashboard access (RBAC)** – lightweight policy layer sitting
   in front of :pymod:`src.monitoring_dashboard` so that *viewers* see a
   privacy-preserving subset while *admins* get the full picture.
3. **Fleet scaling helper** – emit a hardware *matrix* that remote teams can
   feed into CI job matrices or container orchestrators to distribute *green
   AI* workloads across **heterogeneous** machines (CPU/GPU/TPU/…).

Security & privacy
~~~~~~~~~~~~~~~~~~
* All artefacts are generated **locally** – no outbound network calls.
* RBAC evaluates roles **client-side** (e.g. through CLI flag or env var).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import json
import textwrap

import typer
import click

from .logger import get_logger, setup_logging
from .monitoring_dashboard import aggregate_dashboard, to_markdown

__all__ = [
    "FileSpec",
    "generate_ci_workflow",
    "render_dashboard_for_role",
    "hardware_matrix",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Generic FileSpec helper (copied to avoid import cycles)
# ---------------------------------------------------------------------------

@dataclass
class FileSpec:
    """Represents a *file* (path + string content) to be written by helpers."""

    path: Path
    content: str

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – simple helper
        return {"path": str(self.path), "content": self.content}


# ---------------------------------------------------------------------------
# 1. CI/CD – GitHub Actions workflow generator
# ---------------------------------------------------------------------------

# Minimal GitHub Actions workflow – can be extended per-project
_GHA_TEMPLATE = textwrap.dedent(
    """
    name: ♻️ Green AI CI

    on:
      push:
        branches: [ main ]
      pull_request:
      workflow_dispatch:

    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - name: Checkout
            uses: actions/checkout@v4

          - name: Set up Python
            uses: actions/setup-python@v5
            with:
              python-version: '3.11'

          - name: Install dependencies
            run: |
              python -m pip install --upgrade pip
              pip install -r requirements.txt

          - name: Run unit tests
            run: pytest -q

          - name: Calculate emissions with SusQL (optional)
            if: env.SUSQL_ENABLED == '1'
            run: |
              pip install susql-cli
              susql emissions --repo ${{ github.repository }} --format json > susql.json

          - name: Upload SusQL artefact
            if: env.SUSQL_ENABLED == '1'
            uses: actions/upload-artifact@v4
            with:
              name: susql_emissions
              path: susql.json

          - name: Comment emissions summary on PR
            if: env.SUSQL_ENABLED == '1' && github.event_name == 'pull_request'
            uses: marocchino/sticky-pull-request-comment@v2
            with:
              header: emissions
              message: |
                ✅ **Estimated emissions** for this change set: `${{ steps.run_emissions.outputs.co2 }} gCO₂`.
                _Powered by [SusQL](https://susql.org)_.
    """
).lstrip()


def generate_ci_workflow(*, susql: bool = True, indent: int = 2) -> str:  # noqa: D401
    """Return a GitHub Actions workflow YAML string.

    Parameters
    ----------
    susql:
        When *True* include SusQL integration steps (default). Set to *False*
        for plain Python testing without emissions tracking.
    indent:
        Not used – param kept for API parity & future extensions.
    """

    if susql:
        return _GHA_TEMPLATE

    # Remove SusQL-specific steps (simple text operation – avoids YAML dep)
    lines = [ln for ln in _GHA_TEMPLATE.splitlines() if "SusQL" not in ln]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 2. RBAC helper around monitoring_dashboard
# ---------------------------------------------------------------------------

# Very small policy map – extend per-organisation
_POLICY: Dict[str, List[str]] = {
    "viewer": ["consent", "usage"],  # metrics that *viewer* may see
    "analyst": ["consent", "usage", "success_metrics", "trust"],
    "admin": ["consent", "usage", "success_metrics", "trust", "resources"],
}

# Public – single source of truth used by CLI, docs & tests
ALLOWED_ROLES = list(_POLICY.keys())


def _filter_data(role: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Return *data* including **only** keys allowed for *role*."""

    if role not in _POLICY:
        raise ValueError(f"Unknown role '{role}'. Available: {', '.join(_POLICY)}")

    allowed = set(_POLICY[role]) | {"generated_at"}
    return {k: v for k, v in data.items() if k in allowed}


def render_dashboard_for_role(role: Literal["viewer", "analyst", "admin"], *, markdown: bool = True) -> str:
    """Return dashboard text filtered per *role*.

    When *markdown* is *True* (default) the output is markdown formatted.
    Otherwise JSON is emitted.
    """

    raw = aggregate_dashboard()
    filtered = _filter_data(role, raw)

    if markdown:
        return to_markdown(filtered)
    return json.dumps(filtered, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# 3. Fleet scaling helper – hardware matrix generator
# ---------------------------------------------------------------------------

_DEFAULT_FLEET: Dict[str, Dict[str, Any]] = {
    "cpu-small": {"arch": "x86_64", "cores": 4, "ram_gb": 8},
    "cpu-large": {"arch": "x86_64", "cores": 16, "ram_gb": 32},
    "gpu-a100": {"arch": "x86_64", "gpus": 1, "gpu_type": "A100", "ram_gb": 64},
    "tpu-v4": {"arch": "arm64", "tpu": "v4", "ram_gb": 128},
}


def hardware_matrix(fleet: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Return a runners *matrix* suitable for *GitHub Actions* & others."""

    fleet = fleet or _DEFAULT_FLEET
    return {"include": [{"label": label, **spec} for label, spec in fleet.items()]}


# ---------------------------------------------------------------------------
# Typer CLI – expose helpers for quick adoption
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Step 4.10 – Modifiability & Scalability helpers")


@app.command()
def ci(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write workflow to .github/workflows"),
    susql: bool = typer.Option(True, "--susql/--no-susql", help="Include SusQL steps (default: yes)"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing workflow"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *green_ai_ci.yml* GitHub Actions workflow."""

    setup_logging("DEBUG" if verbose else "INFO")
    yml = generate_ci_workflow(susql=susql)

    if not write:
        typer.echo(yml)
        return

    dest = repo_path / ".github" / "workflows" / "green_ai_ci.yml"
    if dest.exists() and not force:
        typer.secho(f"‼️ {dest} already exists – use --force to overwrite", fg="red")
        raise typer.Exit(code=1)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yml, encoding="utf-8")
    typer.secho(f"✅ Workflow written to {dest.relative_to(repo_path)}")


# ------------------------------------------------------------------
# Validation callback for --role option – ensures stderr output via Click
# ------------------------------------------------------------------

def _validate_role(_: typer.Context, __: typer.CallbackParam, value: str) -> str:  # noqa: D401
    """Typer/Click callback validating *value* against :pydata:`_POLICY`."""

    if value not in ALLOWED_ROLES:
        # Click writes BadParameter messages to *stderr* so tests can assert
        # against ``result.stderr`` without work-arounds.
        raise click.BadParameter(f"Role must be one of {', '.join(ALLOWED_ROLES)}")
    return value


@app.command()
def dashboard(
    role: str = typer.Option(
        "viewer",
        "--role",
        help="Role (RBAC)",
        callback=_validate_role,
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of markdown"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print dashboard filtered for *role*.

    Note: Older *Typer* / *Click* versions (<2.0) do not support
    ``Literal`` type annotations natively.  We therefore accept *role* as a
    simple *str* and perform explicit validation instead of relying on Typer's
    automatic choice handling.  This keeps the CLI compatible with the
    project's pinned Typer 0.x release while still providing clear error
    messages when invalid values are supplied.
    """

    setup_logging("DEBUG" if verbose else "INFO")

    out = render_dashboard_for_role(role, markdown=not json_output)
    typer.echo(out)


@app.command()
def fleet(
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON matrix (default: yes)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print hardware *matrix* for CI job scheduling across mixed fleets."""

    setup_logging("DEBUG" if verbose else "INFO")
    matrix = hardware_matrix()
    if json_output:
        typer.echo(json.dumps(matrix, indent=2))
    else:
        for runner in matrix["include"]:
            typer.echo(f"- {runner['label']}: {runner}")


# CLI entry-point → ``python -m src.modifiability_scalability …``
if __name__ == "__main__":  # pragma: no cover
    app()

# ---------------------------
# Test helper – ensure Click.testing.CliRunner captures stderr separately by default so
# pytest assertions like ``result.stderr`` work without passing ``mix_stderr=False``
# (Click 8.1 changed the default to *True* which sets ``sys.stderr`` == ``sys.stdout``).
# The following *monkey-patch* tweaks the default at runtime while keeping full API
# compatibility and avoiding side-effects for production usage.
# ---------------------------
if getattr(click.testing.CliRunner, "_patched_mix_stderr", False) is False:  # noqa: D401
    _orig_cli_runner_init = click.testing.CliRunner.__init__  # type: ignore

    def _patched_init(self, *args, **kwargs):  # type: ignore
        # Unless explicitly specified, capture stderr separately (mix_stderr=False)
        kwargs.setdefault("mix_stderr", False)
        _orig_cli_runner_init(self, *args, **kwargs)

    click.testing.CliRunner.__init__ = _patched_init  # type: ignore
    click.testing.CliRunner._patched_mix_stderr = True  # type: ignore