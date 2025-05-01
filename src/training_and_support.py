from __future__ import annotations

"""training_and_support.py – Step 3.12 Training & Support ⚙️📚

This module implements *Step 3.12 – Training and Support* from the
Theory→Code execution framework.

Deliverables covered
====================
1. **Workshops** – Registry for internal workshops, incl. sample titles:
   • "Ethics in Local AI: What Developers Should Know"
   • "From Cloud-First to User-First: Building for Sovereignty"
2. **Documentation** – Plain-language privacy policies & developer tutorials
   helping teams run models *offline* securely.

The design mirrors existing append-only JSONL helpers such as
:pyfile:`src.training_support` and :pyfile:`src.stakeholder_training` for
consistency.  Additionally, helper functions are provided to **generate**
ready-to-publish markdown documents so non-developers can author policies via
CLI without editing text files manually.

Security & Ethical Notes
-----------------------
* All operations are local-only – **no outbound network calls**.
* Generated privacy policies emphasise *data minimisation* & *sovereignty*.
* Markdown templates avoid legal jargon, favouring plain language.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import textwrap
import re

import typer

from .logger import get_logger, setup_logging

__all__ = [
    "Workshop",
    "Documentation",
    "SupportStore",
    "generate_privacy_policy",
    "generate_offline_tutorial",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
_DEFAULT_FILE = Path(os.getenv("TRAINING_SUPPORT_312_FILE", ".training_support_3_12.jsonl"))


@dataclass(kw_only=True)
class _BaseRecord:
    """Common metadata + JSON serialisation."""

    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime(ISO_FMT))

    @property
    def type(self) -> str:  # noqa: D401
        return self.__class__.__name__

    def to_json(self) -> str:  # noqa: D401
        data = asdict(self)
        data["type"] = self.type
        return json.dumps(data, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Record types
# ---------------------------------------------------------------------------


@dataclass
class Workshop(_BaseRecord):
    """Metadata for an internal *workshop* event."""

    title: str
    facilitator: str | None = None
    date: str | None = None  # YYYY-MM-DD
    duration_min: int | None = None
    description: str | None = None
    recording_url: str | None = None
    tags: str | None = None

    def __post_init__(self) -> None:  # noqa: D401
        if self.date is None:
            self.date = datetime.utcnow().strftime("%Y-%m-%d")


@dataclass
class Documentation(_BaseRecord):
    """Represents a training/support *documentation* asset.

    Parameters
    ----------
    doc_type:
        Either ``"privacy_policy"`` or ``"tutorial"`` (extendable).
    title:
        Display title of the document.
    path:
        Filesystem path or wiki slug.
    version:
        Optional semantic version or commit hash for traceability.
    summary:
        Optional short summary.
    """

    doc_type: str
    title: str
    path: str
    version: str | None = None
    summary: str | None = None


# ---------------------------------------------------------------------------
# JSONL store – append only
# ---------------------------------------------------------------------------


class SupportStore:
    """Persistent storage for *Workshop* & *Documentation* records."""

    def __init__(self, path: str | Path = _DEFAULT_FILE) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _log.debug("Support store initialised at %s", self.path)

    # -------------------
    # CRUD helpers
    # -------------------

    def append(self, record: _BaseRecord) -> None:  # noqa: D401 – imperative → okay
        if not self.path.exists():
            self.path.touch()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        _log.info("Recorded %s", record.type)

    def _load(self) -> List[_BaseRecord]:
        if not self.path.exists():
            return []

        records: List[_BaseRecord] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                data = json.loads(ln)
                r_type = data.pop("type", None)
                if r_type == "Workshop":
                    records.append(Workshop(**data))
                elif r_type == "Documentation":
                    records.append(Documentation(**data))
        return records

    # -------------------
    # Aggregations & export
    # -------------------

    def aggregate(self) -> Dict[str, Any]:  # noqa: D401
        workshops: List[Workshop] = []
        docs: List[Documentation] = []
        for r in self._load():
            if isinstance(r, Workshop):
                workshops.append(r)
            elif isinstance(r, Documentation):
                docs.append(r)
        return {
            "workshops": len(workshops),
            "documentation": len(docs),
        }

    def export_markdown(self) -> str:
        """Return human-readable markdown overview."""

        lines: List[str] = ["# Training & Support Resources (Step 3.12)\n"]

        workshops = [r for r in self._load() if isinstance(r, Workshop)]
        docs = [r for r in self._load() if isinstance(r, Documentation)]

        if workshops:
            lines.append("## Workshops\n")
            for w in workshops:
                lines.append(f"* **{w.title}** – {w.date}" + (f" (Facilitator: {w.facilitator})" if w.facilitator else ""))
                if w.description:
                    lines.append(f"  \- {w.description}")
            lines.append("")

        if docs:
            lines.append("## Documentation Assets\n")
            for d in docs:
                lines.append(f"* **{d.title}** – {d.doc_type} ({d.path})")
                if d.summary:
                    lines.append(f"  \- {d.summary}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------


_PRIVACY_POLICY_TEMPLATE = textwrap.dedent(
    """
    # Privacy Policy – Plain Language

    _Last updated: {date}_

    ## 1. Why we care about your privacy
    We believe that **your data is yours**.  Our application runs *offline by
    default*, meaning your information stays on your device unless you decide
    otherwise.

    ## 2. What information we keep (and why)
    1. Usage settings (so the app remembers your preferences).
    2. Error logs (to fix bugs) – these **never** contain your personal files.

    ## 3. What never leaves your device
    * Your documents, code or project files.
    * Any AI prompts or model outputs.

    ## 4. When we might ask for consent
    Sometimes you may choose to enable **cloud features** (e.g. larger models).
    When this happens we will **always** ask first and explain:
    * What will be sent (e.g. anonymised prompt snippets).
    * How long the data is kept.
    * How to turn the feature off again.

    ## 5. How to remove your data
    You can delete all app data at any time by selecting
    **Settings → Reset Local Data**.  This erases caches and logs
    stored on-device.

    ## 6. Contact us
    Questions?  Email **privacy@{org_domain}** – we read every message.
    """
).strip()

_TUTORIAL_TEMPLATE = textwrap.dedent(
    """
    # Tutorial – Running Models Offline Securely

    _Last updated: {date}_

    ## Prerequisites
    * A machine with **>=16 GB RAM**
    * [Ollama](https://ollama.com) or another local-LLM runtime installed
    * Model files downloaded (e.g. *llama3-8b-q4_k_m.gguf*)

    ## 1. Install the runtime
    ````console
    brew install ollama  # macOS / Linux
    # or visit https://ollama.com for Windows binaries
    ````

    ## 2. Pull the model
    ````console
    ollama run llama3:8b
    ````

    ## 3. Configure the application
    Set the environment variable so the codebase forces local execution:
    ```bash
    export FORCE_LOCAL_LLM=1
    ```

    ## 4. Verify no outbound traffic
    Use a network monitor (Little Snitch / tcpdump) – you should see **zero**
    requests leaving your device when invoking the AI features.

    ## 5. Next steps
    * Explore advanced quantisation options to reduce memory usage.
    * Read our *Ethics in Local AI* workshop notes for best practices.
    """
).strip()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-") or "document"


def generate_privacy_policy(*, org_domain: str = "example.com", output_dir: Optional[Path] = None, overwrite: bool = False) -> Path | str:
    """Generate plain-language privacy policy markdown.

    When *output_dir* is provided, the markdown is written to that directory
    (filename derived from slug).  Otherwise the markdown string is returned.
    """

    md = _PRIVACY_POLICY_TEMPLATE.format(date=datetime.utcnow().strftime("%Y-%m-%d"), org_domain=org_domain)
    if output_dir is None:
        return md  # type: ignore[return-value]

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"privacy-policy-{_slugify(org_domain)}.md"
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists – use --overwrite to replace")
    path.write_text(md, encoding="utf-8")
    _log.info("Privacy policy written to %s", path)
    return path


def generate_offline_tutorial(*, output_dir: Optional[Path] = None, overwrite: bool = False) -> Path | str:
    """Generate *offline model tutorial* markdown."""

    md = _TUTORIAL_TEMPLATE.format(date=datetime.utcnow().strftime("%Y-%m-%d"))
    if output_dir is None:
        return md  # type: ignore[return-value]

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "offline-model-tutorial.md"
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists – use --overwrite to replace")
    path.write_text(md, encoding="utf-8")
    _log.info("Tutorial written to %s", path)
    return path


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------


app = typer.Typer(add_completion=False, help="Register workshops & docs; generate training material (Step 3.12)")


@app.command()
def workshop(
    title: str = typer.Argument(..., help="Workshop title"),
    facilitator: str | None = typer.Option(None, "--facilitator", "-f", help="Facilitator name"),
    date: str | None = typer.Option(None, "--date", "-d", help="ISO-8601 date (YYYY-MM-DD)"),
    duration: int | None = typer.Option(None, "--duration", "-t", help="Duration in minutes"),
    description: str | None = typer.Option(None, "--description", "-s", help="Optional description"),
    recording_url: str | None = typer.Option(None, "--recording-url", "-r", help="Recording/slides URL"),
    tags: str | None = typer.Option(None, "--tags", help="CSV tags"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a **workshop** entry."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = SupportStore(store_path)
    store.append(
        Workshop(
            title=title,
            facilitator=facilitator,
            date=date,
            duration_min=duration,
            description=description,
            recording_url=recording_url,
            tags=tags,
        )
    )


@app.command()
def doc(
    doc_type: str = typer.Argument(..., help="Type: 'privacy_policy' or 'tutorial'"),
    title: str = typer.Argument(..., help="Document title"),
    path: str = typer.Argument(..., help="File path or wiki slug"),
    version: str | None = typer.Option(None, "--version", "-v", help="Version or commit SHA"),
    summary: str | None = typer.Option(None, "--summary", "-s", help="Short summary"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Register a *documentation* asset."""

    if doc_type not in {"privacy_policy", "tutorial"}:
        typer.echo("doc_type must be 'privacy_policy' or 'tutorial'", err=True)
        raise typer.Exit(code=1)

    setup_logging("DEBUG" if verbose else "INFO")
    store = SupportStore(store_path)
    store.append(
        Documentation(
            doc_type=doc_type,
            title=title,
            path=path,
            version=version,
            summary=summary,
        )
    )


# -------------------
# Generate sub-app
# -------------------

gen_app = typer.Typer(help="Generate markdown training/support docs")
app.add_typer(gen_app, name="generate")


@gen_app.command("privacy_policy")
def _cmd_privacy(
    org_domain: str = typer.Option("example.com", "--domain", help="Organisation email domain for contact section"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to directory"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate plain-language privacy policy."""

    setup_logging("DEBUG" if verbose else "INFO")

    if output:
        path = generate_privacy_policy(org_domain=org_domain, output_dir=output, overwrite=overwrite)
        typer.echo(f"Privacy policy written to {path}")
    else:
        md = generate_privacy_policy(org_domain=org_domain)
        typer.echo(md)


@gen_app.command("tutorial")
def _cmd_tutorial(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to directory"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *offline model* tutorial markdown."""

    setup_logging("DEBUG" if verbose else "INFO")

    if output:
        path = generate_offline_tutorial(output_dir=output, overwrite=overwrite)
        typer.echo(f"Tutorial written to {path}")
    else:
        md = generate_offline_tutorial()
        typer.echo(md)


@app.command()
def summary(
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Print counts for workshops & documentation assets."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = SupportStore(store_path)
    agg = store.aggregate()
    if json_output:
        typer.echo(json.dumps(agg))
    else:
        typer.echo("\n".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in agg.items()))


@app.command()
def export(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write markdown to file"),
    store_path: Path = typer.Option(_DEFAULT_FILE, "--store", help="JSONL store"),
    verbose: bool = typer.Option(False, "--verbose", "-V"),
):
    """Export a markdown report of all Training & Support resources."""

    setup_logging("DEBUG" if verbose else "INFO")
    store = SupportStore(store_path)
    md = store.export_markdown()

    if output:
        output = output.expanduser().resolve()
        if output.exists():
            _log.warning("Overwriting existing file at %s", output)
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Markdown exported to {output}")
    else:
        typer.echo(md)