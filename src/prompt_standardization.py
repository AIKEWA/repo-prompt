# -*- coding: utf-8 -*-
from __future__ import annotations

"""prompt_standardization.py – Step 8.7 Standardization 📑📝

This module *operationalises* **Step 8.7 – Standardization** by adding two key
capabilities to the *PromptOps* toolchain:

1. **YAML schemas for all prompt templates**
   Each :class:`src.prompt_ops_framework.PromptTemplate` can be rendered as an
   individual *JSON Schema* (marshalled to **YAML** for human readability). The
   schema acts as a *contract* and enables static validation or IDE tooling
   (e.g. VS Code YAML extension) to flag invalid prompt files as developers
   edit them.

2. **Semantic diff tracking** (commit ⇌ prompt mapping)
   A lightweight tracker analyses the *Git* diff between the current `HEAD` and
   `HEAD~1` for files inside the ``.prompts/`` directory.  It records
   *semantic* changes – added / removed / modified top-level fields – inside an
   append-only JSONL ledger (``.prompt_diffs.jsonl``).  Each record links back
   to the *commit SHA*, facilitating downstream dashboards or approval
   workflows.

The design deliberately mirrors conventions established by earlier helper
modules (e.g. :pymod:`src.standardization`, :pymod:`src.prompt_governance`):

* **Preview → Write** pattern – files are only written when ``--write`` (or
  ``--yes``) is provided; otherwise a dry-run shows the generated content.
* **Append-only ledgers** – both schema files *and* diff logs are strictly
  additive to avoid information loss.
* **No extra dependencies** – relies solely on *stdlib* and :pypi:`gitpython`.
"""

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import typer
from git import Repo  # type: ignore – provided via *requirements.txt*

from .logger import get_logger, setup_logging
from .prompt_ops_framework import PromptTemplate, list_templates, load_template

__all__ = [
    "FileSpec",
    "yaml_schema_for_template",
    "generate_schema_files",
    "track_prompt_diffs",
    "app",
]

###############################################################################
# 0. House-keeping                                                            #
###############################################################################

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

_DEFAULT_DIFF_LEDGER = Path(os.getenv("PROMPT_DIFF_LOG", ".prompt_diffs.jsonl"))

###############################################################################
# 1. Helper dataclass                                                         #
###############################################################################


@dataclass
class FileSpec:  # noqa: D101 – simple container
    path: Path
    content: str

    def write(self, *, overwrite: bool = False) -> None:  # pragma: no cover – trivial
        """Persist *content* to *path* according to *overwrite* flag."""

        if self.path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing {self.path}. Use --force.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.content, encoding="utf-8")


###############################################################################
# 2. YAML Schema generation                                                   #
###############################################################################


def _json_to_yaml(obj: Any, *, indent: int = 0) -> List[str]:
    """Return **YAML** lines for *obj* via hand-rolled emitter (no PyYAML)."""

    sp = "  " * indent
    if isinstance(obj, dict):
        out: List[str] = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out.append(f"{sp}{k}:")
                out.extend(_json_to_yaml(v, indent + 1))
            else:
                out.append(f"{sp}{k}: {json.dumps(v, ensure_ascii=False)}")
        return out
    if isinstance(obj, list):
        out: List[str] = []
        for itm in obj:
            if isinstance(itm, (dict, list)):
                out.append(f"{sp}-")
                out.extend(_json_to_yaml(itm, indent + 1))
            else:
                out.append(f"{sp}- {json.dumps(itm, ensure_ascii=False)}")
        return out
    # primitives
    return [f"{sp}{json.dumps(obj, ensure_ascii=False)}"]


def yaml_schema_for_template(tmpl: PromptTemplate) -> str:  # noqa: D401 – imperative OK
    """Return a *JSON Schema* rendered as YAML for *tmpl*.

    The schema focuses on *structure* rather than content semantics.  It is
    intentionally *lenient* – fields like ``description`` or ``content`` are
    only checked for *type*, not length or regexp constraints (keep schema
    short & maintainable).
    """

    schema: Dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"PromptTemplate {tmpl.name} v{tmpl.version}",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "version": {
                "type": "string",
                "pattern": r"^\\d+\\.\\d+\\.\\d+$",
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "roles": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "enum": ["system", "user", "assistant"],
                        },
                        "content": {"type": "string"},
                    },
                    "required": ["role", "content"],
                },
            },
            "created_at": {"type": "string", "format": "date-time"},
            "updated_at": {"type": "string", "format": "date-time"},
        },
        "required": [
            "name",
            "description",
            "version",
            "roles",
        ],
        "additionalProperties": False,
    }

    yaml_lines = _json_to_yaml(schema)
    return "\n".join(yaml_lines) + "\n"


def generate_schema_files(repo_root: Path | str = ".") -> List[FileSpec]:
    """Return *in-memory* :class:`FileSpec` objects for every prompt template."""

    root = Path(repo_root).resolve()
    specs: List[FileSpec] = []
    for tmpl in list_templates(repo_path=root):
        schema_text = yaml_schema_for_template(tmpl)
        prompt_dir = root / ".prompts"
        base_filename = Path(tmpl.filename(fmt="yaml")).stem  # strip extension
        schema_path = prompt_dir / f"{base_filename}.schema.yaml"
        specs.append(FileSpec(schema_path, schema_text))
        _log.debug("Prepared schema for %s", tmpl.name)
    return specs


###############################################################################
# 3. Semantic diff tracker                                                    #
###############################################################################


