# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the check of the workflow block against a workflow version."""

import hashlib
from typing import Any

import pytest

from ga4gh_io_schema.workflow import (
    HASH_ALGORITHMS,
    Mismatch,
    WorkflowCheck,
    check_workflow,
)

DESCRIPTOR = "version 1.1\nworkflow variant_calling {}\n"
DIGEST = hashlib.sha256(DESCRIPTOR.encode("utf-8")).hexdigest()
OTHER = "0" * 64


def schema_with(**block: Any) -> dict[str, Any]:
    """Build an IO schema with a workflow block.

    Args:
        **block: Fields of ``x-ga4gh-workflow``.

    Returns:
        The schema.
    """
    return {
        "x-ga4gh-workflow": {"descriptor_type": "WDL", **block},
        "type": "object",
        "properties": {"inputs": {}},
    }


def sha256(digest: str) -> list[dict[str, str]]:
    """Build the checksums of a descriptor with one SHA-256 digest.

    Args:
        digest: The hex digest.

    Returns:
        The checksums, in the format of TRS.
    """
    return [{"type": "sha-256", "checksum": digest}]


def test_matching_ids_and_checksum_verify_the_schema() -> None:
    """Test that a schema that matches the workflow version is verified."""
    schema = schema_with(
        trs_tool_id="#workflow/vc",
        trs_version_id="1.2.0",
        checksum=sha256(DIGEST),
    )

    result = check_workflow(
        schema,
        trs_tool_id="#workflow/vc",
        trs_version_id="1.2.0",
        descriptor_type="WDL",
        descriptor={"content": DESCRIPTOR, "checksum": sha256(DIGEST)},
    )

    assert result == WorkflowCheck(mismatches=(), compared=("sha-256",))
    assert result.verified
    assert result.to_dict() == {
        "verified": True,
        "mismatches": [],
        "compared": ["sha-256"],
    }


def test_ids_that_differ_are_mismatches() -> None:
    """Test that each id of another workflow version is a mismatch."""
    schema = schema_with(trs_tool_id="#workflow/vc", trs_version_id="1.1.0")

    result = check_workflow(
        schema,
        trs_tool_id="#workflow/vc",
        trs_version_id="1.2.0",
        descriptor_type="CWL",
    )

    assert result.mismatches == (
        Mismatch("trs_version_id", "1.1.0", "1.2.0"),
        Mismatch("descriptor_type", "WDL", "CWL"),
    )
    assert not result.verified
    assert result.mismatches[0].message == (
        "x-ga4gh-workflow.trs_version_id is '1.1.0', not '1.2.0'."
    )


def test_fields_missing_on_either_side_are_not_compared() -> None:
    """Test that ids are compared only where the schema and caller have them."""
    result = check_workflow(schema_with(trs_version_id="1.1.0"), trs_tool_id="t")

    assert result == WorkflowCheck()
    assert not result.verified
    assert result.mismatch_message == ""


@pytest.mark.parametrize(
    "source",
    [
        {"descriptor": {"checksum": sha256(OTHER)}},
        {"checksums": sha256(OTHER)},
        {"descriptor": {"content": "changed"}},
        {"content": b"changed"},
    ],
)
def test_checksums_that_differ_are_mismatches(source: dict[str, Any]) -> None:
    """Test a drifted descriptor, by its TRS checksum or by its content.

    Args:
        source: Where the checksum of the descriptor comes from.
    """
    result = check_workflow(schema_with(checksum=sha256(DIGEST)), **source)

    assert [mismatch.field for mismatch in result.mismatches] == ["checksum"]
    assert result.compared == ("sha-256",)
    assert not result.verified
    mismatch = result.mismatches[0]
    assert mismatch.schema == DIGEST
    assert mismatch.algorithm == "sha-256"
    assert mismatch.message.startswith(
        f"x-ga4gh-workflow.checksum (sha-256) is '{DIGEST}', but the primary "
        "descriptor has '"
    )
    assert mismatch.to_dict()["message"] == mismatch.message


def test_checksums_are_compared_case_insensitively() -> None:
    """Test that algorithm names and digests match in any case."""
    schema = schema_with(checksum=[{"type": "SHA-256", "checksum": DIGEST.upper()}])

    result = check_workflow(schema, checksums=sha256(DIGEST))

    assert result.verified


