"""CLI interface for repo-prompt."""
import os
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel

from repo_prompt.core.codemap import CodeMap
from repo_prompt.core.parser import Parser
from repo_prompt.gpt.chat import Chat
from repo_prompt.gpt.prompt_generator import PromptGenerator

app = typer.Typer(
    name="repo-prompt",
    help="An advanced developer productivity tool for LLM-based prompt generation",
    add_completion=False,
)

console = Console()

@app.command()
def init(
    path: str = typer.Argument(
        ".",
        help="Path to initialize repo-prompt in",
    ),
):
    """Initialize repo-prompt in the current directory."""
    try:
        # Create .env if it doesn't exist
        env_path = Path(path) / ".env"
        if not env_path.exists():
            env_path.write_text(
                "OPENAI_API_KEY=sk-your-key-here\n"
                "REPOPROMPT_CACHE_DIR=~/.repo_prompt/cache\n"
            )
            print("[green]Created .env file[/green]")

        # Create cache directory
        cache_dir = Path.home() / ".repo_prompt" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        print("[green]Initialized repo-prompt cache directory[/green]")

        print(Panel.fit(
            "[bold green]repo-prompt initialized successfully![/bold green]\n"
            "Next steps:\n"
            "1. Add your OpenAI API key to .env\n"
            "2. Run [cyan]repo-prompt extract codemap[/cyan] to analyze your codebase\n"
            "3. Try [cyan]repo-prompt generate prompt[/cyan] or [cyan]repo-prompt chat[/cyan]"
        ))
    except Exception as e:
        print(f"[red]Error initializing repo-prompt: {str(e)}[/red]")
        raise typer.Exit(1)

@app.command()
def extract(
    path: str = typer.Argument(
        ".",
        help="Path to extract codemap from",
    ),
):
    """Extract a CodeMap from the current directory."""
    try:
        parser = Parser(path)
        codemap = CodeMap(parser)
        codemap.extract()
        print("[green]Successfully extracted CodeMap[/green]")
    except Exception as e:
        print(f"[red]Error extracting CodeMap: {str(e)}[/red]")
        raise typer.Exit(1)

@app.command()
def generate(
    context: str = typer.Argument(
        ...,
        help="Context or description for prompt generation",
    ),
):
    """Generate a prompt based on the current codebase context."""
    try:
        generator = PromptGenerator()
        prompt = generator.generate(context)
        print(Panel(prompt, title="Generated Prompt"))
    except Exception as e:
        print(f"[red]Error generating prompt: {str(e)}[/red]")
        raise typer.Exit(1)

@app.command()
def chat(
    message: str = typer.Argument(
        None,
        help="Initial message to start the chat with",
    ),
):
    """Start an interactive chat session."""
    try:
        chat = Chat()
        if message:
            response = chat.send(message)
            print(Panel(response, title="Assistant"))

        while True:
            message = typer.prompt("You")
            if message.lower() in ("exit", "quit", "q"):
                break
            response = chat.send(message)
            print(Panel(response, title="Assistant"))
    except Exception as e:
        print(f"[red]Error in chat: {str(e)}[/red]")
        raise typer.Exit(1)

@app.command()
def apply(
    diff_file: str = typer.Argument(
        ...,
        help="Path to the diff file to apply",
    ),
):
    """Apply a diff to the codebase."""
    try:
        # TODO: Implement diff application logic
        print("[yellow]Diff application not yet implemented[/yellow]")
    except Exception as e:
        print(f"[red]Error applying diff: {str(e)}[/red]")
        raise typer.Exit(1)

@app.command()
def audit(
    path: str = typer.Argument(
        ".",
        help="Path to audit",
    ),
):
    """Run an ethical audit on the codebase."""
    try:
        # TODO: Implement ethical audit logic
        print("[yellow]Ethical audit not yet implemented[/yellow]")
    except Exception as e:
        print(f"[red]Error running audit: {str(e)}[/red]")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()