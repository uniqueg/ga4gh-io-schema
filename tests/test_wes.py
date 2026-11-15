# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the translation between input values and WES ``workflow_params``.

The language-neutral test vectors of ``tests/vectors/wes-params/`` and
``tests/vectors/wes-requests/`` are run against the library here; other
implementations run them with their own runner (see
``docs/specification/engine-bindings.md``).
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
    WorkflowParamsError,
    build_run_request,
    check_file_value,
    error_response,
    from_workflow_params,
    get_binding,
    to_workflow_params,
    trs_descriptor_url,
)

VECTORS_DIR = Path(__file__).resolve().parent / "vectors" / "wes-params"
VECTORS = sorted(path.parent for path in VECTORS_DIR.glob("*/*/schema.json"))
REQUESTS_DIR = VECTORS_DIR.parent / "wes-requests"
REQUESTS = sorted(path.parent for path in REQUESTS_DIR.glob("*/*/schema.json"))
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
        to_workflow_params(schema, {"reads": "\\data\\reads.fq"})


def test_cwl_file_objects_are_not_values() -> None:
    """Test that CWL file objects can't bypass the checks of file references."""
    schema = make_schema({"rec": {"type": "object"}}, {"descriptor_type": "CWL"})
    smuggled = {"class": "File", "location": "file:///etc/passwd"}

    with pytest.raises(TranslationError, match="aren't input values") as info:
        to_workflow_params(schema, {"rec": {"inner": smuggled}})
    assert info.value.pointer == "/rec/inner"
    # Other engines take such objects as plain objects
    nfl = make_schema({"rec": {"type": "object"}}, NFL)
    assert to_workflow_params(nfl, {"rec": smuggled}) == {"rec": smuggled}


def test_unevaluated_only_where_nothing_else_applies() -> None:
    """Test that members evaluated by an in-place applicator keep their schema."""
    schema = make_schema(
        {
            "rec": {
                "type": "object",
                "allOf": [{"properties": {"a": {"type": "string"}}}],
                "unevaluatedProperties": file_ref(),
            },
            "list": {
                "type": "array",
                "allOf": [{"prefixItems": [{"type": "string"}]}],
                "unevaluatedItems": file_ref(),
            },
        },
        {"descriptor_type": "CWL"},
    )
    location = "https://e.org/x"

    assert to_workflow_params(
        schema,
        {"rec": {"a": "plain text", "b": location}, "list": ["plain", location]},
    ) == {
        "rec": {"a": "plain text", "b": {"class": "File", "location": location}},
        "list": ["plain", {"class": "File", "location": location}],
    }


def test_dynamic_references_fail_closed() -> None:
    """Test that ``$dynamicRef``, which isn't modelled, is rejected."""
    schema = make_schema(
        {"reads": {"$dynamicRef": "#file"}},
        NFL,
        **{"$defs": {"file": {"$dynamicAnchor": "file", **file_ref()}}},
    )

    with pytest.raises(TranslationError, match="'\\$dynamicRef'"):
        to_workflow_params(schema, {"reads": "file:///etc/passwd"})


@pytest.mark.parametrize(
    ("conditional", "expected"),
    [
        # `else` applies; the value is a file reference
        ({"else": file_ref()}, {"class": "File", "location": "https://e.org/x"}),
        # Neither `then` nor `else` applies
        ({"then": file_ref()}, "https://e.org/x"),
    ],
)
def test_if_without_match(conditional: dict[str, Any], expected: Any) -> None:
    """Test the branches of ``if`` for a value that ``if`` doesn't accept.

    Args:
        conditional: ``then`` or ``else`` of the schema.
        expected: Expected translated value.
    """
    schema = make_schema(
        {"reads": {"if": {"maxLength": 1}, **conditional}},
        {"descriptor_type": "CWL"},
    )

    assert to_workflow_params(schema, {"reads": "https://e.org/x"}) == {
        "reads": expected
    }


