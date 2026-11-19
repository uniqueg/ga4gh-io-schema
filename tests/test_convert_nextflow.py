# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the nf-schema converter and of ``ga4gh-io-schema convert nextflow``."""

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.cli import main
from ga4gh_io_schema.cli.app import render_reference
from ga4gh_io_schema.converters.nextflow import (
    Conversion,
    ConversionError,
    Note,
    Output,
    SourceError,
    load_schema,
    sample_sheet_paths,
    to_ga4gh,
)
from ga4gh_io_schema.validator import load_profile, validate_schema
from ga4gh_io_schema.wes import from_workflow_params, to_workflow_params

DATA_DIR = Path(__file__).resolve().parent / "data" / "nextflow"
#: Pipelines of nf-core: nf-schema (Draft 2020-12) and nf-validation (Draft 7).
PIPELINES = ("demo", "fetchngs", "rnaseq")
DRAFT_7 = "http://json-schema.org/draft-07/schema"
DRAFT_2020 = "https://json-schema.org/draft/2020-12/schema"
SHEET = "assets/schema_input.json"


def nf_schema(
    properties: dict[str, Any] | None = None,
    groups: dict[str, Any] | None = None,
    **keywords: Any,
) -> dict[str, Any]:
    """Build an nf-schema file of Draft 2020-12.

    Args:
        properties: Parameters outside of groups.
        groups: Groups of parameters (``$defs``), each referenced from
            ``allOf``.
        **keywords: Other keywords of the root.

    Returns:
        The schema.
    """
    schema: dict[str, Any] = {"$schema": DRAFT_2020, "type": "object", **keywords}
    if groups:
        schema["$defs"] = groups
        schema["allOf"] = [{"$ref": f"#/$defs/{name}"} for name in groups]
    if properties is not None:
        schema["properties"] = properties
    return schema


def group(properties: dict[str, Any], **keywords: Any) -> dict[str, Any]:
    """Build a group of parameters.

    Args:
        properties: The parameters.
        **keywords: Other keywords of the group.

    Returns:
        The schema of the group.
    """
    return {"type": "object", "properties": properties, **keywords}


def parameter(conversion: Conversion, name: str, in_group: str = "") -> Any:
    """Return the converted schema of a parameter.

    Args:
        conversion: The conversion.
        name: Name of the parameter.
        in_group: Its group, or ``""`` for a parameter outside of groups.

    Returns:
        The schema of the parameter.
    """
    if in_group:
        return conversion.schema["$defs"][in_group]["properties"][name]
    return conversion.schema["properties"]["inputs"]["properties"][name]


def messages(conversion: Conversion) -> list[str]:
    """Return the messages of the notes of a conversion.

    Args:
        conversion: The conversion.

    Returns:
        The messages, in order.
    """
    return [note.message for note in conversion.notes]


def notes_with(conversion: Conversion, text: str) -> list[Note]:
    """Return the notes whose message contains a text.

    Args:
        conversion: The conversion.
        text: The text.

    Returns:
        The notes.
    """
    return [note for note in conversion.notes if text in note.message]


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Run the CLI.

    Args:
        argv: Arguments after ``ga4gh-io-schema``.
        capsys: Pytest fixture capturing the output.

    Returns:
        The exit status, standard output and standard error.
    """
    status = main(argv)
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def write_pipeline(
    directory: Path, schema: Any, sheets: dict[str, Any] | None = None
) -> Path:
    """Write the nf-schema file of a pipeline, and its sample-sheet schemas.

    Args:
        directory: Directory of the pipeline.
        schema: The nf-schema file.
        sheets: The sample-sheet schemas, by path in the pipeline.

    Returns:
        Path of the nf-schema file.
    """
    for relative, sheet in (sheets or {}).items():
        file = directory / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(sheet), encoding="utf-8")
    path = directory / "nextflow_schema.json"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema), encoding="utf-8")
    return path


# --- Pipelines of nf-core ---------------------------------------------------


@pytest.mark.parametrize("pipeline", PIPELINES)
def test_pipeline_converts_to_expected_schema(
    pipeline: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that each pipeline converts to its expected, valid IO schema.

    Args:
        pipeline: Directory of the pipeline in ``tests/data/nextflow``.
        capsys: Pytest fixture capturing the output.
    """
    status, out, err = run(
        ["convert", "nextflow", str(DATA_DIR / pipeline / "nextflow_schema.json")],
        capsys,
    )

    assert status == 0, err
    schema = json.loads(out)
    validate_schema(schema)
    expected = json.loads((DATA_DIR / pipeline / "expected.json").read_text("utf-8"))
    assert schema == expected


def test_demo_pipeline_maps_the_keywords_of_nf_schema() -> None:
    """Test the mapping of the nf-core/demo pipeline (nf-schema, 2020-12)."""
    source = load_schema(
        (DATA_DIR / "demo" / "nextflow_schema.json").read_text("utf-8"), "demo"
    )
    sheet = load_schema((DATA_DIR / "demo" / SHEET).read_text("utf-8"), SHEET)

    conversion = to_ga4gh(source, {SHEET: sheet})

    schema = conversion.schema
    assert schema["$schema"] == load_profile()["$id"]
    assert schema["x-ga4gh-workflow"] == {"descriptor_type": "NFL"}
    inputs = schema["properties"]["inputs"]
    assert inputs["allOf"][0] == {"$ref": "#/$defs/input_output_options"}
    assert "properties" not in inputs
    sheet_param = parameter(conversion, "input", "input_output_options")
    assert sheet_param["x-ga4gh-file"] == {"kind": "file"}
    assert sheet_param["x-ga4gh-description-format"] == "markdown"
    assert sheet_param["description"].startswith(
        "Path to comma-separated file containing information about the samples "
        "in the experiment.\n\nYou will need"
    )
    rows = sheet_param["x-ga4gh-tabular-schema"]
    assert rows["type"] == "array"
    assert rows["items"]["properties"]["fastq_1"]["x-ga4gh-file"] == {"kind": "file"}
    assert "meta" not in rows["items"]["properties"]["sample"]
    fasta = parameter(conversion, "fasta", "reference_genome_options")
    assert fasta["x-ga4gh-file"] == {"kind": "file", "mediaType": "text/plain"}
    assert "format" not in fasta and "exists" not in fasta and "fa_icon" not in fasta
    outdir = parameter(conversion, "outdir", "input_output_options")
    assert outdir["x-ga4gh-file"] == {"kind": "directory"}
    hidden = parameter(conversion, "igenomes_ignore", "reference_genome_options")
    assert hidden["x-ga4gh-hidden"] is True
    assert "hidden" not in hidden
    assert schema["properties"]["outputs"] == {"type": "object", "properties": {}}


