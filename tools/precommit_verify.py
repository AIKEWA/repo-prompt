#!/usr/bin/env python3
"""Pre-commit hook: run Step 1.4 environment verification.

The hook ensures that **any** commit pushed to the repository can only be made
from a workstation (or CI container) that passes the requirements defined in
`src/tool_setup.py`.

It is intentionally lightweight and does **not** accept file arguments – the
verification is repository-level, not file-specific.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import from source tree; assumes hook is executed at repo root
try:
    from src.tool_setup import verify_system
except ModuleNotFoundError as exc:
    sys.stderr.write("Could not import src.tool_setup – did you run the hook from the project root?\n")
    raise SystemExit(1) from exc


REPORT = verify_system(Path.cwd())

if REPORT["all_ok"]:
    sys.exit(0)

sys.stderr.write("\n❌ Environment verification failed:\n")
for res in REPORT["results"]:
    if not res["ok"]:
        sys.stderr.write(f" - {res['name']}: {res['details']}\n")

sys.exit(1) 