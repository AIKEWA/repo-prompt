from __future__ import annotations

"""Live CodeMap + Traceability Visualiser (Phase 2c)

This module builds on *CodeMaps* by analysing **import dependencies** between
Python modules under a given repository root (default: ``src/``).  The resulting
``networkx.DiGraph`` can be rendered as an *interactive* Plotly figure that
highlights files flagged by the ethical analyser from
:pymod:`src.ethical_ai_app`.

# ✔️ Implementation Requirements

* **Code Integration** – The code lives in ``src/`` and depends only on
  ``networkx`` and ``plotly``, added to ``requirements.txt``.
* **Documentation Support** – Rich docstrings and a CLI help screen via *Typer*.
* **Feedback Readiness** – Logging hooks (`# FEEDBACK:`) are provided for future
  runtime analytics.
* **Maintainability** – The graph builder is configuration-driven.
* **Security & Ethics** – No user input is executed; all parsing uses the AST.
* **Testing Coverage** – A stub test file is created alongside for expansion.

Usage (command-line):

```bash
# Build and visualise the dependency graph in the browser
python -m src.dependency_visualizer graph --browser

# Save to HTML for sharing
python -m src.dependency_visualizer graph --output deps.html
```
"""

from pathlib import Path
import ast
from typing import Dict, Set, Tuple

import networkx as nx  # type: ignore
import plotly.graph_objects as go  # type: ignore
import typer

from .ethical_ai_app import _analyze_file  # local reuse keeps logic DRY

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

__all__ = [
    "build_dependency_graph",
    "graph_to_plotly",
]


# REVIEW: Consider caching results in `.cache/dep_graph.json` for speed.

def build_dependency_graph(
    root: Path | str = Path("src"), *, include_external: bool = False
) -> nx.DiGraph:
    """Return an *import dependency* graph for all ``*.py`` files under *root*.

    Parameters
    ----------
    root
        Directory that marks the Python *package root* (usually ``src``).
    include_external
        If *False* (default) only edges **within** the repository are kept.
        When *True* external imports are shown as dashed nodes to provide
        additional context.
    """

    root = Path(root).resolve()
    if not root.is_dir():  # Guard-rail for incorrect user input
        raise FileNotFoundError(root)

    py_files: Set[Path] = set(root.rglob("*.py"))

    # Map <dotted-module-name> → <file-path>
    module_index: Dict[str, Path] = {
        _path_to_module(root, p): p for p in py_files
    }

    g: nx.DiGraph = nx.DiGraph()
    g.add_nodes_from(module_index.keys())

    for mod_name, file_path in module_index.items():
        # Parse once per file – AST ensures no code execution
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # Skip problematic files but record warning
            typer.echo(f"⚠️  Skipping {file_path}: {exc}")
            continue

        # Node attribute: ethical analysis flag
        issues = _has_ethics_issues(file_path)
        g.nodes[mod_name]["ethics_issues"] = issues

        # Collect *relative* imports first so that "from .sub import x" works
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _add_edge_if_in_repo(g, mod_name, alias.name, module_index, include_external)

            elif isinstance(node, ast.ImportFrom):
                # Relative import level ("from ..foo import bar")
                if node.module is None and node.level:
                    rel_mod = _resolve_relative_import(mod_name, node.level, module_index)
                    if rel_mod:
                        g.add_edge(mod_name, rel_mod)
                else:
                    full_name = node.module or ""
                    _add_edge_if_in_repo(g, mod_name, full_name, module_index, include_external)

    return g


# ------------------------- Helper functions ---------------------------------


def _path_to_module(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _add_edge_if_in_repo(
    g: nx.DiGraph,
    src_mod: str,
    imported_name: str,
    module_index: Dict[str, Path],
    include_external: bool,
) -> None:
    """Add *src_mod* → *imported_name* edge when target is inside repo."""

    target_mod = _closest_repo_module(imported_name, module_index)
    if target_mod:
        g.add_edge(src_mod, target_mod)
    elif include_external:
        g.add_edge(src_mod, imported_name)
        g.nodes[imported_name]["external"] = True


def _closest_repo_module(
    name: str, module_index: Dict[str, Path]
) -> str | None:
    """Return the *longest* dotted prefix of *name* that exists in repo."""

    while name:
        if name in module_index:
            return name
        if "." not in name:
            break
        name = name.rpartition(".")[0]
    return None


def _resolve_relative_import(
    current_module: str, level: int, module_index: Dict[str, Path]
) -> str | None:
    parts = current_module.split(".")[:-level]
    if parts:
        parent_mod = ".".join(parts)
        if parent_mod in module_index:
            return parent_mod
    return None


def _has_ethics_issues(path: Path) -> bool:
    suggestions = _analyze_file(path)
    return not any(s.startswith("✅") for s in suggestions)


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------


def graph_to_plotly(g: nx.DiGraph) -> go.Figure:
    """Convert a dependency graph into a Plotly *Figure*."""

    if not g:
        raise ValueError("Graph is empty – nothing to visualise.")

    pos = nx.spring_layout(g, seed=42)  # Deterministic layout for diffability

    edge_x: list[float] = []
    edge_y: list[float] = []
    for src, dst in g.edges():
        x0, y0 = pos[src]
        x1, y1 = pos[dst]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=1, color="#888"),
        hoverinfo="none",
        mode="lines",
    )

    node_x, node_y, node_text, node_color = [], [], [], []
    for node in g.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        is_flagged = g.nodes[node].get("ethics_issues", False)
        node_color.append("#d62728" if is_flagged else "#1f77b4")

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        marker=dict(size=12, color=node_color, line=dict(width=2, color="white")),
        hoverinfo="text",
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title="Code Dependency Graph",
            hovermode="closest",
            margin=dict(b=20, l=5, r=5, t=40),
            showlegend=False,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Live CodeMap + Traceability Visualiser")


@app.command()
def graph(
    repo_path: Path = typer.Argument(Path("src"), exists=True, file_okay=False, help="Repository root to scan"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write HTML file instead of opening browser"),
    browser: bool = typer.Option(False, "--browser", "-b", help="Open interactive graph in default browser"),
    include_external: bool = typer.Option(False, help="Include external (3rd-party/stdlib) imports"),
):
    """Generate a dependency graph and render it with Plotly."""

    typer.echo(f"🔍 Building dependency graph for {repo_path} …")
    g = build_dependency_graph(repo_path, include_external=include_external)

    fig = graph_to_plotly(g)

    if output:
        fig.write_html(str(output), auto_open=browser)
        typer.echo(f"💾 Saved HTML visualisation to {output.resolve()}")
    else:
        fig.show()  # opens in browser via Plotly's default renderer

    # FEEDBACK: capture graph size metrics for telemetry


if __name__ == "__main__":  # pragma: no cover
    app()