def test_draft_7_pipeline_moves_definitions_to_defs() -> None:
    """Test that nf-validation's Draft 7 ``definitions`` become ``$defs``."""
    source = load_schema(
        (DATA_DIR / "fetchngs" / "nextflow_schema.json").read_text("utf-8"),
        "fetchngs",
    )

    conversion = to_ga4gh(source)

    assert "definitions" not in json.dumps(conversion.schema)
    assert conversion.schema["properties"]["inputs"]["allOf"][0] == {
        "$ref": "#/$defs/input_output_options"
    }
    assert "input_output_options" in conversion.schema["$defs"]


def test_rnaseq_pipeline_reports_paths_that_may_be_directories() -> None:
    """Test that ``format: path`` parameters are files, with a note each."""
    source = load_schema(
        (DATA_DIR / "rnaseq" / "nextflow_schema.json").read_text("utf-8"), "rnaseq"
    )

    conversion = to_ga4gh(source, directories=["star_index"])

    star = parameter(conversion, "star_index", "reference_genome_options")
    salmon = parameter(conversion, "salmon_index", "reference_genome_options")
    assert star["x-ga4gh-file"] == {"kind": "directory"}
    assert salmon["x-ga4gh-file"] == {"kind": "file"}
    notes = notes_with(conversion, "'format: path' is a file or a directory")
    assert len(notes) == 6
    assert "--directory salmon_index" in " ".join(note.message for note in notes)
    validate_schema(conversion.schema)


# --- Loading ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{", "Invalid JSON - x.json:"),
        ('{"default": NaN}', "Not JSON data - x.json: nan isn't a finite number"),
    ],
)
def test_invalid_sources_are_rejected(text: str, message: str) -> None:
    """Test that sources that aren't JSON data are rejected.

    Args:
        text: The source.
        message: Start of the error message.
    """
    with pytest.raises(SourceError) as info:
        load_schema(text, "x.json")
    assert info.value.message.startswith(message)


def test_sample_sheet_paths_are_found_in_schemas_only() -> None:
    """Test that sample-sheet paths are read from schemas, not from data."""
    source = nf_schema(
        {
            "schema": {"type": "string", "default": "x", "schema": "b.json"},
            "other": {"type": "string", "enum": [{"schema": "data.json"}]},
            "listed": {"anyOf": [{"type": "string", "schema": "a.json"}]},
            "again": {"type": "string", "schema": "a.json"},
        },
        groups={"g": group({"x": {"type": "string", "schema": "c.json"}})},
        dependencies={"x": ["y"]},
    )

    assert sample_sheet_paths(source) == ["a.json", "b.json", "c.json"]


# --- Structure --------------------------------------------------------------


def test_source_must_be_an_object() -> None:
    """Test that a source that isn't an object can't be converted."""
    with pytest.raises(ConversionError, match="must be a JSON object"):
        to_ga4gh([])


def test_parameters_outside_groups_stay_in_inputs() -> None:
    """Test a source without groups, and with an inputs type of its own."""
    conversion = to_ga4gh({"properties": {"n": {"type": "integer"}}})

    inputs = conversion.schema["properties"]["inputs"]
    assert inputs == {"properties": {"n": {"type": "integer"}}, "type": "object"}
    assert "$defs" not in conversion.schema
    assert "names no draft of JSON Schema" in messages(conversion)[0]


def test_outputs_are_added_without_a_note() -> None:
    """Test that the outputs given are the outputs of the IO schema."""
    conversion = to_ga4gh(
        nf_schema({}),
        outputs=[Output("report", "multiqc/multiqc_report.html")],
    )

    assert conversion.schema["properties"]["outputs"]["properties"] == {
        "report": {
            "type": "string",
            "x-ga4gh-file": {"kind": "file"},
            "x-ga4gh-output-glob": "multiqc/multiqc_report.html",
        }
    }
    assert not notes_with(conversion, "outputs")
    validate_schema(conversion.schema)


# --- Names of parameters ----------------------------------------------------


@pytest.mark.parametrize(
    ("name", "engine"),
    [
        ("out-dir", "outDir"),
        ("max-cpus-per-task", "maxCpusPerTask"),
        ("skip_qc-step2", "skip_qcStep2"),
        ("a-1b", "a1b"),
    ],
)
def test_dashed_parameters_bind_to_the_nextflow_name(name: str, engine: str) -> None:
    """Test that parameters with ``-`` bind to the name that Nextflow sets.

    Nextflow renames params-file keys from kebab-case to camelCase, and the
    translators reject keys with ``-`` for Nextflow; with the binding, the
    input keeps its name and translates to the parameter that Nextflow sets.

    Args:
        name: Name of the parameter in nf-schema.
        engine: Nextflow's name of it.
    """
    source = nf_schema(
        {name: {"type": "string"}},
        {"g": group({f"{name}-x": {"type": "integer"}})},
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, name) == {
        "type": "string",
        "x-ga4gh-parameter": {"name": engine},
    }
    assert parameter(conversion, f"{name}-x", "g")["x-ga4gh-parameter"] == {
        "name": f"{engine}X"
    }
    notes = notes_with(conversion, "Nextflow renames")
    assert len(notes) == 2
    assert any(
        f"'{name}' sets the parameter '{engine}'" in note.message for note in notes
    )
    validate_schema(conversion.schema)
    values = {name: "results", f"{name}-x": 2}
    params = to_workflow_params(conversion.schema, values)
    assert params == {engine: "results", f"{engine}X": 2}
    assert from_workflow_params(conversion.schema, params) == values


