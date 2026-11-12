# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the command-line interface against the real meta-schema."""

import json
from pathlib import Path

import pytest

from ga4gh_io_schema import cli
from ga4gh_io_schema.cli import main

DATA_DIR = Path(__file__).resolve().parent / "data"
VALID = sorted(DATA_DIR.glob("*.schema.json"))

#: Expected error message (on stderr) for each deliberately bad schema.
INVALID = {
    "missing-inputs": "Validation Error: 'inputs' is a required property (at $.properties)",
    "empty": "Validation Error: The schema lacks a '$schema' property",
    "missing-schema": "Validation Error: The schema lacks a '$schema' property",
    "foreign-schema": (
        "Validation Error: '$schema' is 'http://json-schema.org/draft-07/schema#', "
        "not the GA4GH IO Profile meta-schema"
    ),
    "not-object-type": "Validation Error: 'object' was expected (at $.type)",
    "ui-widget-custom-newline": (
        "Validation Error: 'custom:my-widget\\n' is not valid under any of the "
        "given schemas "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-ui-widget'])"
    ),
    "ui-widget-unknown": (
        "Validation Error: 'banana' is not valid under any of the given schemas "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-ui-widget'])"
    ),
    "drs-uri-not-boolean": (
        "Validation Error: 'yes' is not of type 'boolean' "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-drs-uri'])"
    ),
    "ontology-not-string": (
        "Validation Error: 42 is not of type 'string' "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-ontology'])"
    ),
    "ontology-not-uri": (
        "Validation Error: 'format_1929' is not a 'uri' "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-ontology'])"
    ),
    "description-format-unknown": (
        "Validation Error: 'html' is not one of ['plain_text', 'markdown', 'rst'] "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-description-format'])"
    ),
    "hidden-not-boolean": (
        "Validation Error: 'true' is not of type 'boolean' "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-hidden'])"
    ),
    "fa-icon-not-string": (
        "Validation Error: ['fas', 'fa-dna'] is not of type 'string' "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-fa-icon'])"
    ),
    "error-message-not-string": (
        "Validation Error: 404 is not of type 'string' "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-error-message'])"
    ),
    "misspelled-keyword": (
        "Validation Error: Unevaluated properties are not allowed "
        "('x-ga4gh-ui-widgte' was unexpected) "
        "(at $.properties.inputs.properties.sample_id)"
    ),
    "tabular-schema-nested": (
        "Validation Error: 'no' is not of type 'boolean' (at $.properties.inputs."
        "properties.sample_id['x-ga4gh-tabular-schema'].items.properties.condition"
        "['x-ga4gh-hidden'])"
    ),
    "outputs-nested": (
        "Validation Error: 3 is not of type 'string' "
        "(at $.properties.outputs.properties.report['x-ga4gh-ui-widget'])"
    ),
}


def test_cli_accepts_other_extension_keywords(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that keywords outside the ``x-ga4gh-`` namespace stay allowed.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = json.loads((DATA_DIR / "valid.schema.json").read_text(encoding="utf-8"))
    sample_id = schema["properties"]["inputs"]["properties"]["sample_id"]
    sample_id["x-my-platform-hint"] = {"any": "value"}
    sample_id["x-ga4ghost"] = 1
    path = tmp_path / "extended.schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")

    main([str(path)])

    assert "complies" in capsys.readouterr().out


def test_every_invalid_fixture_has_an_expected_message() -> None:
    """Test that the table of expected messages covers every bad schema."""
    names = {
        path.name.removesuffix(".schema.json") for path in DATA_DIR.glob("invalid/*")
    }

    assert names == set(INVALID)


@pytest.mark.parametrize("path", VALID, ids=lambda path: path.name)
def test_cli_accepts_valid_schema(
    path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the CLI accepts the valid examples and exits with status 0.

    Args:
        path: Valid IO schema.
        capsys: Pytest fixture capturing standard output and error.
    """
    main([str(path)])

    assert f"Success: '{path}' complies with the GA4GH IO Profile." in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize("name", sorted(INVALID))
def test_cli_rejects_invalid_schema(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the CLI rejects each bad schema with status 1 and a clear message.

    Args:
        name: Name of the bad schema in ``tests/data/invalid/``.
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as exc_info:
        main([str(DATA_DIR / "invalid" / f"{name}.schema.json")])

    assert exc_info.value.code == 1
    assert INVALID[name] in capsys.readouterr().err


def test_cli_rejects_plain_json_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a valid plain JSON Schema doesn't pass as an IO schema.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    path = tmp_path / "plain.schema.json"
    path.write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc_info:
        main([str(path)])

    assert exc_info.value.code == 1
    assert "not the GA4GH IO Profile meta-schema" in capsys.readouterr().err


def test_cli_uses_custom_meta_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--meta-schema`` validates against another meta-schema.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    meta_schema = tmp_path / "meta.schema.json"
    meta_schema.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "required": ["inputs"],
            }
        ),
        encoding="utf-8",
    )
    schema = tmp_path / "io.schema.json"
    schema.write_text(json.dumps({"inputs": {}}), encoding="utf-8")

    main([str(schema), "--meta-schema", str(meta_schema)])

    assert (
        f"Success: '{schema}' complies with the meta-schema '{meta_schema}'."
        in capsys.readouterr().out
    )


def test_cli_reports_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a missing file is reported as such, with status 1.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as exc_info:
        main([str(DATA_DIR / "does-not-exist.schema.json")])

    assert exc_info.value.code == 1
    assert "Error: File not found" in capsys.readouterr().err


def test_cli_reports_invalid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that malformed JSON is reported as such, with status 1.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    path = tmp_path / "broken.schema.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main([str(path)])

    assert exc_info.value.code == 1
    assert "Error: Invalid JSON" in capsys.readouterr().err


def test_cli_reports_invalid_meta_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a malformed custom meta-schema is reported, with status 1.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    meta_schema = tmp_path / "meta.schema.json"
    meta_schema.write_text(json.dumps({"type": "no-such-type"}), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main([str(DATA_DIR / "valid.schema.json"), "-m", str(meta_schema)])

    assert exc_info.value.code == 1
    assert "Meta-schema Error:" in capsys.readouterr().err


def test_cli_reports_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that other errors are reported without a traceback, with status 1.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """

    def fail(**_: object) -> None:
        """Raise an unexpected error.

        Args:
            **_: Ignored keyword arguments.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "validate_schema", fail)

    with pytest.raises(SystemExit) as exc_info:
        main([str(DATA_DIR / "valid.schema.json")])

    assert exc_info.value.code == 1
    assert "An unexpected error occurred: boom" in capsys.readouterr().err


def test_cli_omits_location_of_top_level_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that errors about the whole schema don't name the location ``$``.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit):
        main([str(DATA_DIR / "invalid" / "missing-schema.schema.json")])

    assert "(at $)" not in capsys.readouterr().err
