from __future__ import annotations

"""IDE & workflow standardisation utilities (Step 1.10).

This module turns the theoretical *Standardisation* requirement into practical
assets that can be added to a repository:

1. **IDE integration** – generates boilerplate configuration files for VS Code
   and a shell script snippet for Xcode build phases so that developers can run
   the *Repo-Prompt* workflow via a single shortcut.
2. **Development guidelines** – produces a markdown cheat-sheet that explains
   how to leverage AI-assisted coding tools consistently across the team.
3. **On-boarding material** – exports a quick-start guide for new hires which
   links to the generated IDE configs and emphasises best practices.

The implementation mirrors the style of other *Step 1.* helper modules:
* Read-only by default – files are **only** written when `--write` is passed.
* Typer-based CLI sub-app for easy invocation (`python -m src.standardization …`).
* Append-only audit trail via logging – no destructive actions.

Security considerations
~~~~~~~~~~~~~~~~~~~~~~~
* No remote calls; purely local file generation.
* Uses safe defaults (no secrets included). Any placeholders are clearly
  marked and must be filled in by the repo owner.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List
import json
import textwrap

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "FileSpec",
    "generate_vscode_files",
    "generate_xcode_script",
    "generate_dev_guidelines",
    "generate_onboarding_doc",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileSpec:
    """Represents a file to be created by the standardisation helpers."""

    path: Path  # target location (relative to repository root)
    content: str  # full file content

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "content": self.content,
        }


# ---------------------------------------------------------------------------
# VS Code integration helpers
# ---------------------------------------------------------------------------

_VSCODE_TASKS = {
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Repo-Prompt: Generate XML & review diff",
            "type": "shell",
            "command": "python -m src prompt .",
            "presentation": {
                "reveal": "always",
                "panel": "new"
            },
            "problemMatcher": [],
        }
    ],
}

_VSCODE_EXTENSIONS = {
    "recommendations": [
        "ms-python.python",
        "ms-vscode.makefile-tools",
        # REVIEW: Add Repo-Prompt extension ID once published
    ]
}

_VSCODE_SETTINGS = {
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "editor.formatOnSave": True,
    "files.trimTrailingWhitespace": True,
}


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def generate_vscode_files(repo_root: Path | str) -> List[FileSpec]:
    """Return *.vscode* configuration files for *repo_root* (in-memory)."""

    root = Path(repo_root).resolve()

    files = [
        FileSpec(root / ".vscode" / "tasks.json", _json_dumps(_VSCODE_TASKS)),
        FileSpec(root / ".vscode" / "extensions.json", _json_dumps(_VSCODE_EXTENSIONS)),
        FileSpec(root / ".vscode" / "settings.json", _json_dumps(_VSCODE_SETTINGS)),
    ]

    _log.debug("Prepared %d VS Code config files", len(files))
    return files


# ---------------------------------------------------------------------------
# Xcode integration helper
# ---------------------------------------------------------------------------

_XCODE_SCRIPT = textwrap.dedent(
    """\
    #!/bin/bash
    # Xcode build phase script – Repo-Prompt integration (Step 1.10)
    #
    # This script generates an XML prompt of the current source tree and writes
    # the LLM diff suggestions to *DerivedData/RepoPrompt/*. Review the output
    # after each build and apply patches as needed.
    #
    # **Usage**: Add as a "Run Script" phase in your target's Build Phases:
    #   Shell: /bin/bash
    #   Script: ${PROJECT_DIR}/Scripts/repo_prompt_build_phase.sh

    REPO_ROOT="${PROJECT_DIR}"
    OUTPUT_DIR="${BUILT_PRODUCTS_DIR}/../RepoPrompt"
    mkdir -p "${OUTPUT_DIR}"

    # SECURITY: Input sanitisation – avoid globbing edge cases
    set -euo pipefail

    pushd "${REPO_ROOT}" >/dev/null
    python -m src prompt . > "${OUTPUT_DIR}/prompt.xml"
    popd >/dev/null

    echo "Repo-Prompt XML written to ${OUTPUT_DIR}/prompt.xml"
