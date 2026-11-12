# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the Snakemake converter and of ``ga4gh-io-schema convert snakemake``."""

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.cli import main
from ga4gh_io_schema.cli.commands.convert_snakemake import sample_sheet_argument
from ga4gh_io_schema.converters.snakemake import (
    MAX_VALUES,
    Conversion,
    ConversionError,
    Note,
    SampleSheet,
    SourceError,
    json_path,
    load_schema,
    to_ga4gh,
)
from ga4gh_io_schema.validator import load_profile, validate_schema

DATA_DIR = Path(__file__).resolve().parent / "data" / "snakemake"
RNA_SEQ = DATA_DIR / "rna-seq-star-deseq2"
VARLOCIRAPTOR = DATA_DIR / "dna-seq-varlociraptor"
DRAFT_4 = "http://json-schema.org/draft-04/schema#"
DRAFT_7 = "http://json-schema.org/draft-07/schema#"
DRAFT_2019 = "https://json-schema.org/draft/2019-09/schema"
DRAFT_2020 = "https://json-schema.org/draft/2020-12/schema"


def config(properties: dict[str, Any], **keywords: Any) -> dict[str, Any]:
    """Build a Draft 2020-12 configuration schema.

    Args:
        properties: Its properties.
        **keywords: Other keywords of the root.

    Returns:
        The schema.
    """
    return {
        "$schema": DRAFT_2020,
        "type": "object",
        "properties": properties,
        **keywords,
    }


def inputs(conversion: Conversion) -> dict[str, Any]:
    """Return the inputs of a conversion.

    Args:
        conversion: The conversion.

    Returns:
        The schema of the inputs.
    """
    return conversion.schema["properties"]["inputs"]


def messages(conversion: Conversion) -> list[str]:
    """Return the messages of the notes of a conversion.

    Args:
        conversion: The conversion.

    Returns:
        The messages, in order.
    """
    return [note.message for note in conversion.notes]


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


# --- Real workflows ---------------------------------------------------------


