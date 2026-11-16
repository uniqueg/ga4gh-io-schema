# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the TRS stub of the prototype (``prototype/trs-stub/``).

They cover the TRS endpoints that the host of the form uses, over HTTP
against a local stub that serves the end-to-end demo, and that the host
loads the demo schema from the stub.
"""

import hashlib
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import form_host
import pytest
import trs_stub

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
DEMO_SCHEMA = json.loads((DEMO / "ga4gh-io.schema.json").read_text(encoding="utf-8"))
DEMO_WDL = (DEMO / "demo.wdl").read_text(encoding="utf-8")
TOOL = "ga4gh-io-schema-demo"
VERSION = "1.0.0"


@pytest.fixture
def stub() -> Iterator[str]:
    """Run the stub for the demo workflow on a free port.

    Yields:
        The base URL of the TRS API of the stub.
    """
    server = trs_stub.TrsStub(("127.0.0.1", 0), [trs_stub.load_workflow(DEMO)])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}{trs_stub.API}"
    server.shutdown()
    server.server_close()


def get(url: str) -> tuple[int, str, bytes]:
    """Send a GET request.

    Args:
        url: The URL.

    Returns:
        Status, ``Content-Type`` and body of the response.
    """
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers["Content-Type"], response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers["Content-Type"], exc.read()


def get_json(url: str) -> Any:
    """Get a JSON response with status 200.

    Args:
        url: The URL.

    Returns:
        The parsed body.
    """
    status, media_type, body = get(url)
    assert status == 200
    assert media_type == "application/json"
    return json.loads(body)


def version_url(stub: str) -> str:
    """Build the URL of the demo's tool version.

    Args:
        stub: Base URL of the TRS API.

    Returns:
        The URL.
    """
    return f"{stub}/tools/{TOOL}/versions/{VERSION}"


def test_load_workflow_reads_the_demo() -> None:
    """Test that the tool version comes from the schema's workflow block."""
    workflow = trs_stub.load_workflow(DEMO)
    assert (workflow.tool_id, workflow.version_id) == (TOOL, VERSION)
    assert workflow.name == DEMO_SCHEMA["title"]
    assert (workflow.descriptor_type, workflow.descriptor_type_version) == (
        "WDL",
        "1.1",
    )
    assert workflow.files == {
        "demo.wdl": ("PRIMARY_DESCRIPTOR", DEMO_WDL),
        "ga4gh-io.schema.json": (
            "OTHER",
            (DEMO / "ga4gh-io.schema.json").read_text(encoding="utf-8"),
        ),
    }


def test_load_workflow_puts_the_schema_next_to_the_primary_descriptor(
    tmp_path: Path,
) -> None:
    """Test a primary descriptor in a subdirectory, and a schema without title."""
    schema = json.loads(json.dumps(DEMO_SCHEMA))
    del schema["title"]
    schema["x-ga4gh-workflow"]["primary_descriptor_path"] = "wdl/main.wdl"
    (tmp_path / "ga4gh-io.schema.json").write_text(json.dumps(schema), "utf-8")
    (tmp_path / "main.wdl").write_text(DEMO_WDL, "utf-8")
    workflow = trs_stub.load_workflow(tmp_path)
    assert workflow.name == TOOL
    assert sorted(workflow.files) == ["wdl/ga4gh-io.schema.json", "wdl/main.wdl"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: s.pop("x-ga4gh-workflow"), "x-ga4gh-workflow"),
        (lambda s: s["x-ga4gh-workflow"].pop("trs_version_id"), "trs_version_id"),
        (
            lambda s: s["x-ga4gh-workflow"].update(descriptor_type_version=1),
            "descriptor_type_version",
        ),
    ],
)
def test_load_workflow_needs_the_workflow_block(
    tmp_path: Path, change: Any, message: str
) -> None:
    """Test that a schema without the parts of the block that TRS needs fails."""
    schema = json.loads(json.dumps(DEMO_SCHEMA))
    change(schema)
    (tmp_path / "ga4gh-io.schema.json").write_text(json.dumps(schema), "utf-8")
    (tmp_path / "demo.wdl").write_text(DEMO_WDL, "utf-8")
    with pytest.raises(ValueError, match=message):
        trs_stub.load_workflow(tmp_path)


def test_stub_lists_the_tools(stub: str) -> None:
    """Test ``GET /tools`` and ``GET /tools/{id}``."""
    tools = get_json(f"{stub}/tools")
    assert [tool["id"] for tool in tools] == [TOOL]
    tool = get_json(f"{stub}/tools/{TOOL}")
    assert tool == tools[0]
    assert tool["url"] == f"{stub}/tools/{TOOL}"
    assert tool["name"] == DEMO_SCHEMA["title"]
    assert tool["toolclass"]["name"] == "Workflow"
    assert [version["id"] for version in tool["versions"]] == [VERSION]


def test_stub_serves_the_tool_version(stub: str) -> None:
    """Test ``GET /tools/{id}/versions`` and ``.../versions/{version_id}``."""
    versions = get_json(f"{stub}/tools/{TOOL}/versions")
    version = get_json(version_url(stub))
    assert versions == [version]
    assert version["url"] == version_url(stub)
    assert version["descriptor_type"] == ["WDL"]
    assert version["descriptor_type_version"] == {"WDL": ["1.1"]}


