# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the translation of input values into WES ``workflow_params``.

The language-neutral test vectors of ``tests/vectors/wes-params/`` are run
against the library here; other implementations run them with their own
runner (see ``docs/specification/engine-bindings.md``).
"""

import copy
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from ga4gh_io_schema.validator import load_json
from ga4gh_io_schema.wes import (
    DEFAULT_ALLOWED_SCHEMES,
    DESCRIPTOR_TYPES,
    EngineBinding,
    TranslationError,
    build_run_request,
    check_file_value,
    get_binding,
    to_workflow_params,
    trs_descriptor_url,
)

VECTORS_DIR = Path(__file__).resolve().parent / "vectors" / "wes-params"
VECTORS = sorted(path.parent for path in VECTORS_DIR.glob("*/*/schema.json"))
FILE_VALUES = load_json(VECTORS_DIR.parent / "file-values" / "cases.json")
PROFILE = (
    "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/"
    "ga4gh-io-profile.schema.json"
)
#: Files that a vector may have.
VECTOR_FILES = {
    "schema.json",
    "values.json",
    "workflow_params.json",
    "error.json",
    "options.json",
}


def make_schema(
    inputs: dict[str, Any], workflow: dict[str, Any] | None = None, **extra: Any
) -> dict[str, Any]:
    """Build an IO schema.

    Args:
        inputs: Properties of ``inputs``.
        workflow: The ``x-ga4gh-workflow`` block; omitted if ``None``.
        **extra: Other top-level keywords.

    Returns:
        The schema.
    """
    schema: dict[str, Any] = {
        "$schema": PROFILE,
        "type": "object",
        "properties": {"inputs": {"type": "object", "properties": inputs}},
        **extra,
    }
    if workflow is not None:
        schema["x-ga4gh-workflow"] = workflow
    return schema


def file_ref(**annotation: Any) -> dict[str, Any]:
    """Build a file reference schema.

    Args:
        **annotation: Keys of ``x-ga4gh-file`` besides ``kind``.

    Returns:
        The schema of a file reference to a file.
    """
    return {"type": "string", "x-ga4gh-file": {"kind": "file", **annotation}}


NFL = {"descriptor_type": "NFL"}


def run_vector(path: Path) -> dict[str, Any]:
    """Translate the values of a vector with its options.

    Args:
        path: Directory of the vector.

    Returns:
        The ``workflow_params``.
    """
    options_path = path / "options.json"
    options = load_json(options_path) if options_path.exists() else {}
    return to_workflow_params(
        load_json(path / "schema.json"),
        load_json(path / "values.json"),
        allowed_schemes=options.get("allowedSchemes", DEFAULT_ALLOWED_SCHEMES),
        allow_absolute_paths=options.get("allowAbsolutePaths", False),
    )


def test_vectors_cover_every_descriptor_type() -> None:
    """Test that there are vectors for every descriptor type."""
    assert {path.parent.name for path in VECTORS} == set(DESCRIPTOR_TYPES)


@pytest.mark.parametrize("path", VECTORS, ids=lambda path: path.name)
def test_vector_files(path: Path) -> None:
    """Test that a vector has the expected files, and one expected result.

    Args:
        path: Directory of the vector.
    """
    names = {child.name for child in path.iterdir()}
    assert names <= VECTOR_FILES
    assert {"schema.json", "values.json"} <= names
    assert len(names & {"workflow_params.json", "error.json"}) == 1


@pytest.mark.parametrize(
    "path", VECTORS, ids=lambda path: f"{path.parent.name}/{path.name}"
)
def test_vector(path: Path) -> None:
    """Test that a vector gives its ``workflow_params``, or its error.

    Args:
        path: Directory of the vector.
    """
    assert load_json(path / "schema.json")["x-ga4gh-workflow"]["descriptor_type"] == (
        path.parent.name
    )
    if (path / "workflow_params.json").exists():
        assert run_vector(path) == load_json(path / "workflow_params.json")
        return
    with pytest.raises(TranslationError) as info:
        run_vector(path)
    assert info.value.pointer == load_json(path / "error.json")["pointer"]


def test_file_value_cases_have_unique_names() -> None:
    """Test that every case of the file values has a name of its own."""
    names = [case["name"] for case in FILE_VALUES]

    assert len(names) == len(set(names))


@pytest.mark.parametrize("case", FILE_VALUES, ids=lambda case: case["name"])
def test_file_value(case: dict[str, Any]) -> None:
    """Test a case of the vectors of file reference values.

    Args:
        case: Annotation, value, options and whether the value is valid.
    """
    options = {
        "allowed_schemes": case.get("allowedSchemes", DEFAULT_ALLOWED_SCHEMES),
        "allow_absolute_paths": case.get("allowAbsolutePaths", False),
    }
    if case["valid"]:
        check_file_value(case["annotation"], case["value"], **options)
        return
    with pytest.raises(TranslationError):
        check_file_value(case["annotation"], case["value"], **options)


def test_check_file_value_rejects_forbidden_allow_list() -> None:
    """Test that the allow-list of a single check can't be forbidden either."""
    with pytest.raises(ValueError, match="data"):
        check_file_value({"kind": "file"}, "x", allowed_schemes=["data"])


