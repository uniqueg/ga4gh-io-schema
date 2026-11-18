# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the seeded workflows of the demo (``examples/workflows/``).

Each seeded workflow must work in the demo as the WDL demo does: its IO
schema complies with the profile, names the checksum of its primary
descriptor, and turns its example values into a WES run request, also when
the form host loads it from the TRS stub. ``examples/demo/checksums.py``
keeps the checksums current.
"""

import contextlib
import json
import shutil
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import checksums
import form_host
import pytest
import trs_stub

from ga4gh_io_schema.validator import validate_schema
from ga4gh_io_schema.wes import build_run_request
from ga4gh_io_schema.workflow import check_workflow

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "examples" / "workflows"
SEEDED = sorted(path.parent for path in WORKFLOWS.glob("*/ga4gh-io.schema.json"))
#: The descriptor type of each seeded workflow: one per language besides WDL.
TYPES = {
    "greetings-nextflow": "NFL",
    "report-snakemake": "SMK",
    "word-count-cwl": "CWL",
}


def read_json(path: Path) -> Any:
    """Read a JSON file.

    Args:
        path: The file.

    Returns:
        The parsed content.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def test_one_seeded_workflow_per_language() -> None:
    """Test that CWL, Nextflow and Snakemake each have a seeded workflow."""
    types = {
        path.name: read_json(path / "ga4gh-io.schema.json")["x-ga4gh-workflow"][
            "descriptor_type"
        ]
        for path in SEEDED
    }
    assert types == TYPES


@pytest.mark.parametrize("directory", SEEDED, ids=lambda path: path.name)
def test_seeded_workflow_is_valid_and_bound(directory: Path) -> None:
    """Test that the schema complies and names its descriptor's checksum."""
    schema = read_json(directory / "ga4gh-io.schema.json")
    validate_schema(schema)
    block = schema["x-ga4gh-workflow"]
    content = (directory / block["primary_descriptor_path"]).read_bytes()
    result = check_workflow(schema, content=content)
    assert result.verified


@pytest.mark.parametrize("directory", SEEDED, ids=lambda path: path.name)
def test_seeded_values_give_a_run_request(directory: Path) -> None:
    """Test that the example values give a run request of the right type."""
    schema = read_json(directory / "ga4gh-io.schema.json")
    request = build_run_request(
        schema, read_json(directory / "values.json"), workflow_url="x"
    )
    assert request["workflow_type"] == TYPES[directory.name]
    assert request["workflow_params"]


def test_checksums_and_stub_find_the_same_workflows(tmp_path: Path) -> None:
    """Test that the checksum script and the TRS stub agree on workflows.

    Args:
        tmp_path: A directory with a workflow and one without a schema.
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "ga4gh-io.schema.json").write_text("{}", "utf-8")
    (tmp_path / "b").mkdir()
    for root in (WORKFLOWS, tmp_path):
        assert checksums.workflow_dirs(root) == trs_stub.find_workflows(root)
    assert checksums.workflow_dirs(tmp_path) == [tmp_path / "a"]


def test_checksums_are_current() -> None:
    """Test that the checked-in checksums match the descriptors."""
    assert checksums.main(["--check"]) == 0


def test_checksums_after_an_edit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an edited descriptor is found, and its checksum set."""
    copy = tmp_path / "word-count-cwl"
    shutil.copytree(WORKFLOWS / "word-count-cwl", copy)
    with (copy / "wc.cwl").open("a", encoding="utf-8") as descriptor:
        descriptor.write("# edited\n")
    argv = ["--dir", str(tmp_path)]
    assert checksums.main([*argv, "--check"]) == 1
    assert "word-count-cwl: the checksum is outdated" in capsys.readouterr().err
    assert checksums.main(argv) == 0
    assert "word-count-cwl: checksum set" in capsys.readouterr().err
    assert checksums.main([*argv, "--check"]) == 0
    schema = read_json(copy / "ga4gh-io.schema.json")
    assert check_workflow(schema, content=(copy / "wc.cwl").read_bytes()).verified


def test_checksums_of_a_broken_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a workflow that can't be read is reported, with status 1."""
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "ga4gh-io.schema.json").write_text("{}", "utf-8")
    assert checksums.main(["--dir", str(tmp_path)]) == 1
    assert "Can't read the workflow broken" in capsys.readouterr().err


@contextlib.contextmanager
def serve_seeded() -> Iterator[str]:
    """Run the TRS stub with the seeded workflows, as the demo does.

    Yields:
        The base URL of the TRS API of the stub.
    """
    server = trs_stub.TrsStub(
        ("127.0.0.1", 0), trs_stub.load_workflows([], [WORKFLOWS])
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}{trs_stub.API}"
    finally:
        server.shutdown()
        server.server_close()


def test_host_builds_run_requests_from_the_stub() -> None:
    """Test the path of the demo for each seeded workflow, over TRS."""
    with serve_seeded() as url:
        listed = form_host.list_workflows(url)
        assert {w["descriptor_type"] for w in listed} == set(TYPES.values())
        for directory in SEEDED:
            schema = read_json(directory / "ga4gh-io.schema.json")
            block = schema["x-ga4gh-workflow"]
            loaded, workflow_url = form_host.load_trs_schema(
                url,
                block["trs_tool_id"],
                block["trs_version_id"],
                block["descriptor_type"],
            )
            assert loaded == schema
            assert workflow_url.endswith(
                f"/PLAIN_{block['descriptor_type']}/descriptor/"
                f"{block['primary_descriptor_path']}"
            )
            values = read_json(directory / "values.json")
            request = build_run_request(loaded, values, workflow_url=workflow_url)
            assert request["workflow_url"].startswith(workflow_url)
