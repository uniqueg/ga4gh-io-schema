# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the host of the form proof of concept (``prototype/host/``).

They cover the path from the values of the form to the WES run request,
the messages of failed validation, and the optional submission to a WES
(a local fake), over HTTP against a local host.
"""

import contextlib
import copy
import email.parser
import email.policy
import http.client
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import form_host
import pytest
import trs_stub

ROOT = Path(__file__).resolve().parents[1]
DEMO_SCHEMA = json.loads(
    (ROOT / "examples" / "demo" / "ga4gh-io.schema.json").read_text(encoding="utf-8")
)
DEMO_VALUES = json.loads(
    (ROOT / "examples" / "demo" / "values.json").read_text(encoding="utf-8")
)
PROFILE = DEMO_SCHEMA["$schema"]
MAPQ_MESSAGE = "The minimum mapping quality is a whole number from 0 to 60"
DEMO_REQUEST = {
    "workflow_params": {
        "io_schema_demo.reads": DEMO_VALUES["reads"],
        "io_schema_demo.min_mapq": 20,
        "io_schema_demo.read_filter": "proper_pairs",
    },
    "workflow_type": "WDL",
    "workflow_type_version": "1.1",
    "workflow_url": "demo.wdl",
}
# The example of "Error messages" in docs/specification/keywords.md
SAMPLES_SCHEMA: dict[str, Any] = {
    "$schema": PROFILE,
    "type": "object",
    "properties": {
        "inputs": {
            "type": "object",
            "properties": {
                "samples": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/sample_id"},
                    "minItems": 1,
                    "x-ga4gh-error-message": "Give at least one sample",
                },
                "control": {
                    "$ref": "#/$defs/sample_id",
                    "x-ga4gh-error-message": "The control is a sample ID such as S1",
                },
            },
            "required": ["samples"],
        }
    },
    "$defs": {
        "sample_id": {
            "type": "string",
            "pattern": "^S[0-9]+$",
            "x-ga4gh-error-message": "Sample IDs are S followed by digits, e.g., S1",
        }
    },
}


@pytest.fixture
def host() -> Iterator[str]:
    """Run the host for the demo schema on a free port.

    Yields:
        The base URL of the host.
    """
    with serve(DEMO_SCHEMA, ["https", "s3"], workflow_url="demo.wdl") as url:
        yield url


@contextlib.contextmanager
def serve(
    schema: dict[str, Any] | None, allowed: Sequence[str] = ("https",), **options: Any
) -> Iterator[str]:
    """Run a host on a free port.

    Args:
        schema: The default IO schema, if any.
        allowed: URI schemes of the allow-list.
        **options: Further arguments of :class:`form_host.FormHost`.

    Yields:
        The base URL of the host.
    """
    server = form_host.FormHost(("127.0.0.1", 0), schema, allowed, **options)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class FakeWes(ThreadingHTTPServer):
    """A fake WES: records requests and answers as configured.

    Attributes:
        url: Base URL of its WES API.
        run_answer: Status and body of the answer to ``POST /runs``.
        status_answer: Status and body of the answer to
            ``GET /runs/{id}/status``.
        fields: The form fields of the last ``POST /runs``.
        paths: The paths of the requests, in order.
    """

    def __init__(self) -> None:
        """Bind to a free port."""
        super().__init__(("127.0.0.1", 0), FakeWesHandler)
        self.url = f"http://127.0.0.1:{self.server_address[1]}/ga4gh/wes/v1"
        self.run_answer: tuple[int, bytes] = (200, b'{"run_id": "run-1"}')
        self.status_answer: tuple[int, bytes] = (
            200,
            b'{"run_id": "run-1", "state": "QUEUED"}',
        )
        self.fields: dict[str, str] = {}
        self.paths: list[str] = []


class FakeWesHandler(BaseHTTPRequestHandler):
    """Requests to the fake WES."""

    server: FakeWes

    def do_POST(self) -> None:  # noqa: N802 - name defined by http.server
        """Record a run request and answer as configured."""
        self.server.paths.append(self.path)
        body = self.rfile.read(int(self.headers["Content-Length"]))
        head = f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode()
        message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            head + body
        )
        self.server.fields = {
            str(part.get_param("name", header="content-disposition")): (
                part.get_content()
            )
            for part in message.iter_parts()
        }
        self._answer(*self.server.run_answer)

    def do_GET(self) -> None:  # noqa: N802 - name defined by http.server
        """Answer with the state of the run, as configured."""
        self.server.paths.append(self.path)
        self._answer(*self.server.status_answer)

    def _answer(self, status: int, data: bytes) -> None:
        """Send a response.

        Args:
            status: HTTP status.
            data: The body.
        """
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def wes() -> Iterator[FakeWes]:
    """Run a fake WES on a free port.

    Yields:
        The fake WES.
    """
    server = FakeWes()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def trs() -> Iterator[str]:
    """Run the TRS stub of the prototype for the demo workflow.

    Yields:
        The base URL of its TRS API.
    """
    with run_stub([trs_stub.load_workflow(ROOT / "examples" / "demo")]) as url:
        yield url


@contextlib.contextmanager
def run_stub(workflows: Sequence[trs_stub.Workflow]) -> Iterator[str]:
    """Run the TRS stub of the prototype on a free port.

    Args:
        workflows: The workflows that it serves.

    Yields:
        The base URL of its TRS API.
    """
    server = trs_stub.TrsStub(("127.0.0.1", 0), workflows)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}{trs_stub.API}"
    finally:
        server.shutdown()
        server.server_close()


def _request(
    url: str,
    body: bytes | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Send a request and return the response, also for error statuses.

    Args:
        url: URL of the request.
        body: Body of the request, if any, sent as JSON.
        method: HTTP method.
        headers: Further headers.

    Returns:
        The status, the headers and the body of the response.
    """
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_demo_values_become_a_run_request() -> None:
    """Test that the values of the demo give the request of the demo docs."""
    request, errors = form_host.check_values(
        DEMO_SCHEMA, DEMO_VALUES, ["https", "s3"], "demo.wdl"
    )
    assert errors == []
    assert request == DEMO_REQUEST


