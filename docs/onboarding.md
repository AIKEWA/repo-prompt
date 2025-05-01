# New Hire On-boarding – AI Coding Toolkit

Welcome to the team! 🎉 This quick-start guide will get you productive with
our AI-assisted workflow in no time.

1. **Clone the repository** and create a virtual environment:
   ```bash
   git clone <repo-url>
   cd <repo>
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Verify your system**:
   ```bash
   python -m src setup --verbose
   ```

3. **Import IDE settings**:
   * VS Code – open the workspace; the \`.vscode\` folder is pre-configured.
   * Xcode – drag `Scripts/repo_prompt_build_phase.sh` into Build Phases.

4. **Run your first prompt**:
   ```bash
   python -m src prompt . --model gpt-4o
   ```

5. **Next steps**:
   * Browse `docs/` for guidelines and iteration scaling tips.
   * Join the `#ai-coding-support` Slack channel for questions.