def test_rna_seq_workflow_converts_to_a_valid_io_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test the config and both sheets of a public workflow end to end.

    Args:
        capsys: Pytest fixture capturing the output.
    """
    status, out, err = run(
        [
            "convert",
            "snakemake",
            str(RNA_SEQ / "config.schema.yaml"),
            "--sample-sheet",
            str(RNA_SEQ / "samples.schema.yaml"),
            "-s",
            f"units={RNA_SEQ / 'units.schema.yaml'}",
        ],
        capsys,
    )

    # The command checks the result against the profile before it writes it
    assert status == 0, err
    schema = json.loads(out)
    assert schema["$schema"] == load_profile()["$id"]
    assert schema["properties"]["outputs"] == {"type": "object", "properties": {}}
    properties = schema["properties"]["inputs"]["properties"]
    assert properties["samples"]["x-ga4gh-file"] == {"kind": "file"}
    units = properties["units"]["x-ga4gh-tabular-schema"]
    assert units["type"] == "array"
    columns = units["items"]["properties"]
    assert columns["fq1"]["x-ga4gh-file"] == {"kind": "file"}
    assert "x-ga4gh-file" not in columns["sra"]
    assert "x-ga4gh-file" not in properties["ref"]["properties"]["species"]
    assert "Note: Marked as a file reference (file): its name ends with 'fq'." in err
    assert "--plain units.fq1" in err
    assert err.rstrip().endswith("(at $.properties.outputs)")


def references(node: Any) -> list[str]:
    """Collect the values of all ``$ref`` keywords of a schema.

    Args:
        node: The schema, or a part of it.

    Returns:
        The references, in document order.
    """
    if isinstance(node, list):
        return [ref for item in node for ref in references(item)]
    if not isinstance(node, dict):
        return []
    found = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
    return found + [ref for value in node.values() for ref in references(value)]


def resolve(schema: dict[str, Any], ref: str) -> Any:
    """Follow a local JSON pointer reference.

    Args:
        schema: The document.
        ref: The reference, e.g. ``#/$defs/a``.

    Returns:
        The target.
    """
    node: Any = schema
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def test_varlociraptor_references_resolve() -> None:
    """Test a public config schema with definitions and references.

    The library is used without the CLI's check against the profile, which
    is slow for a schema of this size; the CLI tests check that.
    """
    source = load_schema(
        (VARLOCIRAPTOR / "config.schema.yaml").read_text(encoding="utf-8"), "x"
    )

    conversion = to_ga4gh(source)

    schema = conversion.schema
    assert set(schema["$defs"]) == {"aux-file", "filterentry", "evententry"}
    refs = references(schema)
    assert refs and all(ref.startswith("#/") for ref in refs)
    for ref in refs:
        assert isinstance(resolve(schema, ref), (dict, bool)), ref
    marked = [
        note.location
        for note in conversion.notes
        if note.message.startswith("Marked as a file reference")
    ]
    base = "$.properties.inputs.properties"
    assert marked == [
        f"{base}.samples",
        f"{base}.primers.properties.trimming.properties.primers_fq1",
        f"{base}.primers.properties.trimming.properties.primers_fq2",
        f"{base}.primers.properties.trimming.properties.tsv",
        f"{base}.population.properties.db.properties.path",
        f"{base}.custom_alignment_properties.properties.tsv",
    ]


def test_json_result_has_schema_and_notes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test the result of ``--json``: the schema and the notes, no stderr.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    path = tmp_path / "config.schema.json"
    path.write_text(json.dumps(config({"bam": {"type": "string"}})))

    status, out, err = run(["convert", "snakemake", "--json", str(path)], capsys)

    assert status == 0, err
    assert err == ""
    result = json.loads(out)
    assert result["schema"]["properties"]["inputs"]["properties"]["bam"] == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
    }
    assert [note["location"] for note in result["notes"]] == [
        "$.properties.inputs.properties.bam",
        "$.properties.outputs",
    ]


# --- Command line -----------------------------------------------------------


def test_standard_input_and_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test reading the config schema from standard input, as JSON.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        monkeypatch: Pytest fixture for patching standard input.
        capsys: Pytest fixture capturing the output.
    """
    source = json.dumps(config({"threads": {"type": "integer"}}))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(source.encode())))
    target = tmp_path / "io.schema.json"

    status, out, _ = run(["convert", "snakemake", "-", "-o", str(target)], capsys)

    assert status == 0
    assert out == ""
    assert json.loads(target.read_text())["properties"]["inputs"]["properties"] == {
        "threads": {"type": "integer"}
    }


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("a: [1", "Error: Invalid YAML - {path}: "),
        ("200: {}", "Error: Not JSON data - {path}: the key 200 isn't a string"),
        ("a: .nan", "Error: Not JSON data - {path}: nan isn't a finite number"),
        ("a: !!binary aGk=", "Error: Not JSON data - {path}: a value of type 'bytes'"),
        ("a: !!timestamp 2024-01-01", "Error: Not JSON data - {path}: a value of type"),
        ("[" * 100_000 + "]" * 100_000, "Error: Too deeply nested to convert"),
    ],
)
def test_unreadable_sources_exit_with_3(
    source: str, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that sources that aren't JSON data are I/O errors.

    Args:
        source: Content of the source.
        message: Start of the expected error.
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    path = tmp_path / "config.schema.yaml"
    path.write_text(source)

    status, out, err = run(["convert", "snakemake", str(path)], capsys)

    assert status == 3
    assert out == ""
    assert err.startswith(message.format(path=path))


def test_yaml_aliases_are_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that YAML aliases can't blow up the work of the converter.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    lines += [f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 10)}]" for i in range(1, 7)]
    path = tmp_path / "bomb.yaml"
    path.write_text("\n".join(lines))

    status, _, err = run(["convert", "snakemake", str(path)], capsys)

    assert status == 3
    assert f"more than {MAX_VALUES} values" in err


def test_yaml_needs_pyyaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test the hint to install the extra if PyYAML is missing.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        monkeypatch: Pytest fixture for hiding PyYAML.
        capsys: Pytest fixture capturing the output.
    """
    monkeypatch.setitem(sys.modules, "yaml", None)
    path = tmp_path / "config.schema.yaml"
    path.write_text("type: object\n")

    status, _, err = run(["convert", "snakemake", str(path)], capsys)

    assert status == 3
    assert "install 'ga4gh-io-schema[snakemake]'" in err


def test_conversion_errors_exit_with_1_and_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a schema that can't be converted is reported with its location.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    path = tmp_path / "config.schema.json"
    path.write_text(json.dumps(config({"a": 3})))

    status, _, err = run(["convert", "snakemake", "--json", str(path)], capsys)

    assert status == 1
    error = json.loads(err)["error"]
    assert error["kind"] == "validation"
    assert error["location"] == "$.properties.inputs.properties.a"


def test_results_that_dont_comply_exit_with_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the result is checked against the profile.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    path = tmp_path / "config.schema.json"
    path.write_text(json.dumps(config({}, **{"x-ga4gh-bogus": 1})))

    status, out, err = run(["convert", "snakemake", str(path)], capsys)

    assert status == 1
    assert out == ""
    assert err.startswith(
        "Validation Error: The converted schema doesn't comply with the GA4GH IO "
        "Profile: "
    )
    assert err.rstrip().endswith("(at $.properties.inputs)")


def test_result_errors_at_the_root_have_no_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an error at the root of the result has no location.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        monkeypatch: Pytest fixture for patching the profile identifier.
        capsys: Pytest fixture capturing the output.
    """
    from ga4gh_io_schema.converters import snakemake

    monkeypatch.setattr(snakemake, "load_profile", lambda: {"$id": "urn:other"})
    path = tmp_path / "config.schema.json"
    path.write_text(json.dumps(config({})))

    status, _, err = run(["convert", "snakemake", "--json", str(path)], capsys)

    assert status == 1
    assert json.loads(err)["error"]["location"] is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("sheet.yaml", (None, "sheet.yaml")),
        ("samples=sheet.yaml", ("samples", "sheet.yaml")),
        ("data.units=a=b.yaml", ("data.units", "a=b.yaml")),
        ("./a=b.yaml", (None, "./a=b.yaml")),
        ("=b.yaml", (None, "=b.yaml")),
    ],
)
def test_sample_sheet_argument(value: str, expected: tuple[str | None, str]) -> None:
    """Test the parsing of ``--sample-sheet``.

    Args:
        value: Value of the option.
        expected: Expected property and path.
    """
    assert sample_sheet_argument(value) == expected


@pytest.mark.parametrize("value", ["-", "samples=-", "samples="])
def test_sample_sheet_needs_a_file(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that sample sheets can't come from standard input.

    Args:
        value: Value of the option.
        capsys: Pytest fixture capturing the output.
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["convert", "snakemake", "config.yaml", "-s", value])

    assert exc_info.value.code == 2
    assert "names no file" in capsys.readouterr().err


