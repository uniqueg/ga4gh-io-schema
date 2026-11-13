"""Tests of the CWL converter (``ga4gh-io-schema convert cwl``)."""

import hashlib
import io
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ga4gh_io_schema
from ga4gh_io_schema import cwl
from ga4gh_io_schema.cli import main
from ga4gh_io_schema.cli.commands import convert_cwl
from ga4gh_io_schema.cli.convert import CONVERT_HELP
from ga4gh_io_schema.validator import load_profile, validate_schema

CWL_DIR = Path(__file__).resolve().parent / "data" / "cwl"
PROFILE_ID = load_profile()["$id"]

#: Fixtures, with the warnings that their conversion reports.
FIXTURES = {
    "bwa-mem-tool": [
        "The default value can't be converted (a File next to the CWL document, "
        "'args.py'); it is left out, and the input stays optional. "
        "(at $.properties.inputs.properties['args.py'])",
    ],
    "revsort-packed": [],
    "formattest2_v1_0": [
        "'format' is an expression ('$(inputs.input.format)'), which isn't "
        "evaluated; it is left out. (at $.properties.outputs.properties.output)",
    ],
    "record-output_v1_1": [],
    "call-variants": [
        "Secondary file '.amb' is optional; the profile has only required "
        "secondary files, so it is left out. "
        "(at $.properties.inputs.properties.reference)",
        "Secondary file '.ann' is optional; the profile has only required "
        "secondary files, so it is left out. "
        "(at $.properties.inputs.properties.reference)",
        "Secondary file '$(self.nameroot).bwt' is an expression, which isn't "
        "evaluated; it is left out. (at $.properties.inputs.properties.reference)",
        "The default value can't be converted (a File next to the CWL document, "
        "'blacklist.bed'); it is left out, and the input stays optional. "
        "(at $.properties.inputs.properties.blacklist)",
        "Type 'Any' allows any value but null; values that are files are not "
        "checked as file references. (at $.properties.inputs.properties.options)",
        "Secondary file '.csi' is optional; the profile has only required "
        "secondary files, so it is left out. "
        "(at $.properties.outputs.properties.variants)",
        "'format' is an expression ('$(inputs.reference.format)'), which isn't "
        "evaluated; it is left out. (at $.properties.outputs.properties.alignments)",
    ],
}


@dataclass(frozen=True)
class Converted:
    """Result of a conversion in a test.

    Attributes:
        schema: The converted IO schema.
        notes: The notes of the conversion.
    """

    schema: dict[str, Any]
    notes: list[cwl.ConversionNote]

    @property
    def inputs(self) -> dict[str, Any]:
        """The schema of the inputs, without ``x-ga4gh-parameter``."""
        return _without_parameters(self.schema["properties"]["inputs"])

    @property
    def outputs(self) -> dict[str, Any]:
        """The schema of the outputs, without ``x-ga4gh-parameter``."""
        return _without_parameters(self.schema["properties"]["outputs"])

    def parameter_types(self, group: str) -> dict[str, str]:
        """List the CWL types of ``x-ga4gh-parameter`` of inputs or outputs.

        Args:
            group: ``inputs`` or ``outputs``.

        Returns:
            The type of each property, by name.
        """
        properties = self.schema["properties"][group]["properties"]
        return {
            name: schema["x-ga4gh-parameter"]["type"]
            for name, schema in properties.items()
        }

    @property
    def messages(self) -> list[str]:
        """The messages of the notes, in order."""
        return [note.message for note in self.notes]


def _without_parameters(group: dict[str, Any]) -> dict[str, Any]:
    """Remove ``x-ga4gh-parameter`` from the properties of inputs or outputs.

    Args:
        group: Schema of the inputs or outputs.

    Returns:
        A copy without the keyword, which tests of types don't need.
    """
    result = dict(group)
    result["properties"] = {
        name: {
            key: value for key, value in schema.items() if key != "x-ga4gh-parameter"
        }
        for name, schema in group["properties"].items()
    }
    return result


def convert(text: str, tmp_path: Path, process: str | None = None) -> Converted:
    """Convert a CWL document given as text, and validate the result.

    Args:
        text: The CWL document.
        tmp_path: Directory that the document is written to.
        process: ID of the process to convert in a ``$graph``.

    Returns:
        The converted schema and the notes of the conversion.
    """
    path = tmp_path / "tool.cwl"
    path.write_text(text, encoding="utf-8")
    parser = cwl.CwlParser(process=process)
    schema = parser.to_ga4gh(parser.parse(path))
    validate_schema(schema)
    return Converted(schema=schema, notes=parser.notes)


def tool(inputs: str = "{}", outputs: str = "{}", header: str = "") -> str:
    """Build a CWL v1.2 ``CommandLineTool``.

    Args:
        inputs: The inputs, as YAML.
        outputs: The outputs, as YAML.
        header: Further top-level YAML (e.g., requirements).

    Returns:
        The document.
    """
    return (
        "cwlVersion: v1.2\nclass: CommandLineTool\n"
        "$namespaces: {edam: 'http://edamontology.org/'}\n"
        f"{header}inputs: {inputs}\noutputs: {outputs}\n"
    )


def flat(text: str) -> str:
    """Join the lines of a wrapped message of the parser of ``cwl-utils``.

    Args:
        text: The message.

    Returns:
        The message, with runs of whitespace as single spaces.
    """
    return " ".join(text.split())


def empty_converter(notes: list[cwl.ConversionNote] | None = None) -> Any:
    """Build a converter for a document without named types.

    Args:
        notes: List to append the notes to.

    Returns:
        The converter.
    """
    options = SimpleNamespace(idx={})
    return cwl._Converter(options, [] if notes is None else notes)


