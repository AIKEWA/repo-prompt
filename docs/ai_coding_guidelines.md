# Command Line Reference

This section is auto-generated from the Typer application.

# AI-assisted Coding – Development Guidelines (Step 1.10)

This document standardises how the *Repo-Prompt* workflow is used within the
team. Add it to your internal wiki or keep it version-controlled in the
repository (\`docs/ai_coding_guidelines.md\`).

## Toolchain Integration
* **VS Code** – recommended extensions and tasks are provided in the
  \`.vscode\` folder. Press `Cmd+Shift+B` (or `Ctrl+Shift+B` on Windows) and
  select *"Repo-Prompt: Generate XML & review diff"*.
* **Xcode** – import the shell script at `Scripts/repo_prompt_build_phase.sh`
  as a *Run Script* build phase to trigger Repo-Prompt on each build.

## Best Practices
1. Commit frequently and use feature branches to keep AI-generated diffs
   small and reviewable.
2. Always run `pytest` after applying an LLM-generated patch.
3. Tag unclear sections with `# REVIEW:` to invite peer input.

## Security & Ethics
* Sanitise any proprietary code snippets before sending them to external
  LLMs.
* Follow the *Security Scanner* output (`python -m src.security_scanner`).

## Continuous Improvement
Log your feedback via `python -m src.feedback submit --message "…"` so the
workflow can be refined iteratively.