def test_valid_values_without_workflow_url_are_an_error() -> None:
    """Test that a request can't be built without a workflow URL."""
    request, errors = form_host.check_values(DEMO_SCHEMA, DEMO_VALUES, ["https"])
    assert request is None
    assert errors == [{"pointer": "", "message": form_host.NO_WORKFLOW_URL}]


def test_request_needs_the_language_version() -> None:
    """Test that a schema without ``descriptor_type_version`` gets an error."""
    schema = copy.deepcopy(DEMO_SCHEMA)
    del schema["x-ga4gh-workflow"]["descriptor_type_version"]
    request, errors = form_host.check_values(schema, DEMO_VALUES, ["https"], "x")
    assert request is None
    assert "descriptor type version" in errors[0]["message"]


def test_workflow_url_from_trs_or_the_descriptor_path() -> None:
    """Test the workflow URL: in TRS if known, else the descriptor's path."""
    trs = "http://trs:8080/ga4gh/trs/v2/"
    assert form_host.workflow_url(DEMO_SCHEMA, trs) == (
        "http://trs:8080/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0"
        "/PLAIN_WDL/descriptor/demo.wdl"
    )
    assert form_host.workflow_url(DEMO_SCHEMA) == "demo.wdl"
    schema = copy.deepcopy(DEMO_SCHEMA)
    del schema["x-ga4gh-workflow"]["trs_version_id"]
    assert form_host.workflow_url(schema, trs) == "demo.wdl"
    del schema["x-ga4gh-workflow"]["primary_descriptor_path"]
    assert form_host.workflow_url(schema, trs) is None
    assert form_host.workflow_url(SAMPLES_SCHEMA) is None


def test_out_of_range_value_gets_the_schema_message() -> None:
    """Test that a value out of range gets ``x-ga4gh-error-message``."""
    values = {**DEMO_VALUES, "min_mapq": 61}
    params, errors = form_host.check_values(DEMO_SCHEMA, values, url="demo.wdl")
    assert params is None
    assert errors == [{"pointer": "/min_mapq", "message": MAPQ_MESSAGE}]


def test_every_failure_is_reported() -> None:
    """Test that the form gets all failures at once, one per location."""
    values = {"min_mapq": "high", "read_filter": "all", "extra": 1}
    _, errors = form_host.check_values(DEMO_SCHEMA, values)
    assert errors == [
        {"pointer": "", "message": "'reads' is a required property"},
        {
            "pointer": "",
            "message": "Additional properties are not allowed ('extra' was unexpected)",
        },
        {"pointer": "/min_mapq", "message": MAPQ_MESSAGE},
        {
            "pointer": "/read_filter",
            "message": "'all' is not one of ['none', 'proper_pairs', 'primary_only']",
        },
    ]


def test_message_covers_its_own_location_only() -> None:
    """Test the scope of a message: ``samples`` doesn't cover its items."""
    _, errors = form_host.check_values(SAMPLES_SCHEMA, {"samples": []})
    assert errors == [{"pointer": "/samples", "message": "Give at least one sample"}]
    _, errors = form_host.check_values(SAMPLES_SCHEMA, {"samples": ["S1", "x2"]})
    assert errors == [
        {
            "pointer": "/samples/1",
            "message": "Sample IDs are S followed by digits, e.g., S1",
        }
    ]


def test_outermost_message_wins() -> None:
    """Test the precedence: the property's message over the definition's."""
    values = {"samples": ["S1"], "control": "c1"}
    _, errors = form_host.check_values(SAMPLES_SCHEMA, values)
    assert errors == [
        {"pointer": "/control", "message": "The control is a sample ID such as S1"}
    ]


def test_failures_without_message_get_the_validator_message() -> None:
    """Test that a failure no message covers gets the validator's message."""
    _, errors = form_host.check_values(SAMPLES_SCHEMA, {})
    assert errors == [{"pointer": "", "message": "'samples' is a required property"}]


def test_message_in_nested_objects_and_tuples() -> None:
    """Test messages of nested properties, tuple items and in-place schemas."""
    schema = {
        "$schema": PROFILE,
        "$id": "https://example.org/nested.schema.json",
        "type": "object",
        "properties": {
            "inputs": {
                "type": "object",
                "properties": {
                    "options": {
                        "type": "object",
                        "patternProperties": {
                            "^x-": {
                                "type": "string",
                                "x-ga4gh-error-message": "Extensions are strings",
                            }
                        },
                        "additionalProperties": {
                            "allOf": [
                                {
                                    "type": "integer",
                                    "x-ga4gh-error-message": "Options are integers",
                                }
                            ]
                        },
                    },
                    "pair": {
                        "type": "array",
                        "prefixItems": [
                            {"type": "string", "x-ga4gh-error-message": "A name"}
                        ],
                        "items": {"type": "integer"},
                    },
                },
            }
        },
    }
    values = {"options": {"k": "x", "x-y": 1}, "pair": [1, "a"]}
    _, errors = form_host.check_values(schema, values)
    assert errors == [
        {"pointer": "/options/k", "message": "Options are integers"},
        {"pointer": "/options/x-y", "message": "Extensions are strings"},
        {"pointer": "/pair/0", "message": "A name"},
        {"pointer": "/pair/1", "message": "'a' is not of type 'integer'"},
    ]


