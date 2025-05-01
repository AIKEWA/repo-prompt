"""Test suite for `dependency_visualizer`.

These tests focus on *unit-level* assurances that the graph builder works for a
simple synthetic package tree.  More detailed integration tests can be added
later once performance benchmarks are established.
"""

from pathlib import Path
import types
import textwrap

import networkx as nx

from src.dependency_visualizer import build_dependency_graph


def _create_temp_module(tmp_path: Path, name: str, body: str = "pass") -> Path:
    file_path = tmp_path / f"{name}.py"
    file_path.write_text(textwrap.dedent(body), encoding="utf-8")
    return file_path


def test_single_module(tmp_path: Path):
    # Create a simple package with one file and no imports
    _create_temp_module(tmp_path, "foo")

    g = build_dependency_graph(tmp_path)

    assert isinstance(g, nx.DiGraph)
    assert len(g.nodes) == 1
    assert "foo" in g.nodes
    assert g.out_degree("foo") == 0