def test_stub_lists_the_files(stub: str) -> None:
    """Test ``GET .../{type}/files``: the descriptor and the IO schema."""
    files = get_json(f"{version_url(stub)}/WDL/files")
    assert files == [
        {"path": "demo.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
        {"path": "ga4gh-io.schema.json", "file_type": "OTHER"},
    ]


def test_stub_serves_the_primary_descriptor(stub: str) -> None:
    """Test the descriptor as ``FileWrapper`` and as plain text.

    The checksum of the ``FileWrapper`` is the one that the schema's workflow
    block names, so a client can check that the schema fits the descriptor.
    """
    wrapper = get_json(f"{version_url(stub)}/WDL/descriptor")
    assert wrapper["content"] == DEMO_WDL
    assert wrapper["checksum"] == DEMO_SCHEMA["x-ga4gh-workflow"]["checksum"]
    assert wrapper["url"] == f"{version_url(stub)}/PLAIN_WDL/descriptor"
    status, media_type, body = get(f"{version_url(stub)}/PLAIN_WDL/descriptor")
    assert (status, media_type) == (200, "text/plain; charset=utf-8")
    assert body.decode("utf-8") == DEMO_WDL


def test_stub_serves_the_schema(stub: str) -> None:
    """Test the IO schema by relative path, wrapped and plain."""
    wrapper = get_json(f"{version_url(stub)}/WDL/descriptor/ga4gh-io.schema.json")
    assert json.loads(wrapper["content"]) == DEMO_SCHEMA
    digest = hashlib.sha256(wrapper["content"].encode("utf-8")).hexdigest()
    assert wrapper["checksum"] == [{"type": "sha-256", "checksum": digest}]
    status, _, body = get(
        f"{version_url(stub)}/PLAIN_WDL/descriptor/ga4gh-io.schema.json"
    )
    assert status == 200
    assert json.loads(body) == DEMO_SCHEMA


def test_stub_decodes_relative_paths(tmp_path: Path) -> None:
    """Test a relative path in subdirectories, as segments or percent-encoded."""
    schema = json.loads(json.dumps(DEMO_SCHEMA))
    schema["x-ga4gh-workflow"]["primary_descriptor_path"] = "wdl/main.wdl"
    (tmp_path / "ga4gh-io.schema.json").write_text(json.dumps(schema), "utf-8")
    (tmp_path / "main.wdl").write_text(DEMO_WDL, "utf-8")
    server = trs_stub.TrsStub(("127.0.0.1", 0), [trs_stub.load_workflow(tmp_path)])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = version_url(f"http://127.0.0.1:{server.server_address[1]}/ga4gh/trs/v2")
        for path in ("wdl/main.wdl", "wdl%2Fmain.wdl"):
            status, _, body = get(f"{base}/PLAIN_WDL/descriptor/{path}")
            assert (status, body.decode("utf-8")) == (200, DEMO_WDL)
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/ga4gh/trs/v2",
        "/ga4gh/trs/v2/toolClasses",
        "/ga4gh/trs/v2/tools/unknown",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/0.0.0",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/CWL/files",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/PLAIN_CWL/descriptor",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/descriptor/x.wdl",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/containerfile",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/tests",
    ],
)
def test_stub_answers_404_with_a_trs_error(stub: str, path: str) -> None:
    """Test that anything else is ``404`` with a TRS ``Error`` body."""
    origin = stub.removesuffix(trs_stub.API)
    status, media_type, body = get(f"{origin}{path}")
    assert (status, media_type) == (404, "application/json")
    assert json.loads(body) == {"code": 404, "message": "Not found"}


def test_stub_merges_versions_of_one_tool(tmp_path: Path) -> None:
    """Test that two versions of one tool are listed under one tool."""
    schema = json.loads(json.dumps(DEMO_SCHEMA))
    schema["x-ga4gh-workflow"]["trs_version_id"] = "2.0.0"
    (tmp_path / "ga4gh-io.schema.json").write_text(json.dumps(schema), "utf-8")
    (tmp_path / "demo.wdl").write_text(DEMO_WDL, "utf-8")
    workflows = [trs_stub.load_workflow(DEMO), trs_stub.load_workflow(tmp_path)]
    server = trs_stub.TrsStub(("127.0.0.1", 0), workflows)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}{trs_stub.API}"
        tools = get_json(f"{base}/tools")
        assert [v["id"] for v in tools[0]["versions"]] == ["1.0.0", "2.0.0"]
    finally:
        server.shutdown()
        server.server_close()


def test_host_loads_the_schema_from_the_stub(stub: str) -> None:
    """Test that the host of the form takes the schema from the stub's URL."""
    url = f"{version_url(stub)}/WDL/descriptor/ga4gh-io.schema.json"
    assert form_host.load_schema(url) == DEMO_SCHEMA
    plain = f"{version_url(stub)}/PLAIN_WDL/descriptor/ga4gh-io.schema.json"
    assert form_host.load_schema(plain) == DEMO_SCHEMA


def test_main_serves_until_interrupted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``main`` starts the stub and stops on Ctrl+C."""

    def interrupt(self: trs_stub.TrsStub) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(trs_stub.TrsStub, "serve_forever", interrupt)
    assert trs_stub.main(["--port", "0"]) == 0
    out = capsys.readouterr().out
    assert "Serving TRS on http://127.0.0.1:" in out
    assert f"/ga4gh/trs/v2/tools/{TOOL}/versions/{VERSION}" in out


def test_main_rejects_bad_workflows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``main`` exits with 1 if a workflow can't be read."""
    assert trs_stub.main(["--workflow", str(tmp_path)]) == 1
    assert "Can't serve the workflow" in capsys.readouterr().err
    (tmp_path / "ga4gh-io.schema.json").write_text("{", "utf-8")
    assert trs_stub.main(["--workflow", str(tmp_path)]) == 1
