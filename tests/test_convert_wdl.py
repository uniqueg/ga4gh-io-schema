# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the WDL converter and the ``convert wdl`` subcommand.

The fixtures in ``tests/data/wdl/biowdl-qc`` are the QC workflow of BioWDL
(``biowdl/QC`` at ``ce4ca66d5cf1a1b08b14458961a909854de8d15c``) and the two
tasks that it imports (``biowdl/tasks`` at
``31d6845927dc0b8a783e86801cc4b9332fe53ba1``), unchanged, under the MIT
licence of the Leiden University Medical Center. ``types.wdl`` and
``tasks/count.wdl`` are written for these tests.
"""

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.cli import main
from ga4gh_io_schema.converters import wdl
from ga4gh_io_schema.validator import load_profile, validate_schema

WDL_DIR = Path(__file__).resolve().parent / "data" / "wdl"
QC = WDL_DIR / "biowdl-qc" / "QC.wdl"
TYPES = WDL_DIR / "types.wdl"


def _convert(path: Path, **kwargs: Any) -> wdl.Conversion:
    """Convert a WDL file.

    Args:
        path: Path of the file.
        **kwargs: Options of :func:`ga4gh_io_schema.converters.wdl.convert`.

    Returns:
        The conversion.
    """
    return wdl.convert(path, path.read_text(encoding="utf-8"), **kwargs)


def _write(directory: Path, text: str, name: str = "main.wdl") -> Path:
    """Write a WDL document.

    Args:
        directory: Directory to write it in.
        text: Content of the document.
        name: Name of the file.

    Returns:
        The path of the file.
    """
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _inputs(conversion: wdl.Conversion) -> dict[str, Any]:
    """Return the schemas of the inputs of a conversion.

    Args:
        conversion: The conversion.

    Returns:
        The properties of ``inputs``.
    """
    properties: dict[str, Any] = conversion.schema["properties"]["inputs"]["properties"]
    return properties


def _messages(conversion: wdl.Conversion) -> dict[str, str]:
    """Return the notes of a conversion by location.

    Args:
        conversion: The conversion.

    Returns:
        The messages of the notes, by location (joined if several).
    """
    messages: dict[str, str] = {}
    for note in conversion.notes:
        messages[note.location] = " | ".join(
            filter(None, [messages.get(note.location), note.message])
        )
    return messages


# Fixtures from public workflows


def test_biowdl_qc_converts_to_a_valid_schema() -> None:
    """Test that the BioWDL QC workflow converts to a valid IO schema."""
    conversion = _convert(QC)
    schema = conversion.schema

    validate_schema(schema)
    assert schema["$schema"] == load_profile()["$id"]
    assert schema["title"] == "QC"
    workflow = schema["x-ga4gh-workflow"]
    assert workflow["descriptor_type"] == "WDL"
    assert workflow["descriptor_type_version"] == "1.0"
    assert workflow["entry_point"] == "QC"
    assert workflow["checksum"] == [
        {
            "type": "sha-256",
            "checksum": wdl.descriptor_checksum(QC.read_text(encoding="utf-8")),
        }
    ]
    inputs = schema["properties"]["inputs"]
    assert inputs["required"] == ["read1"]
    assert inputs["additionalProperties"] is False
    assert inputs["properties"]["read1"] == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
        "description": "The first or single end fastq file to be run through cutadapt.",
        "x-ga4gh-parameter": {"type": "File"},
    }
    assert inputs["properties"]["dockerImages"]["x-ga4gh-hidden"] is True
    assert inputs["properties"]["contaminations"]["minItems"] == 1
    assert not any("." in name for name in inputs["properties"])
    outputs = schema["properties"]["outputs"]["properties"]
    assert outputs["qcRead2"]["anyOf"][1] == {"type": "null"}
    assert outputs["reports"]["items"]["x-ga4gh-file"] == {"kind": "file"}
    assert {note.location for note in conversion.notes} == {
        "$.properties.inputs.properties.readgroupName",
        "$.properties.inputs.properties.runAdapterClipping",
    }


def test_biowdl_qc_with_nested_inputs() -> None:
    """Test that nested inputs come from the calls, hidden, with their meta."""
    schema = _convert(QC, nested_inputs=True).schema

    validate_schema(schema)
    threads = schema["properties"]["inputs"]["properties"]["FastqcRead1.threads"]
    assert threads["x-ga4gh-hidden"] is True
    assert threads["default"] == 1
    assert threads["description"].startswith("The number of cores")
    assert "Cutadapt.cores" in schema["properties"]["inputs"]["properties"]
    assert schema["properties"]["inputs"]["required"] == ["read1"]


def test_biowdl_task_converts() -> None:
    """Test that a task of a document with several tasks can be chosen."""
    fastqc = QC.parent / "tasks" / "fastqc.wdl"

    schema = _convert(fastqc, task="Fastqc").schema

    validate_schema(schema)
    assert schema["x-ga4gh-workflow"]["entry_point"] == "Fastqc"
    assert "seqFile" in schema["properties"]["inputs"]["required"]


# Types, defaults and parameter_meta


def test_types_convert_to_a_valid_schema() -> None:
    """Test that the fixture with every type converts to a valid schema."""
    conversion = _convert(TYPES, nested_inputs=True)

    validate_schema(conversion.schema)
    assert conversion.schema["description"] == "Every WDL type."
    assert conversion.schema["x-ga4gh-workflow"]["descriptor_type_version"] == "1.1"


def test_primitive_types() -> None:
    """Test the schemas of primitive types and their defaults."""
    inputs = _inputs(_convert(TYPES))

    assert inputs["name"] == {
        "type": "string",
        "description": "Name of the run.",
        "x-ga4gh-parameter": {"type": "String"},
    }
    assert inputs["threads"]["type"] == "integer"
    assert inputs["scale"] == {
        "type": "number",
        "default": 1,
        "x-ga4gh-parameter": {"type": "Float"},
    }
    assert inputs["verbose"]["type"] == "boolean"
    assert inputs["verbose"]["default"] is False


def test_file_types() -> None:
    """Test that files become file references, and which defaults stay."""
    conversion = _convert(TYPES)
    inputs = _inputs(conversion)
    notes = _messages(conversion)

    assert inputs["reads"]["x-ga4gh-file"] == {"kind": "file"}
    assert inputs["reference"]["default"] == "https://example.org/ref.fa"
    assert "default" not in inputs["local"]
    assert "is a path" in notes["$.properties.inputs.properties.local"]
    assert "anyOf" not in inputs["optional_reads"]
    assert inputs["optional_reads"]["x-ga4gh-parameter"] == {"type": "File?"}
    assert inputs["extra"]["default"] == []
    assert "default" not in inputs["more"]
    assert "file references" in notes["$.properties.inputs.properties.more"]


def test_compound_types() -> None:
    """Test arrays, maps, pairs and structs."""
    conversion = _convert(TYPES)
    inputs = _inputs(conversion)

    assert inputs["lanes"]["minItems"] == 1
    assert inputs["tags"]["items"] == {"type": ["string", "null"]}
    assert inputs["counts"]["additionalProperties"] == {"type": "integer"}
    assert inputs["counts"]["default"] == {"a": 1}
    assert inputs["by_file"]["additionalProperties"] == {"type": "string"}
    assert (
        "refer to files"
        in _messages(conversion)["$.properties.inputs.properties.by_file"]
    )
    assert inputs["pair"]["required"] == ["left", "right"]
    assert inputs["pair"]["properties"]["right"]["x-ga4gh-file"] == {"kind": "file"}
    sample = inputs["sample"]
    assert sample["required"] == ["id", "lanes"]
    assert sample["additionalProperties"] is False
    assert sample["properties"]["reads"]["anyOf"][1] == {"type": "null"}
    assert sample["x-ga4gh-parameter"] == {"type": "Sample"}


def test_required_inputs() -> None:
    """Test that inputs without default and not optional are required."""
    inputs = _convert(TYPES).schema["properties"]["inputs"]

    assert inputs["required"] == [
        "name",
        "reads",
        "lanes",
        "pair",
        "sample",
        "counter.label",
    ]


def test_expression_defaults_are_left_out() -> None:
    """Test that defaults that are expressions are reported and left out."""
    conversion = _convert(TYPES)

    assert "default" not in _inputs(conversion)["derived"]
    assert "name + " in _messages(conversion)["$.properties.inputs.properties.derived"]
    assert "default" not in _inputs(conversion)["nothing"]
    assert "$.properties.inputs.properties.nothing" not in _messages(conversion)


def test_parameter_meta() -> None:
    """Test the mapping of parameter_meta keys."""
    conversion = _convert(TYPES)
    inputs = _inputs(conversion)
    notes = _messages(conversion)

    assert inputs["mode"]["description"] == "Mode of the run.\n\nFast skips the QC."
    assert inputs["mode"]["title"] == "Mode"
    assert inputs["mode"]["enum"] == ["fast", "full"]
    assert inputs["mode"]["examples"] == ["fast"]
    assert inputs["threads"]["x-ga4gh-hidden"] is True
    assert "enum" not in inputs["threads"]
    assert notes["$.properties.inputs.properties.threads"].endswith(": choices")
    assert "enum" not in inputs["reads"]
    assert notes["$.properties.inputs.properties.reads"].endswith(": patterns, choices")
    assert "neither a string" in notes["$.properties.inputs.properties.scale"]
    outputs = conversion.schema["properties"]["outputs"]["properties"]
    assert outputs["report"]["description"] == "The report."
    assert "enum" not in outputs["report"]


def test_help_without_description(tmp_path: Path) -> None:
    """Test that ``help`` alone is the description."""
    path = _write(
        tmp_path,
        "version 1.0\nworkflow w {\n  input { Int n }\n"
        '  parameter_meta { n: { help: "Help." } }\n}\n',
    )

    assert _inputs(_convert(path))["n"]["description"] == "Help."


def test_choices_must_fit_the_type(tmp_path: Path) -> None:
    """Test that choices of another type are dropped."""
    path = _write(
        tmp_path,
        "version 1.0\nworkflow w {\n  input { Int n }\n"
        '  parameter_meta { n: { choices: [1, "two"] } }\n}\n',
    )

    assert "enum" not in _inputs(_convert(path))["n"]


def test_outputs() -> None:
    """Test that outputs have no defaults and may be null if optional."""
    outputs = _convert(TYPES).schema["properties"]["outputs"]

    assert "required" not in outputs
    assert outputs["properties"]["maybe"]["x-ga4gh-parameter"] == {"type": "File?"}
    assert outputs["properties"]["names"] == {
        "type": "array",
        "items": {"type": "string"},
        "x-ga4gh-parameter": {"type": "Array[String]"},
    }


def test_wdl_1_2_directory_and_struct_meta(tmp_path: Path) -> None:
    """Test ``Directory`` and the meta sections of structs of WDL 1.2."""
    path = _write(
        tmp_path,
        "version 1.2\n"
        "struct Ref {\n  String name\n  Directory index\n"
        '  meta { description: "A reference." }\n'
        '  parameter_meta { name: "Name." }\n}\n'
        "workflow w {\n  input { Directory d  Ref ref }\n"
        "  output { Directory out = d }\n}\n",
    )

    schema = _convert(path).schema

    validate_schema(schema)
    inputs = schema["properties"]["inputs"]["properties"]
    assert inputs["d"]["x-ga4gh-file"] == {"kind": "directory"}
    assert inputs["ref"]["description"] == "A reference."
    assert inputs["ref"]["properties"]["name"]["description"] == "Name."
    assert inputs["ref"]["properties"]["index"]["x-ga4gh-file"] == {"kind": "directory"}


# Nested inputs


def test_required_call_inputs_are_always_included() -> None:
    """Test that required inputs of calls are parameters without the option."""
    conversion = _convert(TYPES)
    inputs = _inputs(conversion)

    assert "counter.label" in inputs
    assert "x-ga4gh-hidden" not in inputs["counter.label"]
    assert "counter.threads" not in inputs
    assert (
        "a call"
        in _messages(conversion)["$.properties.inputs.properties['counter.label']"]
    )


def test_nested_inputs_option() -> None:
    """Test that the option includes optional inputs of calls, hidden."""
    inputs = _inputs(_convert(TYPES, nested_inputs=True))

    assert inputs["counter.threads"] == {
        "type": "integer",
        "description": "Threads of the count.",
        "default": 1,
        "x-ga4gh-parameter": {"type": "Int"},
        "x-ga4gh-hidden": True,
    }
    assert "counter.reads" not in inputs


@pytest.mark.parametrize(
    ("version", "meta", "noted"),
    [
        ("1.0", "", False),
        ("1.1", "", True),
        ("1.1", "  meta { allowNestedInputs: true }\n", False),
    ],
)
def test_nested_inputs_need_allow_nested_inputs(
    tmp_path: Path, version: str, meta: str, noted: bool
) -> None:
    """Test the note on nested inputs without ``allowNestedInputs``."""
    _write(
        tmp_path,
        f"version {version}\ntask t {{\n  input {{ Int n = 1 }}\n"
        "  command <<< >>>\n}\n",
        "t.wdl",
    )
    path = _write(
        tmp_path,
        f'version {version}\nimport "t.wdl" as t\nworkflow w {{\n{meta}'
        "  call t.t\n}\n",
    )

    conversion = _convert(path, nested_inputs=True)

    assert "t.n" in _inputs(conversion)
    assert ("$.properties.inputs" in _messages(conversion)) is noted


# Entry points


def test_single_task_document(tmp_path: Path) -> None:
    """Test that the only task of a document without a workflow is converted."""
    path = _write(
        tmp_path,
        "version 1.1\ntask hello {\n  input { String who }\n"
        "  command <<< echo ~{who} >>>\n  output { String out = read_string(stdout()) }\n}\n",
    )

    schema = _convert(path).schema

    validate_schema(schema)
    assert schema["x-ga4gh-workflow"]["entry_point"] == "hello"
    assert schema["properties"]["inputs"]["required"] == ["who"]
    assert schema["properties"]["outputs"]["properties"]["out"]["type"] == "string"


def test_unknown_task(tmp_path: Path) -> None:
    """Test that a task that doesn't exist is an error."""
    with pytest.raises(wdl.ConversionError, match="has no task 'nope'"):
        _convert(QC, task="nope")