def test_values_are_not_changed() -> None:
    """Test that the translation doesn't change the input values."""
    path = VECTORS_DIR / "CWL" / "file-objects"
    values = load_json(path / "values.json")
    before = copy.deepcopy(values)

    to_workflow_params(load_json(path / "schema.json"), values)

    assert values == before


def test_defaults_are_not_inserted() -> None:
    """Test that defaults of the schema don't become parameters."""
    schema = make_schema({"threads": {"type": "integer", "default": 4}}, NFL)

    assert to_workflow_params(schema, {}) == {}


def test_error_message_of_the_schema_is_used() -> None:
    """Test that a failing value reports the schema's ``x-ga4gh-error-message``."""
    schema = make_schema(
        {
            "condition": {
                "enum": ["control", "treatment"],
                "x-ga4gh-error-message": "Condition must be control or treatment",
            }
        },
        NFL,
    )

    with pytest.raises(TranslationError, match="^Condition must be control"):
        to_workflow_params(schema, {"condition": "contrl"})


def test_values_must_be_an_object() -> None:
    """Test that values other than an object are rejected."""
    schema = make_schema({}, NFL)
    schema["properties"]["inputs"] = True

    with pytest.raises(TranslationError, match="must be a JSON object"):
        to_workflow_params(schema, ["a"])


def test_inputs_of_a_boolean_schema_keep_their_names() -> None:
    """Test that ``"inputs": true`` passes values unchanged."""
    schema = make_schema({}, NFL)
    schema["properties"]["inputs"] = True

    assert to_workflow_params(schema, {"a": 1}) == {"a": 1}


def test_colliding_names_are_rejected() -> None:
    """Test that two inputs can't bind to the same engine parameter."""
    schema = make_schema(
        {
            "a": {"type": "integer", "x-ga4gh-parameter": {"name": "b"}},
            "b": {"type": "integer"},
        },
        NFL,
    )

    with pytest.raises(TranslationError, match="'b'") as info:
        to_workflow_params(schema, {"a": 1, "b": 2})
    assert info.value.pointer == "/b"


def test_references_are_followed() -> None:
    """Test ``$ref`` and ``allOf`` to file references and parameter bindings."""
    schema = make_schema(
        {
            "reads": {"$ref": "#/$defs/reads"},
            "index": {"allOf": [{"$ref": "#/$defs/index"}]},
        },
        {"descriptor_type": "CWL"},
        **{
            "$defs": {
                "reads": {**file_ref(), "x-ga4gh-parameter": {"name": "fastq"}},
                "index": {"type": "string", "x-ga4gh-file": {"kind": "directory"}},
            }
        },
    )

    assert to_workflow_params(
        schema, {"reads": "https://e.org/r.fq", "index": "drs://e.org/i"}
    ) == {
        "fastq": {"class": "File", "location": "https://e.org/r.fq"},
        "index": {"class": "Directory", "location": "drs://e.org/i"},
    }


def test_references_in_embedded_resources() -> None:
    """Test that a ``$ref`` resolves against the ``$id`` of its resource."""
    schema = make_schema(
        {"reads": {"$ref": "https://example.org/shared#/$defs/reads"}},
        {"descriptor_type": "CWL"},
        **{
            "$defs": {
                "shared": {
                    "$id": "https://example.org/shared",
                    "$defs": {"reads": {"$ref": "#/$defs/file"}, "file": file_ref()},
                }
            }
        },
    )

    assert to_workflow_params(schema, {"reads": "https://e.org/r.fq"}) == {
        "reads": {"class": "File", "location": "https://e.org/r.fq"}
    }


