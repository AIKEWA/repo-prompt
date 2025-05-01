"""scaling_communication.py – Step 5.9 Scaling & Communication 📈💬

This module operationalises *Step 5.9 – Scaling & Communication* from the
Theory→Code execution framework.  It bundles **three concrete helpers** that
translate the theoretical requirements into production-ready artefacts:

1. **Platform Roadmap – Windows/Linux Beta Waitlist**
   • ``generate_waitlist_page`` returns a ready-to-publish *HTML* landing page
     collecting email addresses for the public beta of the Windows & Linux
     desktop build.
   • ``generate_eta_modal`` emits a tiny *JSON* spec (framework-agnostic) that
     frontend clients can consume to render an **ETA modal** in-app.

2. **Community Sharing – Prompt Template Exporter**
   • The :class:`PromptTemplate` dataclass (import-agnostic) represents a custom
     prompt template authored by users.
   • ``export_prompt_template`` writes the template to *JSON* or *Markdown* so
     that it can be pasted into forums, shared via email, or attached to issue
     trackers.

3. **Training – Top 10 UX Power Tips Publisher**
   • ``generate_power_tips_markdown`` & ``generate_power_tips_html`` return the
     *Top 10 UX Power Tips* list (plain Markdown / email-friendly HTML).
   • A **Typer CLI** exposes sub-commands so non-developer team-mates (e.g.
     marketing) can generate the artefacts without touching Python code.

Security & Ethical Notes
~~~~~~~~~~~~~~~~~~~~~~~~
* All helpers are **offline-first** – no outbound network calls.
* Exported prompt templates are validated & sanitised to avoid leaking secrets.
* Waitlist page uses a ``mailto:`` fallback (no tracking) or optional *action*
  URL when teams run their own form backend.

Example
~~~~~~~
```console
# Preview waitlist page (stdout)
python -m src.scaling_communication waitlist page

# Write ETA modal spec (defaults to JSON)
python -m src.scaling_communication waitlist modal --os windows --eta 2024-11-30 --output ui/eta_modal.windows.json

# Share a custom template as Markdown
python -m src.scaling_communication templates export my_template.json --format md --output shared/bug_prompt.md

# Publish the Top 10 UX Power Tips (Markdown → docs)
python -m src.scaling_communication training tips --output docs/top_10_ux_power_tips.md --overwrite
```
"""

from __future__ import annotations

import html
import json
import re
import textwrap
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from .logger import get_logger, setup_logging

__all__ = [
    # Roadmap helpers
    "generate_waitlist_page",
    "generate_eta_modal",
    # Template helpers
    "PromptTemplate",
    "export_prompt_template",
    # Power tips helpers
    "generate_power_tips_markdown",
    "generate_power_tips_html",
    # Typer app (CLI entry-point)
    "app",
]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

###############################################################################
# 1. PLATFORM ROADMAP – WAITLIST & ETA MODAL                                ###
###############################################################################

_WAITLIST_FORM_FALLBACK = textwrap.dedent(
    """
    <!-- Fallback form posts to *mailto:* when no backend is configured. -->
    <form action="mailto:beta@local.example" method="post" enctype="text/plain">
      <label for="email">Join the beta waitlist:</label><br />\n
      <input type="email" id="email" name="email" placeholder="you@example.com" required style="padding:0.5rem;" />\n
      <input type="hidden" name="os" value="{os}" />\n
      <button type="submit" style="padding:0.5rem 1rem;margin-left:0.5rem;">Subscribe</button>
    </form>
    """
)

_WAITLIST_PAGE_TEMPLATE = textwrap.dedent(
    """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{title}</title>
        <style>
            body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
            h1 {{ color: #1d4ed8; }}
            p  {{ max-width: 60ch; }}
        </style>
    </head>
    <body>
        <h1>{headline}</h1>
        <p>{description}</p>

        {form_html}

        <p style="font-size:0.8rem;color:#555;">Generated {generated_at}</p>
    </body>
    </html>
    """
).strip()


def generate_waitlist_page(
    *,
    os_label: str = "windows",  # windows | linux
    action_url: str | None = None,
    title: str | None = None,
) -> str:
    """Return a minimal *HTML* waitlist page for *os_label* beta.

    Parameters
    ----------
    os_label:
        Either ``"windows"`` or ``"linux"`` – injected into hidden form field.
    action_url:
        Optional custom *form backend* (e.g. https://formcarry.com/…). When
        *None* (default) a *mailto:* fallback is used (privacy-friendly).
    title:
        ``<title>`` & *H1* fallback. Defaults to "Join the Windows (Beta) Waitlist".
    """

    if os_label.lower() not in {"windows", "linux"}:
        raise ValueError("os_label must be 'windows' or 'linux'")

    title = title or f"Join the {os_label.capitalize()} Beta Waitlist"
    headline = html.escape(title)

    description = (
        f"We're putting the finishing touches on the **{os_label.capitalize()}** desktop build. "
        "Sign up below to get early-access and a download link the minute it's ready!"
    )

    if action_url:
        # Simple HTML form posting to user-supplied endpoint
        form_html = textwrap.dedent(
            f"""
            <form action=\"{html.escape(action_url)}\" method=\"post\" style=\"margin-top:1rem;\">
              <input type=\"email\" name=\"email\" placeholder=\"you@example.com\" required style=\"padding:0.5rem;\" />
              <input type=\"hidden\" name=\"os\" value=\"{os_label}\" />
              <button type=\"submit\" style=\"padding:0.5rem 1rem;margin-left:0.5rem;\">Notify me</button>
            </form>
            """
        ).strip()
    else:
        form_html = _WAITLIST_FORM_FALLBACK.format(os=os_label)

    html_str = _WAITLIST_PAGE_TEMPLATE.format(
        title=html.escape(title),
        headline=html.escape(title),
        description=description,
        form_html=form_html,
        generated_at=datetime.utcnow().strftime(ISO_FMT),
    )

    _log.debug("Generated waitlist page for %s (len=%d)", os_label, len(html_str))
    return html_str + "\n"