@pytest.mark.parametrize("algorithm", sorted(HASH_ALGORITHMS))
def test_checksums_are_computed_over_the_content(algorithm: str) -> None:
    """Test that every supported algorithm is computed over the descriptor.

    Args:
        algorithm: The algorithm, by its Hash Name String.
    """
    name = algorithm.replace("-", "")
    digest = hashlib.new(name, DESCRIPTOR.encode("utf-8")).hexdigest()
    schema = schema_with(checksum=[{"type": algorithm, "checksum": digest}])

    assert check_workflow(schema, content=DESCRIPTOR).verified
    assert check_workflow(schema, content=DESCRIPTOR.encode("utf-8")).verified


def test_content_argument_takes_precedence_over_the_file_wrapper() -> None:
    """Test that ``content`` replaces the content of the ``FileWrapper``."""
    schema = schema_with(checksum=sha256(DIGEST))

    result = check_workflow(schema, descriptor={"content": "other"}, content=DESCRIPTOR)

    assert result.verified


def test_trs_checksum_and_content_must_both_match() -> None:
    """Test that a TRS checksum that differs from the content is a mismatch."""
    schema = schema_with(checksum=sha256(DIGEST))

    result = check_workflow(
        schema, descriptor={"content": DESCRIPTOR, "checksum": sha256(OTHER)}
    )

    assert [mismatch.workflow for mismatch in result.mismatches] == [OTHER]


@pytest.mark.parametrize(
    ("schema", "options"),
    [
        (schema_with(), {"content": DESCRIPTOR}),
        (schema_with(checksum=sha256(DIGEST)), {}),
        (
            schema_with(checksum=[{"type": "trunc512", "checksum": "ab"}]),
            {"content": DESCRIPTOR, "checksums": sha256(DIGEST)},
        ),
    ],
)
def test_schemas_that_cant_be_compared_are_unverified(
    schema: dict[str, Any], options: dict[str, Any]
) -> None:
    """Test no checksum, no descriptor, and no supported algorithm.

    Args:
        schema: The IO schema.
        options: The workflow version.
    """
    result = check_workflow(schema, **options)

    assert result == WorkflowCheck()
    assert not result.verified


@pytest.mark.parametrize(
    "schema",
    [
        {},
        {"x-ga4gh-workflow": "WDL"},
        {"x-ga4gh-workflow": {"checksum": "x"}},
        {"x-ga4gh-workflow": {"checksum": [1, {"type": "sha-256"}, {"checksum": "a"}]}},
    ],
)
def test_malformed_blocks_are_skipped(schema: dict[str, Any]) -> None:
    """Test that fields of the wrong type are not compared.

    Args:
        schema: A schema that isn't valid against the profile.
    """
    result = check_workflow(
        schema,
        trs_tool_id="t",
        descriptor={"content": DESCRIPTOR, "checksum": "x"},
    )

    assert result == WorkflowCheck()


def test_id_of_the_wrong_type_mismatches() -> None:
    """Test that an id that isn't a string doesn't match the given id."""
    schema = {"x-ga4gh-workflow": {"trs_version_id": 1.0}}

    result = check_workflow(schema, trs_version_id="1.0")

    assert [mismatch.field for mismatch in result.mismatches] == ["trs_version_id"]


@pytest.mark.parametrize(
    ("descriptor", "content"),
    [([1], None), (None, 123)],
)
def test_inputs_of_the_wrong_type_are_absent(descriptor: Any, content: Any) -> None:
    """Test that a descriptor or content of the wrong type leaves it unverified.

    Args:
        descriptor: Not a FileWrapper.
        content: Neither bytes nor text.
    """
    result = check_workflow(
        schema_with(checksum=sha256(DIGEST)), descriptor=descriptor, content=content
    )

    assert result == WorkflowCheck()


def test_lone_surrogate_in_content_is_hashed() -> None:
    """Test that content with a lone surrogate, as JSON allows, is compared."""
    result = check_workflow(
        schema_with(checksum=sha256(DIGEST)), descriptor={"content": "\ud800"}
    )

    assert [mismatch.field for mismatch in result.mismatches] == ["checksum"]


def test_duplicate_checksums_are_compared_once() -> None:
    """Test that equal checksums from TRS and the content count once."""
    schema = schema_with(checksum=sha256(DIGEST) * 2)

    result = check_workflow(
        schema,
        descriptor={"content": DESCRIPTOR, "checksum": sha256(OTHER)},
        checksums=sha256(OTHER.upper()),
    )

    assert result.compared == ("sha-256",)
    assert len(result.mismatches) == 2
