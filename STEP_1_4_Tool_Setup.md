# Step 1.4 — Tool & Methodology Setup

> **Purpose**   Translate the *"Tool and Methodology Setup"* theory block into a reproducible, automated checklist that verifies whether a developer workstation or CI runner is ready for the Repo-Prompt workflow.

---

## ✅ What is verified?

| # | Requirement | Description |
|:-:|-------------|-------------|
| 1 | **Operating system** | macOS 12 (Monterey) or newer |
| 2 | **Git** | `git` CLI available on `$PATH` |
| 3 | **Repository hygiene** | Project checked-into Git **and** has a `.gitignore` file |
| 4 | **LLM availability** | Either a local *Ollama* binary **or** environment variable `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` present |
| 5 | **Repo-Prompt tool** | `repo-prompt` CLI on `$PATH` *or* `repo_prompt` Python module importable |

All checks are implemented in `src/tool_setup.py` and can be executed **locally** or inside **CI**.

---

## 🖥️ Local usage

```bash
# Human-readable output
python -m src.tool_setup --repo-path .

# JSON report (e.g. for further processing)
python -m src.tool_setup --repo-path . --json > setup_report.json
```

### Example JSON report

```json
{
  "results": [
    {"name": "macOS version", "ok": true, "details": "macOS 14.4"},
    {"name": "git", "ok": true, "details": "/usr/bin/git"},
    {"name": ".gitignore", "ok": true, "details": ".gitignore present"},
    {"name": "Ollama LLM", "ok": true, "details": "`ollama` binary detected – local inference available"},
    {"name": "repo-prompt CLI", "ok": true, "details": "Executable on PATH"}
  ],
  "all_ok": true
}
```

---

## 🚀 CI/CD integration

Add the following workflow file to automatically gate pull-requests if the environment is incomplete.

<details>
<summary><code>.github/workflows/environment-check.yml</code></summary>

```yaml
name: Environment readiness (🛠 Step 1.4)

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  verify-setup:
    runs-on: macos-12  # guarantees access to macOS runners

    steps:
      - name: 📥 Checkout repo
        uses: actions/checkout@v4

      - name: 🐍 Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 📦 Install dependencies
        run: pip install -r requirements.txt

      - name: 🔍 Run Step 1.4 checks
        run: |
          python -m src.tool_setup --json --repo-path . > report.json

      - name: ⬆️ Upload report (artifact)
        uses: actions/upload-artifact@v4
        with:
          name: step-1_4-report
          path: report.json

      - name: ⚖️ Fail if environment incomplete
        run: |
          python - <<'PY'
          import json, sys, pathlib
          report = json.loads(pathlib.Path('report.json').read_text())
          if not report['all_ok']:
              print('❌ Environment incomplete. Details:')
              for r in report['results']:
                  if not r['ok']:
                      print(f" - {r['name']}: {r['details']}")
              sys.exit(1)
          print('✅ Environment ready')
          PY
```
</details>

> 📝 **Tip:** The workflow exits with *non-zero* status if any check fails, preventing merges until the requirements are satisfied.

---

## 🔧 Extending the checklist

* To support **Linux** or **Windows** runners, extend `_check_os()` in `src/tool_setup.py`.
* Add additional checks (e.g. `docker`, `kubectl`) by creating new helper functions and listing them in `verify_system()`.
* Keep the Markdown and CI workflow in-sync whenever checks evolve.

---

## 📚 Related files

* `src/tool_setup.py` – implementation of the verifier
* `src/__main__.py` – exposes the `setup` Typer sub-command (`python -m src setup …`)
* `.github/workflows/environment-check.yml` – optional CI gating (see above) 