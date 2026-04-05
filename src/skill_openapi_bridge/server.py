# -*- coding: utf-8 -*-
"""
skill-openapi-bridge server.

Reads a <skillname>-openapi-spec.json and serves all approved routes
following Progressive Disclosure (agentskills.io).
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any
from urllib.parse import unquote


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _etag(content: str) -> str:
    return f'"sha256:{_sha256(content)}"'


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


SWAGGER_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>Swagger UI - skill-openapi-bridge</title>
  <meta charset="utf-8"/>
  <link rel="stylesheet"
    href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui.min.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui-bundle.min.js">
</script>
<script>
  SwaggerUIBundle({{
    url: "{openapi_url}",
    dom_id: "#swagger-ui",
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
    layout: "BaseLayout"
  }});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Spec loader
# ---------------------------------------------------------------------------

def load_spec(spec_path: str | Path) -> dict[str, Any]:
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec not found: {path}")
    with path.open(encoding="utf-8") as f:
        spec = json.load(f)
    if spec.get("openapi") != "3.1.0":
        raise ValueError(f"Expected openapi: 3.1.0, got: {spec.get('openapi')}")
    return spec


def _extract_skills(spec: dict) -> list[dict]:
    """Extract all skill entries from the spec info block."""
    info = spec["info"]
    skill_name = info["x-skill-name"]
    meta = {}
    for key in ("name", "description", "license", "version"):
        x_key = f"x-skill-{key}" if key != "name" else "x-skill-name"
        # try frontmatter via /meta path example
        meta_path = f"/{skill_name}/meta"
        if meta_path in spec["paths"]:
            example = (
                spec["paths"][meta_path]["get"]["responses"]["200"]
                ["content"]["application/json"]["example"]
            )
            meta = example
            break

    if not meta:
        meta = {
            "name": info.get("x-skill-name", ""),
            "description": info.get("description", ""),
            "license": info.get("x-skill-license", ""),
            "version": info.get("x-skill-version", ""),
        }

    return [{
        "name": skill_name,
        "meta": meta,
        "pin": {
            "repo": info.get("x-skill-source-repo", ""),
            "commit": info.get("x-skill-source-commit", ""),
            "path": info.get("x-skill-source-path", ""),
            "generated_at": info.get("x-skill-generated-at", ""),
        },
    }]


def _extract_files(spec: dict, skill_name: str) -> dict[str, dict]:
    """
    Extract all file paths and their content from spec paths.
    Returns map of relative path -> {content, content_type, sha256}
    """
    files: dict[str, dict] = {}
    prefix = f"/{skill_name}/"

    for path, path_item in spec["paths"].items():
        # only file paths: start with /<skill>/, no trailing slash,
        # not special routes
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if not rel:
            continue
        if rel.endswith("/"):
            continue
        special = {"to-prompt", "to-conventions", "validate", "meta", "pin"}
        if rel in special or rel.startswith("schema/"):
            continue

        resp = path_item.get("get", {}).get("responses", {}).get("200", {})
        content_block = resp.get("content", {})
        if not content_block:
            continue
        content_type = list(content_block.keys())[0]
        example = content_block[content_type].get("example", "")
        if not isinstance(example, str):
            continue

        files[rel] = {
            "content": example,
            "content_type": content_type,
            "sha256": _sha256(example),
        }

    return files


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class SkillHandler(BaseHTTPRequestHandler):

    # injected by SkillServer
    spec: dict
    base_url: str
    skills: list[dict]
    files_by_skill: dict[str, dict[str, dict]]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # suppress default access log

    # -----------------------------------------------------------------------
    # Routing
    # -----------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(self.path.split("?")[0])

        # --- root HATEOAS ---
        if path == "/":
            return self._root_hateoas()

        # --- root special routes ---
        if path == "/list":
            return self._root_list()
        if path == "/to-prompt":
            return self._root_to_prompt()
        if path == "/to-conventions":
            return self._root_to_conventions()
        if path == "/validate":
            return self._root_validate()
        if path == "/meta":
            return self._root_meta()
        if path == "/pin":
            return self._root_pin()
        if path == "/schema/openapi.json":
            return self._schema_openapi()
        if path == "/schema/swagger":
            return self._schema_swagger(f"{self.base_url}/schema/openapi.json")

        # --- /find/<partial> ---
        m = re.match(r"^/find/([^/]+)$", path)
        if m:
            return self._find(m.group(1))

        # --- per-skill routes ---
        for skill in self.skills:
            skill_name = skill["name"]
            prefix = f"/{skill_name}"

            if path == f"{prefix}/":
                return self._skill_root(skill_name)
            if path == f"{prefix}/SKILL.md":
                return self._skill_file(skill_name, "SKILL.md")
            if path == f"{prefix}/to-prompt":
                return self._skill_to_prompt(skill_name)
            if path == f"{prefix}/to-conventions":
                return self._skill_to_conventions(skill_name)
            if path == f"{prefix}/validate":
                return self._skill_validate(skill_name)
            if path == f"{prefix}/meta":
                return self._skill_meta(skill_name)
            if path == f"{prefix}/pin":
                return self._skill_pin(skill_name)
            if path == f"{prefix}/schema/openapi.json":
                return self._skill_schema_openapi(skill_name)
            if path == f"{prefix}/schema/swagger":
                return self._schema_swagger(
                    f"{self.base_url}/{skill_name}/schema/openapi.json"
                )

            # directory listings
            for subdir in ("references", "scripts", "assets"):
                if path == f"{prefix}/{subdir}/":
                    return self._skill_listing(skill_name, subdir)
                if path.startswith(f"{prefix}/{subdir}/"):
                    rel = path[len(f"/{skill_name}/"):]
                    return self._skill_file(skill_name, rel)

        self._not_found()

    # -----------------------------------------------------------------------
    # Response helpers
    # -----------------------------------------------------------------------

    def _send(
        self,
        body: str | bytes,
        content_type: str,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: Any, status: int = 200) -> None:
        self._send(
            json.dumps(data, indent=2),
            "application/json; charset=utf-8",
            status=status,
        )

    def _not_found(self) -> None:
        self._send_json({"error": "not found"}, status=404)

    def _file_headers(self, content: str, skill_name: str) -> dict[str, str]:
        commit = self._skill_commit(skill_name)
        sha = _sha256(content)
        return {
            "ETag": f'"sha256:{sha}"',
            "Cache-Control": "immutable, max-age=31536000",
            "X-Skill-Name": skill_name,
            "X-Skill-Commit": commit,
            "X-Content-SHA256": sha,
        }

    def _skill_commit(self, skill_name: str) -> str:
        for s in self.skills:
            if s["name"] == skill_name:
                return s["pin"]["commit"]
        return ""

    def _skill_description(self, skill_name: str) -> str:
        for s in self.skills:
            if s["name"] == skill_name:
                return s["meta"].get("description", "")
        return ""

    # -----------------------------------------------------------------------
    # Root routes
    # -----------------------------------------------------------------------

    def _root_hateoas(self) -> None:
        result = []
        for s in self.skills:
            name = s["name"]
            base = self.base_url
            result.append({
                "name": name,
                "description": s["meta"].get("description", ""),
                "href": f"{base}/{name}/",
                "skill_md": f"{base}/{name}/SKILL.md",
                "to_prompt": f"{base}/{name}/to-prompt",
                "validate": f"{base}/{name}/validate",
            })
        self._send_json(result)

    def _root_list(self) -> None:
        items = "".join(
            f"<li><a href='{self.base_url}/{s['name']}/'>{s['name']}</a>"
            f" — {s['meta'].get('description','')}</li>"
            for s in self.skills
        )
        html = (
            "<!DOCTYPE html><html><head><title>Skills</title></head>"
            f"<body><h1>Available Skills</h1><ul>{items}</ul></body></html>"
        )
        self._send(html, "text/html; charset=utf-8")

    def _root_to_prompt(self) -> None:
        lines = ["<available_skills>"]
        for s in self.skills:
            name = s["name"]
            desc = s["meta"].get("description", "").strip()
            loc = f"{self.base_url}/{name}/SKILL.md"
            lines += [
                "  <skill>",
                f"    <n>{name}</n>",
                f"    <description>{desc}</description>",
                f"    <location>{loc}</location>",
                "  </skill>",
            ]
        lines.append("</available_skills>")
        self._send("\n".join(lines), "application/xml; charset=utf-8")

    def _root_to_conventions(self) -> None:
        lines = ["## Available Agent Skills", "",
                 "Read the SKILL.md at each location before attempting tasks.", ""]
        for s in self.skills:
            name = s["name"]
            desc = s["meta"].get("description", "").strip()
            loc = f"{self.base_url}/{name}/SKILL.md"
            lines += [f"### {name}", desc, f"Location: {loc}", ""]
        self._send("\n".join(lines), "text/markdown; charset=utf-8")

    def _root_validate(self) -> None:
        results = [self._validate_skill(s["name"]) for s in self.skills]
        self._send_json({"validated_at": _now_iso(), "results": results})

    def _root_meta(self) -> None:
        self._send_json({s["name"]: s["meta"] for s in self.skills})

    def _root_pin(self) -> None:
        self._send_json({s["name"]: s["pin"] for s in self.skills})

    def _schema_openapi(self) -> None:
        self._send(
            json.dumps(self.spec, indent=2),
            "application/json; charset=utf-8",
        )

    def _schema_swagger(self, openapi_url: str) -> None:
        self._send(
            SWAGGER_HTML.format(openapi_url=openapi_url),
            "text/html; charset=utf-8",
        )

    def _find(self, partial: str) -> None:
        partial_lower = partial.lower()
        for s in self.skills:
            if partial_lower in s["name"].lower():
                loc = f"{self.base_url}/{s['name']}/SKILL.md"
                self.send_response(302)
                self.send_header("Location", loc)
                self.end_headers()
                return
        self._not_found()

    # -----------------------------------------------------------------------
    # Per-skill routes
    # -----------------------------------------------------------------------

    def _skill_root(self, skill_name: str) -> None:
        files = self.files_by_skill.get(skill_name, {})
        entries = []
        base = f"{self.base_url}/{skill_name}"

        # SKILL.md always first
        if "SKILL.md" in files:
            entries.append({
                "name": "SKILL.md",
                "href": f"{base}/SKILL.md",
                "sha256": files["SKILL.md"]["sha256"],
            })

        # subdirectory entries
        subdirs: set[str] = set()
        for rel in files:
            if "/" in rel:
                subdirs.add(rel.split("/")[0])
        for subdir in sorted(subdirs):
            entries.append({
                "name": f"{subdir}/",
                "href": f"{base}/{subdir}/",
            })

        self._send_json(entries)

    def _skill_file(self, skill_name: str, rel: str) -> None:
        files = self.files_by_skill.get(skill_name, {})
        if rel not in files:
            return self._not_found()
        f = files[rel]
        self._send(
            f["content"],
            f"{f['content_type']}; charset=utf-8",
            extra_headers=self._file_headers(f["content"], skill_name),
        )

    def _skill_listing(self, skill_name: str, subdir: str) -> None:
        files = self.files_by_skill.get(skill_name, {})
        prefix = f"{subdir}/"
        base = f"{self.base_url}/{skill_name}"
        entries = [
            {
                "name": rel[len(prefix):],
                "href": f"{base}/{rel}",
                "sha256": info["sha256"],
            }
            for rel, info in files.items()
            if rel.startswith(prefix)
        ]
        self._send_json(entries)

    def _skill_to_prompt(self, skill_name: str) -> None:
        files = self.files_by_skill.get(skill_name, {})
        desc = self._skill_description(skill_name).strip()
        loc = f"{self.base_url}/{skill_name}/SKILL.md"
        xml = (
            "<available_skills>\n"
            "  <skill>\n"
            f"    <n>{skill_name}</n>\n"
            f"    <description>{desc}</description>\n"
            f"    <location>{loc}</location>\n"
            "  </skill>\n"
            "</available_skills>"
        )
        self._send(xml, "application/xml; charset=utf-8")

    def _skill_to_conventions(self, skill_name: str) -> None:
        desc = self._skill_description(skill_name).strip()
        loc = f"{self.base_url}/{skill_name}/SKILL.md"
        md = (
            "## Available Agent Skills\n\n"
            f"### {skill_name}\n"
            f"{desc}\n"
            f"Location: {loc}\n"
        )
        self._send(md, "text/markdown; charset=utf-8")

    def _validate_skill(self, skill_name: str) -> dict:
        files = self.files_by_skill.get(skill_name, {})
        errors: list[dict] = []
        warnings: list[dict] = []

        if "SKILL.md" not in files:
            errors.append({
                "field": "SKILL.md",
                "rule": "required",
                "message": "SKILL.md is missing",
            })
        else:
            content = files["SKILL.md"]["content"]
            if not content.startswith("---"):
                errors.append({
                    "field": "SKILL.md",
                    "rule": "frontmatter",
                    "message": "SKILL.md has no YAML frontmatter",
                })
            if skill_name not in content:
                warnings.append({
                    "field": "SKILL.md",
                    "rule": "name-in-body",
                    "message": "skill name not found in SKILL.md content",
                })
            line_count = content.count("\n")
            if line_count > 450:
                warnings.append({
                    "field": "SKILL.md",
                    "rule": "body-length",
                    "message": f"SKILL.md is {line_count} lines — approaching 500 line limit",
                })

        return {
            "valid": len(errors) == 0,
            "skill": skill_name,
            "checked_at": _now_iso(),
            "errors": errors,
            "warnings": warnings,
        }

    def _skill_validate(self, skill_name: str) -> None:
        self._send_json(self._validate_skill(skill_name))

    def _skill_meta(self, skill_name: str) -> None:
        for s in self.skills:
            if s["name"] == skill_name:
                return self._send_json(s["meta"])
        self._not_found()

    def _skill_pin(self, skill_name: str) -> None:
        for s in self.skills:
            if s["name"] == skill_name:
                return self._send_json(s["pin"])
        self._not_found()

    def _skill_schema_openapi(self, skill_name: str) -> None:
        """Return a spec scoped to this skill only."""
        info = dict(self.spec["info"])
        skill_paths = {
            k: v for k, v in self.spec["paths"].items()
            if k == "/" or k.startswith(f"/{skill_name}/")
            or k in ("/list", "/to-prompt", "/to-conventions",
                     "/validate", "/meta", "/pin",
                     "/find/{partial_name}",
                     "/schema/openapi.json", "/schema/swagger")
        }
        scoped = {
            "openapi": "3.1.0",
            "info": info,
            "paths": skill_paths,
        }
        self._send(json.dumps(scoped, indent=2), "application/json; charset=utf-8")


# ---------------------------------------------------------------------------
# Threaded server
# ---------------------------------------------------------------------------

class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _make_handler_class(
    spec: dict,
    base_url: str,
    skills: list[dict],
    files_by_skill: dict[str, dict[str, dict]],
) -> type:
    """Return a SkillHandler subclass with spec data injected as class attrs."""

    class _Handler(SkillHandler):
        pass

    _Handler.spec = spec
    _Handler.base_url = base_url
    _Handler.skills = skills
    _Handler.files_by_skill = files_by_skill
    return _Handler


def build_server(
    spec_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[_ThreadedHTTPServer, str]:
    """
    Build and return a (server, base_url) pair.
    If port=0, a free port is chosen automatically.
    """
    spec = load_spec(spec_path)

    if port == 0:
        port = _find_free_port()

    base_url = f"http://{host}:{port}"
    skills = _extract_skills(spec)
    files_by_skill = {
        s["name"]: _extract_files(spec, s["name"])
        for s in skills
    }

    handler_class = _make_handler_class(spec, base_url, skills, files_by_skill)
    server = _ThreadedHTTPServer((host, port), handler_class)
    return server, base_url


def serve(
    spec_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 0,
) -> None:
    """Start server and block until interrupted."""
    server, base_url = build_server(spec_path, host, port)
    actual_port = server.server_address[1]
    print(f"skill-openapi-bridge serving on {base_url}")
    print(f"READY on :{actual_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
