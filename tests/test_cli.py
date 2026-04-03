"""Smoke tests for skill-openapi-bridge v0.1.0."""

from typer.testing import CliRunner
from skill_openapi_bridge.cli import app
from skill_openapi_bridge import __version__

runner = CliRunner()


def test_version_output():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_serve_not_yet_implemented():
    result = runner.invoke(app, ["serve", "fake-spec.json"])
    assert result.exit_code == 1
    assert "not yet implemented" in result.output


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "version" in result.output
