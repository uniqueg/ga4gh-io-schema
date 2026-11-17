# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the ``workflow_url`` of run requests: TRS URLs of descriptors.

The language-neutral test vectors of ``tests/vectors/workflow-urls/`` are
run against :func:`ga4gh_io_schema.wes.trs_descriptor_url` here. Their
``imports`` check the reason for the form with the primary descriptor's
path: relative imports of a multi-file workflow resolve (RFC 3986) to URLs
that TRS serves.
"""

from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pytest

from ga4gh_io_schema.validator import load_json
from ga4gh_io_schema.wes import trs_descriptor_url

CASES = load_json(
    Path(__file__).resolve().parent / "vectors" / "workflow-urls" / "cases.json"
)
#: Keys that a case may have.
CASE_KEYS = {
    "name",
    "trsUrl",
    "toolId",
    "versionId",
    "descriptorType",
    "primaryDescriptorPath",
    "workflowUrl",
    "imports",
    "error",
}


def build(case: dict[str, Any]) -> str:
    """Build the workflow URL of a case.

    Args:
        case: The case.

    Returns:
        The URL.
    """
    return trs_descriptor_url(
        case["trsUrl"],
        case["toolId"],
        case["versionId"],
        case["descriptorType"],
        case.get("primaryDescriptorPath"),
    )


def test_cases_have_unique_names() -> None:
    """Test that every case has a name of its own."""
    names = [case["name"] for case in CASES]

    assert len(names) == len(set(names))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_case_keys(case: dict[str, Any]) -> None:
    """Test that a case has known keys and one expected result.

    Args:
        case: The case.
    """
    assert set(case) <= CASE_KEYS
    assert ("workflowUrl" in case) != ("error" in case)
    assert "imports" not in case or "workflowUrl" in case


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_case(case: dict[str, Any]) -> None:
    """Test that a case gives its workflow URL, or is rejected.

    Args:
        case: The case.
    """
    if case.get("error"):
        with pytest.raises(ValueError, match="primary descriptor path"):
            build(case)
        return
    assert build(case) == case["workflowUrl"]


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if "imports" in case],
    ids=lambda case: case["name"],
)
def test_imports_resolve(case: dict[str, Any]) -> None:
    """Test that the relative imports of a case resolve as RFC 3986 says.

    Args:
        case: The case.
    """
    for item in case["imports"]:
        assert urljoin(case["workflowUrl"], item["reference"]) == item["url"]


def test_imports_resolve_to_trs_files_only_with_the_path() -> None:
    """Test that imports reach ``.../descriptor/`` only with the path form."""
    base = "https://trs.example.org/ga4gh/trs/v2"
    bare = trs_descriptor_url(base, "t", "v", "WDL")
    with_path = trs_descriptor_url(base, "t", "v", "WDL", "main.wdl")

    assert (
        urljoin(bare, "tasks/sub.wdl")
        == f"{base}/tools/t/versions/v/PLAIN_WDL/tasks/sub.wdl"
    )
    assert urljoin(with_path, "tasks/sub.wdl") == (
        f"{base}/tools/t/versions/v/PLAIN_WDL/descriptor/tasks/sub.wdl"
    )
