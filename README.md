# skill-openapi-bridge

Bridge between [agentskills.io](https://agentskills.io) skills and a local OpenAPI server.

[![CI](https://github.com/roebi/skill-openapi-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/roebi/skill-openapi-bridge/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/skill-openapi-bridge)](https://pypi.org/project/skill-openapi-bridge/)
[![Python](https://img.shields.io/pypi/pyversions/skill-openapi-bridge)](https://pypi.org/project/skill-openapi-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Concept

An [agentskills.io](https://agentskills.io/specification) skill can contain rich supporting files beyond `SKILL.md`:

```
<skill-name>/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
└── assets/           # Optional: templates, resources
```

Claude.ai's skill integration currently only reads `SKILL.md`. All optional subdirectories are invisible to the agent.

`skill-openapi-bridge` solves this with two commands:

- **`generate`** — fetches a skill from GitHub at a pinned commit and produces a `<skillname>-openapi-spec.json` embedding all referenced file content as a valid OpenAPI 3.1.0 spec
- **`serve`** — reads that spec and starts a local HTTP server inside the agent's container session, exposing all skill content via 25 REST routes following [Progressive Disclosure](https://agentskills.io/client-implementation/adding-skills-support#the-core-principle-progressive-disclosure)

No external servers. No tunnels. Everything runs on `localhost` inside the container.

---

## Install

```bash
pip install skill-openapi-bridge
# or with uv:
uv add skill-openapi-bridge
```

Shell tab completion (free via Typer):

```bash
skill-openapi-bridge --install-completion
```

---

## Usage

### generate — GitHub repo → openapi-spec.json

Pin to a specific commit (recommended):

```bash
skill-openapi-bridge generate \
  --repo https://github.com/roebi/agent-skills \
  --commit abc123def456abc123def456abc123def456ab12 \
  --skill skills/brainstorming-topic-dialog-creative-mentor-en
```

Auto-resolve from branch:

```bash
skill-openapi-bridge generate \
  --repo https://github.com/roebi/agent-skills \
  --branch main \
  --skill skills/brainstorming-topic-dialog-creative-mentor-en
```

Outputs: `brainstorming-topic-dialog-creative-mentor-en-openapi-spec.json`

Custom output path:

```bash
skill-openapi-bridge generate \
  --repo https://github.com/roebi/agent-skills \
  --branch main \
  --skill skills/brainstorming-topic-dialog-creative-mentor-en \
  --output ./specs/brainstorming-en.json
```

### serve — openapi-spec.json → local HTTP server

```bash
skill-openapi-bridge serve brainstorming-topic-dialog-creative-mentor-en-openapi-spec.json
# skill-openapi-bridge serving on http://127.0.0.1:52357
# READY on :52357
```

Custom port and host:

```bash
skill-openapi-bridge serve spec.json --port 8080 --host 0.0.0.0
```

### In an agent session

The agent installs the package and starts the server:

```bash
pip install skill-openapi-bridge
skill-openapi-bridge serve brainstorming-topic-dialog-creative-mentor-en-openapi-spec.json &
sleep 1
curl http://localhost:52357/
```

---

## Routes (25 total)

### Fileserver routes

```
GET /                                        HATEOAS root — skill list with full URLs
GET /<skill>/                                Top-level entries
GET /<skill>/SKILL.md                        SKILL.md content
GET /<skill>/references/                     Reference file listing
GET /<skill>/references/<ref>                Reference file content
GET /<skill>/scripts/                        Script file listing
GET /<skill>/scripts/<file>                  Script file content
GET /<skill>/assets/                         Asset file listing
GET /<skill>/assets/<file>                   Asset file content
```

### Special routes — root

```
GET /list                                    Human-readable skill list (HTML)
GET /to-prompt                               <available_skills> XML for all skills
GET /to-conventions                          Markdown conventions block for all skills
GET /validate                                JSON validation results for all skills
GET /meta                                    JSON frontmatter for all skills
GET /pin                                     JSON {commit, repo, path} for all skills
GET /find/<partial>                          302 redirect to best matching SKILL.md
GET /schema/openapi.json                     OpenAPI 3.1.0 spec (all routes)
GET /schema/swagger                          Swagger UI
```

### Special routes — per skill

```
GET /<skill>/to-prompt                       <available_skills> XML for this skill
GET /<skill>/to-conventions                  Markdown conventions block for this skill
GET /<skill>/validate                        JSON validation result for this skill
GET /<skill>/meta                            JSON frontmatter for this skill
GET /<skill>/pin                             JSON {commit, repo, path} for this skill
GET /<skill>/schema/openapi.json             OpenAPI 3.1.0 spec scoped to this skill
GET /<skill>/schema/swagger                  Swagger UI scoped to this skill
```

### Response headers on all file routes

```
Content-Type:      text/markdown; charset=utf-8
ETag:              "sha256:<hex>"
Cache-Control:     immutable, max-age=31536000
X-Skill-Name:      <skill-name>
X-Skill-Commit:    <full-commit-sha>
X-Content-SHA256:  <hex>
```

Content is pinned to a commit — `Cache-Control: immutable` is correct and permanent.

---

## Architecture

```
GitHub repo (pinned commit)
        |
        | skill-openapi-bridge generate
        v
<skillname>-openapi-spec.json   (valid OpenAPI 3.1.0, all file content embedded)
        |
        | skill-openapi-bridge serve
        v
localhost:<port>                (pure stdlib HTTP server, in-container)
        |
        | curl / fetch — Progressive Disclosure
        v
Agent
  GET /                         Discovery  — skill list + URLs
  GET /<skill>/SKILL.md         Activation — full skill instructions
  GET /<skill>/references/x     Loading    — reference files on demand
```

---

## Related

- [agentskills.io specification](https://agentskills.io/specification)
- [roebi/agent-skills](https://github.com/roebi/agent-skills) — skill repository
- [aider-skills](https://pypi.org/project/aider-skills/) — agentskills.io integration for aider

## License

MIT