def test_no_guess_and_overrides_on_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test --no-guess, --file, --directory and --plain.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing the output.
    """
    path = tmp_path / "config.schema.json"
    properties = {
        name: {"type": "string"} for name in ("genome_fasta", "out", "bed", "x")
    }
    path.write_text(json.dumps(config(properties)))

    status, out, err = run(
        [
            "convert",
            "snakemake",
            str(path),
            "--no-guess",
            "--file",
            "x",
            "--directory",
            "out",
            "--plain",
            "bed",
        ],
        capsys,
    )

    assert status == 0, err
    result = json.loads(out)["properties"]["inputs"]["properties"]
    assert result["x"]["x-ga4gh-file"] == {"kind": "file"}
    assert result["out"]["x-ga4gh-file"] == {"kind": "directory"}
    assert "x-ga4gh-file" not in result["genome_fasta"]
    assert "x-ga4gh-file" not in result["bed"]


# --- Reading sources --------------------------------------------------------


def test_load_schema_keeps_dates_as_strings() -> None:
    """Test that YAML dates stay strings, as in JSON."""
    assert load_schema("default: 2024-01-01\n", "x") == {"default": "2024-01-01"}


def test_load_schema_prefers_json() -> None:
    """Test that JSON is read as JSON (e.g., without YAML's booleans)."""
    assert load_schema('{"enum": ["yes"]}', "x") == {"enum": ["yes"]}


def test_load_schema_rejects_cycles() -> None:
    """Test that cyclic YAML (through aliases) is bounded."""
    with pytest.raises(SourceError, match="more than"):
        load_schema("&a [*a]", "x")


@pytest.mark.parametrize("text", ["[" + "1" * 5000 + "]", "a: " + "1" * 5000])
def test_load_schema_rejects_huge_numbers(text: str) -> None:
    """Test that numbers Python won't parse are source errors, not crashes.

    Args:
        text: JSON or YAML with an integer of 5000 digits.
    """
    with pytest.raises(SourceError, match="Invalid YAML - x"):
        load_schema(text, "x")


# --- Structure --------------------------------------------------------------


def test_structure_of_the_io_schema() -> None:
    """Test where the keywords of the root go."""
    source = config(
        {"a": {"$ref": "#/definitions/b"}},
        title="Config",
        required=["a"],
        definitions={"b": {"type": "integer"}},
    )

    conversion = to_ga4gh(source)

    validate_schema(conversion.schema)
    assert conversion.schema == {
        "$schema": load_profile()["$id"],
        "x-ga4gh-workflow": {"descriptor_type": "SMK"},
        "type": "object",
        "properties": {
            "inputs": {
                "type": "object",
                "properties": {"a": {"$ref": "#/$defs/b"}},
                "title": "Config",
                "required": ["a"],
            },
            "outputs": {"type": "object", "properties": {}},
        },
        "$defs": {"b": {"type": "integer"}},
    }
    assert conversion.notes[-1] == Note(
        "Snakemake config schemas don't describe outputs: 'outputs' is left "
        "empty; add the outputs of the workflow by hand.",
        "$.properties.outputs",
    )


def test_inputs_get_type_object() -> None:
    """Test that the inputs are an object, also if the source doesn't say so."""
    assert inputs(to_ga4gh({"$schema": DRAFT_2020}))["type"] == "object"


def test_source_is_not_changed() -> None:
    """Test that the conversion doesn't modify its input."""
    source = config({"reads_fq": {"type": "string", "format": "uri"}})
    before = json.dumps(source)

    to_ga4gh(source)

    assert json.dumps(source) == before


@pytest.mark.parametrize("source", [[], "x", None])
def test_config_must_be_an_object(source: Any) -> None:
    """Test that the config schema must be a JSON object.

    Args:
        source: Something else.
    """
    with pytest.raises(ConversionError, match="must be a JSON object"):
        to_ga4gh(source)


def test_subschemas_must_be_schemas() -> None:
    """Test that a subschema that isn't an object or a boolean is an error."""
    with pytest.raises(ConversionError) as exc_info:
        to_ga4gh(config({"a": {"items": 3}}))

    assert exc_info.value.location == "$.properties.inputs.properties.a.items"


# --- Drafts -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("uri", "note"),
    [
        (None, "The source has no '$schema', which names no draft"),
        ("urn:x", "The source has the '$schema' 'urn:x', which names no draft"),
        (DRAFT_2020, None),
        ("https://json-schema.org/draft/2020-12/schema#", None),
    ],
)
def test_schema_uri(uri: str | None, note: str | None) -> None:
    """Test the notes for missing and unknown drafts.

    Args:
        uri: Value of ``$schema``, if any.
        note: Start of the expected note, if any.
    """
    source = {} if uri is None else {"$schema": uri}

    found = [m for m in messages(to_ga4gh(source)) if m.startswith("The source")]

    assert found == ([] if note is None else [found[0]])
    if note:
        assert found[0].startswith(note)


def test_draft_3_is_rejected() -> None:
    """Test that Draft 3 schemas are rejected."""
    with pytest.raises(ConversionError, match="Draft 3"):
        to_ga4gh({"$schema": "http://json-schema.org/draft-03/schema#"})


