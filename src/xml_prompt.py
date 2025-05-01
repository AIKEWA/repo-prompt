from __future__ import annotations

"""XML prompt builder for Repo Prompt methodology.

This module converts a `CodeMap` representation of a repository into a compact,
self-describing XML document that can be embedded inside LLM prompts. The XML
structure is intentionally shallow and uses attributes rather than deep
nesting to save token count.

The expected consumer is an LLM that can parse XML blocks and reference file
paths when asking for further details or edits.
"""

from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from .codemaps import CodeMap, DirNode, FileNode
from .token_estimator import estimate_tokens, budget_remaining


XML_ENCODING = "utf-8"
_DEFAULT_MAX_TOKENS = 7000  # leaving headroom for user/system messages


# -----------------------
# Public API
# -----------------------

def build_repo_xml(
    code_map: CodeMap,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> str:
    """Serialize `code_map` into an XML string respecting `max_tokens` budget.

    If the repository is too large, only a subset of files will be included
    according to a naïve size-based heuristic (smallest first).
    """
    root_elem = Element("repo", path=str(code_map.root))

    _append_nodes(root_elem, code_map.root_node.children, max_tokens)

    xml_bytes = tostring(root_elem, encoding=XML_ENCODING)
    return xml_bytes.decode(XML_ENCODING)


# -----------------------
# Internal helpers
# -----------------------

def _append_nodes(parent_elem: Element, nodes: list[DirNode | FileNode], max_tokens: int):
    # Sort files by size ascending to maximize information under token cap
    for node in nodes:
        if isinstance(node, DirNode):
            dir_elem = SubElement(parent_elem, "dir", name=node.path.name)
            _append_nodes(dir_elem, node.children, max_tokens)
        else:
            file_elem = SubElement(
                parent_elem,
                "file",
                name=node.path.name,
                lang=node.language or "unknown",
                size=str(node.size),
            )
        # after each addition, check token usage
        xml_so_far = tostring(parent_elem, encoding=XML_ENCODING).decode(XML_ENCODING)
        if estimate_tokens(xml_so_far) > max_tokens:
            # Remove last added element and stop traversal
            parent_elem.remove(parent_elem[-1])  # type: ignore[arg-type]
            break 