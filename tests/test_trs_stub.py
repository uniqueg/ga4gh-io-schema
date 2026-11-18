# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the TRS stub of the prototype (``prototype/trs-stub/``).

They cover the TRS endpoints that the host of the form uses, over HTTP
against a local stub that serves the end-to-end demo, and that the host
loads the demo schema from the stub.
"""

import contextlib
import copy
import hashlib
import http.client
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import form_host
import pytest
import trs_stub

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
WORKFLOWS = ROOT / "examples" / "workflows"
DEMO_SCHEMA = json.loads((DEMO / "ga4gh-io.schema.json").read_text(encoding="utf-8"))
DEMO_WDL = (DEMO / "demo.wdl").read_text(encoding="utf-8")
TOOL = "ga4gh-io-schema-demo"
VERSION = "1.0.0"


@contextlib.contextmanager
def serve(workflows: Sequence[trs_stub.Workflow]) -> Iterator[str]:
    """Run the stub on a free port.

    Args:
        workflows: The workflows to serve.

    Yields:
        The base URL of the TRS API of the stub.
    """
    server = trs_stub.TrsStub(("127.0.0.1", 0), workflows)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}{trs_stub.API}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def stub() -> Iterator[str]:
    """Run the stub for the demo workflow.

    Yields:
        The base URL of the TRS API of the stub.
    """
    with serve([trs_stub.load_workflow(DEMO)]) as url:
        yield url


def make_workflow(
    directory: Path,
    change: Callable[[dict[str, Any]], Any] = lambda block: None,
    descriptor: bytes = DEMO_WDL.encode("utf-8"),
) -> Path:
    """Write a copy of the demo workflow with a changed workflow block.

    Args:
        directory: Directory to write to.
        change: Changes the block (``x-ga4gh-workflow``) in place.
        descriptor: Content of the primary descriptor.

    Returns:
        The directory.
    """
    schema = copy.deepcopy(DEMO_SCHEMA)
    change(schema["x-ga4gh-workflow"])
    (directory / "ga4gh-io.schema.json").write_text(json.dumps(schema), "utf-8")
    (directory / "demo.wdl").write_bytes(descriptor)
    return directory


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
    assert workflow.primary == "demo.wdl"
    assert workflow.files == {
        "demo.wdl": ("PRIMARY_DESCRIPTOR", DEMO_WDL),
        "ga4gh-io.schema.json": (
            "OTHER",
            (DEMO / "ga4gh-io.schema.json").read_text(encoding="utf-8"),
        ),
    }


def test_load_workflow_names_the_tool_by_id_without_title(tmp_path: Path) -> None:
    """Test that a schema without title names the tool by its id."""
    schema = copy.deepcopy(DEMO_SCHEMA)
    del schema["title"]
    make_workflow(tmp_path)
    (tmp_path / "ga4gh-io.schema.json").write_text(json.dumps(schema), "utf-8")
    assert trs_stub.load_workflow(tmp_path).name == TOOL


def test_load_workflow_keeps_the_bytes(tmp_path: Path) -> None:
    """Test that line ends are kept, so that the checksum of the file holds."""
    raw = DEMO_WDL.replace("\n", "\r\n").encode("utf-8")
    workflow = trs_stub.load_workflow(make_workflow(tmp_path, descriptor=raw))
    assert workflow.files["demo.wdl"][1].encode("utf-8") == raw


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda b: b.pop("trs_version_id"), "trs_version_id"),
        (lambda b: b.update(descriptor_type_version=1), "descriptor_type_version"),
        (lambda b: b.update(primary_descriptor_path="wdl/demo.wdl"), "file name"),
        (lambda b: b.update(primary_descriptor_path="./demo.wdl"), "file name"),
        (lambda b: b.update(primary_descriptor_path=".."), "file name"),
    ],
)
def test_load_workflow_needs_the_workflow_block(
    tmp_path: Path, change: Callable[[dict[str, Any]], Any], message: str
) -> None:
    """Test that a block without what TRS needs, or a nested path, fails."""
    with pytest.raises(ValueError, match=message):
        trs_stub.load_workflow(make_workflow(tmp_path, change))


def test_load_workflow_needs_a_workflow_block(tmp_path: Path) -> None:
    """Test that a schema without ``x-ga4gh-workflow`` fails."""
    (tmp_path / "ga4gh-io.schema.json").write_text("[]", "utf-8")
    with pytest.raises(ValueError, match="x-ga4gh-workflow"):
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


def test_stub_builds_urls_from_the_host_header(stub: str) -> None:
    """Test that the ``url`` fields name the host that the client used."""
    origin = stub.removesuffix(trs_stub.API).removeprefix("http://")
    connection = http.client.HTTPConnection(origin, timeout=10)
    try:
        connection.request("GET", f"{trs_stub.API}/tools", headers={"Host": "trs"})
        tools = json.loads(connection.getresponse().read())
    finally:
        connection.close()
    assert tools[0]["url"] == f"http://trs{trs_stub.API}/tools/{TOOL}"


def test_stub_lists_the_files(stub: str) -> None:
    """Test ``GET .../{type}/files``: the descriptor and the IO schema."""
    files = get_json(f"{version_url(stub)}/WDL/files")
    assert files == [
        {"path": "demo.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
        {"path": "ga4gh-io.schema.json", "file_type": "OTHER"},
    ]


def test_stub_serves_the_primary_descriptor(stub: str) -> None:
    """Test the descriptor as ``FileWrapper`` and as plain text.

    For the demo, the checksum of the ``FileWrapper`` is the one that the
    schema's workflow block names, so a client can check that the schema
    fits the descriptor.
    """
    for path in ("WDL/descriptor", "WDL/descriptor/demo.wdl"):
        wrapper = get_json(f"{version_url(stub)}/{path}")
        assert wrapper["content"] == DEMO_WDL
        assert wrapper["checksum"] == DEMO_SCHEMA["x-ga4gh-workflow"]["checksum"]
        assert wrapper["url"] == f"{version_url(stub)}/PLAIN_WDL/descriptor/demo.wdl"
    for path in ("PLAIN_WDL/descriptor", "PLAIN_WDL/descriptor/demo.wdl"):
        status, media_type, body = get(f"{version_url(stub)}/{path}")
        assert (status, media_type) == (200, "text/plain; charset=utf-8")
        assert body.decode("utf-8") == DEMO_WDL


def test_stub_serves_the_schema(stub: str) -> None:
    """Test the IO schema by relative path, wrapped and plain."""
    wrapper = get_json(f"{version_url(stub)}/WDL/descriptor/ga4gh-io.schema.json")
    assert json.loads(wrapper["content"]) == DEMO_SCHEMA
    digest = hashlib.sha256(wrapper["content"].encode("utf-8")).hexdigest()
    assert wrapper["checksum"] == [{"type": "sha-256", "checksum": digest}]
    plain = f"{version_url(stub)}/PLAIN_WDL/descriptor/ga4gh-io.schema.json"
    assert wrapper["url"] == plain
    status, _, body = get(plain)
    assert status == 200
    assert json.loads(body) == DEMO_SCHEMA


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/ga4gh/trs/v2",
        "/ga4gh/trs/v2/toolClasses",
        "/ga4gh/trs/v2/tools/unknown",
        "/ga4gh/trs/v2/tools/unknown/versions",
        "/ga4gh/trs/v2/tools/unknown/versions/1.0.0",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/0.0.0",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/CWL/files",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/PLAIN_WDL/files",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/PLAIN_CWL/descriptor",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/descriptor/x.wdl",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/descriptor/..%2Fdemo.wdl",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/containerfile",
        "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/tests",
    ],
)
def test_stub_answers_404_with_a_trs_error(stub: str, path: str) -> None:
    """Test that any other GET is ``404`` with a TRS ``Error`` body."""
    origin = stub.removesuffix(trs_stub.API)
    status, media_type, body = get(f"{origin}{path}")
    assert (status, media_type) == (404, "application/json")
    assert json.loads(body) == {"code": 404, "message": "Not found"}


def test_stub_merges_versions_of_one_tool(tmp_path: Path) -> None:
    """Test that two versions of one tool are listed under one tool."""
    other = make_workflow(tmp_path, lambda b: b.update(trs_version_id="2.0.0"))
    workflows = [trs_stub.load_workflow(DEMO), trs_stub.load_workflow(other)]
    with serve(workflows) as url:
        tools = get_json(f"{url}/tools")
    assert [v["id"] for v in tools[0]["versions"]] == ["1.0.0", "2.0.0"]


def test_stub_rejects_duplicate_versions() -> None:
    """Test that two workflows can't be the same tool version."""
    workflow = trs_stub.load_workflow(DEMO)
    with pytest.raises(ValueError, match="Two workflows"):
        trs_stub.TrsStub(("127.0.0.1", 0), [workflow, workflow])


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
    assert "proof of concept" in out
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