def test_draft_4_upgrade() -> None:
    """Test the upgrade of the keywords of Draft 4."""
    source = {
        "$schema": DRAFT_4,
        "id": "https://example.org/config.json",
        "type": "object",
        "properties": {
            "max": {"type": "number", "maximum": 1, "exclusiveMaximum": True},
            "min": {"type": "number", "minimum": 0, "exclusiveMinimum": False},
            "lonely": {"type": "number", "exclusiveMinimum": True},
            "anchor": {"id": "#here", "type": "string"},
            "embedded": {
                "id": "https://example.org/embedded.json",
                "properties": {"self": {"$ref": "#/properties/x"}},
            },
            "pair": {
                "type": "array",
                "items": [{"type": "string"}, {"type": "integer"}],
                "additionalItems": False,
            },
            "list": {
                "type": "array",
                "items": {"type": "string"},
                "additionalItems": False,
            },
            "deps": {
                "dependencies": {"a": ["b"], "c": {"required": ["d"]}},
            },
        },
    }

    conversion = to_ga4gh(source)

    validate_schema(conversion.schema)
    result = inputs(conversion)
    assert "id" not in result and "$id" not in result
    properties = result["properties"]
    assert properties["max"] == {"type": "number", "exclusiveMaximum": 1}
    assert properties["min"] == {"type": "number", "minimum": 0}
    assert properties["lonely"] == {"type": "number"}
    assert properties["anchor"] == {"$anchor": "here", "type": "string"}
    assert properties["embedded"] == {
        "$id": "https://example.org/embedded.json",
        "properties": {"self": {"$ref": "#/properties/x"}},
    }
    assert properties["pair"] == {
        "type": "array",
        "prefixItems": [{"type": "string"}, {"type": "integer"}],
        "items": False,
    }
    assert properties["list"] == {"type": "array", "items": {"type": "string"}}
    assert properties["deps"] == {
        "dependentRequired": {"a": ["b"]},
        "dependentSchemas": {"c": {"required": ["d"]}},
    }
    notes = messages(conversion)
    assert (
        "'id' of the source ('https://example.org/config.json') dropped: it names "
        "the source, not the IO schema."
    ) in notes
    assert "'exclusiveMinimum: true' without 'minimum' dropped." in notes
    assert (
        "'additionalItems' dropped: without a list in 'items', it has no effect."
    ) in notes


def test_draft_7_fragment_ids_become_anchors() -> None:
    """Test that ``$id`` fragments of Drafts 6 and 7 become ``$anchor``."""
    source = {
        "$schema": DRAFT_7,
        "$id": "#root",
        "properties": {"a": {"$id": "#a"}, "b": {"$ref": "#a"}},
    }

    result = inputs(to_ga4gh(source))

    assert result["$anchor"] == "root"
    assert result["properties"] == {"a": {"$anchor": "a"}, "b": {"$ref": "#a"}}


def test_draft_2019_recursive_keywords_are_reported() -> None:
    """Test that the recursive keywords of Draft 2019-09 are kept and reported."""
    source = {"$schema": DRAFT_2019, "$recursiveAnchor": True, "$recursiveRef": "#"}

    conversion = to_ga4gh(source)

    assert inputs(conversion)["$recursiveRef"] == "#"
    assert sum("Draft 2019-09" in m for m in messages(conversion)) == 2


def test_defs_and_definitions_merge() -> None:
    """Test that ``definitions`` and ``$defs`` end up in one ``$defs``."""
    source = config({}, definitions={"a": True}, **{"$defs": {"b": False}})

    assert to_ga4gh(source).schema["$defs"] == {"a": True, "b": False}


@pytest.mark.parametrize(
    "source",
    [
        config({}, definitions={"a": True}, **{"$defs": {"a": False}}),
        config(
            {"x": {"dependencies": {"a": ["b"]}, "dependentRequired": {"a": ["c"]}}}
        ),
    ],
)
def test_duplicate_definitions_are_errors(source: dict[str, Any]) -> None:
    """Test that a name defined twice is an error.

    Args:
        source: Schema with a name defined twice.
    """
    with pytest.raises(ConversionError, match="defined twice"):
        to_ga4gh(source)


def test_nested_definitions_stay_in_place() -> None:
    """Test that nested ``definitions`` become ``$defs`` of the same schema."""
    source = config(
        {"a": {"definitions": {"b": True}, "$ref": "#/properties/a/definitions/b"}}
    )

    result = inputs(to_ga4gh(source))["properties"]["a"]

    assert result == {
        "$defs": {"b": True},
        "$ref": "#/properties/inputs/properties/a/$defs/b",
    }