def test_recursive_references_terminate() -> None:
    """Test that a schema that references itself is expanded once."""
    schema = make_schema(
        {"tree": {"$ref": "#/$defs/tree"}},
        {"descriptor_type": "CWL"},
        **{
            "$defs": {
                "tree": {
                    "type": "object",
                    "properties": {
                        "leaf": file_ref(),
                        "child": {"$ref": "#/$defs/tree"},
                    },
                    # The same subschema twice is expanded once
                    "allOf": [{"$ref": "#/$defs/leaf"}, {"$ref": "#/$defs/leaf"}],
                },
                "leaf": {"type": "object"},
            }
        },
    )

    assert to_workflow_params(
        schema, {"tree": {"child": {"leaf": "https://e.org/x"}}}
    ) == {"tree": {"child": {"leaf": {"class": "File", "location": "https://e.org/x"}}}}


def test_unresolvable_reference_in_values_validation() -> None:
    """Test that a reference that can't be resolved locally fails closed."""
    schema = make_schema({"a": {"$ref": "https://example.org/elsewhere.json"}}, NFL)

    with pytest.raises(TranslationError, match="can't be resolved locally"):
        to_workflow_params(schema, {"a": 1})


def test_unresolvable_reference_in_expansion() -> None:
    """Test that the expansion also fails closed on an unresolvable reference.

    The validator stops at the first valid branch of ``anyOf``; the expansion
    checks every branch, so it meets the reference of the second.
    """
    schema = make_schema(
        {"a": {"anyOf": [{"type": "integer"}, {"$ref": "#/$defs/missing"}]}}, NFL
    )

    with pytest.raises(TranslationError, match="can't be resolved locally"):
        to_workflow_params(schema, {"a": 1})


def test_pattern_and_prefix_items() -> None:
    """Test file references in ``patternProperties`` and ``prefixItems``."""
    schema = make_schema(
        {
            "files": {"type": "object", "patternProperties": {"^f": file_ref()}},
            "pair": {
                "type": "array",
                "prefixItems": [file_ref(), {"type": "string"}],
                "items": file_ref(),
            },
            "plain": {"type": "array"},
            "embedded": {
                "$id": "https://example.org/embedded",
                "$ref": "#/$defs/file",
                "$defs": {"file": file_ref()},
            },
        },
        {"descriptor_type": "CWL"},
    )
    location = "https://e.org/x"

    params = to_workflow_params(
        schema,
        {
            "files": {"f1": location, "other": location},
            "pair": [location, location, location],
            "plain": [location],
            "embedded": location,
        },
    )

    as_file = {"class": "File", "location": location}
    assert params == {
        "files": {"f1": as_file, "other": location},
        "pair": [as_file, location, as_file],
        "plain": [location],
        "embedded": as_file,
    }


def test_empty_file_reference_is_rejected() -> None:
    """Test that an empty string isn't a file reference."""
    schema = make_schema({"reads": file_ref()}, NFL)

    with pytest.raises(TranslationError, match="can't be empty"):
        to_workflow_params(schema, {"reads": ""})


def test_windows_absolute_path_and_backslash_segments() -> None:
    """Test that backslashes count as separators of path segments."""
    schema = make_schema({"reads": file_ref()}, NFL)

    with pytest.raises(TranslationError, match="'..' segments"):
        to_workflow_params(schema, {"reads": "data\\..\\secret"})
    with pytest.raises(TranslationError, match="Absolute paths"):
        to_workflow_params(schema, {"reads": "\\\\server\\share"})


def test_schemes_are_compared_in_lowercase() -> None:
    """Test that schemes of values and of the allow-list ignore case."""
    schema = make_schema({"reads": file_ref(schemes=["https"])}, NFL)

    assert to_workflow_params(
        schema, {"reads": "HTTPS://e.org/x"}, allowed_schemes=["HTTPS"]
    ) == {"reads": "HTTPS://e.org/x"}


def test_forbidden_schemes_can_not_be_allowed() -> None:
    """Test that the allow-list can't contain a forbidden scheme."""
    schema = make_schema({}, NFL)

    with pytest.raises(ValueError, match="file"):
        to_workflow_params(schema, {}, allowed_schemes=["https", "file"])


def test_invalid_schema_is_rejected() -> None:
    """Test that a schema that doesn't comply with the profile is rejected."""
    with pytest.raises(jsonschema.exceptions.ValidationError):
        to_workflow_params({"type": "object"}, {})
    with pytest.raises(jsonschema.exceptions.ValidationError):
        build_run_request({"type": "object"}, {}, "https://e.org/w")