def test_dashed_parameter_keeps_a_binding_of_the_source() -> None:
    """Test that an ``x-ga4gh-parameter`` of the source wins, or gets the name."""
    source = nf_schema(
        {
            "out-dir": {"type": "string", "x-ga4gh-parameter": {"name": "outdir"}},
            "in-put": {"type": "string", "x-ga4gh-parameter": {"type": "path"}},
        }
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "out-dir")["x-ga4gh-parameter"] == {"name": "outdir"}
    assert parameter(conversion, "in-put")["x-ga4gh-parameter"] == {
        "type": "path",
        "name": "inPut",
    }
    assert len(notes_with(conversion, "Nextflow renames")) == 1
    # The source isn't changed
    assert source["properties"]["in-put"]["x-ga4gh-parameter"] == {"type": "path"}


@pytest.mark.parametrize(
    ("properties", "unbound", "reason"),
    [
        # Another parameter has the name
        (
            {"out-dir": {"type": "string"}, "outDir": {"type": "string"}},
            ["out-dir"],
            "another parameter has that name",
        ),
        # Two parameters get the same name
        (
            {"out-dir": {"type": "string"}, "out-Dir": {"type": "string"}},
            ["out-dir", "out-Dir"],
            "another parameter has that name",
        ),
        # The source binds another parameter to the name
        (
            {
                "out-dir": {"type": "string"},
                "o": {"type": "string", "x-ga4gh-parameter": {"name": "outDir"}},
            },
            ["out-dir"],
            "another parameter has that name",
        ),
        # Names whose camelCase name isn't certain
        ({"-a": {}}, ["-a"], "isn't kebab-case"),
        ({"a-": {}}, ["a-"], "isn't kebab-case"),
        ({"a--b": {}}, ["a--b"], "isn't kebab-case"),
        ({"a-é": {}}, ["a-é"], "isn't kebab-case"),
        ({"a-$b": {}}, ["a-$b"], "isn't kebab-case"),
    ],
)
def test_dashed_parameters_that_cant_be_bound_are_noted(
    properties: dict[str, Any], unbound: list[str], reason: str
) -> None:
    """Test that a parameter with ``-`` without a certain Nextflow name is noted.

    The translators reject values for it; the note says why.

    Args:
        properties: Parameters of the source.
        unbound: The parameters that get no binding.
        reason: Part of the note.
    """
    conversion = to_ga4gh(nf_schema(properties))

    for name in unbound:
        assert "x-ga4gh-parameter" not in parameter(conversion, name)
    notes = notes_with(conversion, "can't be translated")
    assert len(notes) == len(unbound)
    assert all(reason in note.message for note in notes)


def test_dashes_in_nested_properties_stay() -> None:
    """Test that only parameters get a binding: Nextflow renames only them."""
    source = nf_schema(
        {"rec": {"type": "object", "properties": {"a-b": {"type": "string"}}}}
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "rec") == {
        "type": "object",
        "properties": {"a-b": {"type": "string"}},
    }
    assert not notes_with(conversion, "Nextflow renames")


def test_dashed_parameter_with_a_wrong_binding_is_left_to_the_check() -> None:
    """Test that an ``x-ga4gh-parameter`` that isn't an object is kept as it is."""
    conversion = to_ga4gh(nf_schema({"out-dir": {"x-ga4gh-parameter": "outDir"}}))

    assert parameter(conversion, "out-dir") == {"x-ga4gh-parameter": "outDir"}
    assert not notes_with(conversion, "'out-dir'")


