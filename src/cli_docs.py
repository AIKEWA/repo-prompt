from __future__ import annotations

"""CLI documentation generator.

Usage (programmatic):
    from src.cli_docs import generate_docs
    from src.__main__ import app as main_app
    md = generate_docs(main_app)

The output is a Markdown string listing commands, options and sub-commands –
handy for README inclusion or CI-generated reference docs.
"""

from pathlib import Path
from typing import List

import typer
import click

__all__ = ["generate_docs", "write_docs_file"]


def _unwrap_click(cmd: object) -> click.Command:  # noqa: D401 – imperative util
    """Return the underlying *click.Command* object from *cmd*.

    Typer <0.8 passed actual :class:`click.Command` instances while
    Typer >=0.8 wraps them in a lightweight *CommandInfo* container that
    exposes the click command via the ``.command`` attribute.
    """

    if isinstance(cmd, click.Command):
        return cmd
    # Typer ≥0.8 – CommandInfo wrapper (<=0.9 had .to_click_command())
    inner = getattr(cmd, "command", None)
    if isinstance(inner, click.Command):
        return inner
    # Typer ≥0.15 – CommandInfo with *to_click_command* helper
    to_click = getattr(cmd, "to_click_command", None)
    if callable(to_click):
        res = to_click()
        if isinstance(res, click.Command):
            return res
    # Last-resort: construct a click.Command from the *callback* attribute
    callback = getattr(cmd, "callback", None)
    if callback is not None and callable(callback):
        name = getattr(cmd, "name", callback.__name__)
        return click.Command(name=name, callback=callback)
    raise TypeError("Expected click.Command or CommandInfo with .command attr")


def _command_docs(cmd: object, parent_ctx: click.Context | None = None) -> str:
    # Ensure we deal with a click.Command regardless of Typer version
    click_cmd = _unwrap_click(cmd)
    ctx = click.Context(click_cmd, info_name=click_cmd.name, parent=parent_ctx)
    help_txt = click_cmd.get_help(ctx)
    # fence with triple backticks for markdown code block readability
    return f"```\n{help_txt}\n```\n"


def _walk_app(app: typer.Typer, parent: List[str] | None = None) -> List[tuple[str, click.Command]]:
    """Return list of (full_command, click.Command) including sub-commands."""

    parent = parent or []
    cmds: List[tuple[str, click.Command]] = []

    # Typer <=0.7 stored commands in a dict; >=0.8 switched to a list.
    registered = app.registered_commands  # type: ignore[attr-defined]
    if isinstance(registered, dict):
        items = registered.items()
    else:
        # list[click.Command] – obtain name from the command itself
        items = ((cmd.name, cmd) for cmd in registered)  # type: ignore[arg-type]

    for name, cmd in items:
        if not name:  # skip unnamed commands to avoid errors
            continue
        full = " ".join(parent + [name])
        cmds.append((full, cmd))
        # Derive underlying Typer app if this is a CommandInfo wrapper
        if hasattr(cmd, "to_click_command") and hasattr(cmd, "callback"):
            # CommandInfo – it wraps a Typer callback but not a sub-app
            underlying_cmd = getattr(cmd, "callback", cmd)
        else:
            underlying_cmd = getattr(cmd, "command", cmd)
        if isinstance(underlying_cmd, typer.Typer) and getattr(underlying_cmd, "registered_commands", None):
            cmds.extend(_walk_app(underlying_cmd, parent + [name]))
    return cmds


def generate_docs(app: typer.Typer) -> str:
    """Return markdown reference docs for all commands in *app*."""

    lines: List[str] = ["# Command Line Reference", ""]
    lines.append("This section is auto-generated from the Typer application.")
    lines.append("")

    for full_cmd, cmd in _walk_app(app):
        lines.append(f"## `{full_cmd}`")
        lines.append("")
        lines.append(_command_docs(cmd))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_docs_file(app: typer.Typer, path: Path) -> None:
    """Generate docs and write to *path*. Creates parent dirs if needed."""

    md = generate_docs(app)
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")