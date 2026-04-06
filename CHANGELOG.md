# Changelog

## v0.3.0 (2026-04-06)

- Add `generate` command — fetches a skill from GitHub at a pinned commit and produces a valid `<skillname>-openapi-spec.json`
- `generate --repo / --skill / --commit` pins to an exact commit SHA (reproducible, supply-chain safe)
- `generate --branch` auto-resolves branch to commit SHA via GitHub API, then pins
- SKILL.md body is scanned for file references (`references/`, `scripts/`, `assets/`) — only referenced files are fetched and embedded
- Hard error if a referenced file is missing from the repo at the pinned commit
- `build_spec()` produces a valid OpenAPI 3.1.0 JSON with all 25 routes, embedded file content, correct `ETag`/`Cache-Control`/`X-Skill-*` headers, and `info.version` = `<skill-version>+<commit[:10]>`
- `info.version` fallback to `0.0.0+<commit[:10]>` when SKILL.md has no `version` field
- Fix: disabled Typer/Rich ANSI color output (`rich_markup_mode=None`) — all CLI output is plain text, agent-friendly, no escape codes
- Pure stdlib implementation for HTTP and GitHub fetching — only new runtime dependency is `pyyaml>=6.0.0`
- 219 tests passing (48 spec contract + 106 HTTP server + 62 generate + 3 CLI smoke)

## v0.2.0 (2026-04-05)

- Implement `serve` command — serves all 25 approved routes from a `<skillname>-openapi-spec.json`
- Fileserver routes: `GET /`, `GET /<skill>/`, `GET /<skill>/SKILL.md`, references, scripts, assets
- Special root routes: `/list`, `/to-prompt`, `/to-conventions`, `/validate`, `/meta`, `/pin`, `/find/<partial>`, `/schema/openapi.json`, `/schema/swagger`
- Per-skill special routes: `/<skill>/to-prompt`, `/<skill>/to-conventions`, `/<skill>/validate`, `/<skill>/meta`, `/<skill>/pin`, `/<skill>/schema/*`
- HATEOAS root `GET /` with full URLs per skill entry
- `Cache-Control: immutable` + `ETag: "sha256:..."` + `X-Skill-*` response headers on all file routes
- `/find/<partial>` fuzzy matching with `302` redirect, `404` on no match
- Swagger UI served via CDN at `/schema/swagger` and `/<skill>/schema/swagger`
- Pure stdlib implementation — zero new runtime dependencies
- 154 tests passing (48 spec contract + 106 HTTP server tests)

## v0.1.0 (2026-04-03)

- Initial release — CLI scaffold with `version` and `serve` (stub) commands
- `serve` command not yet implemented — reserved for v0.2.0
- Establishes PyPI name and package structure