def test_sample_sheet_columns_keep_dashes_and_defaults() -> None:
    """Test that columns of sample sheets aren't parameters of Nextflow."""
    column = {"type": "string", "default": "${projectDir}/a.txt"}
    sheet = {
        "$schema": DRAFT_2020,
        "type": "array",
        "items": {"type": "object", "properties": {"read-group": column}},
    }
    source = nf_schema(
        {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
    )

    conversion = to_ga4gh(source, {SHEET: sheet})

    hint = parameter(conversion, "input")["x-ga4gh-tabular-schema"]
    assert hint["items"]["properties"]["read-group"] == column
    assert not notes_with(conversion, "read-group")
    assert not notes_with(conversion, "'${")


def test_defaults_with_nextflow_variables_are_dropped() -> None:
    """Test that a default with ``${`` is dropped, with a note.

    The translators reject strings with ``${`` for Nextflow; a client that
    sent the default would be rejected, and Nextflow sets its own default if
    the value is left out.
    """
    source = nf_schema(
        {
            "manifest": {"type": "string", "default": "${projectDir}/assets/a.txt"},
            "rec": {"type": "object", "default": {"a": "${launchDir}"}},
            "plain": {"type": "string", "default": "$HOME"},
            # Nested: dropped, but not a parameter of its own
            "obj": {
                "type": "object",
                "properties": {"p": {"default": "${launchDir}"}},
                "required": ["p"],
            },
        }
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "manifest") == {"type": "string"}
    assert parameter(conversion, "rec") == {"type": "object"}
    assert parameter(conversion, "plain")["default"] == "$HOME"
    assert parameter(conversion, "obj")["properties"]["p"] == {}
    assert parameter(conversion, "obj")["required"] == ["p"]
    notes = notes_with(conversion, "Dropped 'default'")
    assert len(notes) == 3
    assert "${projectDir}" in notes[0].message


def test_parameters_whose_default_is_dropped_are_not_required() -> None:
    """Test that a required parameter loses ``required`` with its default.

    Clients can't send the default, and Nextflow sets it when the value is
    left out; required, the input could take only other values.
    """
    variable = {"type": "string", "default": "${projectDir}/a.fa"}
    source = nf_schema(
        {"fasta": variable, "reads": {"type": "string"}},
        {
            "g": group({"gtf": variable}, required=["gtf"]),
            "h": group({"bed": variable, "n": {"type": "integer"}}, required=["n"]),
        },
        required=["fasta", "reads", "fasta"],
    )

    conversion = to_ga4gh(source)

    assert conversion.schema["properties"]["inputs"]["required"] == ["reads"]
    assert "required" not in conversion.schema["$defs"]["g"]
    assert conversion.schema["$defs"]["h"]["required"] == ["n"]
    assert len(notes_with(conversion, "from 'required'")) == 2
    assert to_workflow_params(conversion.schema, {"reads": "r", "n": 1}) == {
        "reads": "r",
        "n": 1,
    }


def test_allowed_values_with_nextflow_variables_are_noted() -> None:
    """Test that ``enum`` and ``const`` with ``${`` are kept, with a note.

    Dropping them would allow other values; the values with ``${`` can't be
    translated.
    """
    source = nf_schema(
        {
            "mode": {"type": "string", "enum": ["fast", "${launchDir}"]},
            "fixed": {"const": "${secrets}"},
            "plain": {"enum": ["$a", "{b}"]},
        }
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "mode")["enum"] == ["fast", "${launchDir}"]
    assert parameter(conversion, "fixed") == {"const": "${secrets}"}
    notes = notes_with(conversion, "can't be translated, as Nextflow replaces")
    assert len(notes) == 2
    assert "'enum'" in notes[0].message and "${launchDir}" in notes[0].message
    assert "'const'" in notes[1].message and "${secrets}" in notes[1].message


# --- Keywords of nf-schema --------------------------------------------------


@pytest.mark.parametrize(
    ("keywords", "description"),
    [
        ({"description": "Short.", "help_text": "*Long*."}, "Short.\n\n*Long*."),
        ({"help_text": "*Long*."}, "*Long*."),
        ({"description": "", "help_text": "*Long*."}, "*Long*."),
    ],
)
def test_help_text_is_appended_to_the_description(
    keywords: dict[str, Any], description: str
) -> None:
    """Test that ``help_text`` becomes part of a Markdown description.

    Args:
        keywords: Keywords of the parameter besides its type.
        description: The expected description.
    """
    conversion = to_ga4gh(nf_schema({"p": {"type": "string", **keywords}}))

    assert parameter(conversion, "p") == {
        "type": "string",
        "description": description,
        "x-ga4gh-description-format": "markdown",
    }


def test_help_text_keeps_a_description_format() -> None:
    """Test that a description format of the source is kept."""
    source = nf_schema(
        {"p": {"help_text": "x", "x-ga4gh-description-format": "plain_text"}}
    )

    assert parameter(to_ga4gh(source), "p")["x-ga4gh-description-format"] == (
        "plain_text"
    )


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("help_text", 1, "Dropped 'help_text': not a string."),
        (
            "hidden",
            "yes",
            "Dropped 'hidden': 'x-ga4gh-hidden' takes a bool, not \"yes\".",
        ),
        (
            "errorMessage",
            {"pattern": "No spaces"},
            "Dropped 'errorMessage': 'x-ga4gh-error-message' takes a str, not "
            '{"pattern": "No spaces"}.',
        ),
    ],
)
def test_keywords_with_wrong_values_are_dropped(
    keyword: str, value: Any, message: str
) -> None:
    """Test that keywords whose values the profile can't take are dropped.

    Args:
        keyword: The keyword.
        value: Its value.
        message: The note.
    """
    conversion = to_ga4gh(nf_schema({"p": {"type": "string", keyword: value}}))

    assert parameter(conversion, "p") == {"type": "string"}
    assert message in messages(conversion)


def test_hidden_and_error_message_are_renamed() -> None:
    """Test that ``hidden`` and ``errorMessage`` get their profile keywords."""
    source = nf_schema(
        {"p": {"type": "string", "hidden": True, "errorMessage": "No spaces."}}
    )

    assert parameter(to_ga4gh(source), "p") == {
        "type": "string",
        "x-ga4gh-hidden": True,
        "x-ga4gh-error-message": "No spaces.",
    }


def test_keyword_of_the_profile_wins() -> None:
    """Test that a keyword of the profile in the source is kept."""
    source = nf_schema({"p": {"hidden": True, "x-ga4gh-hidden": False}})

    conversion = to_ga4gh(source)

    assert parameter(conversion, "p") == {"x-ga4gh-hidden": False}
    assert "Dropped 'hidden': the schema has 'x-ga4gh-hidden'." in messages(conversion)


def test_engine_keywords_are_dropped_with_one_note_each() -> None:
    """Test the notes of ``fa_icon``, ``exists`` and ``meta``."""
    source = nf_schema(
        {
            "a": {"type": "boolean", "fa_icon": "fas fa-a"},
            "b": {"type": "boolean", "fa_icon": "fas fa-b", "meta": ["b"]},
            "c": {"type": "boolean", "exists": True},
        }
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "a") == {"type": "boolean"}
    assert parameter(conversion, "b") == {"type": "boolean"}
    icons = notes_with(conversion, "'fa_icon'")
    assert [note.location for note in icons] == ["$.properties.inputs.properties.a"]
    assert icons[0].message.startswith("Dropped 'fa_icon' (here and 1 more): ")
    assert "no icon keyword since version 0.3.0:" in icons[0].message
    assert notes_with(conversion, "'meta' (here):")
    exists = notes_with(conversion, "'exists'")[0].message
    assert "skips it for object-store paths" in exists


@pytest.mark.parametrize("keyword", ["uniqueEntries", "unique"])
def test_unique_entries_are_not_unique_items(keyword: str) -> None:
    """Test that uniqueness across rows isn't mapped to ``uniqueItems``.

    Args:
        keyword: The keyword of nf-schema or nf-validation.
    """
    conversion = to_ga4gh(nf_schema({"rows": {"type": "array", keyword: ["sample"]}}))

    assert parameter(conversion, "rows") == {"type": "array"}
    assert f"Dropped '{keyword}'" in messages(conversion)[-2]
    assert "isn't 'uniqueItems'" in messages(conversion)[-2]


# --- File references --------------------------------------------------------


@pytest.mark.parametrize(
    ("form", "kind"), [("file-path", "file"), ("directory-path", "directory")]
)
def test_path_formats_become_file_references(form: str, kind: str) -> None:
    """Test ``format: file-path`` and ``format: directory-path``.

    Args:
        form: The format.
        kind: The kind of the file reference.
    """
    conversion = to_ga4gh(nf_schema({"p": {"type": "string", "format": form}}))

    assert parameter(conversion, "p") == {
        "type": "string",
        "x-ga4gh-file": {"kind": kind},
    }
    assert len(conversion.notes) == 1  # the outputs


