# -*- coding: utf-8 -*-
"""
skill-openapi-bridge generate.

Fetches a skill from GitHub at a pinned commit and produces
a valid <skillname>-openapi-spec.json following the approved format.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _etag(content: str) -> str:
    return f'"sha256:{_sha256(content)}"'


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_to_owner_repo(repo_url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL."""
    # https://github.com/owner/repo  ->  owner/repo
    m = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo_url.rstrip("/"))
    if not m:
        raise ValueError(f"Cannot parse GitHub repo URL: {repo_url}")
    return m.group(1)


def _content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".md": "text/markdown",
        ".sh": "text/x-shellscript",
        ".py": "text/x-python",
        ".txt": "text/plain",
        ".json": "application/json",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
    }
    return mapping.get(ext, "text/plain")


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from SKILL.md content."""
    import yaml  # optional dep — fallback to manual parse if unavailable

    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    raw = content[3:end]
    try:
        result = yaml.safe_load(raw) or {}
    except Exception:
        return {}

    # normalise version to string
    if "version" in result and result["version"] is not None:
        result["version"] = str(result["version"])

    return result


# ---------------------------------------------------------------------------
# detect_file_references
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(
    r"(?<![:/])"            # not preceded by : or / (avoids URLs)
    r"`?"                   # optional backtick
    r"((?:references|scripts|assets)/[^\s`'\">)\]]+)"
    r"`?",                  # optional closing backtick
)


def detect_file_references(content: str) -> list[str]:
    """
    Scan SKILL.md body (after frontmatter) for file references.
    Returns deduplicated list of relative paths like references/foo.md.
    """
    # strip frontmatter
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            body = content[end + 3:]

    seen: list[str] = []
    for m in _REF_PATTERN.finditer(body):
        ref = m.group(1).strip("`").rstrip(".,;)")
        if ref not in seen:
            seen.append(ref)
    return seen


# ---------------------------------------------------------------------------
# fetch_file
# ---------------------------------------------------------------------------

def fetch_file(
    repo_url: str,
    commit: str,
    skill_path: str,
    rel_path: str,
) -> str:
    """
    Fetch a file from GitHub at a pinned commit via raw URL.
    Returns decoded UTF-8 string content.
    Raises FileNotFoundError on 404.
    """
    owner_repo = _repo_to_owner_repo(repo_url)
    url = (
        f"https://raw.githubusercontent.com/{owner_repo}"
        f"/{commit}/{skill_path}/{rel_path}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise FileNotFoundError(
            f"404: {rel_path} not found in {repo_url} at {commit[:10]}"
        ) from e


# ---------------------------------------------------------------------------
# resolve_commit
# ---------------------------------------------------------------------------

def resolve_commit(repo_url: str, branch: str) -> str:
    """
    Resolve a branch name to a full commit SHA via GitHub API.
    Raises RuntimeError if the branch cannot be resolved.
    """
    owner_repo = _repo_to_owner_repo(repo_url)
    api_url = f"https://api.github.com/repos/{owner_repo}/commits/{branch}"
    req = urllib.request.Request(
        api_url,
        headers={"Accept": "application/vnd.github.v3+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["sha"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Cannot resolve branch '{branch}' in {repo_url}: {e.code} {e.msg}"
        ) from e


# ---------------------------------------------------------------------------
# build_spec
# ---------------------------------------------------------------------------

def _skill_name_from_path(skill_path: str) -> str:
    return skill_path.rstrip("/").split("/")[-1]


def _file_path_entry(
    skill_name: str,
    rel: str,
    content: str,
    commit: str,
) -> dict:
    """Build a single OpenAPI path entry for a file."""
    ct = _content_type(rel)
    sha = _sha256(content)
    return {
        "get": {
            "summary": f"{rel} content",
            "responses": {
                "200": {
                    "description": f"{rel} content",
                    "headers": {
                        "ETag": {
                            "schema": {
                                "type": "string",
                                "example": f'"sha256:{sha}"',
                            }
                        },
                        "Cache-Control": {
                            "schema": {
                                "type": "string",
                                "example": "immutable, max-age=31536000",
                            }
                        },
                        "X-Skill-Name": {
                            "schema": {
                                "type": "string",
                                "example": skill_name,
                            }
                        },
                        "X-Skill-Commit": {
                            "schema": {
                                "type": "string",
                                "example": commit,
                            }
                        },
                        "X-Content-SHA256": {
                            "schema": {
                                "type": "string",
                                "example": sha,
                            }
                        },
                    },
                    "content": {
                        ct: {
                            "example": content
                        }
                    },
                }
            },
        }
    }


def _listing_entry(
    skill_name: str,
    subdir: str,
    files: dict[str, str],
    base_url_placeholder: str = "http://localhost:8080",
) -> dict:
    """Build OpenAPI path entry for a directory listing."""
    prefix = f"{subdir}/"
    base = f"{base_url_placeholder}/{skill_name}"
    entries = [
        {
            "name": rel[len(prefix):],
            "href": f"{base}/{rel}",
            "sha256": _sha256(content),
        }
        for rel, content in files.items()
        if rel.startswith(prefix)
    ]
    return {
        "get": {
            "summary": f"List {subdir} files",
            "responses": {
                "200": {
                    "description": f"JSON list of {subdir} filenames",
                    "content": {
                        "application/json": {
                            "example": entries
                        }
                    },
                }
            },
        }
    }


def build_spec(
    repo_url: str,
    commit: str,
    skill_path: str,
    files: dict[str, str],
) -> dict:
    """
    Build a valid OpenAPI 3.1.0 spec dict from fetched skill files.

    files: map of relative path -> string content
           e.g. {"SKILL.md": "...", "references/foo.md": "..."}
    """
    skill_name = _skill_name_from_path(skill_path)
    frontmatter = parse_frontmatter(files.get("SKILL.md", ""))

    skill_version = frontmatter.get("version") or "0.0.0"
    info_version = f"{skill_version}+{commit[:10]}"
    description = str(frontmatter.get("description") or "").strip()
    license_ = str(frontmatter.get("license") or "")
    generated_at = _now_iso()

    # --- info block ---
    info: dict[str, Any] = {
        "title": skill_name,
        "description": f"Agent skill: {skill_name}",
        "version": info_version,
        "x-skill-name": skill_name,
        "x-skill-version": skill_version,
        "x-skill-license": license_,
        "x-skill-source-repo": repo_url,
        "x-skill-source-commit": commit,
        "x-skill-source-path": skill_path,
        "x-skill-generated-at": generated_at,
    }

    # --- identify subdirectories present ---
    subdirs: set[str] = set()
    for rel in files:
        if rel == "SKILL.md":
            continue
        parts = rel.split("/")
        if len(parts) >= 2:
            subdirs.add(parts[0])

    base = "http://localhost:8080"
    sn = skill_name

    paths: dict[str, Any] = {}

    # root HATEOAS
    paths["/"] = {
        "get": {
            "summary": "HATEOAS root — list of available skills",
            "responses": {
                "200": {
                    "description": "Skill index",
                    "content": {
                        "application/json": {
                            "example": [
                                {
                                    "name": sn,
                                    "description": description,
                                    "href": f"{base}/{sn}/",
                                    "skill_md": f"{base}/{sn}/SKILL.md",
                                    "to_prompt": f"{base}/{sn}/to-prompt",
                                    "validate": f"{base}/{sn}/validate",
                                }
                            ]
                        }
                    },
                }
            },
        }
    }

    # root special routes
    paths["/list"] = {"get": {"summary": "Human-readable skill list",
        "responses": {"200": {"description": "HTML skill list",
            "content": {"text/html": {"example": f"<ul><li>{sn}</li></ul>"}}}}}}

    paths["/to-prompt"] = {"get": {"summary": "available_skills XML for all skills",
        "responses": {"200": {"description": "XML block",
            "content": {"application/xml": {"example":
                f"<available_skills>\n  <skill>\n    <n>{sn}</n>\n"
                f"    <description>{description}</description>\n"
                f"    <location>{base}/{sn}/SKILL.md</location>\n"
                f"  </skill>\n</available_skills>"}}}}}}

    paths["/to-conventions"] = {"get": {"summary": "Markdown conventions block",
        "responses": {"200": {"description": "Markdown block",
            "content": {"text/markdown": {"example":
                f"## Available Agent Skills\n\n### {sn}\n{description}\n"
                f"Location: {base}/{sn}/SKILL.md\n"}}}}}}

    paths["/validate"] = {"get": {"summary": "Validate all skills",
        "responses": {"200": {"description": "Validation results",
            "content": {"application/json": {"example": {
                "validated_at": generated_at,
                "results": [{"valid": True, "skill": sn, "errors": [], "warnings": []}],
            }}}}}}}

    paths["/meta"] = {"get": {"summary": "Frontmatter for all skills",
        "responses": {"200": {"description": "Metadata map",
            "content": {"application/json": {"example": {
                sn: {k: v for k, v in frontmatter.items()
                     if k in ("name", "description", "version", "license")}
            }}}}}}}

    paths["/pin"] = {"get": {"summary": "Source pin for all skills",
        "responses": {"200": {"description": "Pin map",
            "content": {"application/json": {"example": {
                sn: {
                    "repo": repo_url,
                    "commit": commit,
                    "path": skill_path,
                    "generated_at": generated_at,
                }
            }}}}}}}

    paths["/find/{partial_name}"] = {"get": {
        "summary": "Fuzzy redirect to best matching SKILL.md",
        "parameters": [{"name": "partial_name", "in": "path", "required": True,
                        "schema": {"type": "string"}, "example": sn[:12]}],
        "responses": {
            "302": {"description": "Redirect",
                    "headers": {"Location": {"schema": {"type": "string"},
                                             "example": f"{base}/{sn}/SKILL.md"}}},
            "404": {"description": "No match"},
        },
    }}

    paths["/schema/openapi.json"] = {"get": {"summary": "OpenAPI spec",
        "responses": {"200": {"description": "OpenAPI 3.1.0 JSON",
            "content": {"application/json": {"example": {}}}}}}}

    paths["/schema/swagger"] = {"get": {"summary": "Swagger UI",
        "responses": {"200": {"description": "Swagger UI HTML",
            "content": {"text/html": {"example": "<html>Swagger UI</html>"}}}}}}

    # per-skill root listing
    top_entries: list[dict] = []
    if "SKILL.md" in files:
        top_entries.append({
            "name": "SKILL.md",
            "href": f"{base}/{sn}/SKILL.md",
            "sha256": _sha256(files["SKILL.md"]),
        })
    for sd in sorted(subdirs):
        top_entries.append({"name": f"{sd}/", "href": f"{base}/{sn}/{sd}/"})

    paths[f"/{sn}/"] = {"get": {"summary": f"Top-level entries for {sn}",
        "responses": {"200": {"description": "Entry list",
            "content": {"application/json": {"example": top_entries}}}}}}

    # SKILL.md file path
    if "SKILL.md" in files:
        paths[f"/{sn}/SKILL.md"] = _file_path_entry(sn, "SKILL.md", files["SKILL.md"], commit)

    # subdirectory listings + file paths
    for sd in ("references", "scripts", "assets"):
        sd_files = {r: c for r, c in files.items() if r.startswith(f"{sd}/")}
        if sd in subdirs or sd_files:
            paths[f"/{sn}/{sd}/"] = _listing_entry(sn, sd, files)
            for rel, content in sd_files.items():
                paths[f"/{sn}/{rel}"] = _file_path_entry(sn, rel, content, commit)

    # per-skill special routes
    paths[f"/{sn}/to-prompt"] = {"get": {"summary": f"XML for {sn}",
        "responses": {"200": {"description": "XML",
            "content": {"application/xml": {"example":
                f"<available_skills>\n  <skill>\n    <n>{sn}</n>\n"
                f"    <description>{description}</description>\n"
                f"    <location>{base}/{sn}/SKILL.md</location>\n"
                f"  </skill>\n</available_skills>"}}}}}}

    paths[f"/{sn}/to-conventions"] = {"get": {"summary": f"Conventions for {sn}",
        "responses": {"200": {"description": "Markdown",
            "content": {"text/markdown": {"example":
                f"## Available Agent Skills\n\n### {sn}\n{description}\n"
                f"Location: {base}/{sn}/SKILL.md\n"}}}}}}

    paths[f"/{sn}/validate"] = {"get": {"summary": f"Validate {sn}",
        "responses": {"200": {"description": "Validation result",
            "content": {"application/json": {"example": {
                "valid": True, "skill": sn,
                "checked_at": generated_at,
                "errors": [], "warnings": [],
            }}}}}}}

    paths[f"/{sn}/meta"] = {"get": {"summary": f"Frontmatter for {sn}",
        "responses": {"200": {"description": "JSON frontmatter",
            "content": {"application/json": {"example": {
                k: v for k, v in frontmatter.items()
                if k in ("name", "description", "version", "license")
            }}}}}}}

    paths[f"/{sn}/pin"] = {"get": {"summary": f"Pin for {sn}",
        "responses": {"200": {"description": "Pin info",
            "content": {"application/json": {"example": {
                "repo": repo_url,
                "commit": commit,
                "path": skill_path,
                "generated_at": generated_at,
            }}}}}}}

    paths[f"/{sn}/schema/openapi.json"] = {"get": {
        "summary": f"OpenAPI spec for {sn}",
        "responses": {"200": {"description": "OpenAPI 3.1.0 JSON",
            "content": {"application/json": {"example": {}}}}}}}

    paths[f"/{sn}/schema/swagger"] = {"get": {
        "summary": f"Swagger UI for {sn}",
        "responses": {"200": {"description": "Swagger UI HTML",
            "content": {"text/html": {"example": "<html>Swagger UI</html>"}}}}}}

    return {
        "openapi": "3.1.0",
        "info": info,
        "paths": paths,
    }


# ---------------------------------------------------------------------------
# generate entry point
# ---------------------------------------------------------------------------

def generate(
    repo_url: str,
    skill_path: str,
    commit: str | None = None,
    branch: str | None = None,
    output: str | Path | None = None,
) -> Path:
    """
    Fetch skill from GitHub and write <skillname>-openapi-spec.json.
    Returns the output Path.
    """
    if not commit and not branch:
        raise ValueError("Either --commit or --branch must be provided")

    if not commit:
        print(f"Resolving branch '{branch}'...")
        commit = resolve_commit(repo_url, branch)
        print(f"Resolved to commit {commit[:10]}")

    skill_name = _skill_name_from_path(skill_path)

    # fetch SKILL.md
    print(f"Fetching SKILL.md...")
    skill_md_content = fetch_file(repo_url, commit, skill_path, "SKILL.md")

    # detect referenced files from SKILL.md body
    refs = detect_file_references(skill_md_content)
    print(f"Detected {len(refs)} file reference(s): {refs}")

    # fetch all referenced files — hard error if missing
    files: dict[str, str] = {"SKILL.md": skill_md_content}
    for ref in refs:
        print(f"Fetching {ref}...")
        files[ref] = fetch_file(repo_url, commit, skill_path, ref)

    # build spec
    spec = build_spec(repo_url, commit, skill_path, files)

    # derive output path
    if output is None:
        output = Path(f"{skill_name}-openapi-spec.json")
    output = Path(output)

    output.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Written: {output}")
    return output
