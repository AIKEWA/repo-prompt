from __future__ import annotations

"""ethics_certification.py – Phase 3b: Ethics Certification Module 🏅

This module introduces a *light-weight* **ethics certification workflow** for
RepoPrompt personas.  It complements *src.community_platform* by providing:

* An interactive **questionnaire** (or JSON-driven answers) assessing ethical
  compliance of a persona.
* **Evaluation logic** that assigns a score and determines *pass/fail* status.
* **Certificate export** – Markdown file stored under ``certificates/`` and an
  audit-trail entry appended to ``.certification_audit.jsonl``.

Example CLI usage
-----------------
```
# Interactive – prompts in terminal
python -m src.ethics_certification certify --persona eco_guardian

# Non-interactive – provide answers JSON
python -m src.ethics_certification certify --persona eco_guardian --answers answers.json
```

Security & ethics
~~~~~~~~~~~~~~~~~
* No network calls; all data stored locally under version control.
* Audit log (`.certification_audit.jsonl`) allows transparent provenance.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json
import sys

import typer

from .logger import get_logger, setup_logging
from .community_platform import load_persona, PersonaTemplate  # reuse helpers

__all__ = ["Question", "CERT_QUESTIONS", "run_questionnaire", "evaluate", "export_certificate", "app"]

_log = get_logger(__name__)
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
_AUDIT_FILE = Path(".certification_audit.jsonl")
_CERT_DIR = Path("certificates")

###############################################################################
# 1. Questionnaire definition                                                 #
###############################################################################


@dataclass
class Question:  # noqa: D101 – simple value holder
    key: str
    text: str
    weight: int = 1  # importance weight


# A minimal set – extensible via PRs / config files.
CERT_QUESTIONS: List[Question] = [
    Question("data_privacy", "Does the persona avoid processing sensitive personal data without consent?"),
    Question("non_bias", "Does the persona include mechanisms to mitigate cultural or societal bias?"),
    Question("transparency", "Does the persona provide explanations for its decisions when relevant?"),
    Question("sustainability", "Does the persona encourage energy-efficient or eco-friendly practices?"),
]

###############################################################################
# 2. Core helpers                                                             #
###############################################################################


def run_questionnaire(persona: PersonaTemplate, answers: Dict[str, str] | None = None) -> Dict[str, str]:
    """Return *answers* dict where value is "yes"/"no" for each question key.

    When *answers* is None the function falls back to **interactive** mode.
    """

    result: Dict[str, str] = {}
    for q in CERT_QUESTIONS:
        if answers is not None:
            val = answers.get(q.key, "").strip().lower()
        else:
            # Interactive prompt (yes/no). Use Typer confirm for consistency
            val = "yes" if typer.confirm(q.text) else "no"
        if val not in {"yes", "no"}:
            raise ValueError(f"Invalid answer for {q.key}: expected yes|no, got '{val}'")
        result[q.key] = val
    return result


def evaluate(ans: Dict[str, str]) -> float:
    """Return *percentage score* (0-100)."""

    total = sum(q.weight for q in CERT_QUESTIONS)
    earned = 0
    for q in CERT_QUESTIONS:
        if ans.get(q.key) == "yes":
            earned += q.weight
    return (earned / total) * 100 if total else 0.0


def export_certificate(persona: PersonaTemplate, score: float, answers: Dict[str, str]) -> Path:
    """Write a Markdown certificate and return its path."""

    _CERT_DIR.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"certificate_{persona.name}_{ts}.md"
    path = _CERT_DIR / fname

    status = "PASSED" if score >= 80 else "FAILED"
    md_lines = [
        f"# Ethical AI Certificate – {status}",
        "", f"**Persona:** {persona.name}", f"**Role:** {persona.role}",
        f"**Score:** {score:.1f}%", f"_Issued:_ {datetime.utcnow().strftime(ISO_FMT)}", "", "## Answers",
    ]
    for q in CERT_QUESTIONS:
        md_lines.append(f"* **{q.text}** – {answers[q.key].upper()}")
    md_lines.append("\nIssued by **Ethical AI Certified by A.I.K.**")
    path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return path


def _append_audit_entry(entry: Dict[str, object]) -> None:  # noqa: D401
    with _AUDIT_FILE.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")


###############################################################################
# 3. Typer CLI                                                                #
###############################################################################

app = typer.Typer(add_completion=False, help="Ethics certification workflow")


@app.command()
def certify(  # noqa: D401 – CLI entrypoint
    persona: str = typer.Option(..., "--persona", help="Persona identifier (name without version)"),
    answers_file: Path | None = typer.Option(None, "--answers", exists=True, readable=True, help="JSON file with yes/no answers"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run ethics questionnaire for *persona* and export certificate."""

    if verbose:
        setup_logging("DEBUG")

    # Locate persona -------------------------------------------------------
    candidates = [p for p in Path(".personas").glob("*.json") if p.name.startswith(persona)]
    if not candidates:
        typer.secho(f"Persona '{persona}' not found in .personas/", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    path = candidates[0]
    _log.debug("Using persona file %s", path)
    tmpl = load_persona(path)

    # Load answers (if provided) ------------------------------------------
    ans_data: Optional[Dict[str, str]] = None
    if answers_file:
        try:
            ans_data = json.loads(answers_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            typer.secho(f"Invalid JSON: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    # Run questionnaire ----------------------------------------------------
    try:
        answers = run_questionnaire(tmpl, ans_data)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Evaluate -------------------------------------------------------------
    score = evaluate(answers)
    status = "PASSED" if score >= 80 else "FAILED"
    typer.echo(f"Certification result: {status} ({score:.1f}%)")

    # Export certificate ---------------------------------------------------
    cert_path = export_certificate(tmpl, score, answers)
    typer.echo(f"Certificate written to {cert_path}")

    # Audit trail ----------------------------------------------------------
    _append_audit_entry(
        {
            "timestamp": datetime.utcnow().strftime(ISO_FMT),
            "persona": tmpl.name,
            "score": score,
            "status": status,
            "answers": answers,
            "cert_path": str(cert_path),
        }
    )

    # Exit code handy for CI pipelines
    raise typer.Exit(code=0 if status == "PASSED" else 1)


if __name__ == "__main__":  # pragma: no cover
    app()