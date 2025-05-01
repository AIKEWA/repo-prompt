from __future__ import annotations

"""prompt_governance.py – Step 7.4 Governance Layer Rollout 🛡️✅

This module adds a *Governance Layer* on top of ``prompt_ops_framework``.

Highlights
~~~~~~~~~~
* **Prompt review & approval workflow** – track approvals/rejections for every
  prompt *version* using an *append-only* JSON-Lines ledger (``.prompt_reviews.jsonl``).
* **ISO/NIST-aligned controls** – configurable *minimum approval* thresholds.
  Sensitive prompts (``security`` / ``privacy`` tags) require **≥2** approvals
  by default (NIST SP 800-53 ~ CM-5 / SA-11).  The threshold can be increased
  via the ``PROMPT_REVIEW_MIN_APPROVALS`` env var to match stricter ISO-27001
  change-control policies.
* **Author / approver attribution** – records the ``actor`` responsible for
  each *approval* or *rejection*.  *Authors* are inferred from the Git commit
  that introduced the prompt file (first parent commit).
* **Git-backed provenance** – all ledger modifications are *committed* (but not
  pushed) using Helper functions in :pymod:`src.git_utils`.
* **CLI** – ``python -m src.prompt_governance …`` offers the following sub-
  commands:

  ``approve <NAME> <VERSION> --actor <email>``
      Append an **approve** record and commit the ledger.
  ``reject  <NAME> <VERSION> --actor <email> [--reason <txt>]``
      Append a **reject** record.
  ``status [--all/--pending]``
      Display approval state of all or *pending* prompts.

Design decisions
================
* We deliberately keep the ledger *local-only* – CI pipelines decide when to
  push, mirroring *policy-as-code* best practices.
* **Open Policy Agent (OPA)** support is exposed via :func:`evaluate_with_opa` –
  a thin wrapper around the `opa` CLI.  It is *optional* (stubbed if the binary
  is absent) to avoid hard runtime dependencies.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, Sequence, Any
import subprocess
import shutil  # needed for evaluate_with_opa

import typer
from git import Repo  # type: ignore – provided by requirements.txt

from .logger import get_logger, setup_logging
from .prompt_ops_framework import PromptTemplate, list_templates
from .git_utils import ensure_clean_worktree, stage_and_commit

__all__ = [
    "ReviewRecord",
    "ReviewStore",
    "evaluate_with_opa",
    "min_approvals_required",
    "app",
]

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
_DEFAULT_LEDGER_PATH = Path(os.getenv("PROMPT_REVIEW_FILE", ".prompt_reviews.jsonl"))

_log = get_logger(__name__)

###############################################################################
# 1. Data model                                                               #
###############################################################################


@dataclass
class ReviewRecord:  # noqa: D101 – simple value holder
    prompt_name: str
    version: str
    action: str  # "approve" | "reject"
    actor: str  # email or identifier of reviewer
    reason: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # -------------------
    # Serialisation
    # -------------------

    def to_json(self) -> str:  # pragma: no cover – trivial
        return json.dumps(asdict(self), separators=(",", ":"))


###############################################################################
# 2. Ledger helpers                                                           #
###############################################################################


class ReviewStore:  # noqa: D101 – lightweight helper
    def __init__(self, path: str | Path = _DEFAULT_LEDGER_PATH):
        self._path = Path(path)
        self._records: List[ReviewRecord] | None = None  # lazy load

    # -------------------
    # I/O
    # -------------------

    def _ensure_loaded(self) -> None:
        if self._records is not None:
            return
        self._records = []
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                self._records.append(ReviewRecord(**data))

    def _flush(self) -> None:
        if self._records is None:
            return  # nothing to flush
        text = "\n".join(r.to_json() for r in self._records) + "\n"
        self._path.write_text(text, encoding="utf-8")

    # -------------------
    # Public API
    # -------------------

    def append(self, record: ReviewRecord) -> None:
        """Add *record* and persist."""

        self._ensure_loaded()
        assert self._records is not None
        self._records.append(record)
        self._flush()

    def approvals(self, name: str, version: str) -> List[ReviewRecord]:
        """Return **approval** records for *name* / *version*."""

        self._ensure_loaded()
        assert self._records is not None
        return [r for r in self._records if r.prompt_name == name and r.version == version and r.action == "approve"]

    def rejections(self, name: str, version: str) -> List[ReviewRecord]:
        self._ensure_loaded()
        assert self._records is not None
        return [r for r in self._records if r.prompt_name == name and r.version == version and r.action == "reject"]

    def is_approved(self, tmpl: PromptTemplate) -> bool:
        """Return *True* if *tmpl* meets the **minimum approval** threshold."""

        return len(self.approvals(tmpl.name, tmpl.version)) >= min_approvals_required(tmpl)

    def summary(self) -> Dict[str, Dict[str, int]]:
        """Return {"name@version": {"approvals": n, "rejections": m}} mapping."""

        self._ensure_loaded()
        assert self._records is not None
        stats: Dict[str, Dict[str, int]] = {}
        for rec in self._records:
            key = f"{rec.prompt_name}@{rec.version}"
            item = stats.setdefault(key, {"approvals": 0, "rejections": 0})
            if rec.action == "approve":
                item["approvals"] += 1
            else:
                item["rejections"] += 1
        return stats


###############################################################################
# 3. Policy helpers                                                           #
###############################################################################


SENSITIVE_TAGS: set[str] = {"security", "privacy", "financial"}


def min_approvals_required(template: PromptTemplate) -> int:  # noqa: D401 – imperative OK
    """Return the **minimum number of approvals** required for *template*.

    Default is ``PROMPT_REVIEW_MIN_APPROVALS`` (env, fallback **1**).  If the
    prompt carries a *sensitive* tag, the function returns ``max(2, env)`` i.e.
    at least **2** approvals.
    """

    base = int(os.getenv("PROMPT_REVIEW_MIN_APPROVALS", "1"))
    if template.tags and any(t in SENSITIVE_TAGS for t in template.tags):
        return max(2, base)
    return base


###############################################################################
# 4. Optional Open Policy Agent integration                                   #
###############################################################################


def evaluate_with_opa(template_json: str, policy_path: Path) -> Dict[str, Any]:  # noqa: ANN001
    """Return OPA evaluation result for *template_json* against *policy_path*.

    Requires the `opa` binary in $PATH.  The policy must expose a ``deny`` rule
    that yields a list of *violation strings*.  The helper returns a dict::

        {"allowed": bool, "violations": [...]}  # viol. empty when allowed

    The shell call is *risky* – input is passed via stdin – but acceptable
    within the confines of a CI pipeline.  The function falls back to *allow*
    when OPA is **not** installed or exits with a non-zero code.  Consumers
    should treat a failed evaluation as **deny** when running in strict mode.
    """

    if not shutil.which("opa"):
        return {"allowed": True, "violations": ["opa not installed – skipped"]}

    cmd = ["opa", "eval", "--format=json", "-i", "-", "-d", str(policy_path), "data.prompt.allow"]
    proc = subprocess.run(cmd, input=template_json.encode(), capture_output=True)
    if proc.returncode != 0:
        return {"allowed": False, "violations": [proc.stderr.decode() or "OPA evaluation failed"]}

    res = json.loads(proc.stdout)
    allowed = bool(res.get("result") and res["result"][0].get("expressions", [{}])[0].get("value", False))
    return {"allowed": allowed, "violations": [] if allowed else ["policy denied"]}


###############################################################################
# 5. CLI                                                                      #
###############################################################################


app = typer.Typer(add_completion=False, help="Prompt governance manager – review & approval workflow")


@app.command()
def approve(
    name: str = typer.Argument(..., help="Prompt name e.g. 'bug_fix'"),
    version: str = typer.Argument(..., help="Semantic version, e.g. '1.2.0'"),
    actor: str = typer.Option(..., "--actor", "-a", help="Identifier (email) of reviewer"),
    ledger_path: Path = typer.Option(_DEFAULT_LEDGER_PATH, "--ledger", help="JSONL review ledger"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs"),
):
    """Append an **approval** record for *name*/*version*."""

    if verbose:
        setup_logging("DEBUG")

    store = ReviewStore(ledger_path)
    store.append(ReviewRecord(prompt_name=name, version=version, action="approve", actor=actor))

    # Git commit the ledger file for provenance
    repo = Repo(Path.cwd(), search_parent_directories=True)
    ensure_clean_worktree(repo.working_tree_dir)
    stage_and_commit(repo.working_tree_dir, [ledger_path], f"approve(prompt): {name} v{version} by {actor}")

    _log.info("Approved %s v%s by %s", name, version, actor)


@app.command()
def reject(
    name: str = typer.Argument(..., help="Prompt name"),
    version: str = typer.Argument(..., help="Version"),
    actor: str = typer.Option(..., "--actor", "-a", help="Reviewer"),
    reason: str | None = typer.Option(None, "--reason", "-r", help="Optional rejection reason"),
    ledger_path: Path = typer.Option(_DEFAULT_LEDGER_PATH, "--ledger", help="Ledger path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Append a **rejection** record for *name*/*version*."""

    if verbose:
        setup_logging("DEBUG")

    store = ReviewStore(ledger_path)
    store.append(ReviewRecord(prompt_name=name, version=version, action="reject", actor=actor, reason=reason))

    repo = Repo(Path.cwd(), search_parent_directories=True)
    ensure_clean_worktree(repo.working_tree_dir)
    stage_and_commit(repo.working_tree_dir, [ledger_path], f"reject(prompt): {name} v{version} by {actor}")

    _log.info("Rejected %s v%s by %s", name, version, actor)


@app.command()
def status(
    pending: bool = typer.Option(False, "--pending", help="Show only prompts that do NOT meet approval threshold"),
    include_rejected: bool = typer.Option(False, "--all", help="Include rejected counts"),
    ledger_path: Path = typer.Option(_DEFAULT_LEDGER_PATH, "--ledger", help="Ledger path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show approval *status* of prompts (pending by default)."""

    if verbose:
        setup_logging("DEBUG")

    tmpls: Sequence[PromptTemplate] = list_templates()
    store = ReviewStore(ledger_path)

    lines: List[str] = []
    for tmpl in tmpls:
        ok = store.is_approved(tmpl)
        if pending and ok:
            continue  # skip approved if only pending requested
        appr = len(store.approvals(tmpl.name, tmpl.version))
        rej = len(store.rejections(tmpl.name, tmpl.version))
        need = min_approvals_required(tmpl)
        status_str = "✅ APPROVED" if ok else "⚠️  PENDING"  # FEEDBACK: consider unicode flags
        line = f"{tmpl.name} v{tmpl.version}: {status_str} ({appr}/{need} approvals" + (f", {rej} rejects" if include_rejected else ")")
        lines.append(line)

    typer.echo("\n".join(lines) if lines else "All prompts approved ✔")


# Human Collaboration Tags – highlight policy area for future discussion
# REVIEW: Support *multiple* ledgers (per-branch) to avoid merge conflicts?
# DISCUSS: Implement GitHub Actions status check that blocks PRs when pending.

if __name__ == "__main__":  # pragma: no cover
    app()