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
    schema: dict[str, Any], allowed: Sequence[str] = ("https",), **options: Any
) -> Iterator[str]:
    """Run a host on a free port.

    Args:
        schema: The IO schema.
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


class FakeWes(BaseHTTPRequestHandler):
    """A fake WES: records ``POST /runs`` and answers with fixed responses.

    The class attributes configure the answers and record the requests.
    """

    #: Status of ``POST /runs``, and of ``GET /runs/{id}/status``.
    run_status = 200
    status_status = 200
    #: The form fields of the last ``POST /runs``.
    fields: dict[str, str] = {}

    def do_POST(self) -> None:  # noqa: N802 - name defined by http.server
        """Record a run request and answer with a run id."""
        body = self.rfile.read(int(self.headers["Content-Length"]))
        head = f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode()
        message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            head + body
        )
        FakeWes.fields = {
            part.get_param("name", header="content-disposition"): part.get_content()
            for part in message.iter_parts()
        }
        assert self.path == "/ga4gh/wes/v1/runs"
        self._answer(self.run_status, {"run_id": "run-1"})

    def do_GET(self) -> None:  # noqa: N802 - name defined by http.server
        """Answer with the state of the run."""
        assert self.path == "/ga4gh/wes/v1/runs/run-1/status"
        self._answer(self.status_status, {"run_id": "run-1", "state": "QUEUED"})

    def _answer(self, status: int, body: Any) -> None:
        """Send a JSON response.

        Args:
            status: HTTP status.
            body: The body, unless the status is an error.
        """
        data = json.dumps(body if status == 200 else {"msg": "fail"}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def wes() -> Iterator[str]:
    """Run a fake WES on a free port.

    Yields:
        The base URL of its WES API.
    """
    FakeWes.run_status = FakeWes.status_status = 200
    FakeWes.fields = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeWes)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/ga4gh/wes/v1"
    finally:
        server.shutdown()
        server.server_close()


def _request(
    url: str, body: bytes | None = None, method: str = "GET"
) -> tuple[int, dict[str, str], bytes]:
    """Send a request and return the response, also for error statuses.

    Args:
        url: URL of the request.
        body: Body of the request, if any.
        method: HTTP method.

    Returns:
        The status, the headers and the body of the response.
    """
    request = urllib.request.Request(url, data=body, method=method)
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
        "/PLAIN_WDL/descriptor"
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


def test_host_submits_to_the_wes(wes: str) -> None:
    """Test that with a WES the request is posted there, as WES form fields."""
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=f"{wes}/") as host:
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
    assert FakeWes.fields == {
        "workflow_params": json.dumps(DEMO_REQUEST["workflow_params"]),
        "workflow_type": "WDL",
        "workflow_type_version": "1.1",
        "workflow_url": "demo.wdl",
    }


def test_host_reports_a_run_without_state(wes: str) -> None:
    """Test that a run whose state can't be read is reported with its id."""
    FakeWes.status_status = 500
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=wes) as host:
        body = json.dumps(DEMO_VALUES).encode()
        status, _, response = _request(f"{host}/api/runs", body, "POST")
    assert status == 200
    assert json.loads(response)["run_id"] == "run-1"
    assert json.loads(response)["state"] is None


def test_host_reports_failures_of_the_wes(wes: str) -> None:
    """Test that a WES that rejects the run, or answers no JSON, is a 502."""
    FakeWes.run_status = 500
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=wes) as host:
        body = json.dumps(DEMO_VALUES).encode()
        status, _, response = _request(f"{host}/api/runs", body, "POST")
        assert status == 502
        message = json.loads(response)["errors"][0]["message"]
        assert message.startswith(f"The WES at {wes} failed: HTTP Error 500")
        status, _, response = _request(f"{host}/api/runs", b"{}", "POST")
        assert status == 400
    with serve(DEMO_SCHEMA, workflow_url="demo.wdl", wes_url=host) as other:
        # The other host is no WES: it answers 404 for /runs
        status, _, response = _request(f"{other}/api/runs", body, "POST")
    assert status == 502


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
    argv = ["--port", "0", "--trs-url", "http://trs/ga4gh/trs/v2"]
    assert form_host.main([*argv, "--wes-url", "http://wes/ga4gh/wes/v1"]) == 0
    out = capsys.readouterr().out
    assert "workflow URL: http://trs/ga4gh/trs/v2/tools/" in out
    assert "Run requests are sent to http://wes/ga4gh/wes/v1" in out


@pytest.mark.parametrize("option", ["--trs-url", "--wes-url"])
def test_main_rejects_urls_that_arent_http(option: str) -> None:
    """Test that TRS and WES URLs must be http(s) URLs."""
    with pytest.raises(SystemExit) as exc:
        form_host.main([option, "file:///etc/passwd"])
    assert exc.value.code == 2


def test_main_rejects_bad_schemas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``main`` exits with 1 if the schema can't be used."""
    bad = tmp_path / "bad.schema.json"
    bad.write_text(json.dumps({"$schema": PROFILE}), encoding="utf-8")
    assert form_host.main(["--schema", str(bad)]) == 1
    assert "Can't use the schema" in capsys.readouterr().err
    assert form_host.main(["--schema", str(tmp_path / "missing.json")]) == 1


def test_main_rejects_forbidden_schemes() -> None:
    """Test that schemes that can't be allowed are an argument error."""
    with pytest.raises(SystemExit) as exc:
        form_host.main(["--allow-scheme", "JavaScript"])
    assert exc.value.code == 2