def test_conflicting_kinds_are_rejected() -> None:
    """Test that a value can't be a file and a directory at once."""
    directory = {"type": "string", "x-ga4gh-file": {"kind": "directory"}}
    schema = make_schema({"reads": {"allOf": [file_ref(), directory]}}, NFL)

    with pytest.raises(TranslationError, match="different kinds") as info:
        to_workflow_params(schema, {"reads": "https://e.org/x"})
    assert info.value.pointer == "/reads"


def test_unevaluated_items_and_failed_contains() -> None:
    """Test ``unevaluatedItems``, and items that ``contains`` doesn't match."""
    schema = make_schema(
        {
            "files": {"type": "array", "unevaluatedItems": file_ref()},
            "mixed": {"type": "array", "contains": file_ref()},
        },
        {"descriptor_type": "CWL"},
    )
    location = "https://e.org/x"

    assert to_workflow_params(
        schema, {"files": [location], "mixed": [1, location]}
    ) == {
        "files": [{"class": "File", "location": location}],
        "mixed": [1, {"class": "File", "location": location}],
    }


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


def run_request(path: Path) -> dict[str, Any]:
    """Translate the ``workflow_params`` of a request vector with its options.

    Args:
        path: Directory of the vector.

    Returns:
        The input values.
    """
    options_path = path / "options.json"
    options = load_json(options_path) if options_path.exists() else {}
    return from_workflow_params(
        load_json(path / "schema.json"),
        load_json(path / "workflow_params.json"),
        allowed_schemes=options.get("allowedSchemes", DEFAULT_ALLOWED_SCHEMES),
        allow_absolute_paths=options.get("allowAbsolutePaths", False),
        allow_paths=options.get("allowPaths", False),
    )


def test_request_vectors_cover_every_descriptor_type() -> None:
    """Test that there are request vectors for every descriptor type."""
    assert {path.parent.name for path in REQUESTS} == set(DESCRIPTOR_TYPES)


@pytest.mark.parametrize(
    "path", REQUESTS, ids=lambda path: f"{path.parent.name}/{path.name}"
)
def test_request_vector_files(path: Path) -> None:
    """Test that a request vector has the expected files, and one result.

    Args:
        path: Directory of the vector.
    """
    names = {child.name for child in path.iterdir()}
    assert names <= VECTOR_FILES
    assert {"schema.json", "workflow_params.json"} <= names
    assert len(names & {"values.json", "error.json"}) == 1


@pytest.mark.parametrize(
    "path", REQUESTS, ids=lambda path: f"{path.parent.name}/{path.name}"
)
def test_request_vector(path: Path) -> None:
    """Test that a request vector gives its input values, or its error.

    Args:
        path: Directory of the vector.
    """
    assert load_json(path / "schema.json")["x-ga4gh-workflow"]["descriptor_type"] == (
        path.parent.name
    )
    if (path / "values.json").exists():
        assert run_request(path) == load_json(path / "values.json")
        return
    with pytest.raises(WorkflowParamsError) as info:
        run_request(path)
    assert info.value.pointer == load_json(path / "error.json")["pointer"]


@pytest.mark.parametrize(
    "path",
    [path for path in VECTORS if (path / "workflow_params.json").exists()],
    ids=lambda path: f"{path.parent.name}/{path.name}",
)
def test_round_trip(path: Path) -> None:
    """Test that the ``workflow_params`` of a vector translate back to its values.

    Args:
        path: Directory of a valid vector of ``wes-params``.
    """
    options_path = path / "options.json"
    options = load_json(options_path) if options_path.exists() else {}

    assert from_workflow_params(
        load_json(path / "schema.json"),
        load_json(path / "workflow_params.json"),
        allowed_schemes=options.get("allowedSchemes", DEFAULT_ALLOWED_SCHEMES),
        allow_absolute_paths=options.get("allowAbsolutePaths", False),
    ) == load_json(path / "values.json")


def reject(schema: dict[str, Any], params: Any, **options: Any) -> WorkflowParamsError:
    """Translate ``workflow_params`` that must be rejected.

    Args:
        schema: IO schema.
        params: The ``workflow_params``.
        **options: Options of :func:`from_workflow_params`.

    Returns:
        The error.
    """
    with pytest.raises(WorkflowParamsError) as info:
        from_workflow_params(schema, params, **options)
    return info.value