def test_path_format_of_a_parameter_can_be_a_directory() -> None:
    """Test ``format: path`` outside of groups, named with ``--directory``."""
    source = nf_schema({"index": {"type": "string", "format": "path"}})

    conversion = to_ga4gh(source, directories=["index"])

    assert parameter(conversion, "index")["x-ga4gh-file"] == {"kind": "directory"}
    assert not notes_with(conversion, "'format: path'")


def test_path_format_outside_of_parameters_is_a_file() -> None:
    """Test ``format: path`` in a sample sheet, which options can't name."""
    sheet = {
        "type": "array",
        "items": {"properties": {"d": {"type": "string", "format": "path"}}},
    }
    source = nf_schema(
        {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
    )

    conversion = to_ga4gh(source, {SHEET: sheet})

    rows = parameter(conversion, "input")["x-ga4gh-tabular-schema"]
    assert rows["items"]["properties"]["d"]["x-ga4gh-file"] == {"kind": "file"}
    assert notes_with(conversion, "if it's a directory, edit the result")


@pytest.mark.parametrize(
    ("properties", "message"),
    [
        (
            {"p": {"type": "string", "format": "file-path"}},
            "'p' (--directory) has 'format: file-path', not 'format: path'.",
        ),
        (
            {"p": {"type": "string"}},
            "'p' (--directory) can't be a directory: it isn't marked",
        ),
        ({}, "No parameter 'p' with 'format: path' (--directory)."),
    ],
)
def test_directories_must_name_path_parameters(
    properties: dict[str, Any], message: str
) -> None:
    """Test that ``--directory`` names only parameters with ``format: path``.

    Args:
        properties: Parameters of the source.
        message: Start of the error.
    """
    with pytest.raises(ConversionError) as info:
        to_ga4gh(nf_schema(properties), directories=["p"])
    assert info.value.message.startswith(message)


def test_file_path_pattern_fails_without_opt_out() -> None:
    """Test that a glob (``format: file-path-pattern``) is an error by default."""
    source = nf_schema({"reads": {"type": "string", "format": "file-path-pattern"}})

    with pytest.raises(ConversionError) as info:
        to_ga4gh(source)

    assert info.value.message.startswith("'format: file-path-pattern' is a glob")
    assert "--allow-unmarked-files (allow_unmarked_files=True)" in info.value.message
    assert info.value.location == "$.properties.inputs.properties.reads"


def test_file_path_pattern_stays_a_plain_string() -> None:
    """Test that a glob isn't a reference, with ``allow_unmarked_files``."""
    source = nf_schema({"reads": {"type": "string", "format": "file-path-pattern"}})

    conversion = to_ga4gh(source, allow_unmarked_files=True)

    assert parameter(conversion, "reads") == {"type": "string"}
    assert "a glob isn't a reference" in messages(conversion)[0]


@pytest.mark.parametrize(
    ("schema", "problem"),
    [
        ({"type": ["string", "null"]}, 'its type is ["string", "null"], not "string"'),
        ({"type": "string", "anyOf": [{}]}, "it has 'anyOf'"),
        (
            {"type": "string", "x-ga4gh-file": {"kind": "file"}},
            "it has 'x-ga4gh-file' already",
        ),
    ],
)
def test_schemas_that_cant_be_file_references_are_kept(
    schema: dict[str, Any], problem: str
) -> None:
    """Test that a path format is kept where a file reference can't be.

    With ``allow_unmarked_files``; without, an unmarked schema is an error
    (see ``test_unmarkable_path_formats_fail_without_opt_out``).

    Args:
        schema: The schema, without its format.
        problem: Why it can't be a file reference.
    """
    source = nf_schema(
        {
            "p": {
                **schema,
                "format": "file-path",
                "mimetype": "text/csv",
                "schema": SHEET,
            }
        }
    )
    conversion = to_ga4gh(source, allow_unmarked_files=True)

    assert parameter(conversion, "p") == {**schema, "format": "file-path"}
    assert (
        f"Not marked as a file reference ('format: file-path'): {problem}."
        in messages(conversion)
    )
    assert notes_with(conversion, "Dropped 'mimetype': only file references")
    assert notes_with(conversion, "Dropped 'schema': only file references")


@pytest.mark.parametrize(
    ("schema", "problem"),
    [
        ({"type": ["string", "null"]}, 'its type is ["string", "null"], not "string"'),
        ({"type": "string", "anyOf": [{}]}, "it has 'anyOf'"),
    ],
)
def test_unmarkable_path_formats_fail_without_opt_out(
    schema: dict[str, Any], problem: str
) -> None:
    """Test that a path format that can't be a file reference is an error.

    Args:
        schema: The schema, without its format.
        problem: Why it can't be a file reference.
    """
    with pytest.raises(ConversionError) as info:
        to_ga4gh(nf_schema({"p": {**schema, "format": "file-path"}}))

    assert info.value.message.startswith(
        f"Can't mark 'format: file-path' as a file reference: {problem}. "
    )
    assert "--allow-unmarked-files (allow_unmarked_files=True)" in info.value.message
    assert info.value.location == "$.properties.inputs.properties.p"


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "not": {"format": "file-path"}},
        {"type": "string", "if": {"format": "file-path"}, "then": {"minLength": 1}},
        {"type": "string", "not": {"format": "file-path-pattern"}},
    ],
)
def test_path_formats_in_conditions_convert_without_opt_out(
    schema: dict[str, Any],
) -> None:
    """Test that ``not`` and ``if`` don't declare files, so they don't fail.

    Args:
        schema: The schema of the parameter.
    """
    conversion = to_ga4gh(nf_schema({"p": schema}))

    result = parameter(conversion, "p")
    assert "x-ga4gh-file" not in result
    assert notes_with(conversion, "Not marked as a file reference") or notes_with(
        conversion, "a glob isn't a reference"
    )
    # The condition is kept; a glob loses its format, a path keeps it
    condition = result.get("not", result.get("if"))
    form = (schema.get("not") or schema["if"])["format"]
    assert condition.get("format") == (None if form == "file-path-pattern" else form)


