"""Smoke tests for skill-openapi-bridge v0.2.0."""

from typer.testing import CliRunner
from skill_openapi_bridge.cli import app
from skill_openapi_bridge import __version__

runner = CliRunner()


def test_version_output():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_serve_missing_spec_exits_nonzero():
    """serve with a non-existent spec file must exit non-zero."""
    result = runner.invoke(app, ["serve", "no-such-spec.json"])
    assert result.exit_code != 0


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "version" in result.output