CWL = {"descriptor_type": "CWL"}
WDL = {"descriptor_type": "WDL", "entry_point": "wf"}


def test_error_response_names_the_pointer_and_the_message() -> None:
    """Test the ``ErrorResponse`` of the vector with an error message."""
    path = REQUESTS_DIR / "WDL" / "error-message"

    with pytest.raises(WorkflowParamsError) as info:
        run_request(path)

    assert error_response(info.value) == {
        "msg": (
            "/variant_calling.condition: Condition must be either control or treatment"
        ),
        "status_code": 400,
    }


def test_error_response_of_the_request_as_a_whole() -> None:
    """Test that an error without a location names ``workflow_params``."""
    error = reject(make_schema({}, NFL), ["a"])

    assert error.pointer == ""
    assert error_response(error) == {
        "msg": "workflow_params: workflow_params must be a JSON object.",
        "status_code": 400,
    }


def test_outermost_error_message_covers_the_failure() -> None:
    """Test that the message of the property wins over that of a definition."""
    schema = make_schema(
        {"condition": {"$ref": "#/$defs/c", "x-ga4gh-error-message": "Outer"}},
        NFL,
        **{"$defs": {"c": {"enum": ["a"], "x-ga4gh-error-message": "Inner"}}},
    )

    assert reject(schema, {"condition": "b"}).message == "Outer"


def test_error_message_of_a_definition() -> None:
    """Test that the message of a definition covers its failures."""
    schema = make_schema(
        {"condition": {"allOf": [{"$ref": "#/$defs/c"}]}},
        NFL,
        **{"$defs": {"c": {"enum": ["a"], "x-ga4gh-error-message": "Inner"}}},
    )

    assert reject(schema, {"condition": "b"}).message == "Inner"


def test_error_message_does_not_cover_other_locations() -> None:
    """Test that the message of an array doesn't cover its items."""
    schema = make_schema(
        {
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "x-ga4gh-error-message": "Names must be a list",
            }
        },
        NFL,
    )

    error = reject(schema, {"names": ["a", 1]})

    assert error.pointer == "/names/1"
    assert error.message == "The value fails the keyword 'type' of the schema."


def test_messages_do_not_repeat_the_value() -> None:
    """Test that a failure without error message is described by its keyword."""
    schema = make_schema({"condition": {"enum": ["control", "treatment"]}}, NFL)

    error = reject(schema, {"condition": "secret-value"})

    assert error.message == "The value fails the keyword 'enum' of the schema."
    assert "secret-value" not in error_response(error)["msg"]


def test_missing_input_is_named_by_its_key() -> None:
    """Test that a missing input is named by its key in ``workflow_params``."""
    schema = make_schema(
        {"reads": file_ref(), "rec": {"type": "object", "required": ["inner"]}}, WDL
    )
    schema["properties"]["inputs"]["required"] = ["reads"]

    assert reject(schema, {}).message == "The required member 'wf.reads' is missing."
    nested = reject(schema, {"wf.reads": "https://e.org/x", "wf.rec": {}})
    assert nested.pointer == "/wf.rec"
    assert nested.message == "The required member 'inner' is missing."


def test_binding_errors_are_request_errors() -> None:
    """Test that a binding that can't be used rejects the request."""
    error = reject(make_schema({}, {"descriptor_type": "GALAXY"}), {})

    assert error.pointer == ""
    assert "'GALAXY' has no engine binding" in error.message


def test_binding_from_the_request() -> None:
    """Test a binding built from the request's ``workflow_type``."""
    schema = make_schema({"a": {"type": "integer"}})
    binding = get_binding(schema, descriptor_type="WDL", entry_point="wf")

    assert from_workflow_params(schema, {"wf.a": 1}, binding) == {"a": 1}


