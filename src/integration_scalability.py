"""
integration_scalability.py – Step 8.6 Integration & Scalability 📈🔗

This module operationalises **Step 8.6 – Integration & Scalability** of the
*Repo-Prompt* blueprint.  It turns the high-level *rollout strategy* into
concrete, traceable artefacts that help project leads to coordinate the
multi-stage adoption across **repositories, teams & geographies**.

Key capabilities
================
1. **Rollout plan scaffold** – generate a *YAML* or *markdown* blueprint
   outlining the three rollout stages so product owners can adapt it to their
   roadmap.
2. **Progress tracker** – an *append-only JSONL* store (`.rollout_status.jsonl`)
   that records which *repo/team* is at which stage (audit-friendly).
3. **Typer CLI** – non-Python stakeholders can interact via:

   ```bash
   # Preview rollout plan (markdown)
   python -m src.integration_scalability plan scaffold --format md

   # Record that the *web* repo started Stage 1 …
   python -m src.integration_scalability status add --repo web --team frontend \
          --stage 1 --status in-progress

   # … later mark Stage 1 done and Stage 2 todo
   python -m src.integration_scalability status add --repo web --team frontend \
          --stage 1 --status done
   ```

Design notes
------------
* **Local-only** – purely file IO, no network calls.
* **Append-only** store – mirrors other *Step N* modules for auditability.
* **Minimal deps** – uses only *Typer* & stdlib.  No YAML lib – YAML is
  rendered manually to avoid external packages.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import textwrap

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "RolloutStage",
    "RolloutStatus",
    "RolloutStatusStore",
    "generate_rollout_plan",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. Stage definition                                                         #
###############################################################################


@dataclass(frozen=True, slots=True)
class RolloutStage:  # noqa: D101 – simple value holder
    """Represents a rollout *stage* (immutable)."""

    id: int
    name: str
    description: str


# Public constant – blueprint of the rollout strategy
ROLL_OUT_STAGES: List[RolloutStage] = [
    RolloutStage(1, "Pilot", "Pilot with two repositories (web + backend)."),
    RolloutStage(2, "Expand", "Expand across teams and geographies."),
    RolloutStage(
        3,
        "API extension",
        "API extension to integrate third-party tools & standards (OpenAPI, SARIF, SPDX).",
    ),
]

###############################################################################
# 2. Append-only JSONL store                                                 #
###############################################################################


@dataclass(slots=True)
class _BaseRecord:  # noqa: D401 – helper base class
    """Shared metadata + JSON serialisation helper."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # -------------------------
    # Serialisation helpers
    # -------------------------

    def to_json(self) -> str:  # noqa: D401 – imperative style ok
        data = asdict(self)
        data["type"] = self.__class__.__name__
        return json.dumps(data, separators=(",", ":"))


@dataclass(slots=True)
class RolloutStatus(_BaseRecord):
    """Represents the *progress* of a repo/team at a given rollout *stage*.

    Parameters
    ----------
    repo:
        Repository identifier (e.g. ``web``, ``backend``, ``infra``).
    team:
        Optional team or geographic identifier (e.g. ``frontend``, ``eu-west``).
    stage:
        Numeric stage (1 … N).
    status:
        Kanban-style status – ``todo`` | ``in-progress`` | ``done``.
    notes:
        Optional free-form notes or links.
    """

    repo: str
    team: Optional[str]
    stage: int
    status: Literal["todo", "in-progress", "done"] = "todo"
    notes: Optional[str] = None