@pytest.mark.parametrize("branch", ["then", "else"])
def test_unmarkable_path_format_in_then_or_else_fails(branch: str) -> None:
    """Test that ``then`` and ``else``, unlike ``if``, declare inputs.

    Args:
        branch: The branch of the condition that holds the path format.
    """
    schema = {
        "type": "string",
        "if": {"minLength": 1},
        branch: {"type": ["string", "null"], "format": "file-path"},
    }

    with pytest.raises(ConversionError) as info:
        to_ga4gh(nf_schema({"p": schema}))

    assert info.value.location == f"$.properties.inputs.properties.p.{branch}"


def test_parameter_named_not_is_checked() -> None:
    """Test that a parameter called ``not`` is a parameter, not a condition."""
    source = nf_schema({"not": {"type": ["string", "null"], "format": "file-path"}})

    with pytest.raises(ConversionError, match="Can't mark 'format: file-path'"):
        to_ga4gh(source)


@pytest.mark.parametrize("name", ["properties", "patternProperties", "$defs"])
def test_conditions_under_parameters_named_like_keywords_are_notes(
    name: str,
) -> None:
    """Test that a condition stays a note under a name that reads like a keyword.

    Args:
        name: The name of the parameter.
    """
    bad = {"type": ["string", "null"], "format": "file-path"}
    source = nf_schema({name: {"type": "string", "not": bad}})

    conversion = to_ga4gh(source)

    assert notes_with(conversion, "Not marked as a file reference")
    assert parameter(conversion, name)["not"] == bad


def test_unmarkable_path_format_in_items_fails() -> None:
    """Test that a path format under a keyword like ``items`` is checked."""
    items = {"type": ["string", "null"], "format": "file-path"}
    source = nf_schema({"p": {"type": "array", "items": items}})

    with pytest.raises(ConversionError) as info:
        to_ga4gh(source)

    assert info.value.location == "$.properties.inputs.properties.p.items"


def test_inline_tabular_hint_columns_are_notes() -> None:
    """Test that columns of an inline tabular hint stay notes, as from a sheet."""
    column = {"type": ["string", "null"], "format": "file-path"}
    hint = {"type": "array", "items": {"type": "object", "properties": {"f": column}}}
    source = nf_schema(
        {
            "input": {
                "type": "string",
                "format": "file-path",
                "x-ga4gh-tabular-schema": hint,
            }
        }
    )

    conversion = to_ga4gh(source)

    assert notes_with(conversion, "Not marked as a file reference")
    kept = parameter(conversion, "input")["x-ga4gh-tabular-schema"]
    assert kept["items"]["properties"]["f"] == column


def test_path_format_without_own_type_names_the_fix() -> None:
    """Test the error for a path format in a subschema without a type."""
    source = nf_schema({"p": {"type": "string", "allOf": [{"format": "file-path"}]}})

    with pytest.raises(ConversionError) as info:
        to_ga4gh(source)

    assert "it has no 'type' of its own" in info.value.message
    assert info.value.location == "$.properties.inputs.properties.p.allOf[0]"


def test_sample_sheet_columns_that_cant_be_marked_are_notes() -> None:
    """Test that columns of a sample sheet stay notes: no server validates them."""
    sheet = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "f": {"type": ["string", "null"], "format": "file-path"},
                "g": {"type": "string", "format": "file-path-pattern"},
            },
        },
    }
    source = nf_schema(
        {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
    )

    conversion = to_ga4gh(source, {SHEET: sheet})

    assert notes_with(conversion, "Not marked as a file reference")
    assert notes_with(conversion, "a glob isn't a reference")
    columns = parameter(conversion, "input")["x-ga4gh-tabular-schema"]["items"][
        "properties"
    ]
    assert columns["f"] == {"type": ["string", "null"], "format": "file-path"}
    assert columns["g"] == {"type": "string"}


def test_path_format_marked_by_the_source_converts_without_opt_out() -> None:
    """Test that a schema that the source marks itself isn't an error."""
    schema = {"type": "string", "x-ga4gh-file": {"kind": "file"}}

    conversion = to_ga4gh(nf_schema({"p": {**schema, "format": "file-path"}}))

    assert parameter(conversion, "p") == {**schema, "format": "file-path"}
    assert notes_with(conversion, "it has 'x-ga4gh-file' already")


def test_keywords_of_files_are_dropped_from_other_schemas() -> None:
    """Test ``mimetype`` and ``schema`` on a parameter without a path format."""
    conversion = to_ga4gh(nf_schema({"p": {"type": "string", "mimetype": "a/b"}}))

    assert parameter(conversion, "p") == {"type": "string"}
    assert "Dropped 'mimetype'" in messages(conversion)[0]


def test_content_keywords_are_dropped_from_file_references() -> None:
    """Test that keywords that a file reference can't have are dropped."""
    source = nf_schema(
        {"p": {"type": "string", "format": "file-path", "contentEncoding": "base64"}}
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "p") == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
    }
    assert "Dropped 'contentEncoding': file references can't have it." in messages(
        conversion
    )


@pytest.mark.parametrize(
    ("form", "mimetype"),
    [("file-path", "text csv"), ("file-path", 1), ("directory-path", "text/csv")],
)
def test_mimetype_must_be_a_media_type_of_a_file(form: str, mimetype: Any) -> None:
    """Test that ``mimetype`` is dropped unless it's a media type of a file.

    Args:
        form: The format of the parameter.
        mimetype: Its ``mimetype``.
    """
    source = nf_schema({"p": {"type": "string", "format": form, "mimetype": mimetype}})

    conversion = to_ga4gh(source)

    assert "mediaType" not in parameter(conversion, "p")["x-ga4gh-file"]
    assert (
        f"Dropped 'mimetype': {json.dumps(mimetype)} isn't the media type"
        in (messages(conversion)[0])
    )


def test_pattern_of_file_references_is_kept_with_a_note() -> None:
    """Test that ``pattern`` stays on file references, with one note."""
    source = nf_schema(
        {
            "a": {"type": "string", "format": "file-path", "pattern": "\\.csv$"},
            "b": {"type": "string", "pattern": "\\.csv$"},
        }
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "a")["pattern"] == "\\.csv$"
    notes = notes_with(conversion, "Kept 'pattern'")
    assert [note.location for note in notes] == ["$.properties.inputs.properties.a"]
    assert "(here)" in notes[0].message


# --- Sample sheets ----------------------------------------------------------


