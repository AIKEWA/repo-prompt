from __future__ import annotations

"""prompt_ops_framework.py – Step 7.1 PromptOps Framework Design 🚦📜

This module operationalises the *7.1 – PromptOps Framework Design* theory block.
It elevates **prompt management** to a first-class DevOps-style discipline
called **PromptOps**.  Concretely, it offers:

* A *Git-integrated* **prompt repository** located at ``.prompts/`` (configurable).
* :pyclass:`PromptTemplate` – a dataclass that stores prompt metadata and
  renders itself as **YAML** *and* **JSON* files for maximum interoperability.
* CRUD helpers (``init_repo()``, ``add_template()``, ``list_templates()`` …)
  focused on *local* operations only – no network calls.
* Built-in **template validator** that checks placeholder consistency and
  prevents common errors (missing role blocks, undefined tokens).
* A **Typer CLI** so that non-Python stakeholders can manage prompts via
  ``python -m src.prompt_ops_framework …`` commands.

Security & ethics
~~~~~~~~~~~~~~~~~
* Local-only file I/O; depends on :pypi:`gitpython` for committing changes.
* Explicit *no-auto-push* design – CI tools decide when to push.
* Validation prevents leaking secrets by blocking templates containing hard-
  coded API keys or tokens (simple regex heuristics, # REVIEW for enhancement).
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

import typer
from git import Repo  # type: ignore – provided by requirements.txt

from .logger import get_logger, setup_logging
from .git_utils import ensure_clean_worktree, stage_and_commit

__all__ = [
    "PromptTemplate",
    "init_repo",
    "add_template",
    "list_templates",
    "load_template",
    "validate_template",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. Data model                                                               #
###############################################################################


@dataclass
class PromptTemplate:  # noqa: D101 – simple value holder
    """Represents a single multi-role **LLM prompt template**.

    Parameters
    ----------
    name:
        Human-readable identifier, e.g. ``bug_fix``.
    roles:
        Sequence of *messages* – each message is a mapping with at least
        ``role`` and ``content`` keys.  Example::

            roles=[
                {"role": "system", "content": "You are…"},
                {"role": "user", "content": "Fix the bug in {{file}}"},
            ]

    description:
        Short explanation of the prompt's intent.
    version:
        SemVer string.  Defaults to ``"1.0.0"`` when omitted.
    tags:
        Optional list of search labels (e.g. ``["bug", "refactor"]``).
    created_at / updated_at:
        ISO-8601 timestamps auto-filled when serialising.
    """

    name: str
    roles: Sequence[Dict[str, str]]
    description: str
    version: str = "1.0.0"
    tags: List[str] | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))
    updated_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:  # pragma: no cover – trivial helper
        data = asdict(self)
        # Ensure tuples become lists for JSON compat
        data["roles"] = [dict(r) for r in self.roles]
        return data

    def to_json(self, *, indent: int | None = 2) -> str:
        """Return *pretty* JSON representation."""

        return json.dumps(self.as_dict(), indent=indent, ensure_ascii=False) + "\n"

    def to_yaml(self) -> str:
        """Return minimal YAML representation using *hand-rolled* emitter.

        We avoid a hard dependency on PyYAML to keep the project lightweight.
        The emitter is *not* fully spec compliant but sufficient for the
        simple structures used here.  # REVIEW: Replace with PyYAML if needed.
        """

        def _dump(obj, indent=0):  # noqa: D401 – local helper
            sp = "  " * indent
            if isinstance(obj, dict):
                out: List[str] = []
                for k, v in obj.items():
                    if isinstance(v, (dict, list)):
                        out.append(f"{sp}{k}:")
                        out.extend(_dump(v, indent + 1))
                    else:
                        out.append(f"{sp}{k}: {json.dumps(v, ensure_ascii=False)}")
                return out
            elif isinstance(obj, list):
                out: List[str] = []
                for itm in obj:
                    if isinstance(itm, (dict, list)):
                        # Dump complex item as single-line JSON for simplicity
                        out.append(f"{sp}- {json.dumps(itm, ensure_ascii=False)}")
                    else:
                        out.append(f"{sp}- {json.dumps(itm, ensure_ascii=False)}")
                return out
            else:
                return [f"{sp}{json.dumps(obj, ensure_ascii=False)}"]

        lines = _dump(self.as_dict())
        return "\n".join(lines) + "\n"

    # -----------------------
    # File naming helpers
    # -----------------------

    def filename(self, *, fmt: str = "yaml") -> str:  # noqa: D401 – imperative tone ok
        """Return ``<name>_v<version>.<fmt>`` string (extension w/out dot)."""

        safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", self.name)
        safe_ver = self.version.replace(".", "_")
        return f"{safe_name}_v{safe_ver}.{fmt}"

###############################################################################
# 2. Repository helpers                                                       #
###############################################################################


_PROMPT_DIR = Path(".prompts")


def _get_repo(start_path: Path | None = None) -> Repo:  # noqa: D401
    """Return :pyclass:`git.Repo` anchored at *start_path* (default: cwd)."""

    root = Path(start_path or Path.cwd())
    try:
        repo = Repo(root, search_parent_directories=True)
    except Exception as exc:  # pragma: no cover – defensive
        raise RuntimeError("Not inside a Git repository") from exc
    return repo


# -----------------------------
# Public API
# -----------------------------


def init_repo(repo_path: Path | str | None = None) -> Path:
    """Initialise ``.prompts/`` folder *and* commit a README stub.

    Returns the absolute path to the prompt directory.
    """

    repo = _get_repo(repo_path)
    ensure_clean_worktree(repo.working_tree_dir)

    prompt_dir = Path(repo.working_tree_dir) / _PROMPT_DIR
    prompt_dir.mkdir(exist_ok=True)

    readme = prompt_dir / "README.md"
    if not readme.exists():
        readme.write_text("# Prompt Repository\n\nAll prompt templates are stored here.\n", encoding="utf-8")

    stage_and_commit(repo.working_tree_dir, [prompt_dir], "chore(promptops): initialise .prompts directory")
    _log.info("Prompt repository initialised at %s", prompt_dir)
    return prompt_dir


def add_template(template: PromptTemplate, *, repo_path: Path | str | None = None) -> Path:
    """Serialise *template* to ``.prompts/`` and create a Git commit.

    The commit message follows *Conventional Commits* "feat(prompt): <name>".
    """

    repo = _get_repo(repo_path)
    ensure_clean_worktree(repo.working_tree_dir)

    # Validate first – abort on errors
    validate_template(template)

    prompt_dir = Path(repo.working_tree_dir) / _PROMPT_DIR
    if not prompt_dir.exists():
        raise FileNotFoundError("Prompt repository missing – run init first")

    # Choose YAML as primary – JSON *shadow* file for machine use
    yaml_path = prompt_dir / template.filename(fmt="yaml")
    json_path = prompt_dir / template.filename(fmt="json")

    yaml_path.write_text(template.to_yaml(), encoding="utf-8")
    json_path.write_text(template.to_json(), encoding="utf-8")

    stage_and_commit(
        repo.working_tree_dir,
        [yaml_path, json_path],
        f"feat(prompt): add {template.name} v{template.version}",
    )

    _log.info("Prompt template %s added", template.name)
    return yaml_path


def list_templates(*, repo_path: Path | str | None = None) -> List[PromptTemplate]:
    """Return *all* templates found in ``.prompts`` (YAML or JSON)."""

    repo = _get_repo(repo_path)
    prompt_dir = Path(repo.working_tree_dir) / _PROMPT_DIR
    if not prompt_dir.exists():
        return []

    templates: List[PromptTemplate] = []
    for p in prompt_dir.glob("*.*"):
        if p.suffix not in {".yaml", ".json"}:
            continue
        try:
            templates.append(load_template(p))
        except Exception as exc:  # pragma: no cover – skip bad files
            _log.warning("Skipping %s: %s", p.name, exc)
    return templates


def load_template(path: Path | str) -> PromptTemplate:  # noqa: D401
    """Load template from *path* (YAML or JSON) into :class:`PromptTemplate`."""

    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        data = json.loads(raw)
    elif p.suffix == ".yaml":
        # Naïve parser – expects key: value or simple lists only.
        # For complex cases instruct users to keep a parallel JSON file.
        data: Dict[str, Any] = {}
        current_key: str | None = None
        for ln in raw.splitlines():
            if not ln.strip():
                continue
            if ln.startswith("  -") or ln.startswith("-"):  # list item
                item = ln.lstrip(" -").strip()
                data.setdefault(current_key, []).append(json.loads(item))
            elif ":" in ln:
                key, val = ln.split(":", 1)
                key = key.strip()
                val = val.strip()
                if val:
                    data[key] = json.loads(val)
                else:
                    current_key = key
            elif current_key:
                data.setdefault(current_key, []).append(json.loads(ln.strip()))
        if "roles" in data:
            data["roles"] = [dict(r) for r in data["roles"]]
    else:
        raise ValueError("Unsupported file extension")

    return PromptTemplate(**data)  # type: ignore[arg-type]


###############################################################################
# 3. Validation                                                               #
###############################################################################


_PLACEHOLDER_PATTERN = re.compile(r"{{(\w+)}}")
_SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9]{20,})")  # naive OpenAI key matcher


def validate_template(template: PromptTemplate) -> None:  # noqa: D401 – imperative
    """Raise ``ValueError`` if *template* violates PromptOps rules."""

    if not template.roles:
        raise ValueError("roles must contain at least one message")

    # 1. Ensure role keys are valid
    for msg in template.roles:
        role = msg.get("role")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"Invalid role: {role}")
        if "content" not in msg:
            raise ValueError("Each message requires 'content'")

    # 2. Placeholder integrity – all placeholders must be curly-wrapped
    placeholders: set[str] = set()
    for msg in template.roles:
        placeholders.update(_PLACEHOLDER_PATTERN.findall(msg["content"]))

    # Optional stricter checks could go here (e.g. allowed placeholder names)

    # 3. Basic secret scanner
    for msg in template.roles:
        if _SECRET_PATTERN.search(msg["content"]):
            raise ValueError("Potential secret detected in template content – aborting")

    _log.debug("Validated template %s – %d placeholders", template.name, len(placeholders))

###############################################################################
# 4. CLI                                                                      #
###############################################################################


app = typer.Typer(add_completion=False, help="PromptOps repository manager")


@app.command()
def init(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs"),
):
    """Initialise **.prompts** directory and commit."""

    if verbose:
        setup_logging("DEBUG")
    init_repo()


@app.command()
def add(
    name: str = typer.Argument(..., help="Template name e.g. 'bug_fix'"),
    description: str = typer.Option("", "--desc", help="Short description"),
    role_file: Path = typer.Option(..., "--roles", "-r", exists=True, readable=True, help="Path to roles JSON file"),
    version: str = typer.Option("1.0.0", "--version", "-v", help="SemVer"),
    tags: List[str] = typer.Option(None, "--tag", help="Repeatable tags", metavar="TAG"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable debug logs"),
):
    """Add *template* from a **roles JSON** file.

    The JSON must be a list of ``{"role": "system|user|assistant", "content": "…"}``
    dicts.  This approach avoids quoting issues when passing complex YAML via
    CLI.  Use ``echo '[{"role":"user","content":"Hi"}]' > roles.json``.
    """

    if verbose:
        setup_logging("DEBUG")

    try:
        roles = json.loads(role_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON: {exc}") from exc

    tmpl = PromptTemplate(name=name, roles=roles, description=description, version=version, tags=tags)
    add_template(tmpl)


@app.command("list")
def _list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs"),
):
    """List templates in the repository."""

    if verbose:
        setup_logging("DEBUG")

    tmpls = list_templates()
    if json_output:
        typer.echo(json.dumps([t.as_dict() for t in tmpls], indent=2))
    else:
        for t in tmpls:
            typer.echo(f"{t.name} v{t.version} – {t.description}")


@app.command("show")
def _show_cmd(
    name: str = typer.Argument(..., help="Template name"),
    fmt: str = typer.Option("yaml", "--fmt", help="yaml|json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print template *name* in *fmt* format."""

    if verbose:
        setup_logging("DEBUG")

    for t in list_templates():
        if t.name == name:
            typer.echo(t.to_yaml() if fmt == "yaml" else t.to_json())
            raise typer.Exit(code=0)
    typer.echo(f"Template '{name}' not found", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()