@pytest.mark.parametrize(
    ("path", "pointer", "json_path"),
    [
        ((), "", "$"),
        (("a", 0), "/a/0", "$.a[0]"),
        (("a/b", "c~d", "e f"), "/a~1b/c~0d/e f", "$['a/b']['c~d']['e f']"),
    ],
)
def test_error_locations(
    path: tuple[str | int, ...], pointer: str, json_path: str
) -> None:
    """Test the JSON Pointer and JSON Path of an error.

    Args:
        path: Location in the values.
        pointer: Expected JSON Pointer.
        json_path: Expected JSON Path.
    """
    error = TranslationError("x", path)

    assert error.pointer == pointer
    assert error.json_path == json_path


def test_get_binding_from_the_schema() -> None:
    """Test that the binding comes from ``x-ga4gh-workflow``."""
    schema = load_json(VECTORS_DIR / "WDL" / "qualified-names" / "schema.json")

    assert get_binding(schema) == EngineBinding("WDL", "1.1", "variant_calling")


def test_get_binding_fills_in_missing_fields() -> None:
    """Test that arguments fill in fields that the schema lacks."""
    assert get_binding(make_schema({}, NFL), descriptor_type_version="DSL2") == (
        EngineBinding("NFL", "DSL2")
    )
    assert get_binding(make_schema({}), descriptor_type="CWL", entry_point="#main") == (
        EngineBinding("CWL", None, "#main")
    )


def test_get_binding_rejects_conflicts() -> None:
    """Test that an argument must match the schema."""
    with pytest.raises(TranslationError, match="descriptor_type 'CWL' differs"):
        get_binding(make_schema({}, NFL), descriptor_type="CWL")


def test_get_binding_needs_a_descriptor_type() -> None:
    """Test that a schema without workflow block needs the descriptor type."""
    with pytest.raises(TranslationError, match="descriptor type is unknown"):
        get_binding(make_schema({}))


def test_binding_rejects_unsupported_descriptor_types() -> None:
    """Test that GALAXY (and other types) have no engine binding."""
    with pytest.raises(TranslationError, match="'GALAXY' has no engine binding"):
        get_binding(make_schema({}, {"descriptor_type": "GALAXY"}))


def test_wdl_binding_needs_an_entry_point() -> None:
    """Test that a WDL binding without entry point is rejected."""
    with pytest.raises(TranslationError, match="WDL needs the entry point"):
        EngineBinding("WDL", "1.1")


def test_explicit_binding_is_used() -> None:
    """Test that a given binding replaces that of the schema."""
    schema = make_schema({"a": {"type": "integer"}})

    assert to_workflow_params(schema, {"a": 1}, EngineBinding("WDL", None, "wf")) == {
        "wf.a": 1
    }


def test_build_run_request() -> None:
    """Test the fields of a run request."""
    path = VECTORS_DIR / "WDL" / "qualified-names"
    url = "https://trs.example.org/wdl"

    request = build_run_request(
        load_json(path / "schema.json"), load_json(path / "values.json"), url
    )

    assert request == {
        "workflow_params": load_json(path / "workflow_params.json"),
        "workflow_type": "WDL",
        "workflow_type_version": "1.1",
        "workflow_url": url,
    }


def test_build_run_request_appends_cwl_entry_point() -> None:
    """Test that the CWL entry point becomes the fragment of the URL."""
    schema = make_schema(
        {}, {"descriptor_type": "CWL", "descriptor_type_version": "v1.2"}
    )

    for entry_point in ("#main", "main"):
        request = build_run_request(
            schema,
            {},
            "https://e.org/packed.cwl",
            EngineBinding("CWL", "v1.2", entry_point),
        )
        assert request["workflow_url"] == "https://e.org/packed.cwl#main"
    with pytest.raises(TranslationError, match="has a fragment"):
        build_run_request(
            schema, {}, "https://e.org/p.cwl#x", EngineBinding("CWL", "v1.2", "#main")
        )


def test_build_run_request_needs_a_version() -> None:
    """Test that a run request needs the descriptor type version."""
    with pytest.raises(TranslationError, match="version is unknown"):
        build_run_request(make_schema({}, NFL), {}, "https://e.org/w")


def test_trs_descriptor_url() -> None:
    """Test the TRS URL of the plain primary descriptor."""
    assert trs_descriptor_url(
        "https://trs.example.org/ga4gh/trs/v2/",
        "#workflow/example.org/variant-calling",
        "1.2.0",
        "WDL",
    ) == (
        "https://trs.example.org/ga4gh/trs/v2/tools/"
        "%23workflow%2Fexample.org%2Fvariant-calling/versions/1.2.0/PLAIN_WDL/"
        "descriptor"
    )
