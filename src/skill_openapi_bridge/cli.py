"""skill-openapi-bridge CLI."""

import typer
from skill_openapi_bridge import __version__

app = typer.Typer(
    name="skill-openapi-bridge",
    help="Bridge between agentskills.io SKILL.md packages and a local OpenAPI server.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the current version."""
    typer.echo(f"skill-openapi-bridge v{__version__}")


@app.command()
def serve(
    spec: str = typer.Argument(..., help="Path to <skillname>-openapi-spec.json"),
    port: int = typer.Option(0, "--port", "-p", help="Port to listen on (0 = auto-select free port)"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
) -> None:
    """Serve a skill OpenAPI spec as a local HTTP server.

    The server exposes the skill content following Progressive Disclosure:

    \b
      GET /          -> Discovery  (SKILL.md content)
      GET /scripts/  -> Loading    (script files)
      GET /references/ -> Loading  (reference files)
    """
    typer.echo(f"skill-openapi-bridge v{__version__}")
    typer.echo(f"spec: {spec}")
    typer.echo(f"host: {host}  port: {port}")
    typer.echo("")
    typer.echo("serve command is not yet implemented — coming in v0.2.0")
    typer.echo("See: https://github.com/roebi/skill-openapi-bridge")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