# Fixtures


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_fixture_converts_to_expected_schema(
    name: str, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Test that each fixture converts to its expected, valid IO schema."""
    output = tmp_path / "out.json"
    status = main(["convert", "cwl", str(CWL_DIR / f"{name}.cwl"), "-o", str(output)])

    captured = capsys.readouterr()
    assert status == 0, captured.err
    schema = json.loads(output.read_text(encoding="utf-8"))
    expected = json.loads((CWL_DIR / f"{name}.expected.json").read_text("utf-8"))
    assert schema == expected
    assert schema["$schema"] == PROFILE_ID
    validate_schema(schema)
    assert captured.err.splitlines() == [f"Warning: {line}" for line in FIXTURES[name]]
    # A successful command writes nothing to standard output with --output
    assert captured.out == ""


def test_main_process_of_a_graph_is_the_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that a packed workflow converts the inputs of its ``main``."""
    assert main(["convert", "cwl", str(CWL_DIR / "revsort-packed.cwl")]) == 0

    schema = json.loads(capsys.readouterr().out)
    assert schema["description"] == (
        "Reverse the lines in a document, then sort those lines."
    )
    assert schema["properties"]["inputs"]["properties"]["reverse_sort"] == {
        "type": "boolean",
        "description": "If true, reverse (descending) sort",
        "default": True,
        "x-ga4gh-parameter": {"type": "boolean"},
    }
    assert schema["x-ga4gh-workflow"]["entry_point"] == "#main"


@pytest.mark.parametrize("process", ["sorttool.cwl", "#sorttool.cwl"])
def test_process_selects_a_process_of_a_graph(
    process: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--process`` selects a process of a ``$graph``."""
    argv = ["convert", "cwl", "--process", process, str(CWL_DIR / "revsort-packed.cwl")]
    assert main(argv) == 0

    schema = json.loads(capsys.readouterr().out)
    assert schema["description"] == "Sort lines using the `sort` command"
    assert schema["x-ga4gh-workflow"]["entry_point"] == "#sorttool.cwl"
    assert set(schema["properties"]["inputs"]["properties"]) == {"reverse", "input"}


def test_only_process_of_a_graph_needs_no_id(tmp_path: Path) -> None:
    """Test that the only process of a ``$graph`` is converted, whatever its ID."""
    document = {
        "cwlVersion": "v1.2",
        "$graph": [
            {
                "id": "#align",
                "class": "CommandLineTool",
                "inputs": [{"id": "#align/reads", "type": "File"}],
                "outputs": [],
            }
        ],
    }
    result = convert(json.dumps(document), tmp_path)

    assert list(result.inputs["properties"]) == ["reads"]
    assert result.schema["x-ga4gh-workflow"]["entry_point"] == "#align"


# Workflow block and parameters


def test_workflow_block_of_a_single_process(tmp_path: Path) -> None:
    """Test ``x-ga4gh-workflow`` of a document without ``$graph``."""
    text = tool("{a: int}").replace("\n", "\r\n")
    result = convert(text, tmp_path)

    # The checksum is that of the bytes of the file, with its line ends
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert (tmp_path / "tool.cwl").read_bytes() == text.encode("utf-8")
    assert result.schema["x-ga4gh-workflow"] == {
        "descriptor_type": "CWL",
        "descriptor_type_version": "v1.2",
        "checksum": [{"type": "sha-256", "checksum": digest}],
    }


def test_cli_checksum_keeps_line_ends(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the command reads the document without translating line ends."""
    data = tool("{a: int}").replace("\n", "\r\n").encode("utf-8")
    path = tmp_path / "tool.cwl"
    path.write_bytes(data)

    assert main(["convert", "cwl", str(path)]) == 0

    workflow = json.loads(capsys.readouterr().out)["x-ga4gh-workflow"]
    assert workflow["checksum"][0]["checksum"] == hashlib.sha256(data).hexdigest()


def test_workflow_block_without_parse() -> None:
    """Test that a process not read by the parser gets the descriptor type."""
    source = cwl.CwlParser().parse(CWL_DIR / "bwa-mem-tool.cwl")
    parser = cwl.CwlParser()

    assert parser.to_ga4gh(source)["x-ga4gh-workflow"] == {"descriptor_type": "CWL"}


def test_parameter_types(tmp_path: Path) -> None:
    """Test that ``x-ga4gh-parameter`` has the CWL type of each parameter."""
    result = convert(
        tool(
            "{a: 'File[]?', b: [int, string], c: ['null', int, string], "
            "d: {type: {type: enum, symbols: [x]}}, "
            "e: {type: {type: record, fields: {f: int}}}, "
            "g: '#R', h: {type: {type: array, items: {type: array, items: File}}}}",
            "{o: stdout}",
            header=(
                "requirements: {SchemaDefRequirement: {types: "
                "[{name: R, type: record, fields: {f: int}}]}}\n"
            ),
        ),
        tmp_path,
    )

    assert result.parameter_types("inputs") == {
        "a": "File[]?",
        "b": "[int, string]",
        "c": "[null, int, string]",
        "d": "enum",
        "e": "record",
        "g": "R",
        "h": "File[][]",
    }
    assert result.parameter_types("outputs") == {"o": "stdout"}


def test_stdin_and_json_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the document can come from standard input, and ``--json``."""
    text = (CWL_DIR / "formattest2_v1_0.cwl").read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode())))

    assert main(["convert", "cwl", "--json", "-"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    expected = (CWL_DIR / "formattest2_v1_0.expected.json").read_text("utf-8")
    assert json.loads(result["output"]) == json.loads(expected)
    assert result["warnings"] == [
        {
            "message": "'format' is an expression ('$(inputs.input.format)'), which "
            "isn't evaluated; it is left out.",
            "location": "$.properties.outputs.properties.output",
        }
    ]


# Types


def test_primitive_types(tmp_path: Path) -> None:
    """Test the JSON Schema types of the primitive CWL types."""
    result = convert(
        tool("{b: boolean, i: int, l: long, f: float, d: double, s: string}"),
        tmp_path,
    )

    assert result.inputs["properties"] == {
        "b": {"type": "boolean"},
        "i": {"type": "integer"},
        "l": {"type": "integer"},
        "f": {"type": "number"},
        "d": {"type": "number"},
        "s": {"type": "string"},
    }
    assert result.inputs["required"] == ["b", "i", "l", "f", "d", "s"]
    assert result.inputs["additionalProperties"] is False
    assert result.notes == []


def test_optional_inputs_are_not_required(tmp_path: Path) -> None:
    """Test that optional inputs and inputs with defaults are not required."""
    result = convert(
        tool("{a: File?, b: 'string[]?', c: {type: int, default: 1}, d: ['null']}"),
        tmp_path,
    )

    assert "required" not in result.inputs
    assert result.inputs["properties"]["d"] == {"type": "null"}


def test_union_of_one_type_is_that_type(tmp_path: Path) -> None:
    """Test that a union with one type needs no ``anyOf``."""
    result = convert(
        tool("{a: {type: [int]}, b: {type: ['null', int, string]}}"), tmp_path
    )

    assert result.inputs["properties"] == {
        "a": {"type": "integer"},
        "b": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
    }
    assert result.inputs["required"] == ["a"]


def test_null_inside_an_array_stays_a_branch(tmp_path: Path) -> None:
    """Test that ``null`` in a nested union becomes a ``null`` branch."""
    result = convert(
        tool("{a: {type: {type: array, items: ['null', File]}}}"),
        tmp_path,
    )

    assert result.inputs["properties"]["a"] == {
        "type": "array",
        "items": {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "x-ga4gh-file": {"kind": "file"}},
            ]
        },
    }


def test_file_annotation_applies_through_arrays_and_unions(tmp_path: Path) -> None:
    """Test that ``format`` and secondary files reach every file of the type."""
    result = convert(
        tool(
            "{a: {type: [{type: array, items: File}, File, Directory], "
            "format: edam:format_2572, secondaryFiles: [^.bai]}}"
        ),
        tmp_path,
    )

    file_ = {
        "type": "string",
        "x-ga4gh-file": {
            "kind": "file",
            "ontology": "http://edamontology.org/format_2572",
            "secondaryFiles": ["^.bai"],
        },
    }
    assert result.inputs["properties"]["a"] == {
        "anyOf": [
            {"type": "array", "items": file_},
            file_,
            {"type": "string", "x-ga4gh-file": {"kind": "directory"}},
        ]
    }


def test_file_annotation_without_a_file_is_reported(tmp_path: Path) -> None:
    """Test that ``format`` on a type without files is left out and reported."""
    result = convert(
        tool(
            "{a: {type: {type: record, fields: {f: File}}, format: edam:format_2572}}"
        ),
        tmp_path,
    )

    assert result.inputs["properties"]["a"]["properties"]["f"] == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
    }
    assert result.messages == [
        "'format' and 'secondaryFiles' apply only to files; the type has no "
        "File (outside records), so they are left out."
    ]


def test_stdin_stdout_and_stderr_are_files(tmp_path: Path) -> None:
    """Test that the stream shorthands become file references."""
    result = convert(tool("{a: stdin}", "{o: stdout, e: stderr}"), tmp_path)

    file_ = {"type": "string", "x-ga4gh-file": {"kind": "file"}}
    assert result.inputs["properties"]["a"] == file_
    assert result.outputs == {
        "type": "object",
        "properties": {"o": file_, "e": file_},
        "required": ["o", "e"],
        "additionalProperties": False,
    }


def test_outputs_are_never_null(tmp_path: Path) -> None:
    """Test that outputs lose ``null``, and that globs aren't copied."""
    result = convert(
        tool(
            outputs=(
                "{o: {type: {type: array, items: ['null', File]}, "
                "outputBinding: {glob: '*.bam'}}, "
                "p: {type: ['null', int, string], outputBinding: {glob: x}}}"
            )
        ),
        tmp_path,
    )

    assert result.outputs == {
        "type": "object",
        "properties": {
            "o": {
                "type": "array",
                "items": {"type": "string", "x-ga4gh-file": {"kind": "file"}},
            },
            "p": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
        },
        "required": ["o"],
        "additionalProperties": False,
    }
    assert "x-ga4gh-output-glob" not in json.dumps(result.schema)


def test_enum_symbols_are_short_names(tmp_path: Path) -> None:
    """Test that enum symbols lose the prefix of their type."""
    result = convert(
        tool(
            "{a: {type: {type: enum, symbols: [x, y], label: Pick, doc: [One, Two]}}}"
        ),
        tmp_path,
    )

    assert result.inputs["properties"]["a"] == {
        "type": "string",
        "enum": ["x", "y"],
        "title": "Pick",
        "description": "One\nTwo",
    }


def test_named_array_type(tmp_path: Path) -> None:
    """Test that a named array type of a ``SchemaDefRequirement`` is inlined."""
    result = convert(
        tool(
            "{a: '#Ints'}",
            header=(
                "requirements: {SchemaDefRequirement: {types: "
                "[{name: Ints, type: array, items: int}]}}\n"
            ),
        ),
        tmp_path,
    )

    assert result.inputs["properties"]["a"] == {
        "type": "array",
        "items": {"type": "integer"},
    }


def test_record_with_empty_fields(tmp_path: Path) -> None:
    """Test that a record without fields accepts only an empty object."""
    result = convert(tool("{a: {type: {type: record, fields: []}}}"), tmp_path)

    assert result.inputs["properties"]["a"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_recursive_type_fails(tmp_path: Path) -> None:
    """Test that a recursive named type is an error."""
    text = tool(
        "{a: '#R'}",
        header=(
            "requirements: {SchemaDefRequirement: {types: "
            "[{name: R, type: record, fields: [{name: next, type: 'R?'}]}]}}\n"
        ),
    )
    with pytest.raises(cwl.CwlConversionError) as info:
        convert(text, tmp_path)

    assert info.value.message == "Recursive CWL type 'R' can't be converted."
    assert info.value.location == "$.properties.inputs.properties.a.properties.next"


def test_unknown_named_type_fails(tmp_path: Path) -> None:
    """Test that a type that the document doesn't define is an error."""
    with pytest.raises(cwl.CwlConversionError) as info:
        convert(tool("{a: Foo}"), tmp_path)

    assert info.value.message == "Unknown CWL type: 'Foo'"
    assert info.value.location == "$.properties.inputs.properties.a"


def test_unknown_type_object_fails() -> None:
    """Test that a type object that is no array, enum or record is an error."""
    converter = empty_converter()

    with pytest.raises(cwl.CwlConversionError, match="Unknown CWL type"):
        converter.type_schema(object(), "$", cwl._Files({}, is_input=True), ())


# Formats


def test_format_list_of_one(tmp_path: Path) -> None:
    """Test that a list with one format is that format."""
    result = convert(tool("{a: {type: File, format: [edam:format_1930]}}"), tmp_path)

    assert result.inputs["properties"]["a"]["x-ga4gh-file"] == {
        "kind": "file",
        "ontology": "http://edamontology.org/format_1930",
    }


@pytest.mark.parametrize(
    ("format_", "message"),
    [
        (
            "[edam:format_1929, edam:format_1930]",
            "'format' lists 2 formats; 'ontology' takes one term, so it is left out.",
        ),
        (
            "'$(inputs.b.format)'",
            "'format' is an expression ('$(inputs.b.format)'), which isn't "
            "evaluated; it is left out.",
        ),
    ],
)
def test_format_without_equivalent_is_reported(
    format_: str, message: str, tmp_path: Path
) -> None:
    """Test that formats that aren't one IRI are left out and reported."""
    result = convert(tool(f"{{a: {{type: File, format: {format_}}}}}"), tmp_path)

    assert result.inputs["properties"]["a"]["x-ga4gh-file"] == {"kind": "file"}
    assert result.messages == [message]


def test_format_that_is_not_an_iri_is_reported(tmp_path: Path) -> None:
    """Test that formats that aren't strings or http(s) IRIs are left out."""
    # The parser of cwl-utils resolves an undeclared prefix against the document
    result = convert(tool("{a: {type: File, format: 'foo:bar'}}"), tmp_path)

    assert result.inputs["properties"]["a"]["x-ga4gh-file"] == {"kind": "file"}
    assert result.messages[0].startswith("'format' 'file:")
    assert result.messages[0].endswith(
        "#a/bar' is not an http(s) IRI (is its namespace prefix missing from "
        "$namespaces?); it is left out."
    )
    notes: list[cwl.ConversionNote] = []
    notes: list[cwl.ConversionNote] = []
    converter = empty_converter(notes)

    assert converter.ontology([3], "$") is None
    assert converter.ontology("urn:example:fasta", "$") is None
    assert notes == [
        cwl.ConversionNote(
            "$", "'format' is an expression (3), which isn't evaluated; it is left out."
        ),
        cwl.ConversionNote(
            "$",
            "'format' 'urn:example:fasta' is not an http(s) IRI (is its namespace "
            "prefix missing from $namespaces?); it is left out.",
        ),
    ]


# Secondary files


def test_secondary_files_of_cwl_v1_0(tmp_path: Path) -> None:
    """Test the secondary files of CWL v1.0, which are plain patterns."""
    text = (
        "cwlVersion: v1.0\nclass: CommandLineTool\n"
        "inputs: {a: {type: File, secondaryFiles: [.bai, .bai, .csi?, "
        "'$(self.basename).x']}}\n"
        "outputs: {o: {type: File, secondaryFiles: .tbi, outputBinding: {glob: x}}}\n"
    )
    result = convert(text, tmp_path)

    assert result.inputs["properties"]["a"]["x-ga4gh-file"] == {
        "kind": "file",
        "secondaryFiles": [".bai"],
    }
    outputs = result.outputs
    assert outputs["properties"]["o"]["x-ga4gh-file"] == {"kind": "file"}
    assert result.messages == [
        "Secondary file '.csi' is optional; the profile has only required "
        "secondary files, so it is left out.",
        "Secondary file '$(self.basename).x' is an expression, which isn't "
        "evaluated; it is left out.",
        "Secondary file '.tbi' is optional; the profile has only required "
        "secondary files, so it is left out.",
    ]


def test_secondary_files_of_cwl_v1_0_as_expression(tmp_path: Path) -> None:
    """Test that ``secondaryFiles`` given as one expression is reported."""
    text = (
        "cwlVersion: v1.0\nclass: CommandLineTool\n"
        "inputs: {a: {type: File, secondaryFiles: '${return []}'}}\noutputs: {}\n"
    )
    result = convert(text, tmp_path)

    assert result.inputs["properties"]["a"]["x-ga4gh-file"] == {"kind": "file"}
    assert result.messages == [
        "Secondary file '${return []}' is an expression, which isn't evaluated; "
        "it is left out."
    ]


def test_secondary_files_required_by_expression_or_bad_pattern(
    tmp_path: Path,
) -> None:
    """Test secondary files whose requirement or pattern can't be converted."""
    result = convert(
        tool(
            "{a: {type: File, secondaryFiles: ["
            "{pattern: .bai, required: '$(inputs.b)'}, "
            "{pattern: ../x}, {pattern: .ok, required: true}]}}",
            "{o: {type: File, secondaryFiles: [{pattern: .tbi, required: true}], "
            "outputBinding: {glob: x}}}",
        ),
        tmp_path,
    )

    assert result.inputs["properties"]["a"]["x-ga4gh-file"] == {
        "kind": "file",
        "secondaryFiles": [".ok"],
    }
    outputs = result.outputs
    assert outputs["properties"]["o"]["x-ga4gh-file"] == {
        "kind": "file",
        "secondaryFiles": [".tbi"],
    }
    assert result.messages == [
        "Whether secondary file '.bai' is required is an expression "
        "('$(inputs.b)'), which isn't evaluated; it is left out.",
        "Secondary file pattern '../x' is not a suffix that the profile accepts; "
        "it is left out.",
    ]


# Defaults


def test_defaults(tmp_path: Path) -> None:
    """Test defaults with files at URIs, in lists and in records."""
    result = convert(
        tool(
            "{a: {type: 'File[]', default: [{class: File, location: 's3://b/x'}]}, "
            "b: {type: Directory, default: {class: Directory, "
            "location: 'https://example.org/d/'}}, "
            "c: {type: {type: record, fields: {n: int}}, default: {n: 2}}}"
        ),
        tmp_path,
    )

    properties = result.inputs["properties"]
    assert properties["a"]["default"] == ["s3://b/x"]
    assert properties["b"]["default"] == "https://example.org/d/"
    assert properties["c"]["default"] == {"n": 2}
    assert result.notes == []


@pytest.mark.parametrize(
    ("default", "reason"),
    [
        ("{class: File, contents: abc}", "a File without an absolute location"),
        (
            "{class: File, location: 'file:///data/x.txt'}",
            "a File next to the CWL document, 'x.txt'",
        ),
    ],
)
def test_default_files_without_uri_are_reported(
    default: str, reason: str, tmp_path: Path
) -> None:
    """Test that defaults with local files or file literals are left out."""
    result = convert(tool(f"{{a: {{type: File, default: {default}}}}}"), tmp_path)

    assert "default" not in result.inputs["properties"]["a"]
    assert "required" not in result.inputs
    assert result.messages == [
        f"The default value can't be converted ({reason}); it is left out, and "
        "the input stays optional."
    ]


def test_default_file_inside_a_record_is_reported(tmp_path: Path) -> None:
    """Test that a relative file location inside a record default is left out."""
    result = convert(
        tool(
            "{a: {type: {type: record, fields: {f: File}}, "
            "default: {f: {class: File, location: reads.fq}}}}"
        ),
        tmp_path,
    )

    assert "default" not in result.inputs["properties"]["a"]
    assert result.messages == [
        "The default value can't be converted (a File next to the CWL document, "
        "'reads.fq'); it is left out, and the input stays optional."
    ]


def test_default_file_dict_with_uri() -> None:
    """Test that a file given as a mapping in a default becomes its location."""
    converter = empty_converter()

    value = {"f": {"class": "File", "location": "https://example.org/x"}}
    assert converter.default(value, "$") == (True, {"f": "https://example.org/x"})


# Documents


def test_parse_reads_files_relative_to_the_document() -> None:
    """Test that ``parse`` resolves imports next to the document."""
    parser = cwl.CwlParser()
    process = parser.parse(CWL_DIR / "call-variants.cwl")

    assert process.class_ == "CommandLineTool"
    assert parser.to_ga4gh(process)["title"] == "Call variants"


def test_operation_is_converted(tmp_path: Path) -> None:
    """Test that an abstract ``Operation`` is converted too."""
    text = "cwlVersion: v1.2\nclass: Operation\ninputs: {a: int}\noutputs: {b: File}\n"
    result = convert(text, tmp_path)

    assert result.inputs["properties"] == {"a": {"type": "integer"}}


@pytest.mark.parametrize(
    ("text", "process", "message"),
    [
        ("[1]", None, "A CWL document must be a YAML or JSON object."),
        (
            '{"cwlVersion": "v1.2", "$graph": "x"}',
            None,
            "Invalid CWL document - $graph must be a list of objects with an 'id'.",
        ),
        (
            '{"cwlVersion": "v1.2", "$graph": [{"class": "Workflow"}]}',
            None,
            "Invalid CWL document - $graph must be a list of objects with an 'id'.",
        ),
        (
            tool(),
            "main",
            "The document has no $graph to select process 'main' from.",
        ),
        (
            '{"class": "CommandLineTool", "inputs": [], "outputs": []}',
            None,
            "Invalid CWL document - could not get the cwlVersion",
        ),
        (
            '{"cwlVersion": "v1.2", "$graph": [{"id": "a"}, {"id": "b"}]}',
            None,
            "Invalid CWL document - Tool file contains graph of multiple objects, "
            "must specify one of #a, #b",
        ),
    ],
)
def test_invalid_documents_fail(
    text: str, process: str | None, message: str, tmp_path: Path
) -> None:
    """Test that documents that aren't CWL processes are errors."""
    with pytest.raises(cwl.CwlConversionError) as info:
        convert(text, tmp_path, process=process)

    assert info.value.message == message


def test_document_that_is_no_process_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a loaded document that isn't a process is an error."""
    monkeypatch.setattr(cwl, "load_document_by_yaml", lambda *args: object())

    with pytest.raises(cwl.CwlConversionError, match="is not a CWL process"):
        convert(tool(), tmp_path)


def test_include_outside_the_root_is_not_read(tmp_path: Path) -> None:
    """Test that only files under the directory of the document are read."""
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    document = tmp_path / "doc"
    document.mkdir()
    text = tool().replace("inputs:", "doc: {$include: ../secret.txt}\ninputs:")

    with pytest.raises(cwl.CwlConversionError) as info:
        convert(text, document)
    assert f"Not read (not a file under {document})" in flat(info.value.message)

    path = document / "tool.cwl"
    parser = cwl.CwlParser(root=tmp_path)
    assert parser.to_ga4gh(parser.parse(path))["description"] == "secret"


def test_include_through_a_symlink_out_of_the_root_is_not_read(
    tmp_path: Path,
) -> None:
    """Test that a symbolic link can't point the parser out of the root."""
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    document = tmp_path / "doc"
    document.mkdir()
    (document / "link.txt").symlink_to(tmp_path / "secret.txt")

    with pytest.raises(cwl.CwlConversionError) as info:
        convert(
            tool().replace("inputs:", "doc: {$include: link.txt}\ninputs:"), document
        )

    assert "Not read (not a file under" in flat(info.value.message)


def test_include_of_a_remote_or_non_utf8_file_fails(tmp_path: Path) -> None:
    """Test that remote and non-UTF-8 includes fail and name the file."""
    remote = "doc: {$include: 'https://x.invalid/a'}\ninputs:"
    with pytest.raises(cwl.CwlConversionError) as info:
        convert(tool().replace("inputs:", remote), tmp_path)
    assert "Not fetched (not a local file): https://x.invalid/a" in flat(
        info.value.message
    )

    (tmp_path / "latin1.txt").write_bytes(b"caf\xe9")
    local = "doc: {$include: latin1.txt}\ninputs:"
    with pytest.raises(cwl.CwlConversionError) as info:
        convert(tool().replace("inputs:", local), tmp_path)
    uri = (tmp_path / "latin1.txt").as_uri()
    assert f"Not UTF-8 text - {uri}" in flat(info.value.message)


def test_fetcher_checks_existence_under_the_root(tmp_path: Path) -> None:
    """Test the existence check of the fetcher (not used with no_link_check)."""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    fetcher = cwl._LocalFetcher(tmp_path)

    assert fetcher.check_exists((tmp_path / "a.txt").as_uri())
    assert not fetcher.check_exists((tmp_path / "b.txt").as_uri())
    assert not fetcher.check_exists("https://example.org/a.txt")


def test_cli_root_widens_the_readable_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--root`` lets a document include files above it."""
    (tmp_path / "about.txt").write_text("About", encoding="utf-8")
    (tmp_path / "doc").mkdir()
    path = tmp_path / "doc" / "tool.cwl"
    path.write_text(
        tool().replace("inputs:", "doc: {$include: ../about.txt}\ninputs:"),
        encoding="utf-8",
    )

    assert main(["convert", "cwl", str(path)]) == 1
    assert "Not read" in capsys.readouterr().err
    assert main(["convert", "cwl", "--root", str(tmp_path), str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["description"] == "About"


@pytest.mark.parametrize(
    "inputs",
    [
        "{a: '#T0'}",
        "{a: {type: Any, default: [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}}",
    ],
)
def test_too_large_schemas_fail(
    inputs: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a conversion that would create too many schemas or values fails."""
    monkeypatch.setattr(cwl, "MAX_NODES", 10)
    types = ", ".join(
        f"{{name: T{level}, type: record, fields: "
        f"{{x: '#T{level + 1}', y: '#T{level + 1}'}}}}"
        for level in range(3)
    )
    header = (
        "requirements: {SchemaDefRequirement: {types: ["
        f"{types}, {{name: T3, type: record, fields: {{z: int}}}}]}}}}\n"
    )

    with pytest.raises(cwl.CwlConversionError, match="would be too large"):
        convert(tool(inputs, header=header), tmp_path)


def test_deep_types_fail_as_conversion_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that types nested beyond the recursion limit are errors."""

    def deep(*args: Any, **kwargs: Any) -> Any:
        raise RecursionError

    monkeypatch.setattr(cwl._Converter, "parameters", deep)

    with pytest.raises(cwl.CwlConversionError, match="nested too deeply"):
        convert(tool(), tmp_path)


def test_cli_deep_types_fail_validation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a schema too deep to validate exits with status 1."""

    def deep(*args: Any, **kwargs: Any) -> None:
        raise RecursionError

    monkeypatch.setattr(convert_cwl, "validate_schema", deep)

    assert main(["convert", "cwl", str(CWL_DIR / "bwa-mem-tool.cwl")]) == 1
    assert "Types nested too deeply to validate." in capsys.readouterr().err


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        ("{a: {type: {type: enum, symbols: []}}}", "An enum without symbols."),
        ("{a: {type: []}}", "A union without types."),
    ],
)
def test_empty_types_fail(inputs: str, message: str, tmp_path: Path) -> None:
    """Test that enums and unions without members are errors."""
    with pytest.raises(cwl.CwlConversionError) as info:
        convert(tool(inputs), tmp_path)

    assert info.value.message == message


def test_documents_too_large_after_alias_expansion_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that YAML aliases can't expand a document beyond the limit."""
    monkeypatch.setattr(cwl, "MAX_DOCUMENT_NODES", 200)
    # Aliases that expand to more than 4**4 = 256 values
    header = (
        "$x:\n  a0: &a0 [1, 1, 1, 1]\n  a1: &a1 [*a0, *a0, *a0, *a0]\n"
        "  a2: &a2 [*a1, *a1, *a1, *a1]\n  a3: [*a2, *a2, *a2, *a2]\n"
    )

    with pytest.raises(cwl.CwlConversionError, match="once YAML aliases"):
        convert(tool(header=header), tmp_path)


def test_imported_files_count_towards_the_document_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the YAML aliases of imported files count towards the limit."""
    monkeypatch.setattr(cwl, "MAX_DOCUMENT_NODES", 200)
    (tmp_path / "bomb.yml").write_text(
        "- &a0 [1, 1, 1, 1]\n- &a1 [*a0, *a0, *a0, *a0]\n"
        "- &a2 [*a1, *a1, *a1, *a1]\n- [*a2, *a2, *a2, *a2]\n",
        encoding="utf-8",
    )

    with pytest.raises(cwl.CwlConversionError) as info:
        convert(tool("{a: {type: Any, default: {$import: bomb.yml}}}"), tmp_path)

    assert "once YAML aliases are expanded" in flat(info.value.message)


def test_include_of_text_that_isnt_yaml_is_read(tmp_path: Path) -> None:
    """Test that included text that isn't valid YAML is still included."""
    (tmp_path / "about.txt").write_text("key: [unclosed", encoding="utf-8")
    text = tool().replace("inputs:", "doc: {$include: about.txt}\ninputs:")

    assert convert(text, tmp_path).schema["description"] == "key: [unclosed"


def test_imported_files_too_deep_to_read_fail(tmp_path: Path) -> None:
    """Test that an imported file nested too deeply is an error."""
    (tmp_path / "deep.yml").write_text("[" * 5000 + "]" * 5000, encoding="utf-8")

    with pytest.raises(cwl.CwlConversionError) as info:
        convert(tool("{a: {type: Any, default: {$import: deep.yml}}}"), tmp_path)

    assert "Too deeply nested to read" in flat(info.value.message)


def test_parser_recursion_is_a_syntax_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the parser of cwl-utils running out of stack is reported."""

    def deep(*args: Any) -> Any:
        raise RecursionError

    monkeypatch.setattr(cwl, "load_document_by_yaml", deep)

    with pytest.raises(cwl.CwlSyntaxError, match="Too deeply nested"):
        convert(tool(), tmp_path)


def test_include_of_a_path_with_nul_is_not_read(tmp_path: Path) -> None:
    """Test that a path the system can't look up is refused, not a crash."""
    text = tool().replace("inputs:", "doc: {$include: a%00b.txt}\ninputs:")

    with pytest.raises(cwl.CwlConversionError) as info:
        convert(text, tmp_path)

    assert "Not read (not a file under" in flat(info.value.message)


def test_too_much_text_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a conversion that would copy too much text fails."""
    monkeypatch.setattr(cwl, "MAX_TEXT", 20)
    header = (
        "requirements: {SchemaDefRequirement: {types: [{name: E, type: enum, "
        "symbols: [alpha, beta, gamma]}]}}\n"
    )

    with pytest.raises(cwl.CwlConversionError, match="characters of text"):
        convert(tool("{a: '#E', b: '#E'}", header=header), tmp_path)


def test_shared_values_are_counted_once_per_use(tmp_path: Path) -> None:
    """Test that the size of a document counts each use of an alias."""
    shared = [1, 2]
    document = {"a": shared, "b": shared, "c": {"d": "e"}}

    assert cwl._expanded_size(document, {}) == 1 + 2 * 3 + 2


def test_documents_too_deep_to_measure_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a document too deep to measure is a syntax error."""

    def deep(*args: Any) -> int:
        raise RecursionError

    monkeypatch.setattr(cwl, "_expanded_size", deep)

    with pytest.raises(cwl.CwlSyntaxError, match="Too deeply nested"):
        convert(tool(), tmp_path)


def test_non_finite_default_is_left_out(tmp_path: Path) -> None:
    """Test that NaN and infinite defaults, which JSON lacks, are left out."""
    result = convert(tool("{a: {type: double, default: .nan}}"), tmp_path)

    assert "default" not in result.inputs["properties"]["a"]
    assert result.messages == [
        "The default value can't be converted (nan is not a finite number); it "
        "is left out, and the input stays optional."
    ]


def test_null_and_any_types(tmp_path: Path) -> None:
    """Test that a null type is optional and that Any excludes null."""
    result = convert(tool("{a: Any}", "{n: 'null', m: Any}"), tmp_path)

    assert result.inputs["properties"]["a"] == {"not": {"type": "null"}}
    assert result.outputs["properties"]["m"] == {"not": {"type": "null"}}
    assert result.outputs["required"] == ["m"]


def test_format_that_is_not_a_uri_is_reported(tmp_path: Path) -> None:
    """Test that an http(s) format that isn't a valid URI is left out."""
    result = convert(
        tool("{a: {type: File, format: 'ex:fmt'}}").replace(
            "{edam: 'http://edamontology.org/'}",
            "{edam: 'http://edamontology.org/', ex: 'http://ex.org/a b#'}",
        ),
        tmp_path,
    )

    assert result.inputs["properties"]["a"]["x-ga4gh-file"] == {"kind": "file"}
    assert "is not an http(s) IRI" in result.messages[0]


def test_remote_references_are_not_fetched(tmp_path: Path) -> None:
    """Test that the parser has no session, so it can't fetch remote URIs."""
    text = tool(
        "{a: {type: File, default: {class: File, location: 'https://x.invalid/a'}}}"
    )
    result = convert(text, tmp_path)

    # The default is kept as it is; no request was needed to convert it
    assert result.inputs["properties"]["a"]["default"] == "https://x.invalid/a"
    # A remote type is not fetched, so it is unknown
    with pytest.raises(cwl.CwlConversionError, match="Unknown CWL type: 'T'"):
        convert(
            tool("{a: {type: 'https://x.invalid/types.yml#T'}}"),
            tmp_path,
        )


# Command-line interface


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: [", "Error: tool.cwl: Invalid YAML - "),
        ("[" * 100_000, "Error: tool.cwl: Too deeply nested to read."),
    ],
)
def test_cli_unreadable_yaml_is_an_io_error(
    text: str,
    expected: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a document that isn't YAML exits with status 3."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tool.cwl").write_text(text, encoding="utf-8")

    assert main(["convert", "cwl", "tool.cwl"]) == 3

    assert capsys.readouterr().err.startswith(expected)


def test_cli_invalid_cwl_is_a_validation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an invalid CWL document exits with status 1 and the location."""
    path = tmp_path / "tool.cwl"
    path.write_text(tool("{a: Foo}"), encoding="utf-8")

    assert main(["convert", "cwl", "--json", str(path)]) == 1

    error = json.loads(capsys.readouterr().err)
    assert error == {
        "error": {
            "kind": "validation",
            "message": "Unknown CWL type: 'Foo'",
            "location": "$.properties.inputs.properties.a",
        },
        "exitCode": 1,
    }


def test_cli_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a missing document exits with status 3."""
    assert main(["convert", "cwl", str(tmp_path / "missing.cwl")]) == 3

    assert capsys.readouterr().err.startswith("Error: File not found - ")


def test_cli_document_not_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a document that isn't UTF-8 exits with status 3."""
    path = tmp_path / "tool.cwl"
    path.write_bytes(b"\xff\xfe")

    assert main(["convert", "cwl", str(path)]) == 3

    assert capsys.readouterr().err.startswith(f"Error: Not UTF-8 text - {path}: ")


def test_cli_document_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a document that can't be read (a directory) exits with 3."""
    assert main(["convert", "cwl", str(tmp_path)]) == 3

    assert capsys.readouterr().err.startswith("Error: Can't read - ")


def test_cli_without_cwl_utils(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the command explains how to install the optional dependency."""
    # Importing the converter again finds no cwl-utils
    for name in [name for name in sys.modules if name.split(".")[0] == "cwl_utils"]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, "ga4gh_io_schema.cwl")
    monkeypatch.delattr(ga4gh_io_schema, "cwl")

    assert main(["convert", "cwl", str(CWL_DIR / "bwa-mem-tool.cwl")]) == 3

    assert capsys.readouterr().err == (
        "Error: The CWL converter needs the optional dependency cwl-utils; "
        "install it with: pip install 'ga4gh-io-schema[cwl]'\n"
    )


def test_cli_other_import_errors_are_internal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an import error of another module gets no install hint."""
    monkeypatch.setitem(sys.modules, "ga4gh_io_schema.cwl", None)
    monkeypatch.delattr(ga4gh_io_schema, "cwl")

    assert main(["convert", "cwl", str(CWL_DIR / "bwa-mem-tool.cwl")]) == 4

    assert capsys.readouterr().err.startswith("An unexpected error occurred: ")


def test_cli_rejects_output_that_does_not_comply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a converted schema that breaks the profile is an internal error."""

    def broken(self: cwl.CwlParser, source: Any) -> dict[str, Any]:
        return {"$schema": PROFILE_ID, "type": "object", "properties": {}}

    monkeypatch.setattr(cwl.CwlParser, "to_ga4gh", broken)

    assert main(["convert", "cwl", str(CWL_DIR / "bwa-mem-tool.cwl")]) == 4

    assert capsys.readouterr().err == (
        "An unexpected error occurred: The converted schema doesn't comply with "
        "the profile: 'inputs' is a required property (at $.properties)\n"
    )


def test_convert_group_is_shared() -> None:
    """Test that the command is registered in the ``convert`` group."""
    from ga4gh_io_schema.cli.base import ROOT

    group = ROOT.groups["convert"]
    assert group.help == CONVERT_HELP
    assert isinstance(group.commands["cwl"], convert_cwl.ConvertCwlCommand)


def test_child_escapes_keys() -> None:
    """Test that keys of JSON paths are written like those of jsonschema."""
    assert cwl._child("$", "a", "b_1") == "$.a.b_1"
    assert cwl._child("$", "_a", "it's", "a\\b") == "$['_a']['it\\'s']['a\\\\b']"


def test_dev_extra_installs_the_cwl_extra() -> None:
    """Test that the ``dev`` extra installs the ``cwl`` extra, which CI needs."""
    pyproject = tomllib.loads(
        (CWL_DIR.parents[2] / "pyproject.toml").read_text("utf-8")
    )
    extras = pyproject["project"]["optional-dependencies"]

    assert "ga4gh-io-schema[cwl]" in extras["dev"]
