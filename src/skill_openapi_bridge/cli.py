# -*- coding: utf-8 -*-
"""skill-openapi-bridge CLI."""

from __future__ import annotations

from typing import Optional

import typer

from skill_openapi_bridge import __version__

app = typer.Typer(
    name="skill-openapi-bridge",
    help="Bridge between agentskills.io SKILL.md packages and a local OpenAPI server.",
    no_args_is_help=True,
    rich_markup_mode=None,  # plain text output — no ANSI codes, agent-friendly
)


@app.command()
def version() -> None:
    """Print the current version."""
    typer.echo(f"skill-openapi-bridge v{__version__}")


@app.command()
def serve(
    spec: str = typer.Argument(..., help="Path to <skillname>-openapi-spec.json"),
    port: int = typer.Option(0, "--port", "-p", help="Port (0 = auto-select free port)"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
) -> None:
    """Serve a skill OpenAPI spec as a local HTTP server."""
    from skill_openapi_bridge.server import serve as _serve
    _serve(spec_path=spec, host=host, port=port)


@app.command()
def generate(
    repo: str = typer.Option(..., "--repo", help="GitHub repo URL"),
    skill: str = typer.Option(..., "--skill", help="Skill path inside repo"),
    commit: Optional[str] = typer.Option(None, "--commit", help="Full commit SHA to pin to"),
    branch: Optional[str] = typer.Option(None, "--branch", help="Branch to resolve to commit SHA"),
    output: Optional[str] = typer.Option(None, "--output", "-o",
                                          help="Output path (default: <skillname>-openapi-spec.json)"),
) -> None:
    """Generate a <skillname>-openapi-spec.json from a GitHub skill repo.

    \b
    Pin to a specific commit:
      skill-openapi-bridge generate \\
        --repo https://github.com/roebi/agent-skills \\
        --commit abc123def456abc123def456abc123def456ab12 \\
        --skill skills/brainstorming-topic-dialog-creative-mentor-en

    Auto-resolve from branch:
      skill-openapi-bridge generate \\
        --repo https://github.com/roebi/agent-skills \\
        --branch main \\
        --skill skills/brainstorming-topic-dialog-creative-mentor-en
    """
    from skill_openapi_bridge.generate import generate as _generate

    if not commit and not branch:
        typer.echo("Error: provide either --commit or --branch", err=True)
        raise typer.Exit(code=1)

    try:
        out = _generate(
            repo_url=repo,
            skill_path=skill,
            commit=commit,
            branch=branch,
            output=output,
        )
        typer.echo(f"Generated: {out}")
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
