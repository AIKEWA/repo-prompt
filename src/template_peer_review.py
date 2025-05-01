from __future__ import annotations

"""template_peer_review.py – Phase 3e: Peer Review Mode with Comment Overlay ✍️

Adds a lightweight *peer review workflow* for prompt templates:

* **compare** – render markdown diff between two files (YAML/JSON) to STDOUT.
  Optionally overlays existing comments from a JSONL store.
* **comment** – attach a line-based comment to a diff.
* **approve** – record community approval for a template.

Data files
~~~~~~~~~~
* `.template_comments.jsonl` – newline-delimited JSON with diff comments
* `.template_approvals.json` – mapping of template filename ➜ list[user]
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import difflib
import json
import getpass

import typer

from .logger import get_logger, setup_logging

_log = get_logger(__name__)

_COMMENT_FILE = Path(".template_comments.jsonl")
_APPROVAL_FILE = Path(".template_approvals.json")

###############################################################################
# Helpers                                                                     #
###############################################################################


def _load_comments() -> List[Dict[str, Any]]:  # noqa: D401
    if not _COMMENT_FILE.exists():
        return []
    return [json.loads(l) for l in _COMMENT_FILE.read_text().splitlines() if l.strip()]


def _append_comment(rec: Dict[str, Any]) -> None:  # noqa: D401
    _COMMENT_FILE.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8", append=True) if _COMMENT_FILE.exists() else _COMMENT_FILE.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")


###############################################################################
# CLI                                                                         #
###############################################################################

app = typer.Typer(add_completion=False, help="Peer review of templates")


@app.command()
def compare(  # noqa: D401 – CLI entrypoint
    old_file: Path = typer.Argument(..., exists=True, readable=True, help="Original template"),
    new_file: Path = typer.Argument(..., exists=True, readable=True, help="Modified template"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print *markdown* diff between *old_file* and *new_file* with comments."""

    if verbose:
        setup_logging("DEBUG")

    old_lines = old_file.read_text().splitlines()
    new_lines = new_file.read_text().splitlines()
    diff_lines = list(
        difflib.unified_diff(old_lines, new_lines, fromfile=str(old_file), tofile=str(new_file), lineterm="")
    )

    comments = _load_comments()
    # Index comments by (file, diff_line)
    overlay: Dict[int, List[Dict[str, Any]]] = {}
    for c in comments:
        if c.get("target") == new_file.name:
            overlay.setdefault(c["diff_line"], []).append(c)

    typer.echo("```diff")
    for idx, ln in enumerate(diff_lines):
        typer.echo(ln)
        if idx in overlay:
            for c in overlay[idx]:
                typer.echo(f"# COMMENT by {c['user']}: {c['comment']}")
    typer.echo("```")

    if overlay:
        typer.secho(f"\n{sum(len(v) for v in overlay.values())} comment(s) attached", fg=typer.colors.GREEN)


@app.command()
def comment(  # noqa: D401 – CLI entrypoint
    target_file: Path = typer.Argument(..., exists=True, help="Template file being reviewed"),
    diff_line: int = typer.Argument(..., help="Line number in diff output to comment on"),
    text: str = typer.Argument(..., help="Comment text"),
    user: str = typer.Option(getpass.getuser(), "--user", "-u", help="Reviewer identifier"),
):
    """Attach a *comment* to *diff_line* of *target_file* diff."""

    rec = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "target": target_file.name,
        "diff_line": diff_line,
        "comment": text,
    }
    _append_comment(rec)
    typer.secho("Comment recorded", fg=typer.colors.GREEN)


@app.command()
def approve(  # noqa: D401 – CLI entrypoint
    template: Path = typer.Argument(..., exists=True, help="Template to approve"),
    user: str = typer.Option(getpass.getuser(), "--user", "-u", help="Approver identity"),
):
    """Add *user* to approval list for *template*."""

    if _APPROVAL_FILE.exists():
        approvals: Dict[str, List[str]] = json.loads(_APPROVAL_FILE.read_text())
    else:
        approvals = {}

    lst = approvals.get(template.name, [])
    if user in lst:
        typer.secho("Already approved", fg=typer.colors.YELLOW)
        raise typer.Exit()
    lst.append(user)
    approvals[template.name] = lst
    _APPROVAL_FILE.write_text(json.dumps(approvals, indent=2), encoding="utf-8")
    typer.secho(f"✅ {user} approved {template.name} (total approvals: {len(lst)})", fg=typer.colors.GREEN)


if __name__ == "__main__":  # pragma: no cover
    app()