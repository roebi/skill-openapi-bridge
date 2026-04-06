# -*- coding: utf-8 -*-
"""
Tests for v0.3.0 generate command.

These tests define the generate behaviour as law.
They must FAIL before implementation and PASS after.

Run:  pytest tests/test_generate.py -v
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skill_openapi_bridge.generate import (
    build_spec,
    detect_file_references,
    fetch_file,
    parse_frontmatter,
    resolve_commit,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SKILL_NAME = "brainstorming-topic-dialog-creative-mentor-en"
REPO = "https://github.com/roebi/agent-skills"
COMMIT = "abc123def456abc123def456abc123def456ab12"
SKILL_PATH = f"skills/{SKILL_NAME}"

SKILL_MD = textwrap.dedent("""\
    ---
    name: brainstorming-topic-dialog-creative-mentor-en
    version: 1.0.0
    description: >
      Creative brainstorming mentor for structured topic exploration.
      Use when the user wants to brainstorm, explore ideas, or needs
      a structured creative dialog around a topic.
    license: CC BY-NC-SA 4.0
    metadata:
      author: roebi
      spec: https://agentskills.io/specification
    ---

    # Brainstorming Topic Dialog Creative Mentor

    A structured creative brainstorming mentor skill.

    ## When to use this skill

    Use when the user wants to explore a topic creatively.

    ## References

    See `references/mentor-framework.md` for the full framework.
    See `references/examples.md` for worked examples.
    """)

REF_MENTOR = textwrap.dedent("""\
    # Mentor Framework

    ## Core principles

    1. Listen first
    2. Reflect back
    3. Expand and diverge
    """)

REF_EXAMPLES = textwrap.dedent("""\
    # Examples

    ## Example 1: Topic exploration

    User: I want to brainstorm about renewable energy.
    """)

SKILL_MD_WITH_SCRIPTS = textwrap.dedent("""\
    ---
    name: test-skill-with-scripts
    version: 1.0.0
    description: A skill with scripts.
    license: MIT
    ---

    # Test Skill

    Run `scripts/run.sh` to execute.
    See `references/guide.md` for details.
    See `assets/template.md` for the template.
    """)


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:

    def test_extracts_name(self):
        meta = parse_frontmatter(SKILL_MD)
        assert meta["name"] == SKILL_NAME

    def test_extracts_version(self):
        meta = parse_frontmatter(SKILL_MD)
        assert meta["version"] == "1.0.0"

    def test_extracts_description(self):
        meta = parse_frontmatter(SKILL_MD)
        assert "brainstorming" in meta["description"].lower()

    def test_extracts_license(self):
        meta = parse_frontmatter(SKILL_MD)
        assert meta["license"] == "CC BY-NC-SA 4.0"

    def test_extracts_metadata(self):
        meta = parse_frontmatter(SKILL_MD)
        assert meta["metadata"]["author"] == "roebi"

    def test_no_frontmatter_returns_empty(self):
        meta = parse_frontmatter("# Just a heading\n\nNo frontmatter.")
        assert meta == {}

    def test_unclosed_frontmatter_returns_empty(self):
        meta = parse_frontmatter("---\nname: foo\n")
        assert meta == {}

    def test_version_is_string_when_present(self):
        meta = parse_frontmatter(SKILL_MD)
        assert isinstance(meta["version"], str)

    def test_version_missing_returns_none(self):
        content = "---\nname: foo\ndescription: bar\n---\n# body"
        meta = parse_frontmatter(content)
        assert meta.get("version") is None


# ---------------------------------------------------------------------------
# detect_file_references
# ---------------------------------------------------------------------------

class TestDetectFileReferences:

    def test_detects_backtick_references(self):
        refs = detect_file_references(SKILL_MD)
        assert "references/mentor-framework.md" in refs

    def test_detects_multiple_references(self):
        refs = detect_file_references(SKILL_MD)
        assert "references/examples.md" in refs

    def test_detects_scripts(self):
        refs = detect_file_references(SKILL_MD_WITH_SCRIPTS)
        assert "scripts/run.sh" in refs

    def test_detects_assets(self):
        refs = detect_file_references(SKILL_MD_WITH_SCRIPTS)
        assert "assets/template.md" in refs

    def test_detects_references_dir(self):
        refs = detect_file_references(SKILL_MD_WITH_SCRIPTS)
        assert "references/guide.md" in refs

    def test_no_duplicates(self):
        content = textwrap.dedent("""\
            ---
            name: test
            description: test
            ---
            See `references/foo.md` and also references/foo.md.
            """)
        refs = detect_file_references(content)
        assert refs.count("references/foo.md") == 1

    def test_ignores_external_urls(self):
        content = textwrap.dedent("""\
            ---
            name: test
            description: test
            ---
            See https://example.com/references/foo.md for more.
            """)
        refs = detect_file_references(content)
        assert "references/foo.md" not in refs

    def test_returns_list(self):
        refs = detect_file_references(SKILL_MD)
        assert isinstance(refs, list)

    def test_empty_body_returns_empty_list(self):
        refs = detect_file_references("---\nname: x\ndescription: y\n---\n")
        assert refs == []


# ---------------------------------------------------------------------------
# fetch_file
# ---------------------------------------------------------------------------

class TestFetchFile:

    def test_returns_string_content(self):
        with patch("skill_openapi_bridge.generate.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"# content"
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            content = fetch_file(REPO, COMMIT, SKILL_PATH, "SKILL.md")
            assert content == "# content"

    def test_builds_correct_raw_url(self):
        captured = {}
        def fake_urlopen(url, timeout=None):
            captured["url"] = url
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"content"
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("skill_openapi_bridge.generate.urllib.request.urlopen", fake_urlopen):
            fetch_file(REPO, COMMIT, SKILL_PATH, "SKILL.md")

        expected = (
            f"https://raw.githubusercontent.com/roebi/agent-skills"
            f"/{COMMIT}/{SKILL_PATH}/SKILL.md"
        )
        assert captured["url"] == expected

    def test_raises_on_http_error(self):
        import urllib.error
        with patch("skill_openapi_bridge.generate.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.HTTPError(
                url="http://x", code=404, msg="Not Found", hdrs=None, fp=None
            )
            with pytest.raises(FileNotFoundError, match="404"):
                fetch_file(REPO, COMMIT, SKILL_PATH, "references/missing.md")

    def test_decodes_utf8(self):
        with patch("skill_openapi_bridge.generate.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = "# héllo".encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            content = fetch_file(REPO, COMMIT, SKILL_PATH, "SKILL.md")
            assert "héllo" in content


# ---------------------------------------------------------------------------
# resolve_commit
# ---------------------------------------------------------------------------

class TestResolveCommit:

    def test_returns_full_sha(self):
        with patch("skill_openapi_bridge.generate.urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = (
                json.dumps({"sha": COMMIT}).encode()
            )
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            sha = resolve_commit(REPO, "main")
            assert sha == COMMIT

    def test_calls_github_api(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"sha": COMMIT}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("skill_openapi_bridge.generate.urllib.request.urlopen", fake_urlopen):
            resolve_commit(REPO, "main")

        assert "api.github.com" in captured["url"]
        assert "roebi/agent-skills" in captured["url"]
        assert "main" in captured["url"]

    def test_raises_on_failure(self):
        import urllib.error
        with patch("skill_openapi_bridge.generate.urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.HTTPError(
                url="http://x", code=404, msg="Not Found", hdrs=None, fp=None
            )
            with pytest.raises(RuntimeError, match="branch"):
                resolve_commit(REPO, "no-such-branch")


# ---------------------------------------------------------------------------
# build_spec
# ---------------------------------------------------------------------------

class TestBuildSpec:

    @pytest.fixture
    def files(self):
        return {
            "SKILL.md": SKILL_MD,
            "references/mentor-framework.md": REF_MENTOR,
            "references/examples.md": REF_EXAMPLES,
        }

    def test_returns_dict(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert isinstance(spec, dict)

    def test_openapi_version(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert spec["openapi"] == "3.1.0"

    def test_info_title_is_skill_name(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert spec["info"]["title"] == SKILL_NAME

    def test_info_version_format(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        pattern = r"^\d+\.\d+\.\d+\+[a-f0-9]{10}$"
        assert re.match(pattern, spec["info"]["version"])

    def test_info_version_uses_skill_version(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert spec["info"]["version"].startswith("1.0.0+")

    def test_info_version_fallback_when_no_version(self, files):
        files_no_ver = dict(files)
        files_no_ver["SKILL.md"] = textwrap.dedent("""\
            ---
            name: brainstorming-topic-dialog-creative-mentor-en
            description: A skill.
            license: MIT
            ---
            # body
            """)
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files_no_ver)
        assert spec["info"]["version"].startswith("0.0.0+")

    def test_x_skill_source_commit(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert spec["info"]["x-skill-source-commit"] == COMMIT

    def test_x_skill_source_repo(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert spec["info"]["x-skill-source-repo"] == REPO

    def test_x_skill_source_path(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert spec["info"]["x-skill-source-path"] == SKILL_PATH

    def test_x_skill_generated_at_iso8601(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        assert re.match(pattern, spec["info"]["x-skill-generated-at"])

    def test_x_skill_license(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert spec["info"]["x-skill-license"] == "CC BY-NC-SA 4.0"

    def test_skill_md_path_in_spec(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert f"/{SKILL_NAME}/SKILL.md" in spec["paths"]

    def test_skill_md_example_content(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        example = (
            spec["paths"][f"/{SKILL_NAME}/SKILL.md"]
            ["get"]["responses"]["200"]["content"]
            ["text/markdown"]["example"]
        )
        assert example == SKILL_MD

    def test_reference_file_path_in_spec(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert f"/{SKILL_NAME}/references/mentor-framework.md" in spec["paths"]

    def test_reference_listing_path_in_spec(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert f"/{SKILL_NAME}/references/" in spec["paths"]

    def test_reference_listing_example_has_entries(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        example = (
            spec["paths"][f"/{SKILL_NAME}/references/"]
            ["get"]["responses"]["200"]["content"]
            ["application/json"]["example"]
        )
        assert isinstance(example, list)
        names = [e["name"] for e in example]
        assert "mentor-framework.md" in names
        assert "examples.md" in names

    def test_etag_in_skill_md_headers(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        headers = (
            spec["paths"][f"/{SKILL_NAME}/SKILL.md"]
            ["get"]["responses"]["200"]["headers"]
        )
        assert "ETag" in headers

    def test_etag_value_matches_content(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        headers = (
            spec["paths"][f"/{SKILL_NAME}/SKILL.md"]
            ["get"]["responses"]["200"]["headers"]
        )
        expected = f'"sha256:{hashlib.sha256(SKILL_MD.encode()).hexdigest()}"'
        assert headers["ETag"]["schema"]["example"] == expected

    def test_sha256_in_reference_listing(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        example = (
            spec["paths"][f"/{SKILL_NAME}/references/"]
            ["get"]["responses"]["200"]["content"]
            ["application/json"]["example"]
        )
        entry = next(e for e in example if e["name"] == "mentor-framework.md")
        expected = hashlib.sha256(REF_MENTOR.encode()).hexdigest()
        assert entry["sha256"] == expected

    def test_cache_control_immutable_in_headers(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        headers = (
            spec["paths"][f"/{SKILL_NAME}/SKILL.md"]
            ["get"]["responses"]["200"]["headers"]
        )
        assert "Cache-Control" in headers
        assert "immutable" in headers["Cache-Control"]["schema"]["example"]

    def test_root_path_in_spec(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        assert "/" in spec["paths"]

    def test_all_special_root_routes_present(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        for route in [
            "/list", "/to-prompt", "/to-conventions",
            "/validate", "/meta", "/pin",
            "/find/{partial_name}",
            "/schema/openapi.json", "/schema/swagger",
        ]:
            assert route in spec["paths"], f"Missing route: {route}"

    def test_all_per_skill_special_routes_present(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        for route in [
            f"/{SKILL_NAME}/to-prompt",
            f"/{SKILL_NAME}/to-conventions",
            f"/{SKILL_NAME}/validate",
            f"/{SKILL_NAME}/meta",
            f"/{SKILL_NAME}/pin",
            f"/{SKILL_NAME}/schema/openapi.json",
            f"/{SKILL_NAME}/schema/swagger",
        ]:
            assert route in spec["paths"], f"Missing route: {route}"

    def test_spec_is_valid_json_serialisable(self, files):
        spec = build_spec(REPO, COMMIT, SKILL_PATH, files)
        dumped = json.dumps(spec)
        reloaded = json.loads(dumped)
        assert reloaded["openapi"] == "3.1.0"

    def test_scripts_listing_in_spec_when_scripts_present(self):
        files = {
            "SKILL.md": SKILL_MD_WITH_SCRIPTS,
            "scripts/run.sh": "#!/bin/bash\necho hello",
            "references/guide.md": "# Guide",
            "assets/template.md": "# Template",
        }
        spec = build_spec(REPO, COMMIT, "skills/test-skill-with-scripts", files)
        assert "/test-skill-with-scripts/scripts/" in spec["paths"]
        assert "/test-skill-with-scripts/scripts/run.sh" in spec["paths"]

    def test_assets_listing_in_spec_when_assets_present(self):
        files = {
            "SKILL.md": SKILL_MD_WITH_SCRIPTS,
            "scripts/run.sh": "#!/bin/bash\necho hello",
            "references/guide.md": "# Guide",
            "assets/template.md": "# Template",
        }
        spec = build_spec(REPO, COMMIT, "skills/test-skill-with-scripts", files)
        assert "/test-skill-with-scripts/assets/" in spec["paths"]
        assert "/test-skill-with-scripts/assets/template.md" in spec["paths"]


# ---------------------------------------------------------------------------
# CLI integration: generate command
# ---------------------------------------------------------------------------

class TestGenerateCLI:

    def test_generate_command_exists(self):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0

    def test_generate_help_shows_repo_option(self):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["generate", "--help"])
        assert "--repo" in result.output

    def test_generate_help_shows_commit_option(self):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["generate", "--help"])
        assert "--commit" in result.output

    def test_generate_help_shows_skill_option(self):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["generate", "--help"])
        assert "--skill" in result.output

    def test_generate_help_shows_branch_option(self):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["generate", "--help"])
        assert "--branch" in result.output

    def test_generate_help_shows_output_option(self):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["generate", "--help"])
        assert "--output" in result.output

    def test_generate_missing_required_args_exits_nonzero(self):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["generate"])
        assert result.exit_code != 0

    def test_generate_produces_valid_spec_file(self, tmp_path):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app

        def fake_fetch(repo, commit, skill_path, rel_path):
            if rel_path == "SKILL.md":
                return SKILL_MD
            if rel_path == "references/mentor-framework.md":
                return REF_MENTOR
            if rel_path == "references/examples.md":
                return REF_EXAMPLES
            raise FileNotFoundError(f"404: {rel_path}")

        output_file = tmp_path / f"{SKILL_NAME}-openapi-spec.json"

        with patch("skill_openapi_bridge.generate.fetch_file", fake_fetch):
            runner = CliRunner()
            result = runner.invoke(app, [
                "generate",
                "--repo", REPO,
                "--commit", COMMIT,
                "--skill", SKILL_PATH,
                "--output", str(output_file),
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert output_file.exists()
        spec = json.loads(output_file.read_text())
        assert spec["openapi"] == "3.1.0"
        assert spec["info"]["x-skill-name"] == SKILL_NAME

    def test_generate_auto_derives_output_filename(self, tmp_path):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app

        def fake_fetch(repo, commit, skill_path, rel_path):
            if rel_path == "SKILL.md":
                return SKILL_MD
            if rel_path == "references/mentor-framework.md":
                return REF_MENTOR
            if rel_path == "references/examples.md":
                return REF_EXAMPLES
            raise FileNotFoundError(f"404: {rel_path}")

        with patch("skill_openapi_bridge.generate.fetch_file", fake_fetch):
            runner = CliRunner()
            result = runner.invoke(app, [
                "generate",
                "--repo", REPO,
                "--commit", COMMIT,
                "--skill", SKILL_PATH,
            ], catch_exceptions=False)

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        expected = Path(f"{SKILL_NAME}-openapi-spec.json")
        assert expected.exists()
        expected.unlink()

    def test_generate_with_branch_resolves_commit(self, tmp_path):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app

        def fake_fetch(repo, commit, skill_path, rel_path):
            if rel_path == "SKILL.md":
                return SKILL_MD
            if rel_path == "references/mentor-framework.md":
                return REF_MENTOR
            if rel_path == "references/examples.md":
                return REF_EXAMPLES
            raise FileNotFoundError(f"404: {rel_path}")

        output_file = tmp_path / f"{SKILL_NAME}-openapi-spec.json"

        with patch("skill_openapi_bridge.generate.fetch_file", fake_fetch), \
             patch("skill_openapi_bridge.generate.resolve_commit", return_value=COMMIT):
            runner = CliRunner()
            result = runner.invoke(app, [
                "generate",
                "--repo", REPO,
                "--branch", "main",
                "--skill", SKILL_PATH,
                "--output", str(output_file),
            ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        spec = json.loads(output_file.read_text())
        assert spec["info"]["x-skill-source-commit"] == COMMIT

    def test_generate_missing_referenced_file_exits_nonzero(self, tmp_path):
        from typer.testing import CliRunner
        from skill_openapi_bridge.cli import app

        def fake_fetch(repo, commit, skill_path, rel_path):
            if rel_path == "SKILL.md":
                return SKILL_MD
            raise FileNotFoundError(f"404: {rel_path}")

        output_file = tmp_path / f"{SKILL_NAME}-openapi-spec.json"

        with patch("skill_openapi_bridge.generate.fetch_file", fake_fetch):
            runner = CliRunner()
            result = runner.invoke(app, [
                "generate",
                "--repo", REPO,
                "--commit", COMMIT,
                "--skill", SKILL_PATH,
                "--output", str(output_file),
            ])

        assert result.exit_code != 0
