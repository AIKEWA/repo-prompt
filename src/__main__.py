from __future__ import annotations

"""Command line interface for Repo Prompt workflow.

Example usage:

    python -m src . --max-tokens 4096 --model gpt-3.5-turbo
"""

import asyncio
from pathlib import Path
from typing import Optional

import typer

from .logger import setup_logging, get_logger
from .codemaps import map_repository, app as _map_cli
from .xml_prompt import build_repo_xml
from .model_interface import openai_chat_async, openai_chat, chat as _chat
from .token_estimator import estimate_tokens
from .context_analyzer import analyze_context
from .pr_review import _cli as _review_cli
from .tool_setup import verify_system as _verify_system
from .changelog import generate_changelog as _gen_changelog
from .patch_apply import apply_patch_set
from .success_metrics import app as _metrics_cli
from .feedback_mechanism import app as _feedback_cli
from .training_comm import app as _train_cli
from .standardization import app as _std_cli
from .pages_setup import app as _pages_cli
from .context_builder import app as _ctx_cli
from .large_refactor import app as _refactor_cli
from .bug_fix_prompt import app as _bugfix_cli
from .methodology_tools import app as _meth_cli
from .cognitive_primer import app as _primer_cli
from .diff_review_standards import app as _diffstd_cli
from .scalability_adaptation import app as _scale_cli
from .engineering_stack import app as _eng_cli
from .communication_strategy import app as _comm_cli
from .community_platform import app as _community_cli
from .ethics_certification import app as _cert_cli
from .persona_simulation import app as _sim_cli
from .onboarding_center import app as _learn_cli
from .template_peer_review import app as _review_cli2

app = typer.Typer(add_completion=False, help="Convert repo to XML prompt and send to LLM")