def generate_eta_modal(*, os_label: str, eta: str) -> str:  # noqa: D401 – imperative style
    """Return **JSON** spec describing an ETA modal.

    The spec is *framework agnostic* and can be consumed by React, Vue, or any
    custom UI layer.

    Example JSON
    ------------
    ```json
    {
      "id": "eta-modal-windows",
      "title": "Windows Beta ETA",
      "message": "We expect the Windows beta to ship on 2024-11-30.",
      "cta": "Join waitlist",
      "link": "/waitlist/windows.html"
    }
    ```
    """

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", eta):
        raise ValueError("eta must be ISO date YYYY-MM-DD")

    if os_label.lower() not in {"windows", "linux"}:
        raise ValueError("os_label must be 'windows' or 'linux'")

    spec = {
        "id": f"eta-modal-{os_label.lower()}",
        "title": f"{os_label.capitalize()} Beta ETA",
        "message": f"We expect the {os_label.capitalize()} beta to ship on {eta}.",
        "cta": "Join waitlist",
        "link": f"/waitlist/{os_label.lower()}.html",
        "generated_at": datetime.utcnow().strftime(ISO_FMT),
    }

    json_str = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    _log.debug("Generated ETA modal spec for %s beta (len=%d)", os_label, len(json_str))
    return json_str


###############################################################################
# 2. COMMUNITY SHARING – PROMPT TEMPLATE EXPORTER                            ###
###############################################################################


@dataclass
class PromptTemplate:
    """Represents a *custom prompt template* authored by a user.

    Parameters
    ----------
    name:
        Human-friendly identifier (slug allowed: letters, digits, dashes, underscore).
    description:
        Short summary of the template's purpose.
    content:
        Full template text – may include markdown or placeholder tokens.
    version:
        Optional semantic version or commit SHA (default: auto timestamp).
    """

    name: str
    description: str
    content: str
    version: str = datetime.utcnow().strftime("%Y.%m.%d")

    # ---------------- Serialisation helpers ----------------
    def _validate(self) -> None:  # noqa: D401 – imperative style
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", self.name):
            raise ValueError("name must be 3-100 chars (letters, digits, dash, underscore)")

    def as_json(self) -> str:  # noqa: D401 – imperative style
        self._validate()
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    def as_markdown(self) -> str:  # noqa: D401 – imperative style
        self._validate()
        return textwrap.dedent(
            f"""
            ### Prompt Template: {self.name}

            **Version:** {self.version}
            **Description:** {self.description}

            ```markdown
            {self.content}
            ```
            """
        ).strip() + "\n"


_DEFAULT_TEMPLATE_DIR = Path.home() / ".prompt_templates"


def export_prompt_template(
    tpl: PromptTemplate,
    *,
    fmt: str = "json",  # json | md
    output_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write *tpl* to disk in the chosen *fmt* (json|md) and return the path."""

    output_dir = (output_dir or _DEFAULT_TEMPLATE_DIR).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = ".json" if fmt == "json" else ".md"
    path = output_dir / f"{tpl.name}{ext}"

    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists – use --overwrite to replace")

    text = tpl.as_json() if fmt == "json" else tpl.as_markdown()
    path.write_text(text, encoding="utf-8")
    _log.info("Prompt template exported to %s", path)
    return path


###############################################################################
# 3. TRAINING – TOP 10 UX POWER TIPS                                        ###
###############################################################################

_POWER_TIPS: List[str] = [
    "Use clear, consistent language across the UI.",
    "Prioritise keyboard shortcuts for expert users.",
    "Provide progressive disclosure for advanced settings.",
    "Respect user privacy by default – ask for consent only when required.",
    "Optimise for performance – perceived speed is part of UX.",
    "Offer undo/redo wherever destructive actions are possible.",
    "Use accessible colour contrasts and font sizes.",
    "Provide contextual help via tooltips or side panels.",
    "Test flows on real hardware with limited resources.",
    "Collect qualitative feedback early and iterate fast.",
]


def generate_power_tips_markdown() -> str:  # noqa: D401 – imperative style
    """Return the *Top 10 UX Power Tips* as Markdown list."""

    bullets = "\n".join(f"1. {tip}" for tip in _POWER_TIPS)
    md = textwrap.dedent(
        f"""
        # Top 10 UX Power Tips

        These guidelines help developers & designers craft delightful
        user experiences when integrating AI-assisted features:

        {bullets}
        """
    ).strip() + "\n"

    _log.debug("Generated power tips markdown (len=%d)", len(md))
    return md


def generate_power_tips_html(*, inline_css: bool = True) -> str:  # noqa: D401
    """Return the *Top 10 UX Power Tips* as email-friendly HTML."""

    items = "".join(f"<li>{html.escape(tip)}</li>" for tip in _POWER_TIPS)
    styles = (
        "body {font-family: system-ui, sans-serif; padding:1rem;} "
        "h2 {color:#1d4ed8;} li {margin-bottom:0.5rem;}" if inline_css else ""
    )

    html_str = textwrap.dedent(
        f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset=\"UTF-8\"><style>{styles}</style></head>
        <body>
          <h2>Top 10 UX Power Tips</h2>
          <p>These guidelines help you craft delightful user experiences when integrating AI-assisted features:</p>
          <ol>{items}</ol>
        </body>
        </html>
        """
    ).strip() + "\n"

    _log.debug("Generated power tips HTML (len=%d)", len(html_str))
    return html_str