def test_main_reports_a_stub_that_cant_start(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that ``main`` exits with 1 if the stub can't start."""
    assert trs_stub.main(["--port", "0", "--workflow", str(DEMO)] * 2) == 1
    assert "Can't start the stub: Two workflows" in capsys.readouterr().err


def test_stub_ignores_query_parameters(stub: str) -> None:
    """Test that query parameters, e.g., ``format=zip``, are ignored."""
    for path in ("/tools", f"/tools/{TOOL}/versions/{VERSION}/WDL/files"):
        assert get_json(f"{stub}{path}?format=zip") == get_json(f"{stub}{path}")


# Seeded workflows and reloading (the one-command demo)


def test_find_workflows_lists_the_seeded_workflows() -> None:
    """Test that every directory with an IO schema is a workflow."""
    found = trs_stub.find_workflows(WORKFLOWS)
    assert [path.name for path in found] == [
        "greetings-nextflow",
        "report-snakemake",
        "word-count-cwl",
    ]


def test_unlisted_workflow_roots_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a missing directory of workflows isn't an empty one.

    E.g., a checkout that the stub's user can't read: the list would be
    empty without a word in the logs.
    """
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        trs_stub.load_workflows([], [missing])
    assert trs_stub.load_workflows([], [missing], strict=False) == []
    assert f"Can't list the workflows in {missing}" in capsys.readouterr().err


def test_stub_serves_the_seeded_workflows() -> None:
    """Test that the demo and the seeded workflows are served side by side."""
    directories = [DEMO, *trs_stub.find_workflows(WORKFLOWS)]
    workflows = [trs_stub.load_workflow(path) for path in directories]
    with serve(workflows) as url:
        tools = get_json(f"{url}/tools")
    types = {tool["id"]: tool["versions"][0]["descriptor_type"] for tool in tools}
    assert types == {
        TOOL: ["WDL"],
        "io-schema-greetings": ["NFL"],
        "io-schema-report": ["SMK"],
        "io-schema-word-count": ["CWL"],
    }


@contextlib.contextmanager
def serve_reloading(
    directories: Sequence[Path], roots: Sequence[Path] = ()
) -> Iterator[str]:
    """Run the stub on a free port, reading the workflows on each request.

    Args:
        directories: Directories of workflows.
        roots: Directories whose subdirectories are workflows.

    Yields:
        The base URL of the TRS API of the stub.
    """
    server = trs_stub.TrsStub(
        ("127.0.0.1", 0),
        trs_stub.load_workflows(directories, roots),
        reload=lambda: trs_stub.load_workflows(directories, roots, strict=False),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}{trs_stub.API}"
    finally:
        server.shutdown()
        server.server_close()


def test_reload_shows_edits_without_a_restart(tmp_path: Path) -> None:
    """Test that an edited schema is served at the next request."""
    directory = make_workflow(tmp_path)
    with serve_reloading([directory]) as url:
        assert get_json(f"{url}/tools/{TOOL}")["name"] == "I/O Schema demo"
        schema = copy.deepcopy(DEMO_SCHEMA)
        schema["title"] = "Edited"
        (directory / "ga4gh-io.schema.json").write_text(json.dumps(schema), "utf-8")
        assert get_json(f"{url}/tools/{TOOL}")["name"] == "Edited"
        path = f"{version_url(url)}/WDL/descriptor/ga4gh-io.schema.json"
        assert json.loads(get_json(path)["content"])["title"] == "Edited"


def test_reload_finds_new_workflows(tmp_path: Path) -> None:
    """Test that a workflow added under a root is served at the next request."""
    with serve_reloading([], [tmp_path]) as url:
        assert get_json(f"{url}/tools") == []
        (tmp_path / "new").mkdir()
        make_workflow(tmp_path / "new")
        assert [tool["id"] for tool in get_json(f"{url}/tools")] == [TOOL]


def test_reload_skips_broken_workflows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a broken or duplicate workflow is skipped and reported."""
    good = tmp_path / "a"
    broken = tmp_path / "b"
    twin = tmp_path / "c"
    good.mkdir()
    make_workflow(good)
    with serve_reloading([], [tmp_path]) as url:
        # Broken and duplicated while the stub runs, e.g., by an edit
        for directory in (broken, twin):
            directory.mkdir()
            make_workflow(directory)
        (broken / "ga4gh-io.schema.json").write_text("{", "utf-8")
        assert [tool["id"] for tool in get_json(f"{url}/tools")] == [TOOL]
    err = capsys.readouterr().err
    assert f"Can't serve the workflow {broken}" in err
    assert f"Can't serve the workflow {twin}: Two workflows" in err


def test_load_workflows_is_strict_by_default(tmp_path: Path) -> None:
    """Test that a broken workflow fails without ``strict=False``."""
    with pytest.raises(OSError):
        trs_stub.load_workflows([tmp_path])
    (tmp_path / "ga4gh-io.schema.json").write_text("{", "utf-8")
    with pytest.raises(ValueError, match=f"^{tmp_path}: Expecting"):
        trs_stub.load_workflows([tmp_path])


def test_reload_skips_json_nested_too_deeply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that JSON too deep for the parser is skipped, not fatal."""
    (tmp_path / "ga4gh-io.schema.json").write_text("[" * 200_000, "utf-8")
    assert trs_stub.load_workflows([tmp_path], strict=False) == []
    assert f"Can't serve the workflow {tmp_path}" in capsys.readouterr().err
    with pytest.raises(ValueError, match=f"^{tmp_path}: "):
        trs_stub.load_workflows([tmp_path])


def test_main_with_reload_skips_broken_workflows_at_the_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that ``--reload`` starts despite workflows broken while down.

    E.g., a copied workflow with the same tool id, or a schema left
    invalid, after the stack was stopped.
    """
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
        make_workflow(tmp_path / name)
    (tmp_path / "c" / "ga4gh-io.schema.json").write_text("{", "utf-8")
    servers: list[trs_stub.TrsStub] = []

    def interrupt(self: trs_stub.TrsStub) -> None:
        servers.append(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(trs_stub.TrsStub, "serve_forever", interrupt)
    argv = ["--port", "0", "--workflows-dir", str(tmp_path)]
    assert trs_stub.main([*argv, "--reload"]) == 0
    assert list(servers[0].current()) == [TOOL]
    err = capsys.readouterr().err
    assert f"Can't serve the workflow {tmp_path / 'b'}: Two workflows" in err
    assert f"Can't serve the workflow {tmp_path / 'c'}" in err
    assert trs_stub.main(argv) == 1


def test_main_serves_seeded_workflows_with_reload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test ``--workflows-dir`` and ``--reload``."""
    servers: list[trs_stub.TrsStub] = []

    def interrupt(self: trs_stub.TrsStub) -> None:
        servers.append(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(trs_stub.TrsStub, "serve_forever", interrupt)
    argv = ["--port", "0", "--workflow", str(DEMO), "--workflows-dir", str(WORKFLOWS)]
    assert trs_stub.main([*argv, "--reload"]) == 0
    out = capsys.readouterr().out
    assert "/tools/io-schema-word-count/versions/1.0.0" in out
    assert "re-read on every request" in out
    assert servers[0].reload is not None
    assert len(servers[0].current()) == 4


def test_main_without_reload_reads_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that without ``--reload``, the workflows are read at the start."""
    servers: list[trs_stub.TrsStub] = []

    def interrupt(self: trs_stub.TrsStub) -> None:
        servers.append(self)
        raise KeyboardInterrupt

    monkeypatch.setattr(trs_stub.TrsStub, "serve_forever", interrupt)
    assert trs_stub.main(["--port", "0", "--workflows-dir", str(WORKFLOWS)]) == 0
    assert servers[0].reload is None
    assert sorted(servers[0].current()) == [
        "io-schema-greetings",
        "io-schema-report",
        "io-schema-word-count",
    ]