def test_several_inputs_bind_to_one_key() -> None:
    """Test that a key that several inputs bind to is rejected."""
    schema = make_schema(
        {
            "a": {"type": "integer", "x-ga4gh-parameter": {"name": "b"}},
            "b": {"type": "integer"},
        },
        NFL,
    )

    error = reject(schema, {"b": 1})

    assert error.pointer == "/b"
    assert "Several inputs" in error.message


def test_binding_that_depends_on_the_value() -> None:
    """Test that the key must be the one that the value binds to."""
    schema = make_schema(
        {
            "a": {
                "anyOf": [
                    {"type": "integer", "x-ga4gh-parameter": {"name": "x"}},
                    {"type": "string", "x-ga4gh-parameter": {"name": "y"}},
                ]
            }
        },
        NFL,
    )

    assert from_workflow_params(schema, {"x": 1}) == {"a": 1}
    error = reject(schema, {"x": "text"})
    assert error.pointer == "/x"
    assert "'y'" in error.message


def test_unmatched_member_takes_the_key_of_an_input() -> None:
    """Test that a member that matches no input can't collide with one."""
    schema = make_schema(
        {"a": {"type": "integer", "x-ga4gh-parameter": {"name": "x"}}},
        WDL,
    )
    schema["properties"]["inputs"]["additionalProperties"] = {"type": "integer"}

    # The member `x` stays under its name, and binds to `wf.x` like `a`
    error = reject(schema, {"wf.x": 1, "x": 2})

    assert error.pointer == "/x"


@pytest.mark.parametrize(
    ("reads", "pointer", "message"),
    [
        (
            {"class": "File", "location": "https://e.org/x", "secondaryFiles": []},
            "/reads/secondaryFiles",
            "'secondaryFiles'",
        ),
        ({"class": "File", "location": 1}, "/reads/location", "must be a string"),
        (
            {"class": "File", "location": "https://e.org/x", "path": "x"},
            "/reads/path",
            "'path'",
        ),
        ({"class": "File"}, "/reads", "'location' or 'path'"),
    ],
)
def test_fields_of_cwl_objects(reads: Any, pointer: str, message: str) -> None:
    """Test the fields of CWL objects that are rejected, with paths allowed.

    Args:
        reads: The CWL object.
        pointer: Expected location of the error.
        message: Expected part of the message.
    """
    schema = make_schema({"reads": file_ref()}, CWL)

    error = reject(schema, {"reads": reads}, allow_paths=True)

    assert error.pointer == pointer
    assert message in error.message


def test_cwl_objects_in_free_form_objects() -> None:
    """Test that a CWL object where no file reference applies is rejected."""
    schema = make_schema({"rec": {"type": "object"}}, CWL)

    error = reject(schema, {"rec": {"inner": {"class": "File", "location": "x"}}})

    assert error.pointer == "/rec/inner"


def test_cwl_directory_with_path() -> None:
    """Test a CWL ``Directory`` object with ``path``."""
    directory = {"type": "string", "x-ga4gh-file": {"kind": "directory"}}
    schema = make_schema({"index": directory}, CWL)

    assert from_workflow_params(
        schema,
        {"index": {"class": "Directory", "path": "inputs/index"}},
        allow_paths=True,
    ) == {"index": "inputs/index"}


def test_cwl_objects_are_plain_objects_for_other_engines() -> None:
    """Test that other descriptor types take CWL objects as plain objects."""
    schema = make_schema({"rec": {"type": "object"}}, NFL)
    params = {"rec": {"class": "File", "location": "file:///etc/passwd"}}

    assert from_workflow_params(schema, params) == params


def test_workflow_params_are_not_changed() -> None:
    """Test that the translation doesn't change ``workflow_params``."""
    path = REQUESTS_DIR / "CWL" / "file-objects"
    params = load_json(path / "workflow_params.json")
    before = copy.deepcopy(params)

    from_workflow_params(load_json(path / "schema.json"), params)

    assert params == before


