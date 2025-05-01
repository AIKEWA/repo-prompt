"""Minimal, self-contained Typer CLI for the *Ethical AI App*.

This version focuses on **command registration** and a predictable runtime
behaviour so that `python -m src.ethical_ai_app --help` lists all sub-commands
and each handler prints a confirmation message.

The richer feature set from the previous implementation can be re-integrated
incrementally after verifying that this skeleton works in your environment.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import typer

app = typer.Typer(help="Ethical AI application – Phase 2 CLI")

###############################################################################
# Commands
###############################################################################


@app.command()
def prioritize(top: int = 3):
    """Prioritise projects based on ethics, feasibility and impact."""

    typer.echo(f"[{_dt.datetime.now()}] Prioritising **top {top}** ethical projects…")


@app.command()
def scaffold(name: str, open: bool = typer.Option(False, "--open", help="Open in VS Code")):
    """Scaffold a new ethical-AI prototype folder."""

    typer.echo(f"Scaffolding project: **{name}** | Open VS Code: {open}")


@app.command()
def visualize(path: str = typer.Argument(".", help="Repository root to visualise")):
    """Visualise the CodeMap for *path* (stub)."""

    typer.echo(f"Visualising CodeMap at: {Path(path).resolve()}")


@app.command("dashboard")
def launch_dashboard():
    """Launch the live KPI dashboard (stub)."""

    typer.echo("Launching live KPI dashboard…")


@app.command("export-audit")
def export_audit(verbose: bool = typer.Option(False, "--verbose", "-v", help="Print file contents after writing")):
    """Export a timestamped KPI audit log to `.audit/`."""

    timestamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(".audit")
    out_dir.mkdir(exist_ok=True)

    path = out_dir / f"audit_{timestamp}.md"
    content = (
        f"# 📊 KPI Audit Log\n\nGenerated: {timestamp}\n\n"
        "- KPI_1: TODO\n"
        "- KPI_2: TODO\n"
    )
    path.write_text(content, encoding="utf-8")

    typer.echo(f"📝 Audit exported to {path.resolve()}")

    if verbose:
        typer.echo("\n" + content)


###############################################################################
# 🚀 Phase 2b – User-Guided Refactoring Interface                            #
###############################################################################


_BIAS_TERMS = {
    "blacklist": "blocklist",
    "whitelist": "allowlist",
    "master": "primary",
    "slave": "secondary",
}


def _analyze_file(file_path: Path) -> list[str]:
    """Return *human-readable* suggestions for ethical refactors."""

    suggestions: list[str] = []

    try:
        code = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"❌ Could not read file: {exc}"]

    # --- Bias language ---------------------------------------------------
    for term, replacement in _BIAS_TERMS.items():
        if term in code:
            suggestions.append(
                f"🧐 Consider replacing biased term **'{term}'** with **'{replacement}'**"
            )

    # --- Insecure APIs ---------------------------------------------------
    for bad_api in ("eval(", "exec(", "pickle.load("):
        if bad_api in code:
            suggestions.append(
                f"🔐 Avoid dynamic execution via `{bad_api.strip('(')}` – investigate safer alternatives."
            )

    # --- Complexity / sustainability (function length) ------------------
    import ast, inspect

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        suggestions.append(f"❌ SyntaxError while parsing: {exc}")
        return suggestions

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # end-lineno available on Python 3.8+
            if hasattr(node, "end_lineno") and node.end_lineno and node.body:
                length = node.end_lineno - node.lineno
                if length > 50:
                    suggestions.append(
                        f"♻️ Function `{node.name}` is {length} lines – consider refactoring for readability & energy savings."
                    )

    # --- Hard-coded secrets heuristic ------------------------------------
    import re

    secret_rx = re.compile(r"['\"][A-Za-z0-9_]{20,}['\"]")  # very naive
    if secret_rx.search(code):
        suggestions.append("🔑 Potential hard-coded secret detected – move to env vars or secret manager.")

    if not suggestions:
        suggestions.append("✅ No obvious ethical or sustainability issues found.")

    return suggestions


@app.command()
def refactor(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="Python source file to analyse"),
    suggest: bool = typer.Option(True, "--suggest/--no-suggest", help="Print suggestions (default: Yes)"),
):
    """Guide the user through ethical refactor suggestions for *file*."""

    typer.echo(f"🔍 Analysing {file} …")

    suggestions = _analyze_file(file)

    if suggest:
        typer.echo("\n## 💡 Suggestions\n")
        for s in suggestions:
            typer.echo(f"- {s}")

    # Future: implement interactive patch application (# include_ci_cd)

###############################################################################
# Entry-point                                                                #
###############################################################################

if __name__ == "__main__":  # pragma: no cover – manual invocation helper
    app()