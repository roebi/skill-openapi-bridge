"""
Contract tests for <skillname>-openapi-spec.json format.

These tests define the spec format as law.
They must FAIL before implementation and PASS after.

Run:  pytest tests/test_spec_contract.py -v
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

# Path to the reference spec - hand-crafted ground truth
SPEC_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "brainstorming-topic-dialog-creative-mentor-en-openapi-spec.json"

SKILL_NAME = "brainstorming-topic-dialog-creative-mentor-en"


@pytest.fixture(scope="module")
def spec() -> dict:
    """Load the reference spec fixture."""
    assert SPEC_PATH.exists(), f"Reference spec not found: {SPEC_PATH}"
    with SPEC_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# OpenAPI structure
# ---------------------------------------------------------------------------

class TestOpenAPIStructure:

    def test_openapi_version_present(self, spec):
        assert "openapi" in spec

    def test_openapi_version_is_3_1_0(self, spec):
        assert spec["openapi"] == "3.1.0"

    def test_info_block_present(self, spec):
        assert "info" in spec

    def test_paths_block_present(self, spec):
        assert "paths" in spec

    def test_paths_is_not_empty(self, spec):
        assert len(spec["paths"]) > 0


# ---------------------------------------------------------------------------
# info block
# ---------------------------------------------------------------------------

class TestInfoBlock:

    def test_info_title_is_skill_name(self, spec):
        assert spec["info"]["title"] == SKILL_NAME

    def test_info_description_present(self, spec):
        assert "description" in spec["info"]
        assert len(spec["info"]["description"]) > 0

    def test_info_version_format(self, spec):
        """version must be <semver>+<commit10> or 0.0.0+<commit10>"""
        version = spec["info"]["version"]
        pattern = r"^\d+\.\d+\.\d+\+[a-f0-9]{10}$"
        assert re.match(pattern, version), \
            f"version '{version}' does not match <semver>+<commit10> format"

    def test_x_skill_name(self, spec):
        assert spec["info"]["x-skill-name"] == SKILL_NAME

    def test_x_skill_license_present(self, spec):
        assert "x-skill-license" in spec["info"]

    def test_x_skill_source_repo_present(self, spec):
        assert "x-skill-source-repo" in spec["info"]
        assert spec["info"]["x-skill-source-repo"].startswith("https://")

    def test_x_skill_source_commit_is_full_sha(self, spec):
        commit = spec["info"]["x-skill-source-commit"]
        assert re.match(r"^[a-f0-9]{40}$", commit), \
            f"x-skill-source-commit '{commit}' is not a full 40-char SHA"

    def test_x_skill_source_path_present(self, spec):
        assert "x-skill-source-path" in spec["info"]
        path = spec["info"]["x-skill-source-path"]
        assert SKILL_NAME in path

    def test_x_skill_generated_at_is_iso8601(self, spec):
        generated = spec["info"]["x-skill-generated-at"]
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        assert re.match(pattern, generated), \
            f"x-skill-generated-at '{generated}' is not ISO 8601 UTC"

    def test_x_skill_version_consistent_with_info_version(self, spec):
        """x-skill-version must be the semver part of info.version"""
        info_version = spec["info"]["version"]
        semver_part = info_version.split("+")[0]
        x_skill_version = spec["info"].get("x-skill-version")
        if x_skill_version is not None:
            assert x_skill_version == semver_part

    def test_x_skill_source_commit_consistent_with_info_version(self, spec):
        """commit[:10] must match the local part of info.version"""
        info_version = spec["info"]["version"]
        commit_short = info_version.split("+")[1]
        full_commit = spec["info"]["x-skill-source-commit"]
        assert full_commit.startswith(commit_short), \
            f"info.version commit '{commit_short}' not prefix of x-skill-source-commit '{full_commit}'"


# ---------------------------------------------------------------------------
# paths — fileserver routes
# ---------------------------------------------------------------------------

class TestFilesRoutes:

    def test_skill_md_path_exists(self, spec):
        path = f"/{SKILL_NAME}/SKILL.md"
        assert path in spec["paths"], f"Missing path: {path}"

    def test_skill_md_has_get(self, spec):
        path = f"/{SKILL_NAME}/SKILL.md"
        assert "get" in spec["paths"][path]

    def test_skill_md_has_example_content(self, spec):
        path = f"/{SKILL_NAME}/SKILL.md"
        example = (
            spec["paths"][path]["get"]["responses"]["200"]
            ["content"]["text/markdown"]["example"]
        )
        assert len(example) > 0
        assert "name:" in example  # frontmatter must be present

    def test_skill_md_example_starts_with_frontmatter(self, spec):
        path = f"/{SKILL_NAME}/SKILL.md"
        example = (
            spec["paths"][path]["get"]["responses"]["200"]
            ["content"]["text/markdown"]["example"]
        )
        assert example.startswith("---"), "SKILL.md must start with YAML frontmatter ---"

    def test_references_listing_path_exists(self, spec):
        path = f"/{SKILL_NAME}/references/"
        assert path in spec["paths"], f"Missing path: {path}"

    def test_references_listing_has_json_example(self, spec):
        path = f"/{SKILL_NAME}/references/"
        example = (
            spec["paths"][path]["get"]["responses"]["200"]
            ["content"]["application/json"]["example"]
        )
        assert isinstance(example, list)
        assert len(example) > 0

    def test_references_listing_entries_have_href(self, spec):
        path = f"/{SKILL_NAME}/references/"
        example = (
            spec["paths"][path]["get"]["responses"]["200"]
            ["content"]["application/json"]["example"]
        )
        for entry in example:
            assert "name" in entry
            assert "href" in entry
            assert "sha256" in entry

    def test_at_least_one_reference_file_path_exists(self, spec):
        ref_paths = [
            p for p in spec["paths"]
            if p.startswith(f"/{SKILL_NAME}/references/") and not p.endswith("/")
        ]
        assert len(ref_paths) > 0, "No reference file paths found"

    def test_reference_file_has_example_content(self, spec):
        ref_paths = [
            p for p in spec["paths"]
            if p.startswith(f"/{SKILL_NAME}/references/") and not p.endswith("/")
        ]
        for path in ref_paths:
            content_block = spec["paths"][path]["get"]["responses"]["200"]["content"]
            media_type = list(content_block.keys())[0]
            example = content_block[media_type]["example"]
            assert len(example) > 0, f"Empty example for {path}"


# ---------------------------------------------------------------------------
# paths — response headers
# ---------------------------------------------------------------------------

class TestResponseHeaders:

    def _get_headers(self, spec, path):
        return (
            spec["paths"][path]["get"]["responses"]["200"]
            .get("headers", {})
        )

    def test_skill_md_has_etag_header(self, spec):
        headers = self._get_headers(spec, f"/{SKILL_NAME}/SKILL.md")
        assert "ETag" in headers

    def test_skill_md_has_cache_control_header(self, spec):
        headers = self._get_headers(spec, f"/{SKILL_NAME}/SKILL.md")
        assert "Cache-Control" in headers

    def test_skill_md_cache_control_is_immutable(self, spec):
        headers = self._get_headers(spec, f"/{SKILL_NAME}/SKILL.md")
        example = headers["Cache-Control"]["schema"].get("example", "") or \
                  headers["Cache-Control"].get("example", "")
        assert "immutable" in str(example)

    def test_skill_md_has_x_skill_commit_header(self, spec):
        headers = self._get_headers(spec, f"/{SKILL_NAME}/SKILL.md")
        assert "X-Skill-Commit" in headers


# ---------------------------------------------------------------------------
# sha256 integrity
# ---------------------------------------------------------------------------

class TestSHA256Integrity:

    def test_skill_md_etag_matches_content(self, spec):
        """ETag sha256 must match the actual example content."""
        path = f"/{SKILL_NAME}/SKILL.md"
        example = (
            spec["paths"][path]["get"]["responses"]["200"]
            ["content"]["text/markdown"]["example"]
        )
        headers = spec["paths"][path]["get"]["responses"]["200"]["headers"]
        etag_example = headers["ETag"]["schema"]["example"]
        # ETag format: "sha256:<hex>"
        expected = f'"sha256:{hashlib.sha256(example.encode()).hexdigest()}"'
        assert etag_example == expected, \
            f"ETag mismatch: spec has {etag_example}, content hashes to {expected}"

    def test_reference_file_sha256_matches_content(self, spec):
        """sha256 in directory listing must match actual file content."""
        listing_path = f"/{SKILL_NAME}/references/"
        entries = (
            spec["paths"][listing_path]["get"]["responses"]["200"]
            ["content"]["application/json"]["example"]
        )
        for entry in entries:
            file_path = f"/{SKILL_NAME}/references/{entry['name']}"
            if file_path not in spec["paths"]:
                continue
            content_block = spec["paths"][file_path]["get"]["responses"]["200"]["content"]
            media_type = list(content_block.keys())[0]
            content = content_block[media_type]["example"]
            expected_sha = hashlib.sha256(content.encode()).hexdigest()
            assert entry["sha256"] == expected_sha, \
                f"sha256 mismatch for {entry['name']}: " \
                f"listing has {entry['sha256']}, content hashes to {expected_sha}"


# ---------------------------------------------------------------------------
# special routes — root
# ---------------------------------------------------------------------------

class TestSpecialRootRoutes:

    def test_root_path_exists(self, spec):
        assert "/" in spec["paths"]

    def test_list_path_exists(self, spec):
        assert "/list" in spec["paths"]

    def test_to_prompt_path_exists(self, spec):
        assert "/to-prompt" in spec["paths"]

    def test_to_conventions_path_exists(self, spec):
        assert "/to-conventions" in spec["paths"]

    def test_validate_path_exists(self, spec):
        assert "/validate" in spec["paths"]

    def test_meta_path_exists(self, spec):
        assert "/meta" in spec["paths"]

    def test_pin_path_exists(self, spec):
        assert "/pin" in spec["paths"]

    def test_find_path_exists(self, spec):
        assert "/find/{partial_name}" in spec["paths"]

    def test_openapi_json_path_exists(self, spec):
        assert "/schema/openapi.json" in spec["paths"]

    def test_swagger_path_exists(self, spec):
        assert "/schema/swagger" in spec["paths"]


# ---------------------------------------------------------------------------
# special routes — per skill
# ---------------------------------------------------------------------------

class TestSpecialSkillRoutes:

    def test_skill_to_prompt_exists(self, spec):
        assert f"/{SKILL_NAME}/to-prompt" in spec["paths"]

    def test_skill_to_conventions_exists(self, spec):
        assert f"/{SKILL_NAME}/to-conventions" in spec["paths"]

    def test_skill_validate_exists(self, spec):
        assert f"/{SKILL_NAME}/validate" in spec["paths"]

    def test_skill_meta_exists(self, spec):
        assert f"/{SKILL_NAME}/meta" in spec["paths"]

    def test_skill_pin_exists(self, spec):
        assert f"/{SKILL_NAME}/pin" in spec["paths"]

    def test_skill_openapi_json_exists(self, spec):
        assert f"/{SKILL_NAME}/schema/openapi.json" in spec["paths"]

    def test_skill_swagger_exists(self, spec):
        assert f"/{SKILL_NAME}/schema/swagger" in spec["paths"]
