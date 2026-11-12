# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of input values against the inputs of the example schemas.

The meta-schema checks the schemas; these tests check that the examples
constrain the values a client sends (e.g., in WES ``workflow_params``).
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"
EXAMPLES = sorted(DATA_DIR.glob("*.schema.json"))


def inputs_validator(path: Path) -> jsonschema.Draft202012Validator:
    """Return a validator for the input values of an example schema.

    Args:
        path: The example IO schema.

    Returns:
        A validator of the schema's ``inputs``, which checks formats.
    """
    schema = json.loads(path.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(
        schema["properties"]["inputs"],
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_inputs_reject_empty_object(path: Path) -> None:
    """Test that each example requires inputs, so that ``{}`` fails.

    Args:
        path: The example IO schema.
    """
    assert not inputs_validator(path).is_valid({})


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_example_inputs_reject_unknown_inputs(path: Path) -> None:
    """Test that each example rejects inputs that it doesn't declare.

    Args:
        path: The example IO schema.
    """
    validator = inputs_validator(path)
    errors = list(validator.iter_errors({"no_such_input": "x"}))

    assert any(error.validator == "additionalProperties" for error in errors)


@pytest.mark.parametrize(
    "values",
    [{}, {"read_1": 12}, {"reference_fasta": "drs://example.org/1", "read_1": 12}],
    ids=["empty", "number-only", "number-as-file"],
)
def test_example_tool_rejects_bad_values(values: dict[str, Any]) -> None:
    """Test that the tool example rejects missing and mistyped file references.

    Args:
        values: Input values that must fail.
    """
    validator = inputs_validator(DATA_DIR / "example_tool.schema.json")

    assert not validator.is_valid(values)


def test_example_tool_accepts_file_references() -> None:
    """Test that file references of several schemes pass, compact DRS ones too.

    ``format: uri`` would reject the compact identifier
    (``drs://prefix:accession``), and the profile doesn't use it.
    """
    validator = inputs_validator(DATA_DIR / "example_tool.schema.json")

    validator.validate(
        {
            "reference_fasta": "s3://example-bucket/refs/GRCh38.fa",
            "read_1": "drs://dg.4503:6ca5c2a8-1a2b-4c3d-9e8f-0a1b2c3d4e5f",
            "read_2": "https://data.example.org/runs/1/reads_2.fastq.gz",
            "threads": 8,
        }
    )