def test_message_through_conditions_and_embedded_resources() -> None:
    """Test messages behind ``if``, ``dependentSchemas`` and an ``$id``.

    A message is given once per location, however many keywords fail there.
    """
    schema = {
        "$schema": PROFILE,
        "type": "object",
        "properties": {
            "inputs": {
                "type": "object",
                "properties": {
                    "code": {
                        "allOf": [
                            True,
                            {"$ref": "#/$defs/code"},
                            {"$id": "https://example.org/inline.json", "maxLength": 2},
                        ],
                        "$ref": "#/$defs/code",
                    },
                    "mode": {
                        "if": {"const": "fast"},
                        "then": {"x-ga4gh-error-message": "Fast mode is a string"},
                        "not": {"type": "integer"},
                    },
                    "deps": {
                        "dependentSchemas": {
                            "a": {"x-ga4gh-error-message": "Needs b with a"}
                        },
                        "required": ["b"],
                    },
                    "list": {"type": "array", "maxItems": 0},
                },
            }
        },
        "$defs": {
            "code": {
                "$id": "https://example.org/code.schema.json",
                "type": "string",
                "pattern": "^[A-Z]+$",
                "maxLength": 2,
                "x-ga4gh-error-message": "Codes are up to 2 capitals",
            }
        },
    }
    values = {"code": "abc", "mode": 1, "deps": {"a": 1}, "list": [1]}
    _, errors = form_host.check_values(schema, values)
    assert errors == [
        {"pointer": "/code", "message": "Codes are up to 2 capitals"},
        {"pointer": "/deps", "message": "Needs b with a"},
        {"pointer": "/list", "message": "[1] is expected to be empty"},
        {"pointer": "/mode", "message": "Fast mode is a string"},
    ]
    assert (
        form_host.error_message((schema["properties"]["inputs"], None), ["list", 0])
        is None
    )


def test_pointer_escapes_special_characters() -> None:
    """Test that keys with ``/`` and ``~`` are escaped in pointers."""
    schema = {
        "$schema": PROFILE,
        "type": "object",
        "properties": {
            "inputs": {"type": "object", "properties": {"a/b~": {"type": "string"}}}
        },
    }
    _, errors = form_host.check_values(schema, {"a/b~": 1})
    assert errors[0]["pointer"] == "/a~1b~0"


def test_file_reference_rules_are_checked() -> None:
    """Test that a file reference with a scheme not allowed is an error."""
    values = {**DEMO_VALUES, "reads": "ftp://example.org/reads.bam"}
    params, errors = form_host.check_values(DEMO_SCHEMA, values, url="demo.wdl")
    assert params is None
    assert errors[0]["pointer"] == "/reads"
    assert "ftp" in errors[0]["message"]


def test_unresolvable_reference_is_an_error() -> None:
    """Test that a reference out of the schema is reported, not fetched."""
    schema = copy.deepcopy(SAMPLES_SCHEMA)
    schema["$defs"]["sample_id"] = {"$ref": "https://example.org/missing.json"}
    _, errors = form_host.check_values(schema, {"samples": ["S1"]})
    assert errors == [
        {
            "pointer": "",
            "message": "The schema references 'https://example.org/missing.json', "
            "which can't be resolved.",
        }
    ]


def test_host_serves_the_form(host: str) -> None:
    """Test that the host serves the page, its files and the schema."""
    status, headers, body = _request(f"{host}/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["Content-Security-Policy"] == "default-src 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert b"<io-schema-form>" in body
    for path in ("/app.js", "/form.js", "/io-schema-form.js", "/form.css"):
        status, _, body = _request(f"{host}{path}")
        assert status == 200
        assert body
    status, _, body = _request(f"{host}/api/schema?x=1")
    assert status == 200
    assert json.loads(body) == DEMO_SCHEMA


def test_host_rejects_unknown_paths(host: str) -> None:
    """Test that other paths are not found, also outside the form's files."""
    for path in ("/../form_host.py", "/form_host.py", "/api/nothing"):
        status, _, _ = _request(f"{host}{path}")
        assert status == 404
    status, _, _ = _request(f"{host}/api/schema", b"{}", "POST")
    assert status == 404


def test_host_returns_the_run_request(host: str) -> None:
    """Test the values-to-request path over HTTP."""
    body = json.dumps(DEMO_VALUES).encode()
    status, _, response = _request(f"{host}/api/params", body, "POST")
    assert status == 200
    assert json.loads(response) == {"run_request": DEMO_REQUEST}


def test_host_without_wes_sends_nothing(host: str) -> None:
    """Test that without a WES the page offers no submission, and none is made."""
    status, _, response = _request(f"{host}/api/config")
    assert (status, json.loads(response)) == (200, {"wes": False})
    body = json.dumps(DEMO_VALUES).encode()
    status, _, response = _request(f"{host}/api/runs", body, "POST")
    assert status == 404
    assert json.loads(response) == {
        "errors": [{"pointer": "", "message": "No WES is configured."}]
    }


def test_host_submits_to_the_wes(wes: FakeWes) -> None:
    """Test that with a WES the request is posted there, as WES form fields."""
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=f"{wes.url}/") as host:
        status, _, response = _request(f"{host}/api/config")
        assert json.loads(response) == {"wes": True}
        body = json.dumps(DEMO_VALUES).encode()
        status, _, response = _request(f"{host}/api/runs", body, "POST")
    assert status == 200
    assert json.loads(response) == {
        "run_request": DEMO_REQUEST,
        "run_id": "run-1",
        "state": "QUEUED",
    }
    assert wes.paths == ["/ga4gh/wes/v1/runs", "/ga4gh/wes/v1/runs/run-1/status"]
    assert wes.fields == {
        "workflow_params": json.dumps(DEMO_REQUEST["workflow_params"]),
        "workflow_type": "WDL",
        "workflow_type_version": "1.1",
        "workflow_url": "demo.wdl",
    }