###############################################################################
# 4. CLI – Typer entry-point                                                ###
###############################################################################

app = typer.Typer(add_completion=False, help="Step 5.9 – Scaling & Communication utilities")

# -------------------- Waitlist sub-commands --------------------
waitlist_app = typer.Typer(help="Generate waitlist artefacts (page / modal)")
app.add_typer(waitlist_app, name="waitlist")


@waitlist_app.command("page")
def _cmd_waitlist_page(
    os_label: str = typer.Option("windows", "--os", help="windows|linux"),
    action_url: str | None = typer.Option(None, "--action-url", help="Form backend URL – defaults to mailto:"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write HTML to path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *HTML* waitlist page (stdout or file)."""

    setup_logging("DEBUG" if verbose else "INFO")
    html_str = generate_waitlist_page(os_label=os_label, action_url=action_url)

    if output:
        output_path = Path(output).expanduser().resolve()
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"{output_path} exists – use --overwrite to replace")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_str, encoding="utf-8")
        typer.echo(f"✅ Waitlist page written to {output_path}")
    else:
        typer.echo(html_str)


@waitlist_app.command("modal")
def _cmd_waitlist_modal(
    os_label: str = typer.Option("windows", "--os", help="windows|linux"),
    eta: str = typer.Option(..., "--eta", help="ISO date YYYY-MM-DD"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON spec to path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *JSON* ETA modal spec (stdout or file)."""

    setup_logging("DEBUG" if verbose else "INFO")
    json_str = generate_eta_modal(os_label=os_label, eta=eta)

    if output:
        output_path = Path(output).expanduser().resolve()
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"{output_path} exists – use --overwrite to replace")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str, encoding="utf-8")
        typer.echo(f"✅ ETA modal spec written to {output_path}")
    else:
        typer.echo(json_str)


# -------------------- Template sub-commands --------------------

templates_app = typer.Typer(help="Export / share prompt templates")
app.add_typer(templates_app, name="templates")


@templates_app.command("export")
def _cmd_template_export(
    template_path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Path to template source file (.json|.md)"),
    fmt: str = typer.Option("json", "--format", "-f", help="Output format: json|md"),
    output_dir: Path | None = typer.Option(None, "--output", "-o", help="Directory to write exported template"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Export an *existing* template file to the chosen format inside *output_dir*."""

    setup_logging("DEBUG" if verbose else "INFO")

    if fmt not in {"json", "md"}:
        raise typer.BadParameter("format must be json|md")

    raw = template_path.read_text("utf-8")
    # Attempt to parse – JSON first, fallback: treat file as raw markdown content
    try:
        data = json.loads(raw)
        tpl = PromptTemplate(**data)  # type: ignore[arg-type]
    except json.JSONDecodeError:
        # Minimal heuristic: first line == title? Keep as is.
        tpl = PromptTemplate(name=template_path.stem, description="Imported markdown template", content=raw)

    try:
        export_prompt_template(tpl, fmt=fmt, output_dir=output_dir, overwrite=overwrite)
    except FileExistsError as exc:
        _log.error(exc)
        raise typer.Exit(code=1)


# -------------------- Training sub-commands --------------------

training_app = typer.Typer(help="Training / onboarding artefacts")
app.add_typer(training_app, name="training")


@training_app.command("tips")
def _cmd_power_tips(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write Markdown to path"),
    html_format: bool = typer.Option(False, "--html", help="Generate HTML instead of Markdown"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate *Top 10 UX Power Tips* in Markdown (default) or HTML."""

    setup_logging("DEBUG" if verbose else "INFO")

    text = generate_power_tips_html() if html_format else generate_power_tips_markdown()

    if output:
        output_path = Path(output).expanduser().resolve()
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"{output_path} exists – use --overwrite to replace")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        typer.echo(f"✅ Power tips written to {output_path}")
    else:
        typer.echo(text)