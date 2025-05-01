"""MCP agent that exposes basic health information and validates that
required environment variables are loaded securely from the .env file.

This script is intended to be run by Cursor's MCP infrastructure.  It prints a
JSON payload to STDOUT describing the agent and whether the mandatory OPENAI
API key could be loaded successfully.

Run manually:
    $ python3 tools/mcp_aik_agent.py

The agent *never* prints the value of the secret itself – only whether it could
be found.  Additional secrets are loaded for future-proofing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from datetime import datetime
import argparse

# ---------------------------------------------------------------------------
# 1. Load environment variables from a .env file in the project root.
#    Cursor executes the agent from the repository root, but for manual runs we
#    resolve the project root relative to this file to guarantee correct
#    behaviour.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# 2. Read secrets from environment.  They are **never** embedded in the code.
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
NOTION_KEY = os.getenv("NOTION_KEY")

# ---------------------------------------------------------------------------
# 3. Fail fast if the mandatory key is missing – this surfaces mis-configuration
#    early and prevents the agent from running in an unusable state.
# ---------------------------------------------------------------------------
if not OPENAI_API_KEY:
    sys.exit("❌  OPENAI_API_KEY is missing.  Please add it to your .env file.")


def main() -> None:  # noqa: D401
    """Entrypoint executed by Cursor MCP."""

    # ------------------------------------------------------------------
    # Assemble payload – this can be consumed by *multiple* agents.  We
    # deliberately encode *capabilities* so that a coordinator (Option 3)
    # can route tasks dynamically.
    # ------------------------------------------------------------------
    tool_response = {
        "tool_name": "aik-toolkit",
        "version": os.getenv("AIK_TOOLKIT_VERSION", "0.1.0"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "description": "Connects to OpenAI or local LLMs with secure key storage.",
        "openai_key_loaded": bool(OPENAI_API_KEY),
        "capabilities": [
            "chat:openai",
            "chat:ollama",
            "healthcheck",
        ],
    }

    # Optionally pretty-print when invoked manually.
    print(json.dumps(tool_response, indent=2 if _ARGS.pretty else None))


# ---------------------------------------------------------------------------
# CLI handling – allows richer interaction when executed outside MCP runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover – manual execution only
    parser = argparse.ArgumentParser(description="MCP AIK agent")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    _ARGS = parser.parse_args()
    main() 