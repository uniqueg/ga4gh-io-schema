# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the end-to-end demo in ``examples/demo/``.

The scripts talk to TRS-Filer and Conquest over HTTP; here, they talk to a
local mock server instead, so the tests run offline.
"""

import hashlib
import io
import json
import socket
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import build_schema
import conquest
import demo_http
import pytest
import register

from ga4gh_io_schema.outputs import normalise_outputs
from ga4gh_io_schema.validator import validate_schema
from ga4gh_io_schema.wes import TranslationError, to_workflow_params

# build_schema, conquest, demo_http and register are the demo scripts, on the
# path through `pythonpath` of pytest (pyproject.toml).
DEMO_DIR = Path(__file__).resolve().parents[1] / "examples" / "demo"

SHA = "0123456789abcdef0123456789abcdef01234567"
SCHEMA = json.loads((DEMO_DIR / "ga4gh-io.schema.json").read_text(encoding="utf-8"))
VALUES = json.loads((DEMO_DIR / "values.json").read_text(encoding="utf-8"))
RUN_LOG = json.loads(
    (DEMO_DIR / "expected" / "run-log.json").read_text(encoding="utf-8")
)
OUTPUTS = json.loads(
    (DEMO_DIR / "expected" / "outputs.json").read_text(encoding="utf-8")
)
RUN_ID = RUN_LOG["run_id"]


@dataclass
class Exchange:
    """A request that the mock server received.

    Attributes:
        method: The HTTP method.
        path: The path, with the query.
        headers: The headers.
        body: The parsed JSON body, if any.
    """

    method: str
    path: str
    headers: dict[str, str]
    body: Any


@dataclass
class Mock:
    """Routes and log of the mock server.

    Attributes:
        routes: Responses by method and path: the status, and the body as
            bytes or a JSON value.
        received: The requests received, in order.
        url: Base URL of the server.
    """

    routes: dict[tuple[str, str], list[tuple[int, Any]]] = field(default_factory=dict)
    received: list[Exchange] = field(default_factory=list)
    url: str = ""

    def add(self, method: str, path: str, status: int, body: Any) -> None:
        """Queue a response; the last one of a route repeats.

        Args:
            method: The HTTP method.
            path: The path.
            status: The status of the response.
            body: The body: bytes as they are, other values as JSON.
        """
        self.routes.setdefault((method, path), []).append((status, body))


@pytest.fixture
def mock() -> Iterator[Mock]:
    """Run a mock HTTP server on a free local port.

    Yields:
        The routes and the log of the server.
    """
    state = Mock()

    class Handler(BaseHTTPRequestHandler):
        """Answers from the routes of the mock."""

        def _answer(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            state.received.append(
                Exchange(
                    self.command,
                    self.path,
                    dict(self.headers.items()),
                    json.loads(raw) if raw else None,
                )
            )
            queue = state.routes.get((self.command, self.path))
            if not queue:
                status, body = 404, {"msg": "not found"}
            else:
                status, body = queue.pop(0) if len(queue) > 1 else queue[0]
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            if status in (301, 302, 307, 308):
                self.send_header("Location", body.decode())
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = _answer

        def log_message(self, format: str, *args: Any) -> None:
            """Don't log requests."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def test_schema_is_generated() -> None:
    """The checked-in schema is what the converter and the overlay give."""
    schema, _notes = build_schema.build()
    assert build_schema.render(schema) == (DEMO_DIR / "ga4gh-io.schema.json").read_text(
        encoding="utf-8"
    )
    assert build_schema.main(["--check"]) == 0


def test_schema_is_valid_and_bound_to_the_descriptor() -> None:
    """The schema complies and names the checksum of ``demo.wdl``."""
    validate_schema(SCHEMA)
    workflow = SCHEMA["x-ga4gh-workflow"]
    digest = hashlib.sha256((DEMO_DIR / "demo.wdl").read_bytes()).hexdigest()
    assert workflow["checksum"] == [{"type": "sha-256", "checksum": digest}]
    assert workflow["primary_descriptor_path"] == "demo.wdl"
    assert workflow["entry_point"] == "io_schema_demo"


