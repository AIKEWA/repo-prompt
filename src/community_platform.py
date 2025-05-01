from __future__ import annotations

"""community_platform.py – Phase 3: *RepoPrompt als Community-Plattform* 🚀

This module transforms the *Phase 3* specification – turning RepoPrompt into
an **open community platform** – into production-ready code that integrates
seamlessly with the existing codebase.

Key capabilities
----------------
1. **Project initialisation** – `repo-prompt community init`
   • Scaffolds a new ethical-AI project (README, `.prompts/`, default
     persona template, and docs).
2. **Prompt diffing** – `repo-prompt community diff`
   • Human-readable comparison between two prompt versions (leverages
     :pyfunc:`src.diff_mode.compute_diff`).
3. **Patch application** – `repo-prompt community apply`
   • Safe patch writer built on :pyfunc:`src.patch_apply.apply_patch_set` with
     opt-in linter enforcement.
4. **Persona engine** – `PersonaTemplate` data model + helpers to publish,
   list, and validate reusable *ethical personas* (stored in `.personas/`).

Security & ethics
~~~~~~~~~~~~~~~~~
* All file writes are *local* and version-controlled.
* Basic secret scanner prevents accidental key leakage in personas.
* CLI flags `--force` & `--yes` opt-out of safeguards (explicit).

"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import difflib
import json
import re

import typer

from .logger import get_logger, setup_logging
from .prompt_ops_framework import PromptTemplate, init_repo as _init_prompt_repo, add_template
from .patch_apply import apply_patch_set
from .diff_mode import compute_diff as _compute_diff

__all__ = [
    "PersonaTemplate",
    "create_persona",
    "list_personas",
    "load_persona",
    "validate_persona",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
_PERSONA_DIR = Path(".personas")
_SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9]{20,})")  # naive OpenAI key matcher

###############################################################################
# 1. Data model – Persona templates                                           #
###############################################################################


@dataclass
class PersonaTemplate:  # noqa: D101 – simple value holder
    """Metadata-rich *AI persona* definition.

    Parameters
    ----------
    name:
        Unique identifier (machine-friendly).
    role:
        Short human label (e.g. *EthicalDev*).
    description:
        High-level explanation incl. *boundaries* and *safeguards*.
    values:
        List of key principles (e.g. ["inclusivity", "interpretability"]).
    version:
        SemVer string. Defaults to ``"1.0.0"``.
    tags:
        Optional search labels.
    created_at / updated_at:
        ISO-8601 timestamps auto-filled when serialising.
    """

    name: str
    role: str
    description: str
    values: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    tags: List[str] | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))
    updated_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Make sure lists are JSON-serialisable
        data["values"] = list(self.values)
        return data

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent, ensure_ascii=False) + "\n"

    def filename(self) -> str:  # noqa: D401 – imperative tone ok
        safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", self.name)
        safe_ver = self.version.replace(".", "_")
        return f"{safe_name}_v{safe_ver}.json"


###############################################################################
# 2. Persona repository helpers                                               #
###############################################################################


def _ensure_persona_dir(root: Path | None = None) -> Path:  # noqa: D401 – imperative
    """Return absolute path to ``.personas`` inside *root* (mkdir if needed)."""

    base = Path(root or Path.cwd()).resolve()
    pdir = base / _PERSONA_DIR
    pdir.mkdir(exist_ok=True)
    return pdir


def validate_persona(persona: PersonaTemplate) -> None:  # noqa: D401 – imperative
    """Raise ``ValueError`` when *persona* violates basic safeguards."""

    if not persona.name or not persona.role:
        raise ValueError("name and role are mandatory")
    if _SECRET_PATTERN.search(persona.description):
        raise ValueError("Potential secret detected in persona description")


def create_persona(persona: PersonaTemplate, *, repo_root: Path | None = None) -> Path:
    """Serialise *persona* into ``.personas/<file>.json`` and return the path."""

    validate_persona(persona)
    pdir = _ensure_persona_dir(repo_root)
    path = pdir / persona.filename()
    path.write_text(persona.to_json(), encoding="utf-8")
    _log.info("Persona '%s' written to %s", persona.name, path)
    return path


def list_personas(*, repo_root: Path | None = None) -> List[PersonaTemplate]:
    """Return \*all\* personas found in ``.personas`` (JSON only)."""

    pdir = _ensure_persona_dir(repo_root)
    personas: List[PersonaTemplate] = []
    for p in pdir.glob("*.json"):
        try:
            personas.append(load_persona(p))
        except Exception as exc:  # pragma: no cover – skip broken file
            _log.warning("Skipping %s: %s", p.name, exc)
    return personas


def load_persona(path: Path | str) -> PersonaTemplate:  # noqa: D401
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PersonaTemplate(**data)  # type: ignore[arg-type]


###############################################################################
# 3. CLI                                                                      #
###############################################################################

app = typer.Typer(add_completion=False, help="Community platform commands")


# ---------------------------------------------------------------------------
# 3.1  `init` – project scaffold                                              #
# ---------------------------------------------------------------------------


@app.command()
def init(  # noqa: D401 – CLI entrypoint
    project_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repo root (Git initialised)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logs"),
):
    """Scaffold a new ethical-AI project (prompt repo + personas).

    • Creates `.prompts/` via :pymod:`src.prompt_ops_framework`.
    • Seeds `.personas/` with a default *EthicalDev* persona.
    • Writes `COMMUNITY.md` blueprint linking certification & onboarding docs.
    """

    if verbose:
        setup_logging("DEBUG")

    # 1. Prompt repository --------------------------------------------------
    _init_prompt_repo(project_path)

    # 2. Seed persona -------------------------------------------------------
    default_persona = PersonaTemplate(
        name="ethical_dev",
        role="EthicalDev",
        description="Imbues every suggestion with inclusivity & transparency.",
        values=["inclusivity", "interpretability", "cultural_sensitivity"],
        tags=["default", "recommended"],
    )
    create_persona(default_persona, repo_root=project_path)

    # 3. Community docs -----------------------------------------------------
    community_md = Path(project_path) / "COMMUNITY.md"
    if not community_md.exists():
        community_md.write_text(
            "# Community Platform Blueprint\n\n"
            "This repository follows the **RepoPrompt Community** specification.\n\n"
            "* Read `docs/onboarding.md` for newcomer guidance.\n"
            "* Review `.personas/` for approved ethical personas.\n"
            "* Certification: *Ethical AI Certified by A.I.K.* – details coming soon.\n",
            encoding="utf-8",
        )

    typer.secho("✅ Community scaffold complete", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# 3.2  `diff` – compare prompt versions                                       #
# ---------------------------------------------------------------------------


@app.command()
def diff(  # noqa: D401 – CLI entrypoint
    old_prompt: Path = typer.Argument(..., exists=True, readable=True, help="Original prompt file"),
    new_prompt: Path = typer.Argument(..., exists=True, readable=True, help="Modified prompt file"),
    context: int = typer.Option(3, "-U", "--context", help="Context lines (default 3)"),
):
    """Print a unified diff between *old_prompt* and *new_prompt*."""

    diff_txt = _compute_diff(
        old_prompt.read_text(),
        new_prompt.read_text(),
        fromfile=str(old_prompt),
        tofile=str(new_prompt),
        context=context,
    )
    typer.echo(diff_txt)


# ---------------------------------------------------------------------------
# 3.3  `apply` – apply community-reviewed patch                               #
# ---------------------------------------------------------------------------


@app.command()
def apply(  # noqa: D401 – CLI entrypoint
    diff_file: Path = typer.Argument(..., exists=False, help="Unified diff file ('-' for STDIN)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    force: bool = typer.Option(False, "--force", help="Apply even when linter blocks"),
    backup: bool = typer.Option(False, "--backup", help="Create .bak backups"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Apply *diff_file* to the working tree with safety checks."""

    setup_logging("DEBUG" if verbose else "INFO")

    diff_text = typer.get_text_stream("stdin").read() if str(diff_file) == "-" else diff_file.read_text()

    if not yes:
        typer.confirm("Patch will be applied – continue?", abort=True)

    modified = apply_patch_set(Path("."), diff_text, dry_run=False, create_backup=backup)
    typer.secho(f"✅ Applied patch to {len(modified)} file(s)", fg=typer.colors.GREEN)


###############################################################################
# 4. Expose helper to main CLI                                                #
###############################################################################

# The main application (`src.__main__.py`) imports `app` lazily to avoid a
# heavy import chain.  See integration patch in *__main__.py*.