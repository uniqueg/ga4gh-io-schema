# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the host of the form proof of concept (``examples/form/``).

They cover the path from the values of the form to ``workflow_params``, and
the messages of failed validation, over HTTP against a local host.
"""

import copy
import http.client
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
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
    server = form_host.FormHost(("127.0.0.1", 0), DEMO_SCHEMA, ["https", "s3"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
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


def test_demo_values_become_workflow_params() -> None:
    """Test that the values of the demo give the params of the demo docs."""
    params, errors = form_host.check_values(DEMO_SCHEMA, DEMO_VALUES, ["https", "s3"])
    assert errors == []
    assert params == {
        "io_schema_demo.reads": DEMO_VALUES["reads"],
        "io_schema_demo.min_mapq": 20,
        "io_schema_demo.read_filter": "proper_pairs",
    }


def test_out_of_range_value_gets_the_schema_message() -> None:
    """Test that a value out of range gets ``x-ga4gh-error-message``."""
    values = {**DEMO_VALUES, "min_mapq": 61}
    params, errors = form_host.check_values(DEMO_SCHEMA, values)
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
    assert form_host.pointer(["a/b", "c~d", 0]) == "/a~1b/c~0d/0"


def test_file_reference_rules_are_checked() -> None:
    """Test that a file reference with a scheme not allowed is an error."""
    values = {**DEMO_VALUES, "reads": "ftp://example.org/reads.bam"}
    params, errors = form_host.check_values(DEMO_SCHEMA, values)
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


def test_host_returns_workflow_params(host: str) -> None:
    """Test the values-to-params path over HTTP."""
    body = json.dumps(DEMO_VALUES).encode()
    status, _, response = _request(f"{host}/api/params", body, "POST")
    assert status == 200
    assert json.loads(response)["workflow_params"]["io_schema_demo.min_mapq"] == 20


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
    # Only the announced length counts: the host answers without reading
    connection = http.client.HTTPConnection(urllib.parse.urlsplit(host).netloc)
    length = str(form_host.MAX_BODY + 1)
    connection.request("POST", "/api/params", b"", {"Content-Length": length})
    assert connection.getresponse().status == 413
    connection.close()


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
    assert "Serving the form on http://127.0.0.1:" in capsys.readouterr().out


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