def test_check_fails_for_outdated_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--check`` fails if the schema differs or is missing."""
    outdated = tmp_path / "ga4gh-io.schema.json"
    outdated.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(build_schema, "SCHEMA_PATH", outdated)
    assert build_schema.main(["--check"]) == 1
    assert "is outdated" in capsys.readouterr().err
    outdated.unlink()
    assert build_schema.main(["--check"]) == 1


def test_build_prints_notes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Notes of the conversion go to standard error."""
    monkeypatch.setattr(build_schema, "build", lambda: (SCHEMA, ["Note: x (at $)"]))
    assert build_schema.main(["--check"]) == 0
    assert capsys.readouterr().err == "Note: x (at $)\n"


def test_build_writes_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ``--check``, the schema is written."""
    target = tmp_path / "ga4gh-io.schema.json"
    monkeypatch.setattr(build_schema, "SCHEMA_PATH", target)
    assert build_schema.main([]) == 0
    assert json.loads(target.read_text(encoding="utf-8")) == SCHEMA


@pytest.mark.parametrize(
    ("target", "patch", "expected"),
    [
        ({"a": 1, "b": {"c": 2}}, {"b": {"d": 3}}, {"a": 1, "b": {"c": 2, "d": 3}}),
        ({"a": 1, "b": 2}, {"a": None}, {"b": 2}),
        ({"a": [1, 2]}, {"a": [3]}, {"a": [3]}),
        ("text", {"a": 1}, {"a": 1}),
        ({"a": 1}, "text", "text"),
    ],
)
def test_merge_patch(target: Any, patch: Any, expected: Any) -> None:
    """The overlay is applied by the rules of RFC 7396."""
    assert build_schema.merge_patch(target, patch) == expected


def test_values_translate() -> None:
    """The demo values give the qualified ``workflow_params`` of WDL."""
    assert to_workflow_params(SCHEMA, VALUES) == {
        f"io_schema_demo.{name}": value for name, value in VALUES.items()
    }


def test_out_of_range_value_gets_error_message() -> None:
    """A mapping quality out of range gets the schema's message."""
    with pytest.raises(TranslationError) as info:
        to_workflow_params(SCHEMA, {**VALUES, "min_mapq": 61})
    assert info.value.pointer == "/min_mapq"
    assert "whole number from 0 to 60" in str(info.value)


def test_expected_outputs() -> None:
    """The documented outputs are the normalised outputs of the run log."""
    assert normalise_outputs(SCHEMA, RUN_LOG).to_json() == OUTPUTS
    assert OUTPUTS["conformance"] == "conformant"
    assert set(OUTPUTS["outputs"]) == {"filtered_bam", "filtered_bam_index", "report"}


# Registration in TRS-Filer


def test_payload() -> None:
    """The payload follows the TRS convention of the profile."""
    payload = register.build_payload(SHA)
    version = payload["versions"][0]
    workflow = SCHEMA["x-ga4gh-workflow"]
    assert version["id"] == workflow["trs_version_id"]
    assert version["descriptor_type"] == ["WDL"]
    assert version["descriptor_type_version"] == {"WDL": ["1.1"]}
    descriptor, schema_file = version["files"]
    assert descriptor["tool_file"] == {
        "path": "demo.wdl",
        "file_type": "PRIMARY_DESCRIPTOR",
    }
    assert descriptor["type"] == "WDL"
    assert descriptor["file_wrapper"]["checksum"] == workflow["checksum"]
    assert descriptor["file_wrapper"]["url"] == (
        "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/"
        f"{SHA}/examples/demo/demo.wdl"
    )
    assert schema_file["tool_file"] == {
        "path": "ga4gh-io.schema.json",
        "file_type": "OTHER",
    }
    assert schema_file["type"] == "WDL"
    assert json.loads(schema_file["file_wrapper"]["content"]) == SCHEMA


@pytest.mark.parametrize("revision", ["main", SHA[:7], SHA.upper(), SHA + "0"])
def test_revision_must_be_full_sha(revision: str) -> None:
    """Only full commit SHAs are accepted, as Conquest requires."""
    with pytest.raises(ValueError, match="full commit SHA"):
        register.build_payload(revision)


@pytest.mark.parametrize(
    "repository",
    [
        "https://gitlab.com/owner/repo",
        "https://github.com/owner",
        "https://github.com/owner/repo/tree/main",
        "http://github.com/owner/repo",
        "https://github.com/owner/repo.git",
        "https://github.com/../..",
        "https://github.com/owner/..",
        "https://github.com/./repo",
    ],
)
def test_repository_must_be_github_root(repository: str) -> None:
    """Only root URLs of GitHub repositories are accepted."""
    with pytest.raises(ValueError, match="GitHub repository URL"):
        register.build_payload(SHA, repository)


def test_register_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """``--dry-run`` prints the payload and sends nothing."""
    assert register.main(["--revision", SHA, "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out) == register.build_payload(SHA)


def test_register_needs_trs_url(capsys: pytest.CaptureFixture[str]) -> None:
    """Without ``--dry-run``, the TRS URL is required."""
    assert register.main(["--revision", SHA]) == 1
    assert "--trs-url is required" in capsys.readouterr().err


def test_register_rejects_bad_revision(capsys: pytest.CaptureFixture[str]) -> None:
    """A revision that isn't a full SHA is an error."""
    assert register.main(["--revision", "main", "--dry-run"]) == 1
    assert "full commit SHA" in capsys.readouterr().err


def test_register(
    mock: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The tool is created with its ID, with the token from the environment."""
    monkeypatch.setenv("TRS_TOKEN", "secret-token")
    mock.add(
        "PUT", "/ga4gh/trs/v2/tools/ga4gh-io-schema-demo", 200, "ga4gh-io-schema-demo"
    )
    trs_url = f"{mock.url}/ga4gh/trs/v2/"
    assert register.main(["--trs-url", trs_url, "--revision", SHA]) == 0
    (exchange,) = mock.received
    assert exchange.headers["Authorization"] == "Bearer secret-token"
    assert exchange.body == register.build_payload(SHA)
    captured = capsys.readouterr()
    assert captured.out.strip() == (
        f"{mock.url}/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0"
        "/WDL/descriptor/ga4gh-io.schema.json"
    )
    assert "secret-token" not in captured.out + captured.err


def test_register_fails(mock: Mock, capsys: pytest.CaptureFixture[str]) -> None:
    """An error of TRS-Filer is reported, with exit status 1."""
    mock.add("PUT", "/tools/ga4gh-io-schema-demo", 401, {"title": "Unauthorized"})
    assert register.main(["--trs-url", mock.url, "--revision", SHA]) == 1
    assert "HTTP 401" in capsys.readouterr().err


# HTTP


def test_http_rejects_other_schemes() -> None:
    """Only http and https URLs are requested."""
    with pytest.raises(demo_http.HTTPError, match="Not an http or https URL"):
        demo_http.request_json("GET", "file:///etc/passwd")


def test_http_rejects_non_json(mock: Mock) -> None:
    """A response that isn't JSON is an error."""
    mock.add("GET", "/x", 200, b"<html>")
    with pytest.raises(demo_http.HTTPError, match="isn't JSON"):
        demo_http.request_json("GET", f"{mock.url}/x")


def test_http_connection_error() -> None:
    """A failed connection is an error."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    with pytest.raises(demo_http.HTTPError, match=f"GET {url}"):
        demo_http.request_json("GET", url)


def test_http_without_token(mock: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a token, no ``Authorization`` header is sent."""
    monkeypatch.setenv("WES_TOKEN", "")
    mock.add("GET", "/x", 200, {})
    assert demo_http.request_json("GET", f"{mock.url}/x", token_env="WES_TOKEN") == {}
    assert "Authorization" not in mock.received[0].headers


def test_http_token_needs_https(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token isn't sent over plain http, except to loopback hosts."""
    monkeypatch.setenv("TRS_TOKEN", "secret-token")
    with pytest.raises(demo_http.HTTPError, match="Refusing to send the token"):
        demo_http.request_json("GET", "http://trs.example.org/", token_env="TRS_TOKEN")


def test_http_token_not_redirected(mock: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    """The token isn't sent again to the target of a redirect."""
    monkeypatch.setenv("WES_TOKEN", "secret-token")
    mock.add("GET", "/from", 302, f"{mock.url}/to".encode())
    mock.add("GET", "/to", 200, {"ok": True})
    assert demo_http.request_json("GET", f"{mock.url}/from", token_env="WES_TOKEN") == {
        "ok": True
    }
    first, second = mock.received
    assert first.headers["Authorization"] == "Bearer secret-token"
    assert "Authorization" not in second.headers


# Runs on Conquest


def test_engine_parameters() -> None:
    """The repository, the revision and the main workflow are added."""
    request = {"workflow_url": "https://trs.example.org/x", "workflow_type": "WDL"}
    assert conquest.add_engine_parameters(request, SHA) == {
        "workflow_url": "https://github.com/uniqueg/ga4gh-io-schema",
        "workflow_type": "WDL",
        "workflow_engine_parameters": {
            "revision": SHA,
            "main_workflow_path": "examples/demo/demo.wdl",
        },
    }


def test_request_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``request`` reads a run request from a file or standard input."""
    request = {"workflow_type": "WDL", "workflow_params": {"a": 1}}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    assert conquest.main(["request", str(path), "--revision", SHA]) == 0
    from_file = json.loads(capsys.readouterr().out)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    assert conquest.main(["request", "-", "--revision", SHA]) == 0
    assert json.loads(capsys.readouterr().out) == from_file
    assert from_file["workflow_engine_parameters"]["revision"] == SHA


def test_request_command_rejects_bad_revision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed revision is an error, with exit status 1."""
    path = tmp_path / "request.json"
    path.write_text("{}", encoding="utf-8")
    assert conquest.main(["request", str(path), "--revision", "HEAD"]) == 1
    assert "full commit SHA" in capsys.readouterr().err


def test_submit_command(
    mock: Mock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``submit`` posts the request and prints the run ID."""
    mock.add("POST", "/ga4gh/wes/v1/runs", 200, {"run_id": RUN_ID})
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"workflow_type": "WDL"}), encoding="utf-8")
    wes_url = f"{mock.url}/ga4gh/wes/v1"
    assert conquest.main(["submit", str(path), "--wes-url", wes_url]) == 0
    assert capsys.readouterr().out.strip() == RUN_ID
    assert mock.received[0].body == {"workflow_type": "WDL"}
    assert mock.received[0].headers["Content-Type"] == "application/json"


def test_submit_needs_run_id(mock: Mock) -> None:
    """A response without a run ID is an error."""
    mock.add("POST", "/runs", 200, {"msg": "accepted"})
    with pytest.raises(demo_http.HTTPError, match="no run_id"):
        conquest.submit(mock.url, {})


def test_submit_error(
    mock: Mock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rejected request is reported with the server's message."""
    mock.add("POST", "/runs", 400, {"msg": "workflow_url: bad", "status_code": 400})
    path = tmp_path / "request.json"
    path.write_text("{}", encoding="utf-8")
    assert conquest.main(["submit", str(path), "--wes-url", mock.url]) == 1
    assert "HTTP 400" in capsys.readouterr().err


def test_wait(mock: Mock) -> None:
    """``wait`` polls the state until the run has ended."""
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "QUEUED"})
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "RUNNING"})
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "COMPLETE"})
    mock.add("GET", f"/runs/{RUN_ID}", 200, RUN_LOG)
    sleeps: list[float] = []
    assert conquest.wait(mock.url, RUN_ID, interval=2, sleep=sleeps.append) == RUN_LOG
    assert sleeps == [2, 2]


def test_wait_times_out(mock: Mock) -> None:
    """A run that doesn't end in time is an error."""
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "RUNNING"})
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    with pytest.raises(TimeoutError, match="state RUNNING"):
        conquest.wait(
            mock.url, RUN_ID, interval=10, timeout=25, sleep=sleep, clock=lambda: now[0]
        )
    assert now[0] == 20


def test_wait_status_not_object(mock: Mock) -> None:
    """A status that isn't an object counts as not ended."""
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, ["COMPLETE"])
    with pytest.raises(TimeoutError, match="state None"):
        conquest.wait(mock.url, RUN_ID, interval=1, timeout=0)


def test_wait_run_log_not_object(mock: Mock) -> None:
    """A RunLog that isn't an object is an error."""
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "COMPLETE"})
    mock.add("GET", f"/runs/{RUN_ID}", 200, [])
    with pytest.raises(demo_http.HTTPError, match="isn't a JSON object"):
        conquest.wait(mock.url, RUN_ID)


def test_wait_command(mock: Mock, capsys: pytest.CaptureFixture[str]) -> None:
    """``wait`` prints the RunLog."""
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "COMPLETE"})
    mock.add("GET", f"/runs/{RUN_ID}", 200, RUN_LOG)
    assert conquest.main(["wait", RUN_ID, "--wes-url", mock.url]) == 0
    assert json.loads(capsys.readouterr().out) == RUN_LOG


def test_run_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """``run --dry-run`` prints the request that ``wes-params`` and ``request`` give."""
    assert conquest.main(["run", "--dry-run", "--revision", SHA]) == 0
    request = json.loads(capsys.readouterr().out)
    assert request == {
        "workflow_params": {
            f"io_schema_demo.{name}": value for name, value in VALUES.items()
        },
        "workflow_type": "WDL",
        "workflow_type_version": "1.1",
        "workflow_url": "https://github.com/uniqueg/ga4gh-io-schema",
        "workflow_engine_parameters": {
            "revision": SHA,
            "main_workflow_path": "examples/demo/demo.wdl",
        },
    }


def test_run_needs_wes_url(capsys: pytest.CaptureFixture[str]) -> None:
    """Without ``--dry-run``, the WES URL is required."""
    assert conquest.main(["run", "--revision", SHA]) == 1
    assert "--wes-url is required" in capsys.readouterr().err


def test_run_rejects_invalid_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invalid values are reported before anything is sent."""
    values = tmp_path / "values.json"
    values.write_text(json.dumps({**VALUES, "min_mapq": -1}), encoding="utf-8")
    assert (
        conquest.main(["run", "--dry-run", "--revision", SHA, "--values", str(values)])
        == 1
    )
    assert "whole number from 0 to 60" in capsys.readouterr().err


def test_run(mock: Mock, capsys: pytest.CaptureFixture[str]) -> None:
    """``run`` submits, waits and prints the documented outputs."""
    mock.add("POST", "/runs", 200, {"run_id": RUN_ID})
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "COMPLETE"})
    mock.add("GET", f"/runs/{RUN_ID}", 200, RUN_LOG)
    assert conquest.main(["run", "--revision", SHA, "--wes-url", mock.url]) == 0
    assert json.loads(capsys.readouterr().out) == OUTPUTS
    assert mock.received[0].body["workflow_engine_parameters"]["revision"] == SHA


def test_run_sends_wes_token(mock: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Requests to WES carry the token of ``WES_TOKEN``."""
    monkeypatch.setenv("WES_TOKEN", "wes-token")
    mock.add("POST", "/runs", 200, {"run_id": RUN_ID})
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "COMPLETE"})
    mock.add("GET", f"/runs/{RUN_ID}", 200, RUN_LOG)
    assert conquest.main(["run", "--revision", SHA, "--wes-url", mock.url]) == 0
    assert [e.headers["Authorization"] for e in mock.received] == [
        "Bearer wes-token"
    ] * 3


def test_run_failed(mock: Mock, capsys: pytest.CaptureFixture[str]) -> None:
    """A run that fails gets its partial outputs printed, and exit status 1."""
    failed = {**RUN_LOG, "state": "EXECUTOR_ERROR"}
    mock.add("POST", "/runs", 200, {"run_id": RUN_ID})
    mock.add("GET", f"/runs/{RUN_ID}/status", 200, {"state": "EXECUTOR_ERROR"})
    mock.add("GET", f"/runs/{RUN_ID}", 200, failed)
    assert conquest.main(["run", "--revision", SHA, "--wes-url", mock.url]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["conformance"] == "partial"
    assert "ended in state EXECUTOR_ERROR" in captured.err


def test_run_overrides(capsys: pytest.CaptureFixture[str]) -> None:
    """The repository and the main workflow path can be changed."""
    argv = ["run", "--dry-run", "--revision", SHA]
    argv += ["--repository", "https://github.com/fork/repo"]
    argv += ["--main-workflow-path", "demo/main.wdl"]
    assert conquest.main(argv) == 0
    request = json.loads(capsys.readouterr().out)
    assert request["workflow_url"] == "https://github.com/fork/repo"
    assert request["workflow_engine_parameters"]["main_workflow_path"] == (
        "demo/main.wdl"
    )


@pytest.mark.parametrize("content", [None, "{not json"])
def test_request_file_errors(
    tmp_path: Path, content: str | None, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing or invalid request file is an error, with exit status 1."""
    path = tmp_path / "request.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert conquest.main(["request", str(path), "--revision", SHA]) == 1
    assert capsys.readouterr().err.startswith("Error: ")


def test_request_must_be_object(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run request that isn't a JSON object is an error."""
    path = tmp_path / "request.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert conquest.main(["request", str(path), "--revision", SHA]) == 1
    assert "must be a JSON object" in capsys.readouterr().err


def test_run_rejects_invalid_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A schema that doesn't comply with the profile is an error."""
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({**SCHEMA, "type": "array"}), encoding="utf-8")
    argv = ["run", "--dry-run", "--revision", SHA, "--schema", str(schema)]
    assert conquest.main(argv) == 1
    assert capsys.readouterr().err.startswith("Error: ")
