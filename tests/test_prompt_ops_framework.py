from __future__ import annotations

import pytest
from src.prompt_ops_framework import PromptTemplate, validate_template


@pytest.fixture(scope="module")
def valid_template() -> PromptTemplate:
    """Return a minimal *valid* prompt template instance."""

    return PromptTemplate(
        name="bug_fix",
        description="Fix a bug in the provided file",
        roles=[{"role": "user", "content": "Fix the bug in {{file}}"}],
    )


# ---------------------------------------------------------------------------
# Positive path – should *not* raise
# ---------------------------------------------------------------------------

def test_validate_accepts_valid_template(valid_template: PromptTemplate) -> None:
    """`validate_template` should *not* raise for correct input."""

    # Acts as an assertion – pytest will fail when an exception is raised.
    validate_template(valid_template)


@pytest.mark.parametrize(
    "fmt",
    ["json", "yaml"],
)
def test_serialisation_roundtrip(valid_template: PromptTemplate, fmt: str, tmp_path):
    """Serialise ➜ deserialize should preserve *name* & *roles*."""

    # Write to temporary file in the chosen format
    fname = valid_template.filename(fmt=fmt)
    fpath = tmp_path / fname
    data = valid_template.to_json() if fmt == "json" else valid_template.to_yaml()
    fpath.write_text(data, encoding="utf-8")

    from src.prompt_ops_framework import load_template  # late import avoids cycles

    loaded = load_template(fpath)
    assert loaded.name == valid_template.name
    assert loaded.roles == list(valid_template.roles)


# ---------------------------------------------------------------------------
# Negative path – should *raise*
# ---------------------------------------------------------------------------


def test_validate_rejects_missing_roles():
    """Templates without *roles* are invalid."""

    with pytest.raises(ValueError):
        validate_template(
            PromptTemplate(name="invalid", description="", roles=[]),
        )


def test_validate_rejects_unknown_role(valid_template: PromptTemplate):
    """Unknown role identifiers must raise *ValueError*."""

    bad = PromptTemplate(
        name="bad_role",
        description="",
        roles=[{"role": "moderator", "content": "Hi"}],
    )
    with pytest.raises(ValueError):
        validate_template(bad)


def test_validate_detects_secrets(valid_template: PromptTemplate):
    """Basic secret pattern must be detected."""

    secret_msg = [{"role": "user", "content": "sk-THIS_IS_A_FAKE_KEY"}]
    tmpl = PromptTemplate(name="leaky", description="", roles=secret_msg)

    with pytest.raises(ValueError):
        validate_template(tmpl)