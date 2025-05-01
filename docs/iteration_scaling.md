# Iteration & Scaling Guide

This document complements the **Theory-to-Code Execution Layer** by detailing *step 1.8* – **Iteration and Scaling**.

---

## 🎯 Goals

1. **Iteration** – experiment quickly with different LLM providers, model sizes and *CodeMap* filters without changing application code.
2. **Scaling** – integrate Repo-Prompt workflows into CI pipelines via Cursor **MCP** (Model-Context-Protocol) for team-wide adoption.


## 1️⃣ Rapid Iteration

| Feature | How to use |
|---------|------------|
| **Provider switch** | `python -m src prompt --provider ollama`, or set `LLM_PROVIDER=ollama` |
| **Model override**  | `--model llama3:8b` or any value understood by the provider |
| **Include filter**  | `--include-regex "^src/.*\.py$"` to restrict the prompt to Python source files |
| **Exclude filter**  | `--exclude-regex "(\.venv|build)"` |

### Implementation details

* `src/model_interface.py` exposes a `chat()` façade that dispatches to **OpenAI** or **Ollama** back-ends.
* `src/codemaps.py` now supports `include_pattern` and `exclude_pattern` so you can focus the prompt context.
* The CLI (`src/__main__.py`) wires these flags together for an end-to-end interactive loop.


## 2️⃣ Scaling via MCP

Cursor's **MCP** runner discovers JSON descriptors in `.cursor/mcp.json`. The repository already ships a minimal agent at `tools/mcp_aik_agent.py`.

### CI integration steps

1. **Install dependencies** in your CI job:
   ```bash
   pip install -r requirements.txt
   ```
2. **Set secrets** using your CI provider's encrypted variables (e.g. `OPENAI_API_KEY`).
3. **Invoke MCP** (Pseudo-step – orchestrated by Cursor):
   ```yaml
   - name: Cursor MCP
     uses: …
   ```
4. **Verify readiness** using the existing command:
   ```bash
   python -m src setup --json
   ```
5. **Generate prompt & get diff suggestions** as part of your review workflow:
   ```bash
   python -m src prompt --include-regex "^src/" > suggestions.xml
   ```

### Benchmark placeholders

| Stage | Baseline time | Optimised |
|-------|---------------|-----------|
| *CodeMap build*  | TBD | TBD |
| *LLM response*   | TBD | TBD |

*(Populate metrics after the first runs and track via your CI dashboard.)*

---

## ⚙️ Configuration reference

Environment variable | Description | Default
---|---|---
`LLM_PROVIDER` | `openai` or `ollama` | `openai`
`OPENAI_API_KEY` | Secret for OpenAI backend | –
`OLLAMA_HOST` | Host + port for local Ollama | `http://localhost:11434`


## 📌 Next steps

* Extend provider matrix (Anthropic, Mistral, …).
* Cache XML prompts to reduce compute during incremental builds.
* Collect performance telemetry via `metrics` sub-command. 