# --- References -------------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("#", "#/properties/inputs"),
        ("#/definitions/d", "#/$defs/d"),
        ("#/$defs/d", "#/$defs/d"),
        ("#/definitions/missing", "#/$defs/missing"),
        ("#/properties/t/items/1", "#/properties/inputs/properties/t/prefixItems/1"),
        ("#/properties/t/items/9", "#/properties/inputs/properties/t/prefixItems/9"),
        ("#/properties/t/items/x", "#/properties/inputs/properties/t/prefixItems/x"),
        ("#/properties/t/additionalItems", "#/properties/inputs/properties/t/items"),
        ("#/properties/l/items", "#/properties/inputs/properties/l/items"),
        (
            "#/properties/l/additionalItems",
            "#/properties/inputs/properties/l/additionalItems",
        ),
        (
            "#/properties/o/dependencies/s",
            "#/properties/inputs/properties/o/dependentSchemas/s",
        ),
        (
            "#/properties/o/dependencies/r/0",
            "#/properties/inputs/properties/o/dependentRequired/r/0",
        ),
        (
            "#/properties/o/dependencies",
            "#/properties/inputs/properties/o/dependencies",
        ),
        (
            "#/properties/o/patternProperties/%5Ex",
            "#/properties/inputs/properties/o/patternProperties/%5Ex",
        ),
        ("#/properties/o/allOf", "#/properties/inputs/properties/o/allOf"),
        ("#/properties/o/default/x", "#/properties/inputs/properties/o/default/x"),
        ("#/properties/a~1b", "#/properties/inputs/properties/a~1b"),
        ("#/properties/c~0d", "#/properties/inputs/properties/c~0d"),
        ("#/properties/with%20space", "#/properties/inputs/properties/with%20space"),
        ("#/properties/nope/items", "#/properties/inputs/properties/nope/items"),
        ("#anchor", "#anchor"),
        (3, 3),
    ],
)
def test_references_are_rewritten(ref: Any, expected: Any) -> None:
    """Test that local references point to the same schema after the move.

    Args:
        ref: Reference in the source.
        expected: Expected reference in the IO schema.
    """
    source = config(
        {
            "t": {"items": [True, True], "additionalItems": False},
            "l": {"items": True},
            "o": {
                "dependencies": {"s": True, "r": ["x"]},
                "patternProperties": {"^x": True},
                "allOf": [True],
                "default": {"x": 1},
            },
            "a/b": True,
            "c~d": True,
            "with space": True,
            "ref": {"$ref": ref},
        },
        definitions={"d": True},
    )

    assert inputs(to_ga4gh(source))["properties"]["ref"]["$ref"] == expected


def test_external_references_are_reported() -> None:
    """Test that references to other documents are kept, with a note."""
    conversion = to_ga4gh(config({"a": {"$ref": "units.schema.yaml"}}))

    assert inputs(conversion)["properties"]["a"] == {"$ref": "units.schema.yaml"}
    assert messages(conversion)[0].startswith(
        "The reference 'units.schema.yaml' to another document is kept"
    )


def test_references_in_embedded_resources_follow_their_targets() -> None:
    """Test pointers relative to an embedded resource, whose keywords move."""
    source = {
        "$schema": DRAFT_7,
        "definitions": {
            "sub": {
                "$id": "https://example.org/sub.json",
                "definitions": {"x": {"type": "string"}},
                "properties": {"a": {"$ref": "#/definitions/x"}},
            }
        },
        "properties": {"p": {"$ref": "#/definitions/sub"}},
    }

    conversion = to_ga4gh(source)

    sub = conversion.schema["$defs"]["sub"]
    assert sub["properties"]["a"] == {"$ref": "#/$defs/x"}
    assert inputs(conversion)["properties"]["p"] == {"$ref": "#/$defs/sub"}
    assert not any("points to nothing" in m for m in messages(conversion))


def test_assertions_next_to_old_refs_are_dropped() -> None:
    """Test that Draft 7 keywords next to ``$ref`` don't start to apply."""
    source = {
        "$schema": DRAFT_7,
        "definitions": {"n": {"type": "integer"}},
        "properties": {
            "p": {
                "$ref": "#/definitions/n",
                "type": "string",
                "description": "kept",
                "x-mine": 1,
            }
        },
    }

    conversion = to_ga4gh(source)

    assert inputs(conversion)["properties"]["p"] == {
        "$ref": "#/$defs/n",
        "description": "kept",
        "x-mine": 1,
    }
    assert messages(conversion)[0] == (
        "Dropped 'type' next to '$ref': drafts before 2019-09 ignore them, and "
        "Draft 2020-12 would apply them."
    )


def test_assertions_next_to_new_refs_are_kept() -> None:
    """Test that Draft 2020-12 keywords next to ``$ref`` stay."""
    source = config({"p": {"$ref": "#/$defs/n", "type": "integer"}})

    assert inputs(to_ga4gh(source))["properties"]["p"]["type"] == "integer"


def test_dangling_references_are_reported() -> None:
    """Test the note for references whose target is gone after the upgrade."""
    source = config(
        {
            "l": {"items": True, "additionalItems": {"type": "integer"}},
            "m": {"$ref": "#/properties/l/additionalItems"},
        }
    )

    conversion = to_ga4gh(source)

    note = conversion.notes[-2]
    assert note.message == (
        "The reference '#/properties/inputs/properties/l/additionalItems' points "
        "to nothing in the IO schema; fix it by hand."
    )
    assert note.location == "$.properties.inputs.properties.m"


def test_pointer_dynamic_references_are_rewritten() -> None:
    """Test that ``$dynamicRef`` with a JSON pointer moves like ``$ref``."""
    row = {
        "$schema": DRAFT_2020,
        "$defs": {"n": True},
        "properties": {"c": {"$dynamicRef": "#/$defs/n"}, "d": {"$dynamicRef": "#m"}},
    }

    conversion = to_ga4gh(config({"samples": {"type": "string"}}), [SampleSheet(row)])

    items = inputs(conversion)["properties"]["samples"]["x-ga4gh-tabular-schema"]
    columns = items["items"]["properties"]
    base = "#/properties/inputs/properties/samples/x-ga4gh-tabular-schema/items"
    assert columns == {
        "c": {"$dynamicRef": f"{base}/$defs/n"},
        "d": {"$dynamicRef": "#m"},
    }
    assert not any("points to nothing" in m for m in messages(conversion))


