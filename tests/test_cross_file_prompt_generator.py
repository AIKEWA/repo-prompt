from pathlib import Path

from src.cross_file_prompt_generator import build_repo_prompt, _DEFAULT_ROLES


def test_prompt_contains_roles(tmp_path: Path):
    # Prepare tiny repo with one file
    sample_code = """def foo():\n    return 42\n"""
    file_path = tmp_path / "sample.py"
    file_path.write_text(sample_code)

    # Build prompt
    query = "return value"
    prompt = build_repo_prompt(query, repo_root=tmp_path, k=3)

    # All default role names should appear in the prompt
    for role in [r.role for r in _DEFAULT_ROLES]:
        assert f"## Role: {role}" in prompt

    # The code snippet should be embedded
    assert "def foo():" in prompt