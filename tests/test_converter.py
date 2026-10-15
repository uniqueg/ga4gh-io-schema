# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the GA4GH IO Schema converter and its parsers."""

import json
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.converter import main
from ga4gh_io_schema.parsers import AbstractParser, get_parser
from ga4gh_io_schema.parsers.nextflow import GA4GH_META_SCHEMA_URI, NfSchemaParser
from ga4gh_io_schema.validator import validate_schema

DATA_DIR = Path(__file__).parent / "data"
NF_SCHEMA = DATA_DIR / "nextflow_schema.json"


@pytest.fixture
def converted() -> dict[str, Any]:
    """Return the mock nf-schema converted to a GA4GH IO Profile schema."""
    parser = NfSchemaParser()
    return parser.to_ga4gh(parser.parse(NF_SCHEMA))


def test_get_parser_nextflow() -> None:
    """Test that the factory returns the Nextflow parser for 'nextflow'."""
    parser = get_parser("nextflow")
    assert isinstance(parser, NfSchemaParser)
    assert isinstance(parser, AbstractParser)


def test_get_parser_unsupported_format() -> None:
    """Test that the factory raises NotImplementedError for unknown formats."""
    with pytest.raises(NotImplementedError, match="cwl"):
        get_parser("cwl")


def test_abstract_parser_cannot_be_instantiated() -> None:
    """Test that the parser base class enforces the interface."""
    with pytest.raises(TypeError):
        AbstractParser()  # type: ignore[abstract]


def test_nextflow_promotes_to_ga4gh_profile(converted: dict[str, Any]) -> None:
    """Test that the output declares the GA4GH meta-schema and wraps params as inputs.

    Args:
        converted: The converted schema fixture.
    """
    assert converted["$schema"] == GA4GH_META_SCHEMA_URI
    assert converted["$id"] == "https://example.com/nextflow_schema.json"
    assert converted["title"] == "Example Nextflow pipeline parameters"
    assert converted["required"] == ["inputs"]
    assert "definitions" not in converted
    assert set(converted["$defs"]) == {"input_output_options", "generic_options"}

    inputs = converted["properties"]["inputs"]
    assert inputs["type"] == "object"
    assert inputs["allOf"] == [
        {"$ref": "#/$defs/input_output_options"},
        {"$ref": "#/$defs/generic_options"},
    ]
    assert "genome" in inputs["properties"]


def test_nextflow_maps_ui_keywords(converted: dict[str, Any]) -> None:
    """Test that nf-schema UI keywords are renamed to the x-ga4gh-* vocabulary.

    Args:
        converted: The converted schema fixture.
    """
    io_group = converted["$defs"]["input_output_options"]
    sample_sheet = io_group["properties"]["input"]
    max_cpus = converted["$defs"]["generic_options"]["properties"]["max_cpus"]

    assert io_group["x-ga4gh-fa-icon"] == "fas fa-terminal"
    assert sample_sheet["x-ga4gh-fa-icon"] == "fas fa-file-csv"
    assert sample_sheet["x-ga4gh-error-message"].startswith("Sample sheet")
    assert max_cpus["x-ga4gh-hidden"] is True

    serialized = json.dumps(converted)
    for keyword in ("fa_icon", "errorMessage", '"hidden"'):
        assert keyword not in serialized


def test_nextflow_strips_engine_directives(converted: dict[str, Any]) -> None:
    """Test that cloud-toxic directives such as 'exists' are removed.

    Args:
        converted: The converted schema fixture.
    """
    assert '"exists"' not in json.dumps(converted)
    # Standard JSON Schema keywords must survive.
    sample_sheet = converted["$defs"]["input_output_options"]["properties"]["input"]
    assert sample_sheet["pattern"] == "^\\S+\\.csv$"


def test_nextflow_preserves_parameter_names_and_values() -> None:
    """Test that keyword mapping does not touch parameter names or data values."""
    source = {
        "$schema": "http://json-schema.org/draft-07/schema",
        "type": "object",
        "properties": {
            "exists": {"type": "boolean", "hidden": True},
            "hidden": {"type": "object", "default": {"fa_icon": "x", "exists": 1}},
        },
    }
    params = NfSchemaParser().to_ga4gh(source)["properties"]["inputs"]["properties"]
    assert params["exists"] == {"type": "boolean", "x-ga4gh-hidden": True}
    assert params["hidden"]["default"] == {"fa_icon": "x", "exists": 1}


def test_nextflow_does_not_mutate_source() -> None:
    """Test that conversion leaves the parsed source untouched."""
    parser = NfSchemaParser()
    source = parser.parse(NF_SCHEMA)
    snapshot = json.loads(json.dumps(source))
    parser.to_ga4gh(source)
    assert source == snapshot


def test_nextflow_output_passes_validator(converted: dict[str, Any]) -> None:
    """Test that the converter output validates against the GA4GH meta-schema.

    Args:
        converted: The converted schema fixture.
    """
    validate_schema(converted)


def test_cli_writes_output_file(tmp_path: Path) -> None:
    """Test the CLI end to end, writing a valid GA4GH schema to disk.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
    """
    out = tmp_path / "ga4gh_profile.schema.json"
    main(["--format", "nextflow", "--input", str(NF_SCHEMA), "--output", str(out)])
    validate_schema(json.loads(out.read_text(encoding="utf-8")))


def test_cli_writes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the CLI prints to stdout when no output file is given.

    Args:
        capsys: Pytest fixture capturing stdout and stderr.
    """
    main(["--format", "nextflow", "--input", str(NF_SCHEMA)])
    assert json.loads(capsys.readouterr().out)["$schema"] == GA4GH_META_SCHEMA_URI


def test_cli_rejects_unsupported_format() -> None:
    """Test that the CLI exits with an error for unknown formats."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--format", "cwl", "--input", str(NF_SCHEMA)])
    assert excinfo.value.code != 0


def test_cli_missing_input_file(tmp_path: Path) -> None:
    """Test that the CLI exits with an error when the input file is missing.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
    """
    with pytest.raises(SystemExit) as excinfo:
        main(["--format", "nextflow", "--input", str(tmp_path / "missing.json")])
    assert excinfo.value.code == 1