@pytest.mark.parametrize(
    "inputs",
    [
        # Met when the keys of the inputs are collected
        {"a": {"$ref": "https://example.org/elsewhere.json"}},
        # Met only when the values are validated
        {"a": {"type": "object", "properties": {"b": {"$ref": "#/$defs/missing"}}}},
    ],
)
def test_unresolvable_references_reject_the_request(inputs: dict[str, Any]) -> None:
    """Test that references that can't be resolved locally fail closed.

    Args:
        inputs: Properties of ``inputs``.
    """
    error = reject(make_schema(inputs, NFL), {"a": {"b": 1}})

    assert error.pointer == ""
    assert "can't be resolved locally" in error.message


def test_dynamic_references_reject_the_request() -> None:
    """Test that ``$dynamicRef`` at a file reference fails closed."""
    schema = make_schema(
        {"reads": {"$dynamicRef": "#file"}},
        CWL,
        **{"$defs": {"file": {"$dynamicAnchor": "file", **file_ref()}}},
    )

    error = reject(schema, {"reads": {"class": "File", "location": "file:///x"}})

    assert "'$dynamicRef'" in error.message


def test_forbidden_schemes_can_not_be_allowed_on_servers() -> None:
    """Test that the allow-list of a server can't contain a forbidden scheme."""
    with pytest.raises(ValueError, match="file"):
        from_workflow_params(make_schema({}, NFL), {}, allowed_schemes=["file"])


@pytest.mark.parametrize(
    "condition",
    [
        # The failing keyword is in the target of `$ref`, not next to it
        {"$ref": "#/$defs/c", "properties": {"other": {}}},
        {"$ref": "#/$defs/c", "allOf": [{}]},
    ],
)
def test_error_message_behind_a_reference_with_siblings(
    condition: dict[str, Any],
) -> None:
    """Test that the search for the message follows ``$ref`` past its siblings.

    Args:
        condition: Schema of the input, with a reference and siblings.
    """
    schema = make_schema(
        {"condition": condition},
        NFL,
        **{
            "$defs": {
                "c": {
                    "properties": {"level": {"allOf": [{"enum": ["a"]}]}},
                    "allOf": [{"required": ["level"]}],
                    "x-ga4gh-error-message": "Level must be a",
                }
            }
        },
    )

    error = reject(schema, {"condition": {"level": "b"}})
    assert error.pointer == "/condition/level"
    assert error.message == "The value fails the keyword 'enum' of the schema."
    assert reject(schema, {"condition": {}}).message == "Level must be a"


@pytest.mark.parametrize(
    ("inputs", "pointer"),
    [
        # jsonschema reports no instance location for a `false` property
        ({"a": False}, ""),
        ({"a": {"$ref": "#/$defs/never"}}, "/a"),
    ],
)
def test_message_of_the_false_schema(inputs: dict[str, Any], pointer: str) -> None:
    """Test the message for a value that the schema ``false`` rejects.

    Args:
        inputs: Properties of ``inputs``.
        pointer: Expected location of the error.
    """
    schema = make_schema(inputs, NFL, **{"$defs": {"never": False}})

    error = reject(schema, {"a": 1})

    assert error.pointer == pointer
    assert error.message == "The schema doesn't allow a value here."


def test_error_message_behind_a_dynamic_reference() -> None:
    """Test the message of a failure that the search can't follow."""
    schema = make_schema(
        {"a": {"$dynamicRef": "#c"}},
        NFL,
        **{
            "$defs": {
                "c": {
                    "$dynamicAnchor": "c",
                    "enum": [1],
                    "x-ga4gh-error-message": "Must be 1",
                }
            }
        },
    )

    assert reject(schema, {"a": 2}).message == "Must be 1"


def test_keys_of_inputs_with_shared_subschemas() -> None:
    """Test that subschemas reached twice, and boolean ones, are collected once."""
    schema = make_schema(
        {"a": {"allOf": [True, {"$ref": "#/$defs/n"}, {"$ref": "#/$defs/n"}]}},
        NFL,
        **{"$defs": {"n": {"x-ga4gh-parameter": {"name": "b"}}}},
    )

    assert from_workflow_params(schema, {"b": 1}) == {"a": 1}
