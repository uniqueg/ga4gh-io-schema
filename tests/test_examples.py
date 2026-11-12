# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of values against the inputs and outputs of the example schemas.

The meta-schema checks the schemas; these tests check that the examples
constrain the values a client sends (e.g., in WES ``workflow_params``) and
the normalised outputs of a run that clients receive.
JSON Schema checks only that a file reference is a string; the value rules of
file references (schemes, paths) are not JSON Schema keywords.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jsonschema
import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"
EXAMPLES = sorted(DATA_DIR.glob("*.schema.json"))
TOOL = DATA_DIR / "example_tool.schema.json"
WORKFLOW = DATA_DIR / "example_workflow.schema.json"

#: Valid inputs of the tool example.
TOOL_VALUES: dict[str, Any] = {
    "reference_fasta": "s3://example-bucket/refs/GRCh38.fa",
    "read_1": "drs://dg.4503:6ca5c2a8-1a2b-4c3d-9e8f-0a1b2c3d4e5f",
    "read_2": "https://data.example.org/runs/1/reads_2.fastq.gz",
    "threads": 8,
}

#: Valid inputs of the workflow example.
WORKFLOW_VALUES: dict[str, Any] = {
    "sample_manifest": "drs://drs.example.org/314159",
    "genome_index": "s3://example-bucket/refs/GRCh38-index/",
}

#: Normalised outputs of a completed run of the tool example.
TOOL_OUTPUTS: dict[str, Any] = {
    "alignment_bam": "s3://example-bucket/runs/42/out/aligned.bam",
}

#: Normalised outputs of a completed run of the workflow example.
WORKFLOW_OUTPUTS: dict[str, Any] = {
    "qc_report": "s3://example-bucket/runs/7/multiqc/multiqc_report.html",
    "alignments": [
        "s3://example-bucket/runs/7/alignments/s1.bam",
        "s3://example-bucket/runs/7/alignments/s2.bam",
    ],
    "gene_counts": {
        "s1": "s3://example-bucket/runs/7/counts/s1.tsv",
        "s2": "s3://example-bucket/runs/7/counts/s2.tsv",
    },
    "samples_passed_qc": 2,
}


def load(path: Path) -> dict[str, Any]:
    """Load an example schema.

    Args:
        path: The example IO schema.

    Returns:
        The parsed schema.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def inputs_validator(path: Path) -> jsonschema.Draft202012Validator:
    """Return a validator for the input values of an example schema.

    Args:
        path: The example IO schema.

    Returns:
        A validator of the schema's ``inputs``, which checks formats.
    """
    return jsonschema.Draft202012Validator(
        load(path)["properties"]["inputs"],
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )


def failing_keywords(path: Path, values: dict[str, Any]) -> set[str]:
    """Return the keywords that input values violate.

    Args:
        path: The example IO schema.
        values: The input values.

    Returns:
        The keywords (e.g., ``type``) of all errors.
    """
    validator = inputs_validator(path)
    return {str(error.validator) for error in validator.iter_errors(values)}


def file_references(node: Any) -> Iterator[dict[str, Any]]:
    """Yield every schema with ``x-ga4gh-file`` in a schema, at any depth.

    Args:
        node: A schema or part of one.

    Yields:
        The schemas that carry the annotation.
    """
    if isinstance(node, dict):
        if "x-ga4gh-file" in node:
            yield node
        for value in node.values():
            yield from file_references(value)
    elif isinstance(node, list):
        for item in node:
            yield from file_references(item)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_inputs_reject_empty_object(path: Path) -> None:
    """Test that each example requires inputs, so that ``{}`` fails.

    Args:
        path: The example IO schema.
    """
    assert failing_keywords(path, {}) == {"required"}


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_inputs_reject_unknown_inputs(path: Path) -> None:
    """Test that each example rejects inputs that it doesn't declare.

    Args:
        path: The example IO schema.
    """
    assert "additionalProperties" in failing_keywords(path, {"no_such_input": "x"})


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_file_references_have_no_format(path: Path) -> None:
    """Test that each example has file references, none with ``format``.

    Args:
        path: The example IO schema.
    """
    references = list(file_references(load(path)))

    assert references
    assert all("format" not in reference for reference in references)


def test_example_tool_rejects_number_only() -> None:
    """Test that ``{"read_1": 12}`` fails: an input lacks, and one isn't a string."""
    assert failing_keywords(TOOL, {"read_1": 12}) == {"required", "type"}


