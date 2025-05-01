from __future__ import annotations

"""Dependency vulnerability scanner (🔐 Security Scanner Integration).

This module fulfils the *Security Scanner Integration* option from the
recommendation list by adding a **zero-config** CVE checker that queries
`https://osv.dev` for each requirement in *requirements.txt*.

Design goals
------------
* **No external binary** – uses public HTTP API, so it works everywhere.
* **Low-noise** – only reports confirmed vulnerabilities (severity ≥ "MEDIUM").
* **Composable** – returns structured data that can be embedded into CI logs or
  further processed by other modules.

Usage examples
--------------
Library call::

    from pathlib import Path
    from src.security_scanner import scan_requirements
    vulns = scan_requirements(Path("requirements.txt"))
    for v in vulns:
        print(v["package"], v["id"], v["summary"])

CLI call::

    $ python -m src.security_scanner --file requirements.txt --json

The CLI exits with code 1 when **at least one** vulnerability of MEDIUM or
higher severity is found – handy for gating CI pipelines.
"""

from pathlib import Path
import re
import json
import sys
from typing import List, Dict, Any, Tuple

import requests

from .logger import get_logger, setup_logging

_log = get_logger(__name__)

_OSV_API = "https://api.osv.dev/v1/query"
_SEVERITY_PRIORITY = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


# ---------------------------------------------------------------------------
# Core functionality
# ---------------------------------------------------------------------------

def _parse_requirements(req_text: str) -> List[Tuple[str, str | None]]:
    """Return list of *(package, version_or_none)* from a requirements string."""

    entries: List[Tuple[str, str | None]] = []
    pattern = re.compile(r"^\s*([^#\s>=<!~]+)\s*(?:[=<>!~]+\s*([\w\.\-]+))?", re.I)
    for line in req_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = pattern.match(line)
        if m:
            entries.append((m.group(1), m.group(2)))
    return entries


def _query_osv(package: str, version: str | None) -> List[Dict[str, Any]]:
    """Query OSV.dev and return list of vulnerability dicts."""

    payload: Dict[str, Any] = {"package": {"name": package, "ecosystem": "PyPI"}}
    if version:
        payload["version"] = version

    try:
        resp = requests.post(_OSV_API, json=payload, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        _log.error("OSV query failed for %s: %s", package, exc)
        return []

    data = resp.json()
    return data.get("vulns", [])


def scan_requirements(path: Path | str = Path("requirements.txt")) -> List[Dict[str, Any]]:
    """Scan *path* and return list of found vulnerabilities.

    Each list item has keys: ``package``, ``affected_version``, ``id``,
    ``severity`` (highest level found), ``summary``.
    """

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    req_text = path.read_text()
    packages = _parse_requirements(req_text)

    vulns: List[Dict[str, Any]] = []

    for pkg, ver in packages:
        findings = _query_osv(pkg, ver)
        for item in findings:
            severities = [sv["type"] for sv in item.get("severity", [])]
            highest = max(severities, key=lambda s: _SEVERITY_PRIORITY.get(s, -1), default="UNKNOWN")
            # Skip informational / LOW
            if _SEVERITY_PRIORITY.get(highest, 0) < _SEVERITY_PRIORITY["MEDIUM"]:
                continue

            vuln_entry = {
                "package": pkg,
                "affected_version": ver,
                "id": item.get("id"),
                "severity": highest,
                "summary": item.get("summary", ""),
                "references": item.get("references", []),
            }
            vulns.append(vuln_entry)

    return vulns


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scan Python requirements for known CVEs using OSV.dev API")
    parser.add_argument("--file", type=Path, default=Path("requirements.txt"), help="Path to requirements.txt")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human text")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    setup_logging("DEBUG" if args.verbose else "INFO")

    try:
        vulnerabilities = scan_requirements(args.file)
    except Exception as exc:
        _log.error("Scan failed: %s", exc)
        sys.exit(2)

    if args.json:
        json.dump(vulnerabilities, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        if vulnerabilities:
            print("\n🔐 Vulnerabilities detected:\n")
            for v in vulnerabilities:
                print(f"• {v['package']} {v['affected_version']} – {v['severity']} – {v['id']}")
                print(f"  {v['summary']}")
        else:
            print("✅ No known vulnerabilities of medium severity or higher found.")

    # Exit code 1 if issues found
    sys.exit(1 if vulnerabilities else 0) 