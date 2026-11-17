# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the discovery of IO schemas among TRS files (``ga4gh_io_schema.trs``).

The language-neutral test vectors of ``tests/vectors/trs-files/`` are run
against the library here.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.trs import (
    IO_SCHEMA_FILE_TYPE,
    OTHER_FILE_TYPE,
    SchemaFile,
    find_primary_descriptor_path,
    find_schema_file,
    normalise_path,
)

#: The test vectors of the matching of TRS file entries.
CASES = json.loads(
    (
        Path(__file__).resolve().parent / "vectors" / "trs-files" / "cases.json"
    ).read_text(encoding="utf-8")
)


def test_vectors_cover_both_types_and_no_match() -> None:
    """Test that the vectors cover both file types and entries without a match."""
    expected = [case["schemaFile"] for case in CASES]
    assert {e["file_type"] for e in expected if e} == {
        IO_SCHEMA_FILE_TYPE,
        OTHER_FILE_TYPE,
    }
    assert None in expected
    assert len({case["name"] for case in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_vectors(case: dict[str, Any]) -> None:
    """Test the matching of an IO schema in a list of TRS file entries.

    Args:
        case: A test vector: ``files`` and the expected ``schemaFile``.
    """
    expected = case["schemaFile"]
    found = find_schema_file(case["files"])
    assert found == (SchemaFile(**expected) if expected else None)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("main.wdl", "main.wdl"),
        ("./wdl/./main.wdl", "wdl/main.wdl"),
        ("/wdl//main.wdl/", "wdl/main.wdl"),
        (".", None),
        ("/", None),
        ("", None),
        ("a/../main.wdl", None),
        (None, None),
        (1, None),
    ],
)
def test_normalise_path(path: Any, expected: str | None) -> None:
    """Test that paths lose empty and ``.`` segments, and ``..`` is refused.

    Args:
        path: The path of an entry.
        expected: The normalised path.
    """
    assert normalise_path(path) == expected


@pytest.mark.parametrize("files", [None, {"files": []}, "ga4gh-io.schema.json", []])
def test_find_schema_file_needs_a_list(files: Any) -> None:
    """Test that answers other than a list of entries have no IO schema.

    Args:
        files: An answer of ``.../files``.
    """
    assert find_schema_file(files) is None


def test_find_schema_file_skips_entries_that_are_no_objects() -> None:
    """Test that entries that aren't objects are skipped."""
    files = [
        1,
        "ga4gh-io.schema.json",
        {"path": "main.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
        {"path": "ga4gh-io.schema.json", "file_type": "OTHER"},
    ]
    assert find_schema_file(files) == SchemaFile("ga4gh-io.schema.json", "OTHER")


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (
            [
                {"path": "ga4gh-io.schema.json", "file_type": "IO_SCHEMA"},
                {"path": 5, "file_type": "PRIMARY_DESCRIPTOR"},
                "main.wdl",
                {"path": "", "file_type": "PRIMARY_DESCRIPTOR"},
                {"path": "../main.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
                {"path": "wdl/main.wdl", "file_type": "PRIMARY_DESCRIPTOR"},
            ],
            "wdl/main.wdl",
        ),
        ([{"path": "./main.wdl", "file_type": "PRIMARY_DESCRIPTOR"}], None),
        ([{"path": "wdl//main.wdl", "file_type": "PRIMARY_DESCRIPTOR"}], None),
        ([{"path": "ga4gh-io.schema.json", "file_type": "IO_SCHEMA"}], None),
        ({"path": "main.wdl", "file_type": "PRIMARY_DESCRIPTOR"}, None),
    ],
)
def test_find_primary_descriptor_path(files: Any, expected: str | None) -> None:
    """Test that the path of the primary descriptor is found as listed.

    Args:
        files: The answer of ``GET .../{type}/files``.
        expected: The path, or ``None``.
    """
    assert find_primary_descriptor_path(files) == expected