def test_example_tool_rejects_number_as_file() -> None:
    """Test that a number fails as a file reference when all else is valid."""
    assert failing_keywords(TOOL, {**TOOL_VALUES, "read_1": 12}) == {"type"}


def test_example_tool_accepts_file_references() -> None:
    """Test that file references of several schemes pass, compact DRS ones too.

    ``format: uri`` would reject the compact identifier
    (``drs://prefix:accession``); the examples don't use it.
    """
    inputs_validator(TOOL).validate(TOOL_VALUES)


def test_example_workflow_accepts_file_and_directory_references() -> None:
    """Test that the workflow example accepts its file and directory inputs."""
    inputs_validator(WORKFLOW).validate(
        {**WORKFLOW_VALUES, "known_variants": "gs://example-bucket/known.vcf.gz"}
    )


def test_example_workflow_rejects_number_as_directory() -> None:
    """Test that a number fails as a directory reference when all else is valid."""
    values = {**WORKFLOW_VALUES, "genome_index": 7}

    assert failing_keywords(WORKFLOW, values) == {"type"}


def test_example_workflow_checks_file_column_of_sample_sheet() -> None:
    """Test that the sample sheet's file column is checked in its rows."""
    workflow = load(WORKFLOW)
    sheet = workflow["properties"]["inputs"]["properties"]["sample_manifest"]
    validator = jsonschema.Draft202012Validator(sheet["x-ga4gh-tabular-schema"])
    row = {
        "sample_id": "s1",
        "fastq_1": "https://data.example.org/s1_1.fastq.gz",
        "condition": "control",
    }

    validator.validate([row])
    assert not validator.is_valid([{**row, "fastq_1": 1}])


def failing_output_keywords(path: Path, outputs: dict[str, Any]) -> set[str]:
    """Return the keywords that a normalised outputs object violates.

    Args:
        path: The example IO schema.
        outputs: The normalised outputs object of a run.

    Returns:
        The keywords (e.g., ``type``) of all errors.
    """
    validator = jsonschema.Draft202012Validator(load(path)["properties"]["outputs"])
    return {str(error.validator) for error in validator.iter_errors(outputs)}


@pytest.mark.parametrize(
    ("path", "outputs"),
    [(TOOL, TOOL_OUTPUTS), (WORKFLOW, WORKFLOW_OUTPUTS)],
    ids=["tool", "workflow"],
)
def test_example_outputs_accept_normalised_outputs(
    path: Path, outputs: dict[str, Any]
) -> None:
    """Test that the outputs of each example accept a normalised outputs object.

    Args:
        path: The example IO schema.
        outputs: A normalised outputs object of a completed run.
    """
    assert failing_output_keywords(path, outputs) == set()


def test_example_workflow_outputs_allow_absent_optional_outputs() -> None:
    """Test that outputs that a run didn't produce may be absent."""
    outputs = {key: WORKFLOW_OUTPUTS[key] for key in ("qc_report", "alignments")}

    assert failing_output_keywords(WORKFLOW, outputs) == set()


@pytest.mark.parametrize(
    ("change", "keyword"),
    [
        ({"gene_counts": None}, "type"),
        ({"samples_passed_qc": None}, "type"),
        ({"alignments": "s3://example-bucket/runs/7/alignments/s1.bam"}, "type"),
        ({"gene_counts": {"s1": {"class": "File", "location": "s3://b/k"}}}, "type"),
        ({"workflow.qc_report": "s3://example-bucket/r.html"}, "additionalProperties"),
    ],
    ids=["null-file", "null-scalar", "file-for-list", "cwl-file-object", "qualified"],
)
def test_example_workflow_outputs_reject_unnormalised_values(
    change: dict[str, Any], keyword: str
) -> None:
    """Test that values not in the shape of the schema fail.

    Normalised outputs leave out what a run didn't produce instead of using
    ``null``, give file references as URIs instead of engine objects, and use
    the names of the schema's outputs as keys.

    Args:
        change: Values that replace or add to valid outputs.
        keyword: The keyword that fails.
    """
    assert failing_output_keywords(WORKFLOW, {**WORKFLOW_OUTPUTS, **change}) == {
        keyword
    }


def test_example_workflow_outputs_require_declared_outputs() -> None:
    """Test that a completed run without a required output fails."""
    outputs = {
        key: value for key, value in WORKFLOW_OUTPUTS.items() if key != "alignments"
    }

    assert failing_output_keywords(WORKFLOW, outputs) == {"required"}
