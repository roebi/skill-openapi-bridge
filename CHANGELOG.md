# Changelog

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