def test_sample_sheet_becomes_the_tabular_hint() -> None:
    """Test a Draft 7 sample sheet with its own definitions and references."""
    sheet = {
        "$schema": DRAFT_7,
        "type": "array",
        "definitions": {"id": {"type": "string", "pattern": "^\\S+$"}},
        "items": {
            "type": "object",
            "properties": {
                "sample": {"$ref": "#/definitions/id"},
                "fastq": {"type": "string", "format": "file-path", "exists": True},
            },
        },
        "uniqueEntries": ["sample"],
    }
    source = nf_schema(
        groups={
            "io": group(
                {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
            )
        }
    )

    conversion = to_ga4gh(source, {SHEET: sheet})

    hint = parameter(conversion, "input", "io")["x-ga4gh-tabular-schema"]
    assert hint["$defs"] == {"id": {"type": "string", "pattern": "^\\S+$"}}
    assert hint["items"]["properties"]["sample"] == {
        "$ref": "#/$defs/io/properties/input/x-ga4gh-tabular-schema/$defs/id"
    }
    assert hint["items"]["properties"]["fastq"] == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
    }
    assert "uniqueEntries" not in hint
    assert not notes_with(conversion, "points to nothing")
    validate_schema(conversion.schema)


def test_missing_sample_sheet_is_noted() -> None:
    """Test that a sample sheet that isn't given gets no hint."""
    source = nf_schema(
        {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
    )

    conversion = to_ga4gh(source)

    assert parameter(conversion, "input") == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
    }
    assert f"The sample-sheet schema '{SHEET}' wasn't found" in messages(conversion)[0]


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "format": "directory-path", "schema": SHEET},
        {"type": "string", "format": "file-path", "schema": 1},
    ],
)
def test_sample_sheets_only_for_files(schema: dict[str, Any]) -> None:
    """Test that only file references take a sample sheet, by its path.

    Args:
        schema: Schema of the parameter.
    """
    conversion = to_ga4gh(nf_schema({"p": schema}), {SHEET: {"type": "array"}})

    assert "x-ga4gh-tabular-schema" not in parameter(conversion, "p")
    assert "Dropped 'schema': only files of parameters" in messages(conversion)[0]


def test_tabular_hint_of_the_source_wins() -> None:
    """Test that a hint of the source is kept, and ``schema`` dropped."""
    hint = {"type": "array", "title": "Mine"}
    source = nf_schema(
        {
            "input": {
                "type": "string",
                "format": "file-path",
                "schema": SHEET,
                "x-ga4gh-tabular-schema": hint,
            }
        }
    )

    conversion = to_ga4gh(source, {SHEET: {"type": "array"}})

    assert parameter(conversion, "input")["x-ga4gh-tabular-schema"] == hint
    assert "Dropped 'schema': the schema has 'x-ga4gh-tabular-schema'." in messages(
        conversion
    )


def test_sample_sheet_is_converted_once() -> None:
    """Test that a second parameter with the same sheet references the first."""
    sheet = {"type": "array", "items": {"$anchor": "row", "type": "object"}}
    file_param = {"type": "string", "format": "file-path", "schema": SHEET}
    source = nf_schema({"a": file_param, "b": {"anyOf": [file_param]}})

    conversion = to_ga4gh(source, {SHEET: sheet})

    assert parameter(conversion, "a")["x-ga4gh-tabular-schema"]["items"] == {
        "$anchor": "row",
        "type": "object",
    }
    assert parameter(conversion, "b")["anyOf"][0]["x-ga4gh-tabular-schema"] == {
        "$ref": "#/properties/inputs/properties/a/x-ga4gh-tabular-schema"
    }
    assert notes_with(conversion, "referenced, not converted again")
    assert not notes_with(conversion, "points to nothing")
    validate_schema(conversion.schema)


@pytest.mark.parametrize("sheets", [{}, {SHEET: {"type": "array"}}])
def test_sample_sheet_in_a_dropped_keyword_is_skipped(sheets: dict[str, Any]) -> None:
    """Test a sheet named in a keyword that file references can't have.

    Args:
        sheets: The sample-sheet schemas given.
    """
    inner = {"type": "string", "format": "file-path", "schema": SHEET}
    source = nf_schema(
        {"a": {"type": "string", "format": "file-path", "contentSchema": inner}}
    )

    conversion = to_ga4gh(source, sheets)

    assert parameter(conversion, "a") == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
    }
    assert not notes_with(conversion, "sample-sheet schema")
    assert notes_with(conversion, "Dropped 'contentSchema'")