def test_anchors_must_be_unique_across_sources() -> None:
    """Test that the config and a sheet can't both define an anchor."""
    source = config({"samples": {"type": "string"}, "a": {"$anchor": "x"}})
    row = {"$schema": DRAFT_2020, "properties": {"b": {"$anchor": "x"}}}

    with pytest.raises(ConversionError, match="The anchor 'x' is defined twice"):
        to_ga4gh(source, [SampleSheet(row)])


def test_anchors_in_embedded_resources_are_separate() -> None:
    """Test that the same anchor in another resource is no clash."""
    source = config(
        {"a": {"$anchor": "x"}, "b": {"$id": "https://example.org/b", "$anchor": "x"}}
    )

    assert inputs(to_ga4gh(source))["properties"]["b"]["$anchor"] == "x"


def test_identifiers_next_to_old_refs_are_dropped() -> None:
    """Test that a Draft 7 ``$id`` next to ``$ref`` makes no resource."""
    source = {
        "$schema": DRAFT_7,
        "definitions": {
            "a": {"type": "string"},
            "b": {"$id": "http://example.org/b", "$ref": "#/definitions/a"},
        },
        "properties": {"x": {"$ref": "#/definitions/b"}},
    }

    conversion = to_ga4gh(source)

    assert conversion.schema["$defs"]["b"] == {"$ref": "#/$defs/a"}
    assert "Dropped '$id' next to '$ref'" in messages(conversion)[0]
    assert not any("points to nothing" in m for m in messages(conversion))


def test_huge_indexes_in_references_are_dangling() -> None:
    """Test that an index Python won't convert is no internal error."""
    huge = "1" * 5000
    source = config({"x": {"$ref": f"#/allOf/{huge}"}}, allOf=[True])

    conversion = to_ga4gh(source)

    assert any("points to nothing" in m for m in messages(conversion))


def test_schemas_named_like_data_keywords_are_checked() -> None:
    """Test that a property named ``default`` is checked like any other."""
    source = config({"default": {"$ref": "#/definitions/missing"}})

    conversion = to_ga4gh(source)

    assert conversion.notes[-2].location == "$.properties.inputs.properties.default"
    assert "points to nothing" in conversion.notes[-2].message


# --- File references --------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "schema", "reference", "reason"),
    [
        ("outdir", {}, {"kind": "directory"}, "its name ends with 'outdir'"),
        ("results_folder", {}, {"kind": "directory"}, "its name ends with 'folder'"),
        ("genomeFasta", {}, {"kind": "file"}, "its name ends with 'fasta'"),
        ("fastq_1", {}, {"kind": "file"}, "its name ends with 'fastq'"),
        ("samples", {}, {"kind": "file"}, "its name is that of a sample sheet"),
        (
            "cache",
            {"default": "cache/"},
            {"kind": "directory"},
            "its default 'cache/' ends with '/'",
        ),
        (
            "units",
            {"default": "config/units.tsv"},
            {"kind": "file", "mediaType": "text/tab-separated-values"},
            "its default 'config/units.tsv' has a file extension",
        ),
        (
            "table",
            {"default": "a.CSV"},
            {"kind": "file", "mediaType": "text/csv"},
            "its default 'a.CSV' has a file extension",
        ),
        (
            "calls",
            {"default": "x.vcf.gz"},
            {"kind": "file"},
            "its default 'x.vcf.gz' has a file extension",
        ),
        (
            "reads",
            {"description": "Path to FASTQ file"},
            {"kind": "file"},
            "its description names a path",
        ),
        (
            "out",
            {"description": "path to the output directory"},
            {"kind": "directory"},
            "its description names a path to a directory",
        ),
        (
            "listing",
            {"description": "path to a file listing directories"},
            {"kind": "file"},
            "its description names a path",
        ),
    ],
)
def test_heuristics(
    name: str, schema: dict[str, Any], reference: dict[str, str], reason: str
) -> None:
    """Test the rules that mark strings as file references.

    Args:
        name: Name of the property.
        schema: Keywords of its schema besides ``type``.
        reference: Expected annotation.
        reason: Expected reason in the note.
    """
    conversion = to_ga4gh(config({name: {"type": "string", **schema}}))

    validate_schema(conversion.schema)
    assert inputs(conversion)["properties"][name]["x-ga4gh-file"] == reference
    kind = reference["kind"]
    assert messages(conversion)[0] == (
        f"Marked as a file reference ({kind}): {reason}. Keep it a plain string "
        f"with --plain {name}."
    )


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string"},
        {"type": "string", "default": "genome"},
        {"type": "string", "default": 3},
        {"type": "string", "description": "the name of the file"},
        {"type": "integer", "description": "path to nowhere"},
        {"description": "path to nowhere"},
    ],
)
def test_heuristics_leave_other_strings(schema: dict[str, Any]) -> None:
    """Test that strings that don't look like paths stay plain.

    Args:
        schema: Schema of the property ``species``.
    """
    conversion = to_ga4gh(config({"species": schema}))

    assert "x-ga4gh-file" not in inputs(conversion)["properties"]["species"]
    assert len(conversion.notes) == 1  # outputs


def test_heuristics_off() -> None:
    """Test that ``guess=False`` marks nothing by itself."""
    conversion = to_ga4gh(config({"genome_fasta": {"type": "string"}}), guess=False)

    assert "x-ga4gh-file" not in inputs(conversion)["properties"]["genome_fasta"]


