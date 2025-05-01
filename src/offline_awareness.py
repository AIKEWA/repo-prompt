"""offline_awareness.py – Ethical offline-aware helpers.

This module embodies **Step 3.4 – Design Ethical, Offline-Aware Applications** by
providing a *thin façade* that enforces the following principles:

1. **Local Processing** – Force on-device inference via *Ollama* (or any local
   adapter) when the environment variable ``FORCE_LOCAL_LLM=1`` is set.  Remote
   calls to cloud vendors are automatically **blocked** unless explicit user
   consent is recorded via :class:`src.data_sovereignty.ConsentManager`.
2. **Diff Approval (HITL)** – Interactive file-by-file review for unified diffs
   that leverages :pymod:`src.patch_apply` utilities.  Every file patch is
   presented to the user who can *accept*, *skip* or *abort* the session – a
   practical realisation of **human-in-the-loop** dignity protection.
3. **Permission Management** – Re-uses :class:`~src.data_sovereignty.ConsentManager`
   to implement *opt-in* upload permission **per session** and **per file**.
4. **No Telemetry by Default** – All helpers refrain from any outbound
   telemetry.  A helper function :func:`enable_telemetry()` is provided but
   requires **explicit** consent before activating.

Public API
~~~~~~~~~~
```
# Local LLM wrapper – will raise when cloud usage is disallowed
response = safe_chat(messages, provider="openai")

# Interactive review – returns list of applied files
modified = interactive_diff_review(Path("change.diff"), repo_root=Path("."), apply=True)
```
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

import typer

from .logger import get_logger, setup_logging
from .data_sovereignty import ConsentManager
from .patch_apply import split_diff_by_file, apply_patch_set
from .model_interface import chat as _chat
from .success_metrics import MetricsStore, LocalOperationEvent, EnergyEvent
from .token_estimator import estimate_tokens

__all__ = [
    "safe_chat",
    "interactive_diff_review",
    "telemetry_enabled",
    "enable_telemetry",
    "app",
]

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Telemetry control – opt-in only
# ---------------------------------------------------------------------------

_TELEMETRY_ENV = "ENABLE_TELEMETRY"

def telemetry_enabled() -> bool:
    """Return *True* when outbound telemetry is allowed."""

    return os.getenv(_TELEMETRY_ENV, "0").lower() in {"1", "true", "yes"}

def enable_telemetry(*, consent_mgr: Optional[ConsentManager] = None) -> None:  # noqa: D401 – imperative style
    """Enable telemetry **only after explicit consent**.

    When called from a CLI command we ask the user via the provided
    ``ConsentManager`` (or a new one).  In *non-interactive* environments this
    function is a **no-op** to avoid coercion.
    """

    mgr = consent_mgr or ConsentManager()
    if mgr.request("telemetry", "Allow sending anonymous telemetry data to help improve the tool?", auto_deny=True):
        os.environ[_TELEMETRY_ENV] = "1"
        _log.info("Telemetry enabled for this session")
    else:
        _log.info("Telemetry remains disabled")

# ---------------------------------------------------------------------------
# Local-first chat helper – blocks cloud unless consent recorded
# ---------------------------------------------------------------------------

_FORCE_LOCAL_ENV = "FORCE_LOCAL_LLM"


def safe_chat(messages: List[Dict[str, str]], *, provider: str | None = None, model: str | None = None, **kwargs) -> str:
    """Proxy to :func:`src.model_interface.chat` that enforces *local-first*.

    Behaviour rules (ordered):
    1. If the environment variable ``FORCE_LOCAL_LLM=1`` **or**
       ``provider='local'`` is set we *force* usage of the *ollama* backend and
       raise if the binary is not available.
    2. When the chosen provider would invoke a **remote service** we attempt to
       obtain user consent via :class:`ConsentManager` *once per session*.
    3. All other arguments are transparently forwarded to
       :func:`src.model_interface.chat`.
    """

    # Phase 2: Carbon-aware scheduling – defer if grid dirty and operation heavy (>=1e3 tokens est).
    try:
        from .carbon_scheduler import delay_if_dirty

        # Rough heuristic: large operations when prompt tokens > 1000
        approx_prompt_tokens = sum(estimate_tokens(m.get("content", "")[:10000]) for m in messages)
        if approx_prompt_tokens > 1000:
            delay_if_dirty()
    except ModuleNotFoundError:
        # carbon_scheduler optional
        pass

    # Normalise provider hint – possible aliases
    provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()

    if os.getenv(_FORCE_LOCAL_ENV, "0") in {"1", "true", "yes"} or provider in {"local", "ollama"}:
        provider = "ollama"
        _log.debug("FORCE_LOCAL_LLM active – using provider 'ollama'")

    # Quick remote heuristic: any provider not equal to 'ollama' is considered remote
    is_remote = provider not in {"ollama", "local"}

    if is_remote:
        mgr = ConsentManager()
        if not mgr.request(
            "remote_llm",
            (
                f"The application needs to contact the remote LLM provider '{provider}' to fulfil "
                "your request. This may transmit prompt data over the network. Do you grant "
                "permission for this one-time operation?"
            ),
            auto_deny=True,
        ):
            raise PermissionError(
                "Remote LLM usage denied by user consent. Set FORCE_LOCAL_LLM=1 to enforce local execution explicitly."
            )

    # Record KPI – local-only operation success
    try:
        MetricsStore().append_event(LocalOperationEvent(local_operation_success=not is_remote))
    except Exception as exc:  # pragma: no cover – non-critical
        _log.debug("Failed to record LocalOperationEvent: %s", exc, exc_info=False)

    # ---------------------------
    # Perform the actual chat call
    # ---------------------------

    # Phase 2 – Telemetry: measure emissions via CodeCarbon when available.
    try:
        from .telemetry_tracker import track_emissions  # local import to avoid hard dep

        with track_emissions("safe_chat"):
            response = _chat(messages, provider=provider, model=model, **kwargs)
    except ModuleNotFoundError:
        # CodeCarbon/telemetry tracker not installed – fallback silently
        response = _chat(messages, provider=provider, model=model, **kwargs)

    # -------------------------------------------------------------------
    # Energy KPI – approximate ecological footprint of this interaction
    # -------------------------------------------------------------------

    try:
        # Token approximation – count tokens of prompt + response
        prompt_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
        response_tokens = estimate_tokens(response)
        total_tokens = prompt_tokens + response_tokens

        # Simple heuristics: local execution ~1e-7 kWh per token, remote 5×
        kwh_per_token = 1e-7 if not is_remote else 5e-7
        energy_kwh = total_tokens * kwh_per_token

        MetricsStore().append_event(
            EnergyEvent(tokens=total_tokens, energy_kwh=energy_kwh, local_execution=not is_remote)
        )
    except Exception as exc:  # pragma: no cover – non-critical
        _log.debug("Failed to record EnergyEvent: %s", exc, exc_info=False)

    return response

# ---------------------------------------------------------------------------
# Human-in-the-loop diff approval
# ---------------------------------------------------------------------------

def _print_patch(patch: str, max_lines: int = 200):
    """Pretty-print *patch* to STDOUT (trimmed after *max_lines*)."""

    lines = patch.strip().splitlines()
    truncated = len(lines) > max_lines
    preview = lines[:max_lines]
    for ln in preview:
        # Simple colour: additions green, deletions red
        if ln.startswith("+"):
            typer.secho(ln, fg="green")
        elif ln.startswith("-"):
            typer.secho(ln, fg="red")
        else:
            typer.echo(ln)
    if truncated:
        typer.secho(f"… {len(lines) - max_lines} more line(s) truncated …", fg="yellow")


def interactive_diff_review(
    diff_path: Path, *,
    repo_root: Path = Path("."),
    apply: bool = False,
    backup: bool = False,
    consent_mgr: Optional[ConsentManager] = None,
) -> List[str]:
    """Interactively review *diff_path* and optionally apply accepted files.

    Parameters
    ----------
    diff_path:
        File containing a unified diff (use ``-`` for STDIN in the CLI).
    repo_root:
        Root directory of the target repository.
    apply:
        When *True* write changes to disk for *accepted* files only.
    backup:
        Create ``.bak`` backup copies before overwriting (ignored when
        *apply* is *False*).
    consent_mgr:
        Optional :class:`ConsentManager` instance to record choices.

    Returns
    -------
    list[str]
        Relative paths of files that were (or would be) modified.
    """

    mgr = consent_mgr or ConsentManager()

    diff_text = diff_path.read_text() if diff_path != Path("-") and str(diff_path) != "-" else sys.stdin.read()
    file_patches = split_diff_by_file(diff_text)

    accepted_patches: Dict[str, str] = {}

    for rel_path, patch in file_patches.items():
        typer.secho(f"\n--- Reviewing patch for {rel_path} ---", fg="cyan", bold=True)
        _print_patch(patch)
        # Ask user – default is *no* for safety
        if mgr.request(f"patch:{rel_path}", f"Apply changes to {rel_path}?", auto_deny=True):
            accepted_patches[rel_path] = patch
            typer.secho("✔ accepted", fg="green")
        else:
            typer.secho("✖ skipped", fg="yellow")

    if not accepted_patches:
        typer.echo("No files accepted – exiting.")
        return []

    # Re-assemble accepted patches into one unified diff
    accepted_diff = "\n".join(accepted_patches.values())
    return apply_patch_set(repo_root, accepted_diff, dry_run=not apply, create_backup=backup)

# ---------------------------------------------------------------------------
# Typer CLI bundling everything together
# ---------------------------------------------------------------------------

app = typer.Typer(add_help_option=True, no_args_is_help=True, pretty_exceptions_show_locals=False)


@app.command()
def chat(
    prompt: str = typer.Argument(..., help="Prompt string (simple demo; not multi-turn)"),
    model: str = typer.Option("llama3", "--model", "-m"),
    provider: str = typer.Option(None, "--provider", "-p", help="LLM provider (default honours FORCE_LOCAL_LLM)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """CLI wrapper around :func:`safe_chat`. Useful for quick tests."""

    setup_logging("DEBUG" if verbose else "INFO")
    messages = [{"role": "user", "content": prompt}]
    try:
        resp = safe_chat(messages, provider=provider, model=model)
        typer.echo(resp)
    except PermissionError as exc:
        typer.secho(f"Error: {exc}", fg="red", err=True)
        raise typer.Exit(code=2)


@app.command()
def review(
    diff_file: Path = typer.Argument(..., exists=False, help="Path to unified diff ('-' for STDIN)"),
    repo_root: Path = typer.Option(".", "--repo", help="Repository root for applying the patch"),
    apply: bool = typer.Option(False, "--apply", help="Write accepted files instead of preview only"),
    backup: bool = typer.Option(False, "--backup", help="Create *.bak backups before overwriting"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Interactive file-by-file diff review (**HITL**)."""

    setup_logging("DEBUG" if verbose else "INFO")

    try:
        modified = interactive_diff_review(diff_file, repo_root=repo_root, apply=apply, backup=backup)
        if modified:
            typer.secho(f"{len(modified)} file(s) {'were' if apply else 'would be'} modified:", fg="green")
            for p in modified:
                typer.echo(f"  • {p}")
    except KeyboardInterrupt:  # pragma: no cover – user abort
        typer.secho("Aborted by user", fg="red")
        raise typer.Exit(code=130)


if __name__ == "__main__":
    app()