def _dict_from_yaml(text: str) -> Dict[str, Any]:  # very naïve, reuse logic from load_template
    """Parse *simple* YAML subset into a dict (like :func:`load_template`)."""

    # We re-use *load_template* for parsing because it already handles the same
    # subset without external deps.  However it expects a *Path*.  Therefore
    # we create a *temp file* if necessary.  Using *NamedTemporaryFile* keeps
    # it safe on all OSes.
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile("w+", delete=False, suffix=".yaml") as tmp:
        tmp.write(text)
        tmp.flush()
        path = Path(tmp.name)
    try:
        tmpl = load_template(path)
        return tmpl.as_dict()
    finally:
        try:
            path.unlink()
        except FileNotFoundError:  # pragma: no cover – unlikely
            pass


def _semantic_diff(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Return *key-level* diff between *old* and *new* prompt dicts."""

    added = {k: new[k] for k in new.keys() - old.keys()}
    removed = {k: old[k] for k in old.keys() - new.keys()}
    changed = {}
    for k in old.keys() & new.keys():
        if old[k] != new[k]:
            changed[k] = {
                "from": old[k],
                "to": new[k],
            }
    return {"added": added, "removed": removed, "changed": changed}


def track_prompt_diffs(repo_root: Path | str = ".", *, ledger_path: Path = _DEFAULT_DIFF_LEDGER) -> int:
    """Analyse *HEAD~1…HEAD* and append diff records.

    Returns the number of prompt files processed.
    """

    repo = Repo(Path(repo_root))
    if repo.head.is_detached:
        _log.warning("Detached HEAD – diff tracking skipped")
        return 0

    head = repo.head.commit
    if not head.parents:
        _log.info("Initial commit – nothing to diff")
        return 0
    parent = head.parents[0]

    processed = 0
    ledger_entries: List[Dict[str, Any]] = []

    for diff in head.diff(parent):
        path = diff.b_path or diff.a_path  # file path after / before change
        if not path or not path.startswith(".prompts/") or not path.endswith( (".yaml", ".json") ):
            continue

        # ------------------ retrieve contents -----------------------------
        new_path = Path(repo.working_tree_dir) / path if diff.b_path else None
        old_text: str | None = None
        new_text: str | None = None

        if diff.a_blob:  # exists in parent
            old_text = parent.repo.git.show(f"{parent.hexsha}:{path}")
        if diff.b_blob:  # exists in head ⇒ current fs copy
            # prefer working tree file (might include un-committed changes, but
            # commit can't have them – still OK)
            try:
                new_text = new_path.read_text(encoding="utf-8") if new_path else head.repo.git.show(f"{head.hexsha}:{path}")
            except FileNotFoundError:
                new_text = head.repo.git.show(f"{head.hexsha}:{path}")

        # ------------------ classify change kind --------------------------
        if old_text is None:  # new file
            summary: Dict[str, Any] = {"change": "created"}
            tmpl = load_template(new_path or Path(path))
        elif new_text is None:  # deleted
            summary = {"change": "deleted"}
            tmpl = load_template(Path(path))  # parse old state
        else:
            old_dict = _dict_from_yaml(old_text) if path.endswith(".yaml") else json.loads(old_text)
            new_dict = _dict_from_yaml(new_text) if path.endswith(".yaml") else json.loads(new_text)
            summary = _semantic_diff(old_dict, new_dict)
            tmpl = PromptTemplate(**new_dict)  # type: ignore[arg-type]

        entry = {
            "commit": head.hexsha,
            "path": path,
            "prompt_name": tmpl.name,
            "version": tmpl.version,
            "timestamp": datetime.utcnow().strftime(ISO_FMT),
            "summary": summary,
        }
        ledger_entries.append(entry)
        processed += 1
        _log.debug("Recorded diff for %s", path)

    # ------------------ persist ledger ------------------------------------
    if ledger_entries:
        ledger_path = ledger_path.expanduser().resolve()
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="utf-8") as fh:
            for rec in ledger_entries:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        _log.info("Appended %d prompt diff record(s) to %s", processed, ledger_path)
    else:
        _log.info("No prompt changes detected – ledger unchanged")

    return processed


###############################################################################
# 4. Typer CLI                                                                #
###############################################################################

app = typer.Typer(add_completion=False, help="Step 8.7 Standardization helpers")


@app.command()
def schema(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write .schema.yaml files to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing schema files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate YAML *schemas* for all prompts (preview or write)."""

    setup_logging("DEBUG" if verbose else "INFO")
    specs = generate_schema_files(repo_path)

    for spec in specs:
        if write:
            try:
                spec.write(overwrite=force)
                typer.echo(f"✅ {spec.path.relative_to(Path.cwd())} written")
            except FileExistsError as exc:
                _log.warning(str(exc))
        else:
            header = f"----- {spec.path.relative_to(Path.cwd())} -----"
            typer.echo(header)
            typer.echo(spec.content.rstrip())
            typer.echo("-" * len(header))


@app.command()
def track(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    ledger_path: Path = typer.Option(_DEFAULT_DIFF_LEDGER, "--ledger", help="Path of JSONL diff ledger"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Analyse ``HEAD~1…HEAD`` and append semantic diff records to *ledger*."""

    setup_logging("DEBUG" if verbose else "INFO")
    count = track_prompt_diffs(repo_path, ledger_path=ledger_path)
    typer.echo(f"📝 {count} prompt file(s) processed")


if __name__ == "__main__":  # pragma: no cover
    app()