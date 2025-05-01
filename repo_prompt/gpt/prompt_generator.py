"""Module for generating prompts based on code context."""
import os
from pathlib import Path
from typing import Dict, Optional

from openai import OpenAI

from repo_prompt.core.codemap import CodeMap
from repo_prompt.core.parser import Parser


class PromptGenerator:
    """A class that generates prompts based on code context using GPT models."""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.cache_dir = Path.home() / ".repo_prompt" / "cache"
        self._load_cached_map()

    def _load_cached_map(self):
        """Load the cached CodeMap if available."""
        try:
            cache_file = self.cache_dir / "codemap.json"
            if cache_file.exists():
                import json
                with open(cache_file) as f:
                    self.codemap = json.load(f)
            else:
                self.codemap = {}
        except Exception:
            self.codemap = {}

    def generate(self, context: str) -> str:
        """Generate a prompt based on the given context and code structure."""
        try:
            # Prepare the system message with code context
            system_msg = self._prepare_system_message()

            # Generate the prompt using GPT
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": context}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"Failed to generate prompt: {str(e)}")

    def _prepare_system_message(self) -> str:
        """Prepare the system message with code context."""
        msg = (
            "You are an AI coding assistant that helps developers write better code. "
            "You have access to the following code context:\n\n"
        )

        if self.codemap:
            msg += "Project Structure:\n"
            for file_path, info in self.codemap.items():
                msg += f"\n- {file_path}\n"
                if info.get("docstring"):
                    msg += f"  Docstring: {info['docstring']}\n"
                if info.get("classes"):
                    msg += "  Classes:\n"
                    for cls in info["classes"]:
                        msg += f"    - {cls['name']}\n"
                if info.get("functions"):
                    msg += "  Functions:\n"
                    for func in info["functions"]:
                        msg += f"    - {func['name']}\n"

        msg += (
            "\nBased on this context, I will help you generate appropriate "
            "code, documentation, or other development artifacts. Please provide "
            "your request or question."
        )

        return msg