@pytest.mark.parametrize(
    ("schema", "problem"),
    [
        ({"type": ["string", "null"]}, 'its type is ["string", "null"], not "string"'),
        ({"type": "string", "allOf": [{"minLength": 1}]}, "it has 'allOf'"),
    ],
)
def test_heuristics_report_strings_they_cant_mark(
    schema: dict[str, Any], problem: str
) -> None:
    """Test the note for paths that can't be file references.

    Args:
        schema: Schema of the property ``genome_fasta``.
        problem: Expected reason.
    """
    conversion = to_ga4gh(config({"genome_fasta": schema}))

    assert "x-ga4gh-file" not in inputs(conversion)["properties"]["genome_fasta"]
    assert messages(conversion)[0] == (
        "Looks like a file (its name ends with 'fasta'), but isn't marked as a "
        f"file reference: {problem}."
    )


def test_marking_drops_keywords_that_file_references_cant_have() -> None:
    """Test that ``format`` and the content keywords are dropped, with a note."""
    source = config(
        {
            "reads_fq": {"type": "string", "format": "uri", "contentMediaType": "x/y"},
            "named": {"type": "string", "format": "uri"},
        }
    )

    conversion = to_ga4gh(source, files=["named"])

    validate_schema(conversion.schema)
    properties = inputs(conversion)["properties"]
    assert properties["reads_fq"] == {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
    }
    assert properties["named"] == {"type": "string", "x-ga4gh-file": {"kind": "file"}}
    assert messages(conversion)[:2] == [
        "Marked as a file reference (file): its name ends with 'fq'. Dropped "
        "'format', 'contentMediaType': file references can't have it. Keep it a "
        "plain string with --plain reads_fq.",
        "Marked as a file reference (file): named with --file. Dropped 'format': "
        "file references can't have it.",
    ]


def test_existing_file_references_are_kept() -> None:
    """Test that the author's own file references are left alone."""
    reference = {"kind": "directory", "schemes": ["s3"]}
    source = config({"index_file": {"type": "string", "x-ga4gh-file": reference}})

    conversion = to_ga4gh(source)

    assert inputs(conversion)["properties"]["index_file"]["x-ga4gh-file"] == reference
    assert len(conversion.notes) == 1


def test_unnamed_properties_are_marked_with_another_hint() -> None:
    """Test properties that the options can't name (e.g., in ``$defs``)."""
    source = config(
        {}, definitions={"ref": {"properties": {"fasta": {"type": "string"}}}}
    )

    conversion = to_ga4gh(source)

    assert conversion.schema["$defs"]["ref"]["properties"]["fasta"]["x-ga4gh-file"]
    assert messages(conversion)[0].endswith(
        "It can't be named on the command line: edit the result to undo it."
    )
    assert conversion.notes[0].location == "$['$defs'].ref.properties.fasta"


# --- Options ----------------------------------------------------------------


def test_options_name_nested_properties() -> None:
    """Test dotted paths, and that --plain wins over the heuristics."""
    source = config(
        {
            "ref": {
                "type": "object",
                "properties": {
                    "genome": {"type": "string"},
                    "fasta": {"type": "string"},
                },
            }
        }
    )

    conversion = to_ga4gh(source, directories=["ref.genome"], plain=["ref.fasta"])

    properties = inputs(conversion)["properties"]["ref"]["properties"]
    assert properties["genome"]["x-ga4gh-file"] == {"kind": "directory"}
    assert "x-ga4gh-file" not in properties["fasta"]
    assert len(conversion.notes) == 1


def test_options_conflict() -> None:
    """Test that a property can't be named by two options."""
    with pytest.raises(ConversionError, match="named by both --file and --plain"):
        to_ga4gh(config({}), files=["a"], plain=["a"])


def test_options_name_existing_properties() -> None:
    """Test that options must name properties of the sources."""
    with pytest.raises(ConversionError, match=r"No property 'ref\.x' \(--file\)"):
        to_ga4gh(config({"ref": {"type": "object"}}), files=["ref.x"])


@pytest.mark.parametrize(
    ("schema", "problem"),
    [
        ({"type": "integer"}, 'its type is "integer", not "string"'),
        ({}, 'its type is null, not "string"'),
        ({"type": "string", "$ref": "#/$defs/x"}, "it has '$ref'"),
        (True, "its schema is a boolean"),
    ],
)
def test_options_name_strings(schema: Any, problem: str) -> None:
    """Test that --file names only schemas that can be file references.

    Args:
        schema: Schema of the property.
        problem: Expected reason.
    """
    with pytest.raises(ConversionError) as exc_info:
        to_ga4gh(config({"a": schema}), files=["a"])

    assert exc_info.value.message == f"'a' can't be a file reference: {problem}."
    assert exc_info.value.location == "$.properties.inputs.properties.a"


def test_plain_boolean_schemas_are_kept() -> None:
    """Test that boolean property schemas pass through."""
    conversion = to_ga4gh(config({"a": True, "b": False}), plain=["a"])

    assert inputs(conversion)["properties"] == {"a": True, "b": False}


# --- Sample sheets ----------------------------------------------------------


ROW = {
    "$schema": DRAFT_4,
    "definitions": {"id": {"type": "string", "pattern": "^[a-z]+$"}},
    "properties": {
        "sample": {"$ref": "#/definitions/id"},
        "bam": {"type": "string"},
        "self": {"$ref": "#"},
    },
}