"""
)


def generate_xcode_script(repo_root: Path | str) -> FileSpec:
    """Return the *FileSpec* for the Xcode run-script helper."""

    root = Path(repo_root).resolve()
    return FileSpec(root / "Scripts" / "repo_prompt_build_phase.sh", _XCODE_SCRIPT)


# ---------------------------------------------------------------------------
# Documentation helpers
# ---------------------------------------------------------------------------

_DEV_GUIDELINES = textwrap.dedent(
    """\
    # AI-assisted Coding – Development Guidelines (Step 1.10)

    This document standardises how the *Repo-Prompt* workflow is used within the
    team. Add it to your internal wiki or keep it version-controlled in the
    repository (\`docs/ai_coding_guidelines.md\`).

    ## Toolchain Integration
    * **VS Code** – recommended extensions and tasks are provided in the
      \`.vscode\` folder. Press `Cmd+Shift+B` (or `Ctrl+Shift+B` on Windows) and
      select *"Repo-Prompt: Generate XML & review diff"*.
    * **Xcode** – import the shell script at `Scripts/repo_prompt_build_phase.sh`
      as a *Run Script* build phase to trigger Repo-Prompt on each build.

    ## Best Practices
    1. Commit frequently and use feature branches to keep AI-generated diffs
       small and reviewable.
    2. Always run `pytest` after applying an LLM-generated patch.
    3. Tag unclear sections with `# REVIEW:` to invite peer input.

    ## Security & Ethics
    * Sanitise any proprietary code snippets before sending them to external
      LLMs.
    * Follow the *Security Scanner* output (`python -m src.security_scanner`).

    ## Continuous Improvement
    Log your feedback via `python -m src.feedback submit --message "…"` so the
    workflow can be refined iteratively.

    ## CLI Quick Reference

    ```bash
    # 📚 Display VS Code configurations (preview)
    python -m src standardize vscode

    # 💾 Write VS Code files to .vscode/
    python -m src standardize vscode --write

    # 🛠️ Create Xcode build phase script
    python -m src standardize xcode --write

    # 📖 Generate development guidelines
    python -m src standardize guidelines > docs/ai_coding_guidelines.md

    # 🧭 Export onboarding document
    python -m src standardize onboarding --output docs/onboarding.md
    ```

    ## Extension Benefits

    | Advantage | Benefit |
    |-----------|---------|
    | IDE compatibility | Seamless integration of AI workflows directly into developer toolchains |
    | Faster start for new team members | Ready-made instructions and setup help from day&nbsp;1 |
    | Team-wide consistency | Uniform standards and workflows, regardless of individual development environments |
    | Full audit readiness | All documents & processes are traceable and versioned |
"""
)


_ONBOARDING_DOC = textwrap.dedent(
    """\
    # New Hire On-boarding – AI Coding Toolkit

    Welcome to the team! 🎉 This quick-start guide will get you productive with
    our AI-assisted workflow in no time.

    1. **Clone the repository** and create a virtual environment:
       ```bash
       git clone <repo-url>
       cd <repo>
       python -m venv .venv && source .venv/bin/activate
       pip install -r requirements.txt
       ```

    2. **Verify your system**:
       ```bash
       python -m src setup --verbose
       ```

    3. **Import IDE settings**:
       * VS Code – open the workspace; the \`.vscode\` folder is pre-configured.
       * Xcode – drag `Scripts/repo_prompt_build_phase.sh` into Build Phases.

    4. **Run your first prompt**:
       ```bash
       python -m src prompt . --model gpt-4o
       ```

    5. **Next steps**:
       * Browse `docs/` for guidelines and iteration scaling tips.
       * Join the `#ai-coding-support` Slack channel for questions.
"""
)


def generate_dev_guidelines() -> str:
    """Return the development guidelines markdown string."""

    return _DEV_GUIDELINES


def generate_onboarding_doc() -> str:
    """Return the onboarding quick-start markdown string."""

    return _ONBOARDING_DOC


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Generate standardisation assets (Step 1.10)")

@app.command()
def vscode(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write files to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate VS Code configuration files."""

    setup_logging("DEBUG" if verbose else "INFO")

    specs = generate_vscode_files(repo_path)
    _output(specs, write, force)


@app.command()
def xcode(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Repository root"),
    write: bool = typer.Option(False, "--write", help="Write file to disk"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate the Xcode *Run Script* helper."""

    setup_logging("DEBUG" if verbose else "INFO")

    spec = generate_xcode_script(repo_path)
    _output([spec], write, force)


@app.command()
def guidelines(
    output: Path | None = typer.Option(None, "--output", "-o", help="Path to write markdown (stdout if omitted)"),
):
    """Print or write the AI-coding development guidelines."""

    md = generate_dev_guidelines()
    _write_text(md, output)


@app.command()
def onboarding(
    output: Path | None = typer.Option(None, "--output", "-o", help="Path to write onboarding doc (stdout if omitted)"),
):
    """Print or write the onboarding quick-start guide."""

    md = generate_onboarding_doc()
    _write_text(md, output)


# ---------------------------------------------------------------------------
# Internal I/O helpers – isolated for testability
# ---------------------------------------------------------------------------

def _write_text(text: str, dest: Path | None) -> None:  # noqa: D401 – imperative mood not required
    """Write *text* to *dest* or stdout if *dest* is *None*."""

    if dest:
        dest = dest.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        typer.echo(f"Written {dest}")
    else:
        typer.echo(text)


def _output(specs: List[FileSpec], write: bool, force: bool) -> None:  # FEEDBACK: unify param names across modules
    """Write or preview *specs* depending on *write* flag."""

    for spec in specs:
        if write:
            if spec.path.exists() and not force:
                _log.warning("Skipping existing %s (use --force to overwrite)", spec.path)
                continue
            spec.path.parent.mkdir(parents=True, exist_ok=True)
            spec.path.write_text(spec.content, encoding="utf-8")
            typer.echo(f"✅ {spec.path.relative_to(Path.cwd())} written")
        else:
            header = f"----- {spec.path.relative_to(Path.cwd())} -----"
            typer.echo(header)
            typer.echo(spec.content.rstrip())
            typer.echo("-" * len(header))