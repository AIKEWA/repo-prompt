"""Module for handling interactive chat sessions."""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from openai import OpenAI

from repo_prompt.core.codemap import CodeMap
from repo_prompt.core.parser import Parser


class Chat:
    """A class that manages interactive chat sessions with GPT models."""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.cache_dir = Path.home() / ".repo_prompt" / "cache"
        self.history: List[Dict[str, str]] = []
        self._load_cached_map()
        self._init_chat()

    def _load_cached_map(self):
        """Load the cached CodeMap if available."""
        try:
            cache_file = self.cache_dir / "codemap.json"
            if cache_file.exists():
                with open(cache_file) as f:
                    self.codemap = json.load(f)
            else:
                self.codemap = {}
        except Exception:
            self.codemap = {}

    def _init_chat(self):
        """Initialize the chat session with system context."""
        system_msg = self._prepare_system_message()
        self.history.append({"role": "system", "content": system_msg})

    def send(self, message: str) -> str:
        """Send a message to the chat and get the response."""
        try:
            # Add user message to history
            self.history.append({"role": "user", "content": message})

            # Get response from GPT
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=self.history,
                temperature=0.7,
                max_tokens=2000
            )

            # Add assistant response to history
            assistant_msg = response.choices[0].message.content
            self.history.append({"role": "assistant", "content": assistant_msg})

            return assistant_msg
        except Exception as e:
            raise Exception(f"Failed to get chat response: {str(e)}")

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
            "\nI am here to help you with coding tasks, answer questions, and provide "
            "guidance based on the codebase context. Feel free to ask anything!"
        )

        return msg

    def clear_history(self):
        """Clear the chat history but keep the system message."""
        system_msg = next(msg for msg in self.history if msg["role"] == "system")
        self.history = [system_msg]