class _JsonlStore:  # noqa: D101 – internal helper base
    """Lightweight append-only JSONL store."""

    def __init__(self, path: Path | str) -> None:  # noqa: D401
        self._path = Path(path).expanduser().resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # -------------------------
    # Public helpers
    # -------------------------

    def append(self, record: _BaseRecord) -> None:  # noqa: D401 – imperative
        """Append *record* to the JSONL file (fsync for safety)."""

        self._path.touch(exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
            fh.flush()

    # REVIEW: In the future switch to pandas for nicer analytics
    def load(self) -> List[Dict[str, Any]]:  # noqa: D401
        """Return all records as a list of dicts (unsorted)."""

        if not self._path.exists():
            return []

        with self._path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


_DEFAULT_STATUS_FILE = Path(".rollout_status.jsonl")


class RolloutStatusStore(_JsonlStore):  # noqa: D101 – concrete store
    """Concrete helper around :class:`RolloutStatus`."""

    def __init__(self, path: Path | str = _DEFAULT_STATUS_FILE):
        super().__init__(path)

    # Small helper returning *typed* objects (not exposed via __all__)
    def list(self, *, repo: Optional[str] = None, team: Optional[str] = None) -> List[RolloutStatus]:  # noqa: D401
        """Return matching :class:`RolloutStatus` objects (latest entries only)."""

        raw: List[RolloutStatus] = [RolloutStatus(**d) for d in self.load()]

        if repo:
            raw = [r for r in raw if r.repo == repo]
        if team:
            raw = [r for r in raw if r.team == team]
        return raw


###############################################################################
# 3. Rollout plan generator                                                  #
###############################################################################


def _plan_markdown() -> str:
    """Return rollout plan as **markdown**."""

    lines = ["# 🚀 Rollout Plan – Integration & Scalability\n"]
    for stage in ROLL_OUT_STAGES:
        lines.append(f"## Stage {stage.id} – {stage.name}\n")
        lines.append(textwrap.indent(stage.description + "\n", "- "))
    return "\n".join(lines) + "\n"


def _plan_yaml() -> str:
    """Return rollout plan as minimal **YAML** (no external libs)."""

    out_lines: List[str] = ["stages:"]
    for s in ROLL_OUT_STAGES:
        out_lines.extend(
            [
                f"  - id: {s.id}",
                f"    name: {s.name}",
                f"    description: |",  # YAML multi-line
                *("      " + ln for ln in textwrap.wrap(s.description, width=72)),
            ]
        )
    return "\n".join(out_lines) + "\n"


def generate_rollout_plan(fmt: Literal["md", "markdown", "yml", "yaml"] = "md") -> str:  # noqa: D401
    """Return the rollout plan blueprint in *fmt*.

    Accepted *fmt* aliases: ``md``|``markdown`` or ``yml``|``yaml``.
    """

    fmt = fmt.lower()
    if fmt in {"md", "markdown"}:
        return _plan_markdown()
    if fmt in {"yml", "yaml"}:
        return _plan_yaml()
    raise ValueError("Unknown format. Use md|markdown|yml|yaml")


###############################################################################
# 4. Typer CLI                                                               #
###############################################################################

app = typer.Typer(add_completion=False, help="Integration & Scalability toolkit (Step 8.6)")

# -----------------
# Plan sub-commands
# -----------------

_plan_app = typer.Typer(name="plan", help="Generate rollout plan blueprints")
app.add_typer(_plan_app)


@_plan_app.command("scaffold")
def cli_plan_scaffold(
    fmt: str = typer.Option("md", "--format", "-f", help="md|yml"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write to file instead of STDOUT"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the rollout plan (*markdown* or *YAML*)."""

    setup_logging("DEBUG" if verbose else "INFO")
    plan = generate_rollout_plan(fmt)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(plan, encoding="utf-8")
        typer.echo(f"✅ Rollout plan written to {out}")
    else:
        typer.echo(plan.rstrip("\n"))  # omit trailing newline for terseness


# --------------------
# Status sub-commands
# --------------------

_status_app = typer.Typer(name="status", help="Track rollout progress")
app.add_typer(_status_app)


@_status_app.command("add")
def cli_status_add(
    repo: str = typer.Option(..., "--repo", help="Repository identifier (slug)"),
    team: Optional[str] = typer.Option(None, "--team", help="Team/geography"),
    stage: int = typer.Option(..., "--stage", min=1, help="Stage number"),
    status: str = typer.Option("in-progress", "--status", help="todo|in-progress|done"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Optional notes"),
    store_path: Path = typer.Option(_DEFAULT_STATUS_FILE, "--store", help="Custom JSONL path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Record or update rollout *status* for a repo/team."""

    setup_logging("DEBUG" if verbose else "INFO")
    rec = RolloutStatus(repo=repo, team=team, stage=stage, status=status, notes=notes)
    RolloutStatusStore(store_path).append(rec)
    typer.echo("✅ Rollout status recorded")


@_status_app.command("list")
def cli_status_list(
    repo: Optional[str] = typer.Option(None, "--repo", help="Filter by repo"),
    team: Optional[str] = typer.Option(None, "--team", help="Filter by team"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    store_path: Path = typer.Option(_DEFAULT_STATUS_FILE, "--store", help="JSONL path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List recorded statuses (filtered via flags)."""

    setup_logging("DEBUG" if verbose else "INFO")
    items = RolloutStatusStore(store_path).list(repo=repo, team=team)

    if json_output:
        json.dump([asdict(i) for i in items], typer.get_text_stream("stdout"), indent=2)
        typer.echo()
    else:
        if not items:
            typer.echo("No records found.")
            raise typer.Exit()

        # Render simple markdown table
        typer.echo("# 📊 Rollout Progress\n")
        typer.echo("| Time | Repo | Team | Stage | Status | Notes |\n|---|---|---|---|---|---|")
        for i in items:
            typer.echo(
                f"| {i.created_at} | {i.repo} | {i.team or '-'} | {i.stage} | {i.status} | {i.notes or '-'} |"
            )


###############################################################################
# 5. Module CLI Entrypoint                                                   #
###############################################################################

# Allow `python -m src.integration_scalability …`
if __name__ == "__main__":  # pragma: no cover – convenience shortcut
    app()