def test_sample_sheet_becomes_the_tabular_hint() -> None:
    """Test the conversion of a sample-sheet schema, with its references."""
    source = config({"samples": {"type": "string", "default": "config/samples.tsv"}})

    conversion = to_ga4gh(source, [SampleSheet(ROW)])

    validate_schema(conversion.schema)
    samples = inputs(conversion)["properties"]["samples"]
    assert samples["x-ga4gh-file"] == {
        "kind": "file",
        "mediaType": "text/tab-separated-values",
    }
    items = samples["x-ga4gh-tabular-schema"]["items"]
    base = "#/properties/inputs/properties/samples/x-ga4gh-tabular-schema/items"
    assert items["properties"]["sample"] == {"$ref": f"{base}/$defs/id"}
    assert items["properties"]["self"] == {"$ref": base}
    assert items["properties"]["bam"]["x-ga4gh-file"] == {"kind": "file"}
    notes = messages(conversion)
    assert notes[0] == "Marked as a file reference (file): it holds a sample sheet."
    assert "Keep it a plain string with --plain samples.bam." in notes[1]
    assert notes[2] == (
        "The sample-sheet schema is the experimental tabular hint of 'samples': an "
        "array with one item per row."
    )


def test_sample_sheet_columns_can_be_named() -> None:
    """Test that options name columns as ``<property>.<column>``."""
    source = config({"data": {"properties": {"units": {"type": "string"}}}})
    row = {"$schema": DRAFT_2020, "properties": {"bam": {"type": "string"}}}

    conversion = to_ga4gh(
        source, [SampleSheet(row, "data.units")], plain=["data.units.bam"]
    )

    units = inputs(conversion)["properties"]["data"]["properties"]["units"]
    assert (
        "x-ga4gh-file"
        not in units["x-ga4gh-tabular-schema"]["items"]["properties"]["bam"]
    )


def test_sample_sheet_may_also_be_named_with_file() -> None:
    """Test that --file on the property of a sheet is allowed."""
    source = config({"samples": {"type": "string"}})

    conversion = to_ga4gh(source, [SampleSheet(True, "samples")], files=["samples"])

    assert inputs(conversion)["properties"]["samples"]["x-ga4gh-tabular-schema"] == {
        "type": "array",
        "items": True,
    }


@pytest.mark.parametrize(
    ("source", "sheets", "options", "message"),
    [
        (config({}), [SampleSheet(True), SampleSheet(True)], {}, "Name the property"),
        (config({}), [SampleSheet(True)], {}, r"candidates: none\)"),
        ({"$schema": DRAFT_2020}, [SampleSheet(True)], {}, r"candidates: none\)"),
        (
            config({"samples": {}, "sample_sheet": {}}),
            [SampleSheet(True)],
            {},
            r"candidates: samples, sample_sheet\)",
        ),
        (
            config({"s": {"type": "string"}}),
            [SampleSheet(True, "s"), SampleSheet(True, "s")],
            {},
            "Two sample sheets for 's'",
        ),
        (
            config({"s": {"type": "string"}}),
            [SampleSheet(True, "s")],
            {"plain": ["s"]},
            "'s' holds a sample sheet, and is named by --plain",
        ),
        (
            config({"s": {"type": "string", "x-ga4gh-file": {"kind": "directory"}}}),
            [SampleSheet(True, "s")],
            {},
            "'s' holds a sample sheet, but isn't a file reference",
        ),
        (
            config({"s": {"type": "string", "x-ga4gh-tabular-schema": True}}),
            [SampleSheet(True, "s")],
            {},
            "'s' has an 'x-ga4gh-tabular-schema' already",
        ),
        (
            config({}),
            [SampleSheet(True, "units")],
            {},
            r"No property 'units' \(--sample-sheet\)",
        ),
        (
            config({"s": {"type": "string"}}),
            [SampleSheet(True, "s"), SampleSheet({"properties": {"c": True}}, "s.c")],
            {},
            r"No property 's\.c' \(--sample-sheet\)",
        ),
        (
            config({"s": {"type": "string"}}),
            [SampleSheet({"$schema": "http://json-schema.org/draft-03/schema"}, "s")],
            {},
            "Draft 3",
        ),
    ],
)
def test_sample_sheet_errors(
    source: dict[str, Any],
    sheets: list[SampleSheet],
    options: dict[str, list[str]],
    message: str,
) -> None:
    """Test sample sheets that can't be attached.

    Args:
        source: The config schema.
        sheets: The sample-sheet schemas.
        options: Other options of the conversion.
        message: Pattern of the expected error.
    """
    with pytest.raises(ConversionError, match=message):
        to_ga4gh(source, sheets, **options)


# --- Helpers ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("pointer", "expected"),
    [
        ((), "$"),
        (("properties", "inputs", 0), "$.properties.inputs[0]"),
        (("x-ga4gh-file", "it's", "a\\b"), "$['x-ga4gh-file']['it\\'s']['a\\\\b']"),
    ],
)
def test_json_path(pointer: tuple[str | int, ...], expected: str) -> None:
    """Test that locations are rendered as the validator renders them.

    Args:
        pointer: The location.
        expected: The JSON path.
    """
    assert json_path(pointer) == expected


def test_note_rendering() -> None:
    """Test the text and JSON forms of notes."""
    note = Note("Done.", "$.a")

    assert note.to_text() == "Note: Done. (at $.a)"
    assert note.to_dict() == {"message": "Done.", "location": "$.a"}
