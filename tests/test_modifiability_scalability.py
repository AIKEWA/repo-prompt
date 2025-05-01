from typer.testing import CliRunner

import pytest

from src.modifiability_scalability import app, ALLOWED_ROLES


runner = CliRunner()


@pytest.mark.parametrize("role", ALLOWED_ROLES)
def test_dashboard_valid_roles(role):
    result = runner.invoke(app, ["dashboard", "--role", role, "--json"])
    assert result.exit_code == 0, f"CLI failed for valid role '{role}': {result.stderr}"
    assert "generated_at" in result.stdout


def test_dashboard_invalid_role():
    result = runner.invoke(app, ["dashboard", "--role", "hacker", "--json"])
    assert result.exit_code != 0
    assert "Role must be one of" in result.stderr