def test_several_tasks_need_a_choice() -> None:
    """Test that a document with several tasks and no workflow needs --task."""
    with pytest.raises(wdl.ConversionError, match=r"several tasks \(Fastqc, "):
        _convert(QC.parent / "tasks" / "fastqc.wdl")


def test_empty_document(tmp_path: Path) -> None:
    """Test that a document without workflow and tasks is an error."""
    path = _write(tmp_path, "version 1.0\nstruct S { Int a }\n")

    with pytest.raises(wdl.ConversionError, match="no workflow and no task"):
        _convert(path)


def test_workflow_without_inputs_or_outputs(tmp_path: Path) -> None:
    """Test that a workflow without input and output sections converts."""
    path = _write(tmp_path, "version 1.0\nworkflow w {\n}\n")

    schema = _convert(path).schema

    validate_schema(schema)
    assert schema["properties"]["inputs"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert "description" not in schema


# Loading


def test_standard_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a document from standard input resolves imports in the cwd."""
    _write(tmp_path, "version 1.0\ntask t {\n  command <<< >>>\n}\n", "t.wdl")
    monkeypatch.chdir(tmp_path)

    conversion = wdl.convert(
        "-", 'version 1.0\nimport "t.wdl"\nworkflow w {\n  call t.t\n}\n'
    )

    assert conversion.schema["x-ga4gh-workflow"]["entry_point"] == "w"


def test_imports_outside_the_document_need_an_import_path(tmp_path: Path) -> None:
    """Test that imports may only read files below the allowed directories."""
    _write(tmp_path, "version 1.0\ntask t {\n  command <<< >>>\n}\n", "tasks/t.wdl")
    path = _write(
        tmp_path,
        'version 1.0\nimport "../tasks/t.wdl"\nworkflow w {\n  call t.t\n}\n',
        "workflows/main.wdl",
    )

    with pytest.raises(wdl.SourceError, match="outside the directory"):
        _convert(path)
    conversion = _convert(path, import_paths=[tmp_path])
    assert conversion.schema["title"] == "w"


def test_absolute_imports_are_checked(tmp_path: Path) -> None:
    """Test that absolute and ``file://`` imports are checked too."""
    outside = _write(tmp_path, "version 1.0\ntask t {\n  command <<< >>>\n}\n", "t.wdl")
    for uri in (str(outside), f"file://{outside}"):
        path = _write(
            tmp_path,
            f'version 1.0\nimport "{uri}"\nworkflow w {{\n  call t.t\n}}\n',
            "sub/main.wdl",
        )
        with pytest.raises(wdl.SourceError, match="outside the directory"):
            _convert(path)


def test_remote_imports_are_rejected(tmp_path: Path) -> None:
    """Test that the converter doesn't fetch remote imports."""
    path = _write(
        tmp_path,
        'version 1.0\nimport "https://example.org/t.wdl"\nworkflow w {\n}\n',
    )

    with pytest.raises(wdl.SourceError, match="Remote import 'https://example.org"):
        _convert(path)


@pytest.mark.parametrize(
    ("imported", "message"),
    [
        (None, "Failed to import t.wdl: file not found"),
        (b"\xff\xfe", "Failed to import t.wdl: not UTF-8 text"),
        (b"version 1.0\ntask {", "Failed to import t.wdl: "),
    ],
)
def test_failed_imports(tmp_path: Path, imported: bytes | None, message: str) -> None:
    """Test the messages of imports that can't be read or parsed."""
    if imported is not None:
        (tmp_path / "t.wdl").write_bytes(imported)
    path = _write(tmp_path, 'version 1.0\nimport "t.wdl"\nworkflow w {\n}\n')

    with pytest.raises(wdl.SourceError) as exc_info:
        _convert(path)
    assert exc_info.value.message.startswith(message)


def test_syntax_error(tmp_path: Path) -> None:
    """Test that a syntax error names the position."""
    path = _write(tmp_path, "version 1.0\nworkflow {\n")

    with pytest.raises(wdl.SourceError, match=r"WDL syntax error in .* at line 2"):
        _convert(path)


def test_type_error(tmp_path: Path) -> None:
    """Test that a type error names the position."""
    path = _write(
        tmp_path, "version 1.0\nworkflow w {\n  input { Int n = undefined_name }\n}\n"
    )

    with pytest.raises(wdl.SourceError, match=r"Invalid WDL in .* at line 3"):
        _convert(path)


def test_several_type_errors(tmp_path: Path) -> None:
    """Test that several type errors are counted."""
    path = _write(
        tmp_path,
        "version 1.0\nworkflow w {\n  Int a = b\n  Int c = d\n}\n",
    )

    with pytest.raises(wdl.SourceError, match=r"\(and 1 more errors\)"):
        _convert(path)


def test_draft_2_is_not_supported(tmp_path: Path) -> None:
    """Test that documents without a version (draft-2) are rejected."""
    path = _write(tmp_path, "workflow w {\n}\n")

    with pytest.raises(wdl.SourceError, match="'draft-2' isn't supported"):
        _convert(path)


def test_missing_miniwdl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the error without the optional dependency."""
    monkeypatch.setitem(sys.modules, "WDL", None)

    with pytest.raises(wdl.MissingDependencyError, match=r"ga4gh-io-schema\[wdl\]"):
        wdl.miniwdl()


# Types that WDL doesn't allow in inputs, built directly


def _converter() -> Any:
    """Build a converter for an empty document.

    Returns:
        The converter.
    """
    return wdl._Converter(wdl.miniwdl(), document=None)


def test_types_without_equivalent() -> None:
    """Test that types without an equivalent are errors with a location."""
    types = wdl.miniwdl().Type

    with pytest.raises(wdl.ConversionError) as exc_info:
        _converter()._type(types.Any(), ("properties", "inputs"), False)
    assert exc_info.value.location == "$.properties.inputs"
    with pytest.raises(wdl.ConversionError, match="keys of Map"):
        _converter()._type(
            types.Map((types.Int(), types.Int())), ("properties",), False
        )


def test_has_files_in_compound_types() -> None:
    """Test that files are found in maps, pairs and structs."""
    types = wdl.miniwdl().Type
    struct = types.StructInstance("S")
    struct.members = {"f": types.File()}

    assert wdl._has_files(types.Map((types.String(), types.File())), types)
    assert wdl._has_files(types.Pair(types.Int(), types.File()), types)
    assert wdl._has_files(struct, types)
    assert not wdl._has_files(types.Pair(types.Int(), types.Int()), types)


def test_json_path_escapes_names() -> None:
    """Test that names that aren't identifiers are bracketed and escaped."""
    assert wdl.json_path(("a", 0, "b.c", "it's")) == "$.a[0]['b.c']['it\\'s']"


def test_notes_render() -> None:
    """Test the text and JSON forms of notes."""
    note = wdl.Note(message="Dropped.", location="$.properties")

    assert note.to_text() == "Note: Dropped. (at $.properties)"
    assert note.to_dict() == {"message": "Dropped.", "location": "$.properties"}


# Command-line interface


def test_cli_writes_schema_and_notes(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the command writes the schema, and notes to stderr."""
    status = main(["convert", "wdl", str(QC)])

    captured = capsys.readouterr()
    assert status == 0
    schema = json.loads(captured.out)
    validate_schema(schema)
    assert captured.err.count("Note: ") == 2


def test_cli_output_validates(tmp_path: Path) -> None:
    """Test that the written file passes ``validate``."""
    output = tmp_path / "qc.schema.json"

    assert (
        main(["convert", "wdl", str(TYPES), "--nested-inputs", "-o", str(output)]) == 0
    )
    assert main(["validate", str(output)]) == 0


def test_cli_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--json`` puts the notes into the result."""
    status = main(["convert", "wdl", "--json", str(QC)])

    captured = capsys.readouterr()
    assert status == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["schema"]["title"] == "QC"
    assert len(result["notes"]) == 2


def test_cli_options(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test ``--task`` and ``--import-path``."""
    _write(tmp_path, "version 1.0\ntask t {\n  command <<< >>>\n}\n", "tasks/t.wdl")
    path = _write(
        tmp_path,
        'version 1.0\nimport "../tasks/t.wdl"\nworkflow w {\n  call t.t\n}\n',
        "workflows/main.wdl",
    )

    assert main(["convert", "wdl", str(path), "--import-path", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["title"] == "w"
    fastqc = QC.parent / "tasks" / "fastqc.wdl"
    assert main(["convert", "wdl", str(fastqc), "-t", "Fastqc"]) == 0
    assert json.loads(capsys.readouterr().out)["title"] == "Fastqc"


def test_cli_standard_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the command reads standard input."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(b"version 1.0\nworkflow w {\n}\n"))
    )

    assert main(["convert", "wdl", "-"]) == 0
    assert json.loads(capsys.readouterr().out)["title"] == "w"


@pytest.mark.parametrize(
    ("arguments", "status", "message"),
    [
        (["missing.wdl"], 3, "Error: File not found"),
        (["--task", "nope", str(QC)], 1, "Validation Error: The document has no task"),
    ],
)
def test_cli_errors(
    arguments: list[str],
    status: int,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test the errors of the command."""
    assert main(["convert", "wdl", *arguments]) == status
    assert capsys.readouterr().err.startswith(message)


def test_cli_wdl_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that an invalid document fails as not complying."""
    path = _write(tmp_path, "version 1.0\nworkflow {\n")

    assert main(["convert", "wdl", str(path)]) == 1
    assert capsys.readouterr().err.startswith("Validation Error: WDL syntax error")


def test_cli_conversion_error_location(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that conversion errors report their location."""

    def fail(*args: Any, **kwargs: Any) -> wdl.Conversion:
        """Fail like a type without equivalent.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Raises:
            ConversionError: Always.
        """
        raise wdl.ConversionError("No equivalent", "$.properties.inputs")

    monkeypatch.setattr(wdl, "to_ga4gh", fail)

    assert main(["convert", "wdl", str(QC)]) == 1
    assert capsys.readouterr().err == (
        "Validation Error: No equivalent (at $.properties.inputs)\n"
    )


def test_cli_without_miniwdl(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the command explains how to install miniwdl."""
    monkeypatch.setitem(sys.modules, "WDL", None)

    assert main(["convert", "wdl", str(QC)]) == 3
    assert "pip install 'ga4gh-io-schema[wdl]'" in capsys.readouterr().err


def test_struct_without_required_members(tmp_path: Path) -> None:
    """Test a struct of optional members, with a default without strings."""
    path = _write(
        tmp_path,
        "version 1.1\nstruct O {\n  Int? n\n  File? f\n}\n"
        "workflow w {\n  input { O o = O { n: 1 } }\n}\n",
    )

    o = _inputs(_convert(path))["o"]

    assert "required" not in o
    assert o["default"] == {"n": 1, "f": None}


def test_conversion_without_checksum() -> None:
    """Test that the checksum is optional, and later tasks can be chosen."""
    fastqc = QC.parent / "tasks" / "fastqc.wdl"
    document = wdl.load_document(fastqc, fastqc.read_text(encoding="utf-8"))

    schema = wdl.to_ga4gh(document, task="GetConfiguration").schema

    assert "checksum" not in schema["x-ga4gh-workflow"]
    assert schema["title"] == "GetConfiguration"