def test_sample_sheets_are_not_nested() -> None:
    """Test that a sample sheet in a sample sheet isn't converted."""
    sheet = {
        "type": "array",
        "items": {
            "properties": {
                "sub": {"type": "string", "format": "file-path", "schema": "x.json"}
            }
        },
    }
    source = nf_schema(
        {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
    )

    conversion = to_ga4gh(source, {SHEET: sheet, "x.json": {"type": "array"}})

    hint = parameter(conversion, "input")["x-ga4gh-tabular-schema"]
    assert "x-ga4gh-tabular-schema" not in hint["items"]["properties"]["sub"]
    assert notes_with(conversion, "Dropped 'schema': only files of parameters")


def test_sample_sheet_that_cant_be_converted_is_an_error() -> None:
    """Test that a sample sheet that can't be converted raises an error."""
    source = nf_schema(
        {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
    )

    with pytest.raises(ConversionError, match="Not a schema"):
        to_ga4gh(source, {SHEET: {"items": 1}})


# --- Command line -----------------------------------------------------------


def test_cli_reads_sample_sheets_from_the_pipeline_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test ``--pipeline-dir``, ``--directory``, the outputs and ``--json``.

    Args:
        tmp_path: Temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    source = nf_schema(
        {
            "input": {"type": "string", "format": "file-path", "schema": SHEET},
            "index": {"type": "string", "format": "path"},
        }
    )
    pipeline = tmp_path / "pipeline"
    write_pipeline(pipeline, {}, {SHEET: {"type": "array"}})
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(source), encoding="utf-8")

    status, out, err = run(
        [
            "convert",
            "nextflow",
            str(schema_file),
            "--pipeline-dir",
            str(pipeline),
            "--directory",
            "index",
            "--out-files",
            "bams=star/*.bam",
            "--json",
        ],
        capsys,
    )

    assert status == 0, err
    assert err == ""
    result = json.loads(out)
    properties = result["schema"]["properties"]
    assert properties["inputs"]["properties"]["input"]["x-ga4gh-tabular-schema"] == {
        "type": "array"
    }
    assert properties["inputs"]["properties"]["index"]["x-ga4gh-file"] == {
        "kind": "directory"
    }
    assert properties["outputs"]["properties"]["bams"]["x-ga4gh-output-glob"] == (
        "star/*.bam"
    )
    assert any("tabular hint" in note["message"] for note in result["notes"])


def test_cli_reads_standard_input_relative_to_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that the sample sheets of standard input are in the working directory.

    Args:
        tmp_path: Temporary directory.
        monkeypatch: Pytest fixture for patching standard input.
        capsys: Pytest fixture capturing the output.
    """
    source = nf_schema(
        {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
    )
    write_pipeline(tmp_path, source, {SHEET: {"type": "array"}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(source).encode()))
    )

    status, out, err = run(["convert", "nextflow", "-"], capsys)

    assert status == 0, err
    hint = json.loads(out)["properties"]["inputs"]["properties"]["input"]
    assert hint["x-ga4gh-tabular-schema"] == {"type": "array"}
    assert "is the experimental tabular hint" in err


def test_cli_allows_unmarked_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test ``--allow-unmarked-files`` of ``convert nextflow``.

    Args:
        tmp_path: Temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    path = write_pipeline(
        tmp_path,
        nf_schema({"reads": {"type": "string", "format": "file-path-pattern"}}),
    )

    status, out, err = run(["convert", "nextflow", str(path)], capsys)
    assert status == 1
    assert out == ""
    assert "'format: file-path-pattern' is a glob" in err

    reference = " ".join(render_reference().split())
    assert "(format: file-path-pattern), which can hold files" in reference
    assert ",," not in reference

    command = ["convert", "nextflow", "--allow-unmarked-files", str(path)]
    status, _, err = run(command, capsys)
    assert status == 0
    assert "a glob isn't a reference to one file" in err


def test_cli_notes_a_missing_sample_sheet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a sample sheet that isn't there is noted, not an error.

    Args:
        tmp_path: Temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    path = write_pipeline(
        tmp_path,
        nf_schema(
            {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
        ),
    )

    status, _, err = run(["convert", "nextflow", str(path)], capsys)

    assert status == 0
    assert f"Note: The sample-sheet schema '{SHEET}' wasn't found" in err


@pytest.mark.parametrize(
    ("sheet_path", "sheets", "message"),
    [
        (
            "../outside.json",
            {},
            "Error: The sample-sheet schema '../outside.json' is outside the "
            "directory of the pipeline",
        ),
        (SHEET, {SHEET: "{"}, "Error: Invalid JSON - "),
        (
            "a\x00b",
            {},
            "Error: The sample-sheet schema 'a\x00b' isn't a valid path: ",
        ),
    ],
)
def test_cli_rejects_bad_sample_sheets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sheet_path: str,
    sheets: dict[str, str],
    message: str,
) -> None:
    """Test sample sheets outside of the pipeline, and invalid ones.

    Args:
        tmp_path: Temporary directory.
        capsys: Pytest fixture capturing the output.
        sheet_path: The path that the source gives.
        sheets: Texts of the sample-sheet files, by path in the pipeline.
        message: Start of the error.
    """
    pipeline = tmp_path / "pipeline"
    path = write_pipeline(
        pipeline,
        nf_schema(
            {"input": {"type": "string", "format": "file-path", "schema": sheet_path}}
        ),
    )
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    for name, text in sheets.items():
        (pipeline / name).parent.mkdir(parents=True, exist_ok=True)
        (pipeline / name).write_text(text, encoding="utf-8")

    status, out, err = run(["convert", "nextflow", str(path)], capsys)

    assert status == 3
    assert out == ""
    assert err.startswith(message)


@pytest.mark.parametrize(
    ("source", "argv", "status", "message"),
    [
        # Valid JSON (Python 3.14 parses it), too deep to convert
        (
            '{"properties": {"a": ' * 20_000 + "{}" + "}}" * 20_000,
            [],
            3,
            "Error: Too deeply nested to convert",
        ),
        ("[]", [], 1, "Validation Error: The nf-schema must be a JSON object."),
        (
            json.dumps(nf_schema({"p": {"type": "string"}})),
            ["--directory", "p"],
            1,
            "Validation Error: 'p' (--directory) can't be a directory",
        ),
        (
            json.dumps(nf_schema({"p": {"x-ga4gh-hidden": "no"}})),
            [],
            1,
            "Validation Error: The converted schema doesn't comply with the GA4GH "
            "IO Profile: ",
        ),
    ],
)
def test_cli_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source: str,
    argv: list[str],
    status: int,
    message: str,
) -> None:
    """Test the errors of the command and their exit status.

    Args:
        tmp_path: Temporary directory.
        capsys: Pytest fixture capturing the output.
        source: Text of the nf-schema file.
        argv: More arguments.
        status: The exit status.
        message: Start of the error.
    """
    path = tmp_path / "nextflow_schema.json"
    path.write_text(source, encoding="utf-8")

    result, out, err = run(["convert", "nextflow", str(path), *argv], capsys)

    assert result == status
    assert out == ""
    assert err.startswith(message)


def test_cli_reports_sheet_paths_that_cant_be_checked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that an error of the file check (e.g., no access) exits with 3.

    Args:
        tmp_path: Temporary directory.
        monkeypatch: Pytest fixture for patching the file check.
        capsys: Pytest fixture capturing the output.
    """
    path = write_pipeline(
        tmp_path,
        nf_schema(
            {"input": {"type": "string", "format": "file-path", "schema": SHEET}}
        ),
    )

    def is_file(self: Path) -> bool:
        """Fail like a path in a directory without access.

        Args:
            self: The path.

        Raises:
            PermissionError: Always.
        """
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "is_file", is_file)

    status, out, err = run(["convert", "nextflow", str(path)], capsys)

    assert status == 3
    assert out == ""
    assert err.startswith(
        f"Error: The sample-sheet schema '{SHEET}' isn't a valid path: "
    )
