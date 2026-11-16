# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

r"""End-to-end test of the prototype, against the running Docker Compose stack.

It follows the path of a user (see ``docs/adoption/prototype.md``): open the
page, pick the demo workflow from the TRS stub, get its form, submit wrong
and then right values, and see the WES run request. It makes the requests
that the page makes, over HTTP. Start the stack first, then set
``PROTOTYPE_URL`` (and ``PROTOTYPE_TRS_URL`` for the stub)::

    docker compose -f prototype/compose.yaml up --detach --build --wait
    PROTOTYPE_URL=http://127.0.0.1:8000 \
        PROTOTYPE_TRS_URL=http://127.0.0.1:8080/ga4gh/trs/v2 \
        pytest -m e2e --no-cov tests/test_prototype_e2e.py

Without ``PROTOTYPE_URL``, the tests are skipped.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        "PROTOTYPE_URL" not in os.environ,
        reason="needs the running prototype (PROTOTYPE_URL)",
    ),
]

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
HOST = os.environ.get("PROTOTYPE_URL", "").rstrip("/")
TRS = os.environ.get("PROTOTYPE_TRS_URL", "").rstrip("/")
#: The demo workflow, as the page picks it.
PICK = "?tool=ga4gh-io-schema-demo&version=1.0.0&type=WDL"
#: The TRS URL of the demo's primary descriptor, inside the stack.
WORKFLOW_URL = (
    "http://trs-stub:8080/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0"
    "/PLAIN_WDL/descriptor"
)


def call(path: str, values: Any = None) -> tuple[int, Any]:
    """Send a request to the host, as the page does.

    Args:
        path: Path and query on the host.
        values: Values to post as JSON; without them, a GET is sent.

    Returns:
        The status and the parsed JSON body (the text for other bodies).
    """
    data = None if values is None else json.dumps(values).encode("utf-8")
    request = urllib.request.Request(
        f"{HOST}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read()
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body.decode("utf-8")


def test_user_gets_the_run_request_of_a_workflow_from_trs() -> None:
    """Test the path from the TRS to the WES run request."""
    status, page = call("/")
    assert status == 200
    assert "<io-schema-form>" in page
    # The page lists the workflows of the TRS stub, and nothing is sent
    status, config = call("/api/config")
    assert config == {
        "wes": False,
        "workflows": [
            {
                "tool_id": "ga4gh-io-schema-demo",
                "version_id": "1.0.0",
                "descriptor_type": "WDL",
                "name": "I/O Schema demo",
            }
        ],
    }
    # Without a pick, there is no form
    status, _ = call("/api/schema")
    assert status == 404
    # The picked workflow's IO schema comes from the stub
    schema = json.loads((DEMO / "ga4gh-io.schema.json").read_text("utf-8"))
    assert call(f"/api/schema{PICK}") == (200, schema)
    # Wrong values get the schema's own messages
    values = json.loads((DEMO / "values.json").read_text("utf-8"))
    status, body = call(f"/api/params{PICK}", {**values, "min_mapq": 61})
    assert status == 400
    assert body["errors"][0] == {
        "pointer": "/min_mapq",
        "message": "The minimum mapping quality is a whole number from 0 to 60",
    }
    # Right values give the WES run request
    status, body = call(f"/api/params{PICK}", values)
    assert status == 200
    assert body["run_request"] == {
        "workflow_params": {
            "io_schema_demo.reads": values["reads"],
            "io_schema_demo.min_mapq": 20,
            "io_schema_demo.read_filter": "proper_pairs",
        },
        "workflow_type": "WDL",
        "workflow_type_version": "1.1",
        "workflow_url": WORKFLOW_URL,
    }
    # Without a WES, the request isn't sent
    status, body = call(f"/api/runs{PICK}", values)
    assert status == 404


@pytest.mark.skipif(not TRS, reason="needs the URL of the stub (PROTOTYPE_TRS_URL)")
def test_trs_stub_serves_the_descriptor_that_the_schema_names() -> None:
    """Test that the stub's descriptor has the checksum that the schema names."""
    schema = json.loads((DEMO / "ga4gh-io.schema.json").read_text("utf-8"))
    url = f"{TRS}/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/descriptor"
    with urllib.request.urlopen(url, timeout=30) as response:
        wrapper = json.loads(response.read())
    assert wrapper["checksum"] == schema["x-ga4gh-workflow"]["checksum"]
