# skill-openapi-bridge

Bridge between [agentskills.io](https://agentskills.io) SKILL.md packages and a local OpenAPI server.

## Concept

An [agentskills.io](https://agentskills.io/specification) skill can contain rich supporting files beyond `SKILL.md`:

```
<skill-name>/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
└── assets/           # Optional: templates, resources
```

`skill-openapi-bridge` takes a `<skillname>-openapi-spec.json` — generated from a pinned commit of a skill repo — and serves it as a local OpenAPI server inside the agent's container session.

This enables **Progressive Disclosure** directly from a PyPI-installed package:

```
GET /              -> Discovery   (SKILL.md content)
GET /scripts/x     -> Loading     (script file)
GET /references/y  -> Loading     (reference file)
```

No external servers. No tunnels. The server runs on `localhost` inside the agent container.

## Install

```bash
pip install skill-openapi-bridge
# or with uv:
uv add skill-openapi-bridge
```

## Usage

```bash
# Show help
skill-openapi-bridge --help

# Show version
skill-openapi-bridge version

# Serve a skill spec (coming in v0.2.0)
skill-openapi-bridge serve brainstorming-topic-dialog-creative-mentor-en-openapi-spec.json
```

Shell tab completion:

```bash
skill-openapi-bridge --install-completion
```

## Status

| Version | Status |
|---------|--------|
| v0.1.0  | Name reserved — CLI scaffold only |
| v0.2.0  | `serve` command implemented via [apiup](https://pypi.org/project/apiup/) |
| v0.3.0  | `generate` command: GitHub repo → openapi-spec.json |

## Architecture

```
<skillname>-openapi-spec  (PyPI)
        |
        | depends on
        v
skill-openapi-bridge  (PyPI)
        |
        | depends on
        v
apiup[validate]  (PyPI)
        |
        | serves on
        v
localhost:<port>  (in-container HTTP)
        |
        | curl / fetch
        v
Agent (Progressive Disclosure)
```

## Related

- [agentskills.io specification](https://agentskills.io/specification)
- [apiup](https://pypi.org/project/apiup/) — Litestar-based OpenAPI mock server
- [roebi/agent-skills](https://github.com/roebi/agent-skills) — skill repository

## License

MIT
