from src.offline_awareness import safe_chat, interactive_diff_review

from pathlib import Path
import os


def test_safe_chat_local(monkeypatch):
    """When FORCE_LOCAL_LLM=1 provider must be 'ollama' and no consent needed."""

    # Ensure env variable forces local
    monkeypatch.setenv("FORCE_LOCAL_LLM", "1")
    # Disable interactive prompts
    monkeypatch.setenv("ASSUME_YES", "1")

    # Monkeypatch underlying _chat to capture provider argument
    captured = {}

    def _fake_chat(messages, provider=None, model=None, **kwargs):  # noqa: D401 – test helper
        captured["provider"] = provider
        return "ok"

    monkeypatch.setattr("src.offline_awareness._chat", _fake_chat)

    resp = safe_chat([{"role": "user", "content": "hi"}])
    assert resp == "ok"
    assert captured["provider"] == "ollama"


def test_interactive_diff_review_auto_apply(monkeypatch, tmp_path):
    """interactive_diff_review should apply patch when consent auto-yes."""

    monkeypatch.setenv("ASSUME_YES", "1")

    # Create simple diff – add a file
    diff_text = """--- /dev/null\n+++ b/hello.txt\n@@\n+hello\n"""
    diff_file = tmp_path / "change.diff"
    diff_file.write_text(diff_text)

    # Run review with apply=true
    modified = interactive_diff_review(diff_file, repo_root=tmp_path, apply=True)

    assert "hello.txt" in modified
    assert (tmp_path / "hello.txt").read_text() == "hello\n"