@app.command()
def prompt(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to code repository"),
    model: str = typer.Option("gpt-3.5-turbo", "--model", "-m"),
    max_tokens: int = typer.Option(7000, "--max-tokens", "-t"),
    async_mode: bool = typer.Option(False, "--async"),
    provider: str = typer.Option(
        "openai",
        "--provider",
        help="LLM provider to use (openai|ollama). Falls back to $LLM_PROVIDER env var.",
    ),
    include_regex: str | None = typer.Option(
        None,
        "--include-regex",
        help="Only include file paths that match this regular expression",
    ),
    exclude_regex: str | None = typer.Option(
        None,
        "--exclude-regex",
        help="Exclude file or directory paths matching this regular expression",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate repo XML and call model."""

    setup_logging("DEBUG" if verbose else "INFO")
    log = get_logger(__name__)

    log.info("Scanning repository %s (include=%s, exclude=%s)", repo_path, include_regex, exclude_regex)
    cm = map_repository(repo_path, include_pattern=include_regex, exclude_pattern=exclude_regex)

    log.info("Building XML prompt (max %s tokens)", max_tokens)
    xml_prompt = build_repo_xml(cm, max_tokens=max_tokens)
    log.debug("XML size (bytes): %d", len(xml_prompt.encode()))
    log.debug("Approx tokens: %d", estimate_tokens(xml_prompt))

    messages = [
        {"role": "system", "content": "You are an AI coding assistant."},
        {"role": "user", "content": xml_prompt},
    ]

    from .model_interface import openai_chat_async as _openai_chat_async

    if async_mode:
        if provider != "openai":
            log.warning("Async mode is only supported for provider 'openai'. Falling back to synchronous call.")
            content = _chat(messages, provider=provider, model=model)
        else:
            content = asyncio.run(_openai_chat_async(messages, model=model))
    else:
        content = _chat(messages, provider=provider, model=model)

    typer.echo("\n--- LLM Response ---\n")
    typer.echo(content)


@app.command()
def context(
    repo_path: Path = typer.Argument(".", exists=True, file_okay=False, help="Path to Git repository"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print a JSON summary of the local dev environment (step 1.2)."""

    setup_logging("DEBUG" if verbose else "INFO")

    ctx = analyze_context(repo_path)
    import json, sys

    json.dump(ctx, sys.stdout, indent=2)
    sys.stdout.write("\n")


@app.command()
def setup(
    repo_path: Path = typer.Argument(".", exists=True, file_okay=False, help="Path to project root for verification"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of human readable"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run **step 1.4 Tool & Methodology Setup** checks and print a readiness report."""

    setup_logging("DEBUG" if verbose else "INFO")

    report = _verify_system(repo_path)

    import json, sys

    if json_output:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for res in report["results"]:
            glyph = "✅" if res["ok"] else "❌"
            typer.echo(f"{glyph} {res['name']}: {res['details']}")
        typer.echo("---")
        typer.echo("Environment ready ✔" if report["all_ok"] else "Environment incomplete ✖")

    # convey readiness via exit code when used programmatically
    raise typer.Exit(code=0 if report["all_ok"] else 1)


@app.command()
def changelog(
    from_ref: str = typer.Option(None, "--from", help="Start revision (exclusive, default last tag)"),
    to_ref: str = typer.Option("HEAD", "--to", help="End revision (inclusive)"),
    llm: bool = typer.Option(False, "--llm", help="Use LLM summarisation if key present"),
    feedback_store: Path | None = typer.Option(None, "--feedback-store", "--feedback", help="Path to feedback JSONL file to embed top requests"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a markdown changelog from Git history (optional step)."""

    setup_logging("DEBUG" if verbose else "INFO")

    md = _gen_changelog(Path("."), from_ref, to_ref, llm, feedback_store=feedback_store)
    typer.echo(md)


@app.command()
def patch(
    diff_file: Path = typer.Argument(..., exists=False, help="Path to unified diff file. Use '-' to read stdin."),
    repo_path: Path = typer.Option(".", "--repo-path", help="Repository root for applying the patch"),
    apply: bool = typer.Option(False, "--apply", help="Perform write – otherwise act as dry-run preview"),
    backup: bool = typer.Option(False, "--backup", help="Create *.bak backups before overwriting"),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable summary"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Preview or apply a unified diff produced by an LLM or manual edits.

    This command finalises *Step 1.5* of the implementation plan by taking the
    diff text (from a file or STDIN) and – if `--apply` is given – updating the
    repository in-place. Without `--apply` it shows what **would** change.
    """

    setup_logging("DEBUG" if verbose else "INFO")

    if diff_file == Path("-") or str(diff_file) == "-":
        diff_text = typer.get_text_stream("stdin").read()
    else:
        diff_text = Path(diff_file).read_text()

    modified = apply_patch_set(repo_path, diff_text, dry_run=not apply, create_backup=backup)

    import json as _json, sys as _sys

    if json_output:
        _json.dump({"modified": modified, "dry_run": not apply}, _sys.stdout, indent=2)
        _sys.stdout.write("\n")
    else:
        mode = "would be" if not apply else "were"
        if modified:
            typer.echo(f"{len(modified)} file(s) {mode} modified:")
            for p in modified:
                typer.echo(f"  • {p}")
        else:
            typer.echo("No files matched the patch – nothing to do")


app.add_typer(_metrics_cli, name="metrics")
app.add_typer(_feedback_cli, name="feedback")
app.add_typer(_train_cli, name="training")
app.add_typer(_std_cli, name="standardize")
app.add_typer(_pages_cli, name="pages")
app.add_typer(_ctx_cli, name="attention")
app.add_typer(_refactor_cli, name="refactor")
app.add_typer(_bugfix_cli, name="bugfix")
app.add_typer(_meth_cli, name="methodology")
app.add_typer(_map_cli, name="codemap")
app.add_typer(_primer_cli, name="primer")
app.add_typer(_diffstd_cli, name="apply-standards")
app.add_typer(_scale_cli, name="scale")
app.add_typer(_eng_cli, name="stack")
app.add_typer(_comm_cli, name="communicate")
app.add_typer(_community_cli, name="community")
app.add_typer(_cert_cli, name="certify")
app.add_typer(_sim_cli, name="persona")
app.add_typer(_learn_cli, name="learn")
app.add_typer(_review_cli2, name="template-review")


# ---------------------------------------------------------------------------
# Integration into standard practice – PR review helper
# ---------------------------------------------------------------------------

# The following Typer command exposes the **LLM-powered pull-request review**
# utility (`src.pr_review.summarize_diff`) as a *top-level* sub-command.  This
# allows CI pipelines (e.g. the *Repo Prompt* GitHub Action) and human users to
# invoke it via a **consistent** CLI entry-point:
#
#     python -m src review --range "HEAD~3..HEAD" --model gpt-4o
#
# The command is intentionally lightweight and simply forwards arguments to the
# internal helper – avoiding duplicate logic while keeping import-time overhead
# minimal.


@app.command(name="review")
def review_command(
    repo_path: Path = typer.Argument(Path("."), exists=True, file_okay=False, help="Path to Git repository"),
    commit_range: str = typer.Option("HEAD~1..HEAD", "--range", "-r", help="Git commit range for diff"),
    model: str = typer.Option("gpt-3.5-turbo", "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate an LLM-based pull-request review for *commit_range*.

    This wrapper exists so that external automation (CI pipelines, Git hooks)
    can *mandate* Repo Prompt reviews as part of the PR process.  All heavy
    lifting (diff extraction, prompt construction, API calls) is delegated to
    :pymod:`src.pr_review` in order to keep concerns separated.
    """

    _review_cli(repo_path, commit_range, model, verbose)


if __name__ == "__main__":
    app()