@pytest.mark.parametrize("answer", [(500, b"{}"), (200, b"no JSON")])
def test_host_reports_a_run_without_state(
    wes: FakeWes, answer: tuple[int, bytes]
) -> None:
    """Test that a run whose state can't be read is reported with its id."""
    wes.status_answer = answer
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=wes.url) as host:
        body = json.dumps(DEMO_VALUES).encode()
        status, _, response = _request(f"{host}/api/runs", body, "POST")
    assert status == 200
    assert json.loads(response)["run_id"] == "run-1"
    assert json.loads(response)["state"] is None


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ((500, b"{}"), "HTTP Error 500"),
        ((404, b"{}"), "HTTP Error 404"),
        ((200, b"<html>"), "Expecting value"),
        ((200, b"[]"), "The answer has no run_id."),
    ],
)
def test_host_reports_failures_of_the_wes(
    wes: FakeWes, answer: tuple[int, bytes], reason: str
) -> None:
    """Test that a WES that rejects the run, or answers no run, is a 502."""
    wes.run_answer = answer
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=wes.url) as host:
        body = json.dumps(DEMO_VALUES).encode()
        status, _, response = _request(f"{host}/api/runs", body, "POST")
        assert status == 502
        message = json.loads(response)["errors"][0]["message"]
        assert message.startswith(f"The WES at {wes.url} failed: {reason}")
        # Invalid values are rejected before anything is sent
        status, _, response = _request(f"{host}/api/runs", b"{}", "POST")
        assert status == 400
    assert wes.paths == ["/ga4gh/wes/v1/runs"]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Content-Type": "text/plain;charset=UTF-8"}, 415),
        ({"Content-Type": "application/x-www-form-urlencoded"}, 415),
        ({"Host": "attacker.example:8000"}, 403),
        ({"Origin": "https://evil.example"}, 403),
        ({"Host": "localhost:8000", "Origin": "http://localhost:8000"}, 200),
        ({"Content-Type": "Application/JSON; charset=utf-8"}, 200),
    ],
)
def test_host_takes_only_json_from_its_own_pages(
    wes: FakeWes, headers: dict[str, str], expected: int
) -> None:
    """Test that other web pages can't make the host submit runs."""
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=wes.url) as host:
        body = json.dumps(DEMO_VALUES).encode()
        for path in ("/api/params", "/api/runs"):
            status, _, _ = _request(f"{host}{path}", body, "POST", headers)
            assert status == expected
    assert len(wes.paths) == (2 if expected == 200 else 0)


