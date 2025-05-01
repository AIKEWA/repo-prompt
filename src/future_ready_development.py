from __future__ import annotations

"""future_ready_development.py – Step 7.5 Future-Ready Development 🚀🔮

This module implements **Step 7.5 – Future-Ready Development**.
It prepares the infrastructure for:

1. **Prompt auto-optimisation** driven by feedback loops.
2. **Cross-team prompt sharing** via a local *prompt registry*.
3. **No-code interfaces** for prompt design (markdown skeletons).
4. A *Curriculum add-on* – generates a 1-hour onboarding module
   *"Prompt Engineering 101: From Template to Orchestration"*.

Design principles
=================
* Pure Python + :pypi:`typer` only – no outbound network calls.
* Append-only JSONL stores mirror earlier helpers to maximise consistency.
* Heavy ML/optimisation logic is **stubbed** – exposes clear extension
  points (`# TODO:` tags) so the community can contribute concrete
  algorithms later without touching the public API.
"""

import json
import os
import re
import textwrap
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

import typer

from .logger import get_logger, setup_logging
from .prompt_ops_framework import PromptTemplate, validate_template  # re-use existing structures
from .feedback_mechanism import FeedbackStore  # for auto-optimisation heuristics

__all__ = [
    "OptimisationReport",
    "PromptRegistry",
    "auto_optimize_prompt",
    "generate_markdown_skeleton",
    "generate_training_module",
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. Data structures                                                          #
###############################################################################


@dataclass(slots=True)
class OptimisationReport:  # noqa: D101 – simple value object
    """Represents the outcome of **prompt auto-optimisation**.

    Parameters
    ----------
    prompt_name:
        Name of the *source* prompt that was optimised.
    old_version:
        Semantic version of the original prompt.
    new_version:
        Semantic version of the generated prompt.
    improvements:
        Human-readable bullet list summarising changes.
    created_at:
        ISO-8601 timestamp (auto-filled).
    """

    prompt_name: str
    old_version: str
    new_version: str
    improvements: Sequence[str]
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    # ---------------------
    # Serialisation helpers
    # ---------------------

    def to_json(self) -> str:  # noqa: D401 – imperative tone ok
        return json.dumps(asdict(self), separators=(",", ":"))

###############################################################################
# 2. Prompt registry helpers                                                  #
###############################################################################


_DEFAULT_REGISTRY = Path(os.getenv("PROMPT_REGISTRY_FILE", ".prompt_registry.jsonl"))


class PromptRegistry:  # noqa: D101 – lightweight JSONL store
    """Append-only registry that stores **prompt templates** for sharing."""

    def __init__(self, path: str | Path = _DEFAULT_REGISTRY) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Prompt registry at %s", self.path)

    # -------------------
    # Public API
    # -------------------

    def append(self, tmpl: PromptTemplate) -> None:  # noqa: D401 – imperative
        """Serialise *tmpl* as JSON and append to the registry."""

        line = tmpl.to_json() if hasattr(tmpl, "to_json") else json.dumps(tmpl.as_dict(), ensure_ascii=False)
        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _log.info("Registered prompt %s v%s", tmpl.name, tmpl.version)

    def list(self) -> List[PromptTemplate]:  # noqa: D401
        """Return **all** prompts stored in the registry."""

        if not self.path.exists():
            return []
        templates: List[PromptTemplate] = []
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            data = json.loads(ln)
            templates.append(PromptTemplate(**data))
        return templates

    def find(self, name: str, version: str | None = None) -> PromptTemplate | None:  # noqa: D401
        """Return prompt *name* (optionally @version) or *None* if absent."""

        for tmpl in self.list():
            if tmpl.name == name and (version is None or tmpl.version == version):
                return tmpl
        return None

###############################################################################
# 3. Auto-optimisation placeholder                                            #
###############################################################################


_FEEDBACK_WEIGHTS: Dict[str, float] = {
    "DeveloperSurvey": 1.0,
    "AlignmentRating": 1.5,  # more weight to explicit alignment ratings
}


def _bump_version(ver: str) -> str:  # noqa: D401 – helper
    """Return *ver* with incremented patch (1.2.3 ➜ 1.2.4)."""

    parts = re.split(r"[._]", ver)
    if not parts or not parts[-1].isdigit():
        return ver + ".1"
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def auto_optimize_prompt(
    template: PromptTemplate,
    *,
    feedback_path: Path | str = ".feedback.jsonl",
) -> tuple[PromptTemplate, OptimisationReport]:  # noqa: D401 – imperative ok
    """Return **optimised** clone of *template* based on minimal heuristics.

    The current implementation is a **stub**:
    it increments the patch version and prefixes the description with
    "Auto-optimised".  A real implementation could analyse feedback events,
    success metrics, etc. to tune temperature, system messages, or few-shot
    examples.
    """

    _log.debug("Auto-optimising prompt %s v%s", template.name, template.version)

    # TODO: Replace heuristic with actual optimisation logic
    new_roles = list(template.roles)
    improvements: List[str] = []

    # Simple heuristic: add a system note when satisfaction < threshold
    store = FeedbackStore(feedback_path)
    agg = store.aggregate()
    surveys_info = agg.get("developer_surveys", {})
    satisfaction = surveys_info.get("average_satisfaction")

    if satisfaction is not None and satisfaction < 7:
        new_roles.insert(0, {"role": "system", "content": "Ensure concise answers (auto-optimised)."})
        improvements.append("Added concise-answer system instruction based on low satisfaction")
    else:
        improvements.append("No feedback-based changes (heuristic)")

    new_version = _bump_version(template.version)
    optimised = PromptTemplate(
        name=template.name,
        roles=new_roles,
        description=f"Auto-optimised version of {template.description}",
        version=new_version,
        tags=template.tags or [],
    )

    validate_template(optimised)  # ensure still valid

    report = OptimisationReport(
        prompt_name=template.name,
        old_version=template.version,
        new_version=new_version,
        improvements=improvements,
    )

    _log.info("Optimised prompt %s: %s", template.name, ", ".join(improvements))
    return optimised, report

###############################################################################
# 4. No-code markdown skeleton                                                #
###############################################################################


def generate_markdown_skeleton(name: str) -> str:  # noqa: D401
    """Return a **markdown skeleton** that non-coder stakeholders can fill in."""

    return textwrap.dedent(
        f"""
        # 📝 Prompt Design: {name}

        > Fill in each section below – *no coding required!*  Replace placeholder
        > text (〈…〉) with concrete instructions.

        ## 1. 🎯 Intent
        *What should the assistant accomplish?*
        〈Describe the primary goal…〉

        ## 2. 📥 Inputs
        | Placeholder | Description |
        |-------------|-------------|
        | `{{input}}` | 〈Describe variable data…〉 |

        ## 3. 🧩 Roles
        ````yaml
        - role: system
          content: "You are a helpful assistant."
        - role: user
          content: "〈User request using placeholders〉"
        ````

        ## 4. ✅ Success criteria
        *How do we evaluate a good answer?*
        〈Bullet list of acceptance criteria…〉

        ## 5. 🏷️ Tags
        〈e.g. bug-fix, refactor, security〉
        """
    ).lstrip()

###############################################################################
# 5. Training module generator                                                #
###############################################################################


_TRAINING_MD = textwrap.dedent(
    """\
    # 🎓 Prompt Engineering 101 – From Template to Orchestration

    > **Duration:** 60 min &nbsp;|&nbsp; **Audience:** New engineering hires

    Welcome! This crash-course introduces the **PromptOps** workflow adopted by
    our team.  By the end, you will be able to **design, optimise, share and
    orchestrate** LLM prompts confidently.

    ---

    ## Agenda (60 min)

    | #  | Topic | Format | Time |
    |:-:|-------|--------|------|
    | 1 | Prompt lifecycle & versioning             | Slide deck | 10 min |
    | 2 | Prompt design fundamentals (roles, placeholders, tags) | Live demo | 15 min |
    | 3 | Auto-optimisation via feedback loops       | Hands-on   | 10 min |
    | 4 | Cross-team registry & governance           | Walk-through | 10 min |
    | 5 | No-code editor (markdown skeleton)         | Exercise   | 10 min |
    | 6 | Q&A                                        | ––         | 5 min  |

    ---

    ## 1️⃣ Prompt lifecycle & versioning (10 min)
    * **Create** – `python -m src.prompt_ops_framework add …`
    * **Review & approve** – `python -m src.prompt_governance approve …`
    * **Optimise** – `python -m src.future_ready_development optimise …`
    * **Share** – `python -m src.future_ready_development register …`

    ## 2️⃣ Prompt design fundamentals (15 min)
    Explore role patterns, placeholder naming, and success criteria.

    ## 3️⃣ Auto-optimisation (10 min)
    Analyse developer feedback → iterate on system prompts & examples.

    ## 4️⃣ Registry & governance (10 min)
    Learn how cross-team sharing works and why approvals matter.

    ## 5️⃣ No-code editor (10 min)
    Use the markdown skeleton to craft prompts without touching Python.

    ## Resources
    * Repo wiki: **PromptOps Manual**
    * `src/prompt_ops_framework.py` – Prompt CRUD helpers
    * `src/prompt_governance.py` – Governance layer
    * `src/future_ready_development.py` – Auto-optimisation & registry
    """
)


def generate_training_module() -> str:  # noqa: D401
    """Return the **Prompt Engineering 101** onboarding markdown."""

    return _TRAINING_MD + "\n"

###############################################################################
# 6. Typer CLI                                                                #
###############################################################################


app = typer.Typer(add_completion=False, help="Future-Ready utilities (Step 7.5)")


@app.command()
def optimise(  # noqa: D401 – CLI wrapper
    name: str = typer.Argument(..., help="Prompt name to optimise"),
    version: str = typer.Option(None, "--version", "-v", help="Specific version to optimise (latest if omitted)"),
    feedback_store: Path = typer.Option(Path(".feedback.jsonl"), "--feedback", help="Feedback JSONL path"),
    registry_path: Path = typer.Option(_DEFAULT_REGISTRY, "--registry", help="Prompt registry JSONL"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable debug logs"),
):
    """Auto-optimise *name* and register new version."""

    setup_logging("DEBUG" if verbose else "INFO")

    reg = PromptRegistry(registry_path)
    tmpl = reg.find(name, version)
    if tmpl is None:
        typer.echo(f"❌ Prompt {name}@{version or 'latest'} not found in registry")
        raise typer.Exit(1)

    new_tmpl, report = auto_optimize_prompt(tmpl, feedback_path=feedback_store)
    reg.append(new_tmpl)

    typer.echo("✔ Optimised → " + new_tmpl.filename())
    typer.echo("Improvement summary:")
    for imp in report.improvements:
        typer.echo(f" • {imp}")


@app.command()
def register(  # noqa: D401
    template_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to prompt YAML or JSON"),
    registry_path: Path = typer.Option(_DEFAULT_REGISTRY, "--registry", help="Prompt registry JSONL"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable debug logs"),
):
    """Import *template_file* into the prompt registry (cross-team sharing)."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        import yaml  # type: ignore – optional dependency, only CLI-time
    except ModuleNotFoundError:
        typer.echo("⚠️  PyYAML not installed – install via `pip install pyyaml` or provide JSON file")
        raise typer.Exit(1)

    text = template_file.read_text(encoding="utf-8")
    data: Dict[str, Any]
    if template_file.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        # Naive YAML → JSON via regex (mirrors prompt_ops_framework style)
        data = yaml.safe_load(text)  # noqa: S506 – local-only input

    tmpl = PromptTemplate(**data)
    validate_template(tmpl)

    reg = PromptRegistry(registry_path)
    reg.append(tmpl)
    typer.echo(f"✔ Registered {tmpl.name} v{tmpl.version}")


@app.command("list")
def _list_cmd(
    registry_path: Path = typer.Option(_DEFAULT_REGISTRY, "--registry", help="Prompt registry path"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable debug logs"),
):
    """Display prompts in the registry."""

    setup_logging("DEBUG" if verbose else "INFO")

    reg = PromptRegistry(registry_path)
    tmpls = reg.list()
    if json_output:
        json.dump([t.as_dict() for t in tmpls], typer.stdout, indent=2)
        typer.echo()
        return

    if not tmpls:
        typer.echo("(Registry empty)")
        return

    for t in tmpls:
        typer.echo(f"• {t.name} v{t.version} ({', '.join(t.tags or [])})")


@app.command()
def skeleton(
    name: str = typer.Argument(..., help="Prompt name for the markdown skeleton"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to file instead of stdout"),
):
    """Generate *no-code* markdown skeleton for *name*."""

    md = generate_markdown_skeleton(name)
    if output:
        output = output.expanduser().resolve()
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✔ Skeleton written to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)


@app.command()
def training(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown training module to file"),
):
    """Generate the **Prompt Engineering 101** training module."""

    md = generate_training_module()
    if output:
        output = output.expanduser().resolve()
        output.write_text(md, encoding="utf-8")
        typer.echo(f"✔ Training module saved to {output.relative_to(Path.cwd())}")
    else:
        typer.echo(md)