# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the command-line interface against the real meta-schema."""

import json
from pathlib import Path

import pytest

from ga4gh_io_schema.cli import main
from ga4gh_io_schema.cli.commands import validate as validate_command

DATA_DIR = Path(__file__).resolve().parent / "data"
VALID = sorted(DATA_DIR.glob("*.schema.json"))

#: Definition of ``x-ga4gh-output-glob`` in its vocabulary.
_OUTPUT_GLOB = json.loads(
    (
        DATA_DIR.parents[1] / "schemas" / "vocabularies" / "outputs.schema.json"
    ).read_text(encoding="utf-8")
)["$defs"]["outputGlob"]
#: Patterns of ``x-ga4gh-output-glob`` as error messages show them (as their
#: repr without the quotes, with backslashes doubled).
OUTPUT_GLOB_PATTERN = repr(_OUTPUT_GLOB["pattern"])[1:-1]
OUTPUT_GLOB_NOT_PATTERN = repr(_OUTPUT_GLOB["not"]["pattern"])[1:-1]

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
    "drs-uri-removed": (
        "Validation Error: Unevaluated properties are not allowed "
        "('x-ga4gh-drs-uri' was unexpected) (at $.properties.inputs.properties.reads)"
    ),
    "file-kind-unknown": (
        "Validation Error: 'symlink' is not one of ['file', 'directory'] "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].kind)"
    ),
    "file-kind-missing": (
        "Validation Error: 'kind' is a required property "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'])"
    ),
    "file-unknown-key": (
        "Validation Error: Additional properties are not allowed "
        "('mimetype' was unexpected) "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'])"
    ),
    "file-not-string": (
        "Validation Error: 'string' was expected "
        "(at $.properties.inputs.properties.reads.type)"
    ),
    "file-type-missing": (
        "Validation Error: 'type' is a required property "
        "(at $.properties.inputs.properties.reads)"
    ),
    "file-format-uri": (
        "Validation Error: False schema does not allow 'uri' "
        "(at $.properties.inputs.properties.reads)"
    ),
    "file-content-media-type": (
        "Validation Error: False schema does not allow 'text/csv' "
        "(at $.properties.inputs.properties.reads)"
    ),
    "file-media-type-bad": (
        "Validation Error: 'csv' does not match "
        "'^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}$' "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].mediaType)"
    ),
    "file-ontology-not-uri": (
        "Validation Error: 'format_2572' is not a 'uri' "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].ontology)"
    ),
    "file-compression-unknown": (
        "Validation Error: 'rar' is not one of "
        "['gzip', 'bgzip', 'bzip2', 'xz', 'zstd'] "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].compression)"
    ),
    "file-secondary-pattern-bad": (
        # The message shows the pattern's repr, with the backslash doubled
        r"Validation Error: '../etc/passwd' does not match "
        r"'^\\^*[.]*[A-Za-z0-9_+-][A-Za-z0-9_.+-]*$' "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].secondaryFiles[0])"
    ),
    "file-directory-secondary": (
        "Validation Error: False schema does not allow ['.bai'] "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'])"
    ),
    "file-scheme-bad": (
        "Validation Error: 'javascript' should not be valid under "
        "{'enum': ['javascript', 'vbscript', 'livescript', 'data', 'blob', "
        "'filesystem', 'file', 'jar', 'view-source', 'about']} "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].schemes[1])"
    ),
    "file-secondary-dots": (
        r"Validation Error: '^..' does not match "
        r"'^\\^*[.]*[A-Za-z0-9_+-][A-Za-z0-9_.+-]*$' "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].secondaryFiles[0])"
    ),
    "file-in-place-applicator": (
        "Validation Error: False schema does not allow [{'format': 'uri'}] "
        "(at $.properties.inputs.properties.reads)"
    ),
    "file-content-encoding": (
        "Validation Error: False schema does not allow 'base64' "
        "(at $.properties.inputs.properties.reads)"
    ),
    "file-directory-media-type": (
        "Validation Error: False schema does not allow 'text/csv' "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'])"
    ),
    "file-schemes-empty": (
        "Validation Error: [] should be non-empty "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].schemes)"
    ),
    "file-ontology-prefixed": (
        "Validation Error: 'edam:format_2572' does not match '^https?://' "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].ontology)"
    ),
    "file-in-tabular-column": (
        "Validation Error: 'kind' is a required property "
        "(at $.properties.inputs.properties.reads['x-ga4gh-tabular-schema'].items."
        "properties.fastq_1['x-ga4gh-file'])"
    ),
    "file-in-outputs": (
        "Validation Error: 'kind' is a required property "
        "(at $.properties.outputs.properties.reads['x-ga4gh-file'])"
    ),
    "file-scheme-pattern-bad": (
        "Validation Error: 's3://' does not match '^[a-z][a-z0-9+.-]*$' "
        "(at $.properties.inputs.properties.reads['x-ga4gh-file'].schemes[0])"
    ),
    "file-in-array-items": (
        "Validation Error: 'folder' is not one of ['file', 'directory'] "
        "(at $.properties.inputs.properties.reads.items['x-ga4gh-file'].kind)"
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
        "Validation Error: 'html' is not one of ['plain_text', 'markdown'] "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-description-format'])"
    ),
    "hidden-not-boolean": (
        "Validation Error: 'true' is not of type 'boolean' "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-hidden'])"
    ),
    # Keywords and values that version 0.3 removed (cut or deferred)
    "fa-icon-removed": (
        "Validation Error: Unevaluated properties are not allowed "
        "('x-ga4gh-fa-icon' was unexpected) "
        "(at $.properties.inputs.properties.sample_id)"
    ),
    "description-format-rst": (
        "Validation Error: 'rst' is not one of ['plain_text', 'markdown'] "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-description-format'])"
    ),
    "ui-widget-password": (
        "Validation Error: 'password' is not valid under any of the given schemas "
        "(at $.properties.inputs.properties.sample_id['x-ga4gh-ui-widget'])"
    ),
    "ui-widget-deferred-viewer": (
        "Validation Error: 'genome-browser' is not valid under any of the given "
        "schemas (at $.properties.outputs.properties.alignment['x-ga4gh-ui-widget'])"
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
    # The outputs model
    "outputs-boolean": (
        "Validation Error: True is not of type 'object' (at $.properties.outputs)"
    ),
    "outputs-not-object-type": (
        "Validation Error: 'object' was expected (at $.properties.outputs.type)"
    ),
    "outputs-applicator": (
        "Validation Error: False schema does not allow '#/$defs/outputs' "
        "(at $.properties.outputs)"
    ),
    "output-glob-tuple": (
        "Validation Error: False schema does not allow [{'type': 'integer'}] "
        "(at $.properties.outputs.properties.report)"
    ),
    "output-glob-not-string": (
        "Validation Error: 3 is not of type 'string' "
        "(at $.properties.outputs.properties.report['x-ga4gh-output-glob'])"
    ),
    **{
        name: (
            f"Validation Error: '{glob}' does not match '{OUTPUT_GLOB_PATTERN}' "
            "(at $.properties.outputs.properties.report['x-ga4gh-output-glob'])"
        )
        for name, glob in [
            ("output-glob-absolute", "/results/*.html"),
            # The message shows the value's repr, with the backslash doubled
            ("output-glob-backslash", r"results\\*.html"),
            ("output-glob-braces", "results/*.{html,htm}"),
            ("output-glob-empty-segment", "results//report.html"),
        ]
    },
    **{
        name: (
            f"Validation Error: '{glob}' should not be valid under "
            f"{{'pattern': '{OUTPUT_GLOB_NOT_PATTERN}'}} "
            "(at $.properties.outputs.properties.report['x-ga4gh-output-glob'])"
        )
        for name, glob in [
            ("output-glob-parent", "../secrets/*.txt"),
            ("output-glob-double-star", "results/**.html"),
        ]
    },
    "output-glob-on-scalar": (
        "Validation Error: 'integer' is not one of ['string', 'array'] "
        "(at $.properties.outputs.properties.report.type)"
    ),
    "output-glob-not-file": (
        "Validation Error: 'x-ga4gh-file' is a required property "
        "(at $.properties.outputs.properties.report)"
    ),
    "output-glob-items-not-file": (
        "Validation Error: 'x-ga4gh-file' is a required property "
        "(at $.properties.outputs.properties.report.items)"
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

    assert main(["validate", str(path)]) == 0

    assert "complies" in capsys.readouterr().out


#: Values of ``x-ga4gh-ui-widget`` that version 0.3 removed (cut or deferred).
REMOVED_WIDGETS = [
    "password",
    "genome-browser",
    "scatter-plot",
    "pdf-viewer",
    "markdown-viewer",
]

#: Viewers that version 0.3 keeps, and a platform-specific widget.
KEPT_OUTPUT_WIDGETS = ["table-viewer", "html-viewer", "custom:igv-browser"]


def _write_with_output_widget(tmp_path: Path, widget: str) -> Path:
    """Write the valid example with a UI widget on its output.

    Args:
        tmp_path: Directory to write the schema to.
        widget: Value of ``x-ga4gh-ui-widget`` for the output.

    Returns:
        Path of the written schema.
    """
    schema = json.loads((DATA_DIR / "valid.schema.json").read_text(encoding="utf-8"))
    output_vcf = schema["properties"]["outputs"]["properties"]["output_vcf"]
    output_vcf["x-ga4gh-ui-widget"] = widget
    path = tmp_path / "widget.schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    return path


@pytest.mark.parametrize("widget", REMOVED_WIDGETS)
def test_cli_rejects_removed_widget(
    widget: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that every widget removed in version 0.3 is rejected.

    Args:
        widget: Removed value of ``x-ga4gh-ui-widget``.
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    path = _write_with_output_widget(tmp_path, widget)

    assert main(["validate", str(path)]) == 1

    assert f"'{widget}' is not valid under any of the given schemas" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("widget", KEPT_OUTPUT_WIDGETS)
def test_cli_accepts_kept_output_widget(
    widget: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the viewers kept in version 0.3 and custom widgets are accepted.

    Args:
        widget: Value of ``x-ga4gh-ui-widget`` that stays valid.
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    path = _write_with_output_widget(tmp_path, widget)

    assert main(["validate", str(path)]) == 0

    assert "complies" in capsys.readouterr().out


@pytest.mark.parametrize("description_format", ["plain_text", "markdown"])
def test_cli_accepts_kept_description_format(
    description_format: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the description formats kept in version 0.3 are accepted.

    Args:
        description_format: Value of ``x-ga4gh-description-format``.
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = json.loads((DATA_DIR / "valid.schema.json").read_text(encoding="utf-8"))
    sample_id = schema["properties"]["inputs"]["properties"]["sample_id"]
    sample_id["x-ga4gh-description-format"] = description_format
    path = tmp_path / "format.schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")

    assert main(["validate", str(path)]) == 0

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
    assert main(["validate", str(path)]) == 0

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
    assert main(["validate", str(DATA_DIR / "invalid" / f"{name}.schema.json")]) == 1
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

    assert main(["validate", str(path)]) == 1
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

    assert main(["validate", str(schema), "--meta-schema", str(meta_schema)]) == 0

    assert (
        f"Success: '{schema}' complies with the meta-schema '{meta_schema}'."
        in capsys.readouterr().out
    )


def test_cli_reports_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a missing file is reported as such, with status 1.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(["validate", str(DATA_DIR / "does-not-exist.schema.json")]) == 3
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

    assert main(["validate", str(path)]) == 3
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

    assert (
        main(["validate", str(DATA_DIR / "valid.schema.json"), "-m", str(meta_schema)])
        == 3
    )
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

    monkeypatch.setattr(validate_command, "validate_schema", fail)

    assert main(["validate", str(DATA_DIR / "valid.schema.json")]) == 4
    assert "An unexpected error occurred: boom" in capsys.readouterr().err


def test_cli_omits_location_of_top_level_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that errors about the whole schema don't name the location ``$``.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert (
        main(["validate", str(DATA_DIR / "invalid" / "missing-schema.schema.json")])
        == 1
    )

    assert "(at $)" not in capsys.readouterr().err


def test_cli_rejects_meta_schema_that_is_no_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a meta-schema file holding e.g. ``null`` is reported.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    meta_schema = tmp_path / "null.json"
    meta_schema.write_text("null", encoding="utf-8")

    assert (
        main(["validate", str(DATA_DIR / "valid.schema.json"), "-m", str(meta_schema)])
        == 3
    )
    assert "Meta-schema Error: The meta-schema must be" in capsys.readouterr().err
