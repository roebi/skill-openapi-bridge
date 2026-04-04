"""
HTTP server tests for v0.2.0 serve command.

These tests define the server behaviour as law.
They must FAIL before implementation and PASS after.

Run:  pytest tests/test_server.py -v
"""

import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

SKILL_NAME = "brainstorming-topic-dialog-creative-mentor-en"
FIXTURE_SPEC = (
    Path(__file__).parent
    / "fixtures"
    / f"{SKILL_NAME}-openapi-spec.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=1.0)
            return True
        except Exception:
            time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# Server fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def server():
    """
    Start skill-openapi-bridge serve as a subprocess.
    Yields base URL. Kills server after module tests complete.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "skill_openapi_bridge",
            "serve", str(FIXTURE_SPEC),
            "--port", str(port),
            "--host", "127.0.0.1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    ready = _wait_for_server(base_url, timeout=5.0)
    if not ready:
        proc.kill()
        out, err = proc.communicate()
        pytest.fail(
            f"Server did not start within 5s.\n"
            f"stdout: {out.decode()}\nstderr: {err.decode()}"
        )

    yield base_url

    proc.kill()
    proc.wait()


@pytest.fixture(scope="module")
def spec() -> dict:
    with FIXTURE_SPEC.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Root HATEOAS  GET /
# ---------------------------------------------------------------------------

class TestRootHATEOAS:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/")
        assert "application/json" in r.headers["content-type"]

    def test_body_is_list(self, server):
        r = httpx.get(f"{server}/")
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_entry_has_name(self, server):
        r = httpx.get(f"{server}/")
        entry = r.json()[0]
        assert "name" in entry
        assert entry["name"] == SKILL_NAME

    def test_entry_has_href(self, server):
        r = httpx.get(f"{server}/")
        entry = r.json()[0]
        assert "href" in entry
        assert SKILL_NAME in entry["href"]

    def test_entry_has_skill_md_url(self, server):
        r = httpx.get(f"{server}/")
        entry = r.json()[0]
        assert "skill_md" in entry
        assert entry["skill_md"].endswith("SKILL.md")

    def test_entry_urls_are_reachable(self, server):
        r = httpx.get(f"{server}/")
        entry = r.json()[0]
        r2 = httpx.get(entry["skill_md"])
        assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Skill root  GET /<skill-name>/
# ---------------------------------------------------------------------------

class TestSkillRoot:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/")
        assert "application/json" in r.headers["content-type"]

    def test_body_is_list(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/")
        data = r.json()
        assert isinstance(data, list)

    def test_skill_md_in_listing(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/")
        names = [e["name"] for e in r.json()]
        assert "SKILL.md" in names

    def test_entries_have_href(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/")
        for entry in r.json():
            assert "href" in entry


# ---------------------------------------------------------------------------
# SKILL.md  GET /<skill-name>/SKILL.md
# ---------------------------------------------------------------------------

class TestSkillMd:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert r.status_code == 200

    def test_content_type_markdown(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert "text/markdown" in r.headers["content-type"]

    def test_body_starts_with_frontmatter(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert r.text.startswith("---")

    def test_body_contains_skill_name(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert SKILL_NAME in r.text

    def test_etag_header_present(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert "etag" in r.headers

    def test_etag_format_sha256(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert r.headers["etag"].startswith('"sha256:')

    def test_etag_matches_content(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        expected = f'"sha256:{hashlib.sha256(r.content).hexdigest()}"'
        assert r.headers["etag"] == expected

    def test_cache_control_immutable(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert "immutable" in r.headers["cache-control"]

    def test_x_skill_name_header(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert r.headers.get("x-skill-name") == SKILL_NAME

    def test_x_skill_commit_header_present(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert "x-skill-commit" in r.headers

    def test_x_content_sha256_header(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        assert "x-content-sha256" in r.headers

    def test_x_content_sha256_matches_body(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/SKILL.md")
        expected = hashlib.sha256(r.content).hexdigest()
        assert r.headers["x-content-sha256"] == expected


# ---------------------------------------------------------------------------
# References listing  GET /<skill-name>/references/
# ---------------------------------------------------------------------------

class TestReferencesListing:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/")
        assert "application/json" in r.headers["content-type"]

    def test_body_is_list(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/")
        assert isinstance(r.json(), list)

    def test_entries_have_name_href_sha256(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/")
        for entry in r.json():
            assert "name" in entry
            assert "href" in entry
            assert "sha256" in entry


# ---------------------------------------------------------------------------
# Reference file  GET /<skill-name>/references/<ref>
# ---------------------------------------------------------------------------

class TestReferenceFile:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/mentor-framework.md")
        assert r.status_code == 200

    def test_content_type_markdown(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/mentor-framework.md")
        assert "text/markdown" in r.headers["content-type"]

    def test_body_not_empty(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/mentor-framework.md")
        assert len(r.text) > 0

    def test_etag_present(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/mentor-framework.md")
        assert "etag" in r.headers

    def test_etag_matches_content(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/mentor-framework.md")
        expected = f'"sha256:{hashlib.sha256(r.content).hexdigest()}"'
        assert r.headers["etag"] == expected

    def test_cache_control_immutable(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/mentor-framework.md")
        assert "immutable" in r.headers["cache-control"]

    def test_unknown_ref_returns_404(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/references/does-not-exist.md")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Scripts listing  GET /<skill-name>/scripts/
# ---------------------------------------------------------------------------

class TestScriptsListing:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/scripts/")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/scripts/")
        assert "application/json" in r.headers["content-type"]

    def test_body_is_list(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/scripts/")
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Assets listing  GET /<skill-name>/assets/
# ---------------------------------------------------------------------------

class TestAssetsListing:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/assets/")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/assets/")
        assert "application/json" in r.headers["content-type"]

    def test_body_is_list(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/assets/")
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Special root routes
# ---------------------------------------------------------------------------

class TestRootList:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/list")
        assert r.status_code == 200

    def test_content_type_html(self, server):
        r = httpx.get(f"{server}/list")
        assert "text/html" in r.headers["content-type"]

    def test_body_contains_skill_name(self, server):
        r = httpx.get(f"{server}/list")
        assert SKILL_NAME in r.text


class TestRootToPrompt:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/to-prompt")
        assert r.status_code == 200

    def test_content_type_xml(self, server):
        r = httpx.get(f"{server}/to-prompt")
        assert "xml" in r.headers["content-type"]

    def test_body_contains_available_skills_tag(self, server):
        r = httpx.get(f"{server}/to-prompt")
        assert "<available_skills>" in r.text

    def test_body_contains_skill_name(self, server):
        r = httpx.get(f"{server}/to-prompt")
        assert SKILL_NAME in r.text

    def test_location_is_http_url(self, server):
        r = httpx.get(f"{server}/to-prompt")
        assert "<location>http" in r.text


class TestRootToConventions:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/to-conventions")
        assert r.status_code == 200

    def test_content_type_markdown(self, server):
        r = httpx.get(f"{server}/to-conventions")
        assert "text/markdown" in r.headers["content-type"]

    def test_body_contains_skill_name(self, server):
        r = httpx.get(f"{server}/to-conventions")
        assert SKILL_NAME in r.text


class TestRootValidate:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/validate")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/validate")
        assert "application/json" in r.headers["content-type"]

    def test_body_has_results(self, server):
        r = httpx.get(f"{server}/validate")
        data = r.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_body_has_validated_at(self, server):
        r = httpx.get(f"{server}/validate")
        assert "validated_at" in r.json()

    def test_result_has_valid_field(self, server):
        r = httpx.get(f"{server}/validate")
        result = r.json()["results"][0]
        assert "valid" in result

    def test_result_has_errors_list(self, server):
        r = httpx.get(f"{server}/validate")
        result = r.json()["results"][0]
        assert "errors" in result
        assert isinstance(result["errors"], list)


class TestRootMeta:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/meta")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/meta")
        assert "application/json" in r.headers["content-type"]

    def test_body_contains_skill_name_key(self, server):
        r = httpx.get(f"{server}/meta")
        assert SKILL_NAME in r.json()

    def test_meta_has_name_field(self, server):
        r = httpx.get(f"{server}/meta")
        meta = r.json()[SKILL_NAME]
        assert meta["name"] == SKILL_NAME


class TestRootPin:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/pin")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/pin")
        assert "application/json" in r.headers["content-type"]

    def test_body_contains_skill_name_key(self, server):
        r = httpx.get(f"{server}/pin")
        assert SKILL_NAME in r.json()

    def test_pin_has_repo(self, server):
        r = httpx.get(f"{server}/pin")
        pin = r.json()[SKILL_NAME]
        assert "repo" in pin
        assert pin["repo"].startswith("https://")

    def test_pin_has_commit(self, server):
        r = httpx.get(f"{server}/pin")
        pin = r.json()[SKILL_NAME]
        assert "commit" in pin
        assert len(pin["commit"]) == 40

    def test_pin_has_generated_at(self, server):
        r = httpx.get(f"{server}/pin")
        pin = r.json()[SKILL_NAME]
        assert "generated_at" in pin


class TestRootFind:

    def test_partial_match_redirects(self, server):
        r = httpx.get(f"{server}/find/brainstorming", follow_redirects=False)
        assert r.status_code == 302

    def test_redirect_location_contains_skill_name(self, server):
        r = httpx.get(f"{server}/find/brainstorming", follow_redirects=False)
        assert SKILL_NAME in r.headers["location"]

    def test_redirect_location_points_to_skill_md(self, server):
        r = httpx.get(f"{server}/find/brainstorming", follow_redirects=False)
        assert r.headers["location"].endswith("SKILL.md")

    def test_following_redirect_returns_200(self, server):
        r = httpx.get(f"{server}/find/brainstorming", follow_redirects=True)
        assert r.status_code == 200

    def test_no_match_returns_404(self, server):
        r = httpx.get(f"{server}/find/zzznomatch", follow_redirects=False)
        assert r.status_code == 404


class TestRootSchema:

    def test_openapi_json_status_200(self, server):
        r = httpx.get(f"{server}/schema/openapi.json")
        assert r.status_code == 200

    def test_openapi_json_content_type(self, server):
        r = httpx.get(f"{server}/schema/openapi.json")
        assert "application/json" in r.headers["content-type"]

    def test_openapi_json_is_valid_openapi(self, server):
        r = httpx.get(f"{server}/schema/openapi.json")
        data = r.json()
        assert data["openapi"] == "3.1.0"
        assert "info" in data
        assert "paths" in data

    def test_swagger_status_200(self, server):
        r = httpx.get(f"{server}/schema/swagger")
        assert r.status_code == 200

    def test_swagger_content_type_html(self, server):
        r = httpx.get(f"{server}/schema/swagger")
        assert "text/html" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# Per-skill special routes
# ---------------------------------------------------------------------------

class TestSkillToPrompt:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/to-prompt")
        assert r.status_code == 200

    def test_content_type_xml(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/to-prompt")
        assert "xml" in r.headers["content-type"]

    def test_body_contains_only_this_skill(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/to-prompt")
        assert "<available_skills>" in r.text
        assert SKILL_NAME in r.text


class TestSkillToConventions:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/to-conventions")
        assert r.status_code == 200

    def test_content_type_markdown(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/to-conventions")
        assert "text/markdown" in r.headers["content-type"]

    def test_body_contains_skill_name(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/to-conventions")
        assert SKILL_NAME in r.text


class TestSkillValidate:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/validate")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/validate")
        assert "application/json" in r.headers["content-type"]

    def test_result_has_valid_field(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/validate")
        assert "valid" in r.json()

    def test_result_has_skill_name(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/validate")
        assert r.json()["skill"] == SKILL_NAME

    def test_result_has_errors_list(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/validate")
        assert isinstance(r.json()["errors"], list)

    def test_result_has_warnings_list(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/validate")
        assert isinstance(r.json()["warnings"], list)

    def test_result_has_checked_at(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/validate")
        assert "checked_at" in r.json()


class TestSkillMeta:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/meta")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/meta")
        assert "application/json" in r.headers["content-type"]

    def test_meta_has_name(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/meta")
        assert r.json()["name"] == SKILL_NAME

    def test_meta_has_license(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/meta")
        assert "license" in r.json()


class TestSkillPin:

    def test_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/pin")
        assert r.status_code == 200

    def test_content_type_json(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/pin")
        assert "application/json" in r.headers["content-type"]

    def test_pin_has_repo(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/pin")
        assert "repo" in r.json()

    def test_pin_has_commit(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/pin")
        assert len(r.json()["commit"]) == 40

    def test_pin_has_generated_at(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/pin")
        assert "generated_at" in r.json()


class TestSkillSchema:

    def test_openapi_json_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/schema/openapi.json")
        assert r.status_code == 200

    def test_openapi_json_is_valid(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/schema/openapi.json")
        data = r.json()
        assert data["openapi"] == "3.1.0"

    def test_swagger_status_200(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/schema/swagger")
        assert r.status_code == 200

    def test_swagger_content_type_html(self, server):
        r = httpx.get(f"{server}/{SKILL_NAME}/schema/swagger")
        assert "text/html" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# Unknown routes
# ---------------------------------------------------------------------------

class TestUnknownRoutes:

    def test_unknown_skill_returns_404(self, server):
        r = httpx.get(f"{server}/no-such-skill/SKILL.md")
        assert r.status_code == 404

    def test_unknown_root_path_returns_404(self, server):
        r = httpx.get(f"{server}/no-such-path")
        assert r.status_code == 404
