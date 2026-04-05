# -*- coding: utf-8 -*-
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
    port: int = typer.Option(0, "--port", "-p", help="Port (0 = auto-select free port)"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
) -> None:
    """Serve a skill OpenAPI spec as a local HTTP server.

    Exposes all approved routes following Progressive Disclosure:

    \b
      GET /                        -> HATEOAS root
      GET /<skill>/SKILL.md        -> SKILL.md content
      GET /<skill>/references/     -> reference file listing
      GET /to-prompt               -> <available_skills> XML
      GET /validate                -> validation results
      ...and more (GET /list for full route list)
    """
    from skill_openapi_bridge.server import serve as _serve
    _serve(spec_path=spec, host=host, port=port)


if __name__ == "__main__":
    app()