def test_host_accepts_its_own_address() -> None:
    """Test that a host bound to an address takes requests for that address."""
    server = form_host.FormHost(("127.0.0.1", 0), DEMO_SCHEMA, ["https"], "x")
    port = server.server_address[1]
    # Stands in for --host 192.0.2.1: binding an address of the network
    # isn't possible everywhere tests run
    server.server_address = ("192.0.2.1", port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{port}/api/params"
        body = json.dumps(DEMO_VALUES).encode()
        headers = {"Host": f"192.0.2.1:{port}"}
        assert _request(url, body, "POST", headers)[0] == 200
        headers = {"Host": f"192.0.2.2:{port}"}
        assert _request(url, body, "POST", headers)[0] == 403
    finally:
        server.shutdown()
        server.server_close()


def test_submit_needs_a_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a WES answer without ``run_id`` is an error."""

    def answer(*args: Any) -> Any:
        return {"msg": "no run"}

    monkeypatch.setattr(form_host, "_fetch_json", answer)
    with pytest.raises(ValueError, match="no run_id"):
        form_host.submit_run("http://wes", DEMO_REQUEST)


def test_host_returns_errors(host: str) -> None:
    """Test that invalid values get status 400 and the messages."""
    body = json.dumps({**DEMO_VALUES, "min_mapq": 99}).encode()
    status, _, response = _request(f"{host}/api/params", body, "POST")
    assert status == 400
    assert json.loads(response) == {
        "errors": [{"pointer": "/min_mapq", "message": MAPQ_MESSAGE}]
    }


def test_host_rejects_bad_bodies(host: str) -> None:
    """Test bodies that aren't JSON, and bodies that are too large."""
    status, _, response = _request(f"{host}/api/params", b"{", "POST")
    assert status == 400
    assert json.loads(response)["errors"][0]["message"] == "The values aren't JSON."
    deep = b"[" * 100_000
    status, _, response = _request(f"{host}/api/params", deep, "POST")
    assert status == 400
    # Only the announced length counts: the host answers without reading
    for length, expected in (
        (str(form_host.MAX_BODY + 1), 413),
        ("-1", 400),
        ("abc", 400),
    ):
        connection = http.client.HTTPConnection(urllib.parse.urlsplit(host).netloc)
        connection.putrequest("POST", "/api/params")
        connection.putheader("Content-Length", length)
        connection.endheaders()
        assert connection.getresponse().status == expected
        connection.close()


def test_host_rejects_values_nested_too_deeply(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that values that parse but are too deep for validation get 400."""

    def too_deep(*args: Any) -> None:
        raise RecursionError

    monkeypatch.setattr(form_host, "check_values", too_deep)
    for path in ("/api/params", "/api/runs"):
        status, _, response = _request(f"{host}{path}", b"{}", "POST")
        assert status == 400
        message = json.loads(response)["errors"][0]["message"]
        assert message == "The values are nested too deeply."


def test_load_schema_from_a_file() -> None:
    """Test that a schema file is read and validated."""
    path = ROOT / "examples" / "demo" / "ga4gh-io.schema.json"
    assert form_host.load_schema(str(path)) == DEMO_SCHEMA


def test_load_schema_from_trs(host: str) -> None:
    """Test a schema from a URL: as it is, or in a TRS ``FileWrapper``."""
    # A host serves its schema, as it is, at /api/schema; a second one
    # serves a FileWrapper there, as TRS does
    assert form_host.load_schema(f"{host}/api/schema") == DEMO_SCHEMA
    wrapper = {"content": json.dumps(DEMO_SCHEMA), "checksum": []}
    server = form_host.FormHost(("127.0.0.1", 0), wrapper)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api/schema"
        assert form_host.load_schema(url) == DEMO_SCHEMA
        server.schema = {"url": "https://example.org/schema.json"}
        with pytest.raises(ValueError, match="no FileWrapper"):
            form_host.load_schema(url)
    finally:
        server.shutdown()
        server.server_close()


def test_main_serves_until_interrupted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``main`` starts the host and stops on Ctrl+C."""

    def interrupt(self: form_host.FormHost) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(form_host.FormHost, "serve_forever", interrupt)
    assert form_host.main(["--port", "0", "--allow-scheme", "https"]) == 0
    out = capsys.readouterr().out
    assert "Serving the form on http://127.0.0.1:" in out
    assert "workflow URL: demo.wdl" in out
    assert "No WES configured: run requests are shown, not sent." in out
    demo = str(ROOT / "examples" / "demo" / "ga4gh-io.schema.json")
    argv = ["--port", "0", "--schema", demo, "--trs-url", "http://trs/ga4gh/trs/v2"]
    assert form_host.main([*argv, "--wes-url", "http://wes/ga4gh/wes/v1"]) == 0
    out = capsys.readouterr().out
    assert "workflow URL: http://trs/ga4gh/trs/v2/tools/" in out
    assert "Run requests are sent to http://wes/ga4gh/wes/v1" in out


def test_main_needs_a_trs_url_for_a_wes() -> None:
    """Test that a WES can't get a workflow URL that it can't fetch."""
    with pytest.raises(SystemExit) as exc:
        form_host.main(["--wes-url", "http://wes/ga4gh/wes/v1"])
    assert exc.value.code == 2


@pytest.mark.parametrize("option", ["--trs-url", "--wes-url"])
def test_main_rejects_urls_that_arent_http(option: str) -> None:
    """Test that TRS and WES URLs must be http(s) URLs."""
    with pytest.raises(SystemExit) as exc:
        form_host.main([option, "file:///etc/passwd"])
    assert exc.value.code == 2


@pytest.mark.parametrize("option", ["--trs-url", "--wes-url"])
def test_main_rejects_urls_with_user_information(
    option: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a password in a URL can't reach error messages.

    Args:
        option: The option of the URL.
        capsys: Captures the error message.
    """
    with pytest.raises(SystemExit) as exc:
        form_host.main([option, "https://user:secret@trs.example.org/ga4gh"])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "user information" in error
    assert "secret" not in error


def test_host_rejects_answers_that_are_too_large(
    wes: FakeWes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the host reads at most MAX_ANSWER bytes of an answer.

    Args:
        wes: The fake WES.
        monkeypatch: Lowers the limit.
    """
    monkeypatch.setattr(form_host, "MAX_ANSWER", 64)
    wes.run_answer = (200, json.dumps({"run_id": "r" * 64}).encode())
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=wes.url) as host:
        body = json.dumps(DEMO_VALUES).encode()
        status, _, response = _request(f"{host}/api/runs", body, "POST")
    assert status == 502
    message = json.loads(response)["errors"][0]["message"]
    assert message.endswith("The answer is larger than 64 bytes.")
    # An answer of the limit is read
    wes.run_answer = (200, b'{"run_id": "run-1"}'.ljust(64))
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=wes.url) as host:
        status, _, response = _request(f"{host}/api/runs", body, "POST")
    assert status == 200


def test_schemas_from_urls_are_read_up_to_the_limit(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    """Test that a schema from a URL is read up to MAX_ANSWER bytes.

    Args:
        monkeypatch: Lowers the limit.
        host: Base URL of a host that serves the demo schema.
    """
    monkeypatch.setattr(form_host, "MAX_ANSWER", 64)
    with pytest.raises(ValueError, match="larger than 64 bytes"):
        form_host.load_schema(f"{host}/api/schema")


def test_answers_are_not_read_past_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the host reads at most one byte more than MAX_ANSWER.

    Args:
        monkeypatch: Lowers the limit.
    """
    monkeypatch.setattr(form_host, "MAX_ANSWER", 64)
    answer = io.BytesIO(b"x" * 1000)

    with pytest.raises(ValueError, match="larger than 64 bytes"):
        form_host._read_answer(answer)
    assert answer.tell() == 65


def test_empty_wes_url_is_no_wes() -> None:
    """Test that an empty WES URL (as Docker Compose passes it) means none."""
    assert form_host._parser().parse_args(["--wes-url", ""]).wes_url is None


def test_main_rejects_bad_schemas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``main`` exits with 1 if the schema can't be used."""
    bad = tmp_path / "bad.schema.json"
    bad.write_text(json.dumps({"$schema": PROFILE}), encoding="utf-8")
    assert form_host.main(["--schema", str(bad)]) == 1
    assert "Can't use the schema" in capsys.readouterr().err
    assert form_host.main(["--schema", str(tmp_path / "missing.json")]) == 1


def test_main_rejects_a_bad_primary_descriptor_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a path with ``..`` can't go into a TRS workflow URL."""
    schema = copy.deepcopy(DEMO_SCHEMA)
    schema["x-ga4gh-workflow"]["primary_descriptor_path"] = "../demo.wdl"
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    argv = ["--schema", str(path), "--trs-url", "http://trs/ga4gh/trs/v2"]
    assert form_host.main(argv) == 1
    assert "primary descriptor path" in capsys.readouterr().err


def test_main_rejects_forbidden_schemes() -> None:
    """Test that schemes that can't be allowed are an argument error."""
    with pytest.raises(SystemExit) as exc:
        form_host.main(["--allow-scheme", "JavaScript"])
    assert exc.value.code == 2


def test_patterns_are_ecma_262() -> None:
    r"""Test ECMA-262 patterns: ``\p{L}`` works, ``$`` rejects a newline."""
    schema = copy.deepcopy(SAMPLES_SCHEMA)
    inputs = schema["properties"]["inputs"]
    inputs["properties"] = {
        "name": {"type": "string", "pattern": r"^\p{L}+$"},
        "tag": {"type": "string", "pattern": "^[a-z]+$"},
    }
    inputs.pop("required", None)

    _, errors = form_host.check_values(schema, {"name": "äbc", "tag": "abc\n"})

    assert [error["pointer"] for error in errors] == ["/tag"]


@pytest.mark.parametrize(
    ("tag", "value", "message"),
    [
        ({"type": "string", "pattern": "("}, "a", "isn't a valid ECMA-262"),
        (
            {
                "type": "object",
                "patternProperties": {"(": True},
                "unevaluatedProperties": False,
            },
            {"a": 1},
            "isn't a valid ECMA-262",
        ),
    ],
)
def test_invalid_pattern_is_an_error(
    tag: dict[str, Any], value: Any, message: str
) -> None:
    """Test that an invalid pattern is reported, not raised.

    Args:
        tag: The schema of the input.
        value: The value of the input.
        message: Part of the expected message.
    """
    schema = copy.deepcopy(SAMPLES_SCHEMA)
    inputs = schema["properties"]["inputs"]
    inputs["properties"] = {"tag": tag}
    inputs.pop("required", None)

    _, errors = form_host.check_values(schema, {"tag": value})

    assert errors[0]["pointer"] == ""
    assert message in errors[0]["message"]


DEMO_PICK = "tool=ga4gh-io-schema-demo&version=1.0.0&type=WDL"
DEMO_ENTRY = {
    "tool_id": "ga4gh-io-schema-demo",
    "version_id": "1.0.0",
    "descriptor_type": "WDL",
    "name": "I/O Schema demo",
}


def test_list_workflows(trs: str) -> None:
    """Test that the tool versions of a TRS are listed, per descriptor type."""
    assert form_host.list_workflows(trs) == [DEMO_ENTRY]


def test_list_workflows_needs_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that an answer that isn't a list of tools is an error."""
    answers: list[Any] = [
        {"id": "x"},
        [{"versions": []}],
        [{"id": "x", "versions": [1]}],
    ]
    for answer in answers:
        monkeypatch.setattr(form_host, "_fetch_json", lambda *a, answer=answer: answer)
        with pytest.raises(ValueError, match="list of tools"):
            form_host.list_workflows("http://trs")


def test_load_trs_schema(trs: str) -> None:
    """Test that the schema is found next to the primary descriptor in TRS."""
    schema, url = form_host.load_trs_schema(trs, "ga4gh-io-schema-demo", "1.0.0", "WDL")
    assert schema == DEMO_SCHEMA
    assert url == (
        f"{trs}/tools/ga4gh-io-schema-demo/versions/1.0.0/PLAIN_WDL/descriptor/demo.wdl"
    )


def test_load_trs_schema_checks_the_workflow_block() -> None:
    """Test that a schema of another tool version or type is rejected."""
    demo = trs_stub.load_workflow(ROOT / "examples" / "demo")
    other = trs_stub.Workflow(**{**demo.__dict__, "tool_id": "other"})
    with run_stub([other]) as base:
        with pytest.raises(ValueError, match="trs_tool_id"):
            form_host.load_trs_schema(base, "other", "1.0.0", "WDL")
        with pytest.raises(OSError):
            form_host.load_trs_schema(base, "other", "1.0.0", "CWL")


def test_load_trs_schema_without_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a descriptor that can't be fetched leaves the schema unverified.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
    """
    demo = trs_stub.load_workflow(ROOT / "examples" / "demo")
    fetch = form_host._fetch_json
    failed: list[str] = []

    def fail_on_descriptor(request: urllib.request.Request) -> Any:
        """Fail on the primary descriptor, fetch anything else.

        Args:
            request: The request.

        Returns:
            The parsed answer.

        Raises:
            ValueError: For the primary descriptor, as for an answer that
                isn't JSON.
        """
        if request.full_url.endswith("/descriptor"):
            failed.append(request.full_url)
            raise ValueError("not JSON")
        return fetch(request)

    monkeypatch.setattr(form_host, "_fetch_json", fail_on_descriptor)
    with run_stub([demo]) as base:
        schema, _ = form_host.load_trs_schema(
            base, demo.tool_id, demo.version_id, "WDL"
        )

    assert failed
    assert schema["x-ga4gh-workflow"]["trs_version_id"] == demo.version_id


def test_load_trs_schema_checks_the_checksum() -> None:
    """Test that a schema whose descriptor changed since is rejected (#85)."""
    demo = trs_stub.load_workflow(ROOT / "examples" / "demo")
    files = {**demo.files, demo.primary: ("PRIMARY_DESCRIPTOR", "version 1.1\n")}
    drifted = trs_stub.Workflow(**{**demo.__dict__, "files": files})
    with run_stub([drifted]) as base:
        with pytest.raises(ValueError, match=r"checksum \(sha-256\)"):
            form_host.load_trs_schema(base, demo.tool_id, demo.version_id, "WDL")


def test_load_trs_schema_takes_entries_with_more_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that entries with more or fewer fields are matched by path and type."""
    checksum = [{"checksum": "0" * 64, "type": "sha-256"}]
    files = [
        {"path": "README.md"},
        {"path": "main.wdl", "file_type": "PRIMARY_DESCRIPTOR", "checksum": checksum},
        {"path": "ga4gh-io.schema.json", "file_type": "OTHER", "checksum": checksum},
    ]
    monkeypatch.setattr(form_host, "_fetch_json", lambda *args: files)
    sources: list[Any] = []

    def load_schema(source: Any) -> dict[str, Any]:
        sources.append(source)
        return {}

    monkeypatch.setattr(form_host, "load_schema", load_schema)
    _, url = form_host.load_trs_schema("http://trs", "t", "v", "WDL")
    assert sources == [
        "http://trs/tools/t/versions/v/WDL/descriptor/ga4gh-io.schema.json"
    ]
    assert url == "http://trs/tools/t/versions/v/PLAIN_WDL/descriptor/main.wdl"


@pytest.mark.parametrize(
    ("primary", "suffix"),
    [
        ("./main.wdl", "/main.wdl"),
        ("wdl//main.wdl", "/wdl/main.wdl"),
        ("/main.wdl", ""),
        ("../main.wdl", ""),
    ],
)
def test_load_trs_schema_normalises_the_primary_descriptor_path(
    monkeypatch: pytest.MonkeyPatch, primary: str, suffix: str
) -> None:
    """Test that the workflow URL takes the normalised primary descriptor path.

    A leading ``/`` gives the URL without a path, as does a path with
    ``..``, which isn't usable; the schema is of type ``IO_SCHEMA``, which
    is found whatever the path of the primary descriptor.

    Args:
        monkeypatch: Pytest fixture.
        primary: The path of the primary descriptor, as listed.
        suffix: The end of the expected URL after ``.../descriptor``.
    """
    files = [
        {"path": primary, "file_type": "PRIMARY_DESCRIPTOR"},
        {"path": "ga4gh-io.schema.json", "file_type": "IO_SCHEMA"},
    ]
    monkeypatch.setattr(form_host, "_fetch_json", lambda *args: files)
    monkeypatch.setattr(form_host, "load_schema", lambda source: {})
    _, url = form_host.load_trs_schema("http://trs", "t", "v", "WDL")
    assert url == f"http://trs/tools/t/versions/v/PLAIN_WDL/descriptor{suffix}"


def test_load_trs_schema_names_a_nested_primary_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the workflow URL of a primary descriptor in a directory.

    The URL ends in the path that TRS lists, so that a relative import of a
    multi-file workflow resolves to a file of the tool version.
    """
    files = [
        {"path": "workflows/main.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
        {"path": "workflows/tasks/sub.wdl", "file_type": "SECONDARY_DESCRIPTOR"},
        {"path": "workflows/ga4gh-io.schema.json", "file_type": "OTHER"},
    ]
    monkeypatch.setattr(form_host, "_fetch_json", lambda *args: files)
    monkeypatch.setattr(form_host, "load_schema", lambda source: {})
    _, url = form_host.load_trs_schema("http://trs", "t", "v", "WDL")
    assert url == (
        "http://trs/tools/t/versions/v/PLAIN_WDL/descriptor/workflows/main.wdl"
    )
    assert urllib.parse.urljoin(url, "tasks/sub.wdl") == (
        "http://trs/tools/t/versions/v/PLAIN_WDL/descriptor/workflows/tasks/sub.wdl"
    )


def test_load_trs_schema_prefers_the_io_schema_file_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a file of type IO_SCHEMA wins, fetched by its path as listed."""
    files = [
        {"path": "main.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
        {"path": "ga4gh-io.schema.json", "file_type": "OTHER"},
        {"path": "./io/inputs.json", "file_type": "IO_SCHEMA"},
    ]
    monkeypatch.setattr(form_host, "_fetch_json", lambda *args: files)
    sources: list[Any] = []

    def load_schema(source: Any) -> dict[str, Any]:
        sources.append(source)
        return {}

    monkeypatch.setattr(form_host, "load_schema", load_schema)
    _, url = form_host.load_trs_schema("http://trs", "t", "v", "WDL")
    assert sources == [
        "http://trs/tools/t/versions/v/WDL/descriptor/.%2Fio%2Finputs.json"
    ]
    assert url == "http://trs/tools/t/versions/v/PLAIN_WDL/descriptor/main.wdl"


def test_load_trs_schema_without_primary_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that an IO_SCHEMA file without primary descriptor gives a bare URL."""
    files = [{"path": "ga4gh-io.schema.json", "file_type": "IO_SCHEMA"}]
    monkeypatch.setattr(form_host, "_fetch_json", lambda *args: files)
    monkeypatch.setattr(form_host, "load_schema", lambda source: {})
    _, url = form_host.load_trs_schema("http://trs", "t", "v", "WDL")
    assert url == "http://trs/tools/t/versions/v/PLAIN_WDL/descriptor"


@pytest.mark.parametrize("ids", [("..", "v", "WDL"), ("t", ".", "WDL"), ("t", "v", "")])
def test_load_trs_schema_rejects_dot_ids(ids: tuple[str, str, str]) -> None:
    """Test that ids that would change the path of the TRS URL are rejected."""
    with pytest.raises(ValueError, match="aren't allowed"):
        form_host.load_trs_schema("http://trs", *ids)


def test_load_trs_schema_needs_a_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a tool version without IO schema is an error."""
    files = [
        {"path": "main.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
        {"path": "other/ga4gh-io.schema.json", "file_type": "OTHER"},
    ]
    monkeypatch.setattr(form_host, "_fetch_json", lambda *args: files)
    with pytest.raises(ValueError, match="no IO schema"):
        form_host.load_trs_schema("http://trs", "t", "v", "WDL")
    for answer in (
        {"x": 1},
        [{"path": "main.wdl", "file_type": "PRIMARY_DESCRIPTOR"}, 1],
    ):
        monkeypatch.setattr(form_host, "_fetch_json", lambda *a, answer=answer: answer)
        with pytest.raises(ValueError, match="no IO schema"):
            form_host.load_trs_schema("http://trs", "t", "v", "WDL")


def test_host_picks_a_workflow_from_trs(trs: str) -> None:
    """Test the path of the prototype: pick in TRS, fill in, get the request."""
    with serve(None, ["https", "s3"], trs_url=trs) as host:
        status, _, response = _request(f"{host}/api/config")
        assert json.loads(response) == {"wes": False, "workflows": [DEMO_ENTRY]}
        status, _, response = _request(f"{host}/api/schema")
        assert status == 404
        assert "Pick a workflow" in json.loads(response)["errors"][0]["message"]
        status, _, response = _request(f"{host}/api/schema?{DEMO_PICK}")
        assert (status, json.loads(response)) == (200, DEMO_SCHEMA)
        body = json.dumps(DEMO_VALUES).encode()
        status, _, response = _request(f"{host}/api/params?{DEMO_PICK}", body, "POST")
        assert status == 200
        request = json.loads(response)["run_request"]
        assert request == {
            **DEMO_REQUEST,
            "workflow_url": f"{trs}/tools/ga4gh-io-schema-demo/versions/1.0.0"
            "/PLAIN_WDL/descriptor/demo.wdl",
        }
        status, _, _ = _request(f"{host}/api/params", body, "POST")
        assert status == 404


def test_host_reports_failures_of_the_trs(trs: str) -> None:
    """Test that a workflow that can't be loaded from TRS is a 502."""
    with serve(None, trs_url=trs) as host:
        query = "tool=unknown&version=1.0.0&type=WDL"
        status, _, response = _request(f"{host}/api/schema?{query}")
        assert status == 502
        message = json.loads(response)["errors"][0]["message"]
        assert message.startswith(f"Can't load the workflow from {trs}: ")
        status, _, _ = _request(f"{host}/api/schema?tool=x")
        assert status == 404
    with serve(None, trs_url="http://127.0.0.1:9/ga4gh/trs/v2") as host:
        status, _, response = _request(f"{host}/api/config")
    assert status == 200
    config = json.loads(response)
    assert config["workflows"] == []
    assert config["trs_error"].startswith("Can't list the workflows")


def test_host_answers_api_reads_for_its_own_pages_only(host: str) -> None:
    """Test that other hosts (DNS rebinding) can't read the API."""
    headers = {"Host": "attacker.example"}
    for path in ("/api/config", "/api/schema"):
        assert _request(f"{host}{path}", headers=headers)[0] == 403
    assert _request(f"{host}/", headers=headers)[0] == 200


def test_host_without_trs_has_no_picker(host: str) -> None:
    """Test that without a TRS the page gets no list and the query is ignored."""
    status, _, response = _request(f"{host}/api/config")
    assert json.loads(response) == {"wes": False}
    status, _, response = _request(f"{host}/api/schema?{DEMO_PICK}")
    assert (status, json.loads(response)) == (200, DEMO_SCHEMA)


def test_main_with_trs_needs_no_schema(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that with a TRS URL and no schema, workflows are picked in TRS."""

    def interrupt(self: form_host.FormHost) -> None:
        assert self.schema is None
        assert self.trs_url == "http://trs/ga4gh/trs/v2"
        raise KeyboardInterrupt

    monkeypatch.setattr(form_host.FormHost, "serve_forever", interrupt)
    argv = ["--port", "0", "--trs-url", "http://trs/ga4gh/trs/v2"]
    assert form_host.main([*argv, "--wes-url", "http://wes/ga4gh/wes/v1"]) == 0
    out = capsys.readouterr().out
    assert "Workflows are picked from http://trs/ga4gh/trs/v2" in out
