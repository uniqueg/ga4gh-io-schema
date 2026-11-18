# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the translation between input values and WES ``workflow_params``.

The language-neutral test vectors of ``tests/vectors/wes-params/`` and
``tests/vectors/wes-requests/`` are run against the library here; other
implementations run them with their own runner (see
``docs/specification/engine-bindings.md``).
"""

import contextlib
import copy
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import jsonschema
import pytest

from ga4gh_io_schema import wes
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
FILE_VALUES: list[dict[str, Any]] = json.loads(
    (VECTORS_DIR.parent / "file-values" / "cases.json").read_text(encoding="utf-8")
)
PROFILE = (
    "https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/"
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


@pytest.mark.parametrize("key", ["$include", "$import", "$mixin", "$namespaces"])
def test_cwl_loader_directives_are_not_values(key: str) -> None:
    """Test that schema-salad directives can't make the runner load files.

    Args:
        key: Key of a directive of the CWL loader (schema-salad).
    """
    schema = make_schema({"rec": {"type": "object"}}, {"descriptor_type": "CWL"})
    smuggled = {key: "file:///etc/passwd"}

    with pytest.raises(TranslationError, match=r"start with '\$'") as info:
        to_workflow_params(schema, {"rec": {"inner": [smuggled]}})
    assert info.value.pointer == f"/rec/inner/0/{key}"
    # The message names the location only, not the value
    assert "passwd" not in info.value.message
    with pytest.raises(WorkflowParamsError, match=r"start with '\$'") as error:
        from_workflow_params(schema, {"rec": smuggled})
    assert error.value.pointer == f"/rec/{key}"
    # Other engines take such keys as plain members
    nfl = make_schema({"rec": {"type": "object"}}, NFL)
    assert to_workflow_params(nfl, {"rec": smuggled}) == {"rec": smuggled}


def test_cwl_loader_directives_at_the_top_level() -> None:
    """Test that a directive can't come as a member of the input values."""
    schema = make_schema({"reads": {"type": "string"}}, {"descriptor_type": "CWL"})

    with pytest.raises(TranslationError, match=r"start with '\$'") as info:
        to_workflow_params(schema, {"reads": "a", "$namespaces": {}})
    assert info.value.pointer == "/$namespaces"
    with pytest.raises(WorkflowParamsError, match=r"start with '\$'") as error:
        from_workflow_params(schema, {"reads": "a", "$schemas": []})
    assert error.value.pointer == "/$schemas"
    # Also where the schema binds other members to a name without `$`: a
    # server passes the member on under its own key
    renamed = make_schema({}, {"descriptor_type": "CWL"})
    renamed["properties"]["inputs"]["additionalProperties"] = {
        "x-ga4gh-parameter": {"name": "extra"}
    }
    with pytest.raises(WorkflowParamsError, match=r"start with '\$'") as error:
        from_workflow_params(renamed, {"$include": "file:///etc/passwd"})
    assert error.value.pointer == "/$include"
    with pytest.raises(TranslationError, match=r"start with '\$'") as info:
        to_workflow_params(renamed, {"$include": "file:///etc/passwd"})
    assert info.value.pointer == "/$include"


@pytest.mark.parametrize(
    "key", ["cwltool:overrides", "cwl:requirements", "http://commonwl.org/cwltool#x"]
)
def test_cwl_namespaced_keys_are_not_values(key: str) -> None:
    """Test that keys of the namespaces of the CWL loader are rejected.

    cwltool expands keys like ``cwltool:overrides`` of the job order and
    applies them as requirements (e.g., another container image).

    Args:
        key: A key with a namespace prefix or a URI.
    """
    schema = make_schema({"rec": {"type": "object"}}, {"descriptor_type": "CWL"})

    with pytest.raises(TranslationError, match="contain ':'") as info:
        to_workflow_params(schema, {"rec": {}, key: {}})
    assert info.value.pointer == "/" + key.replace("/", "~1")
    with pytest.raises(WorkflowParamsError, match="contain ':'") as error:
        from_workflow_params(schema, {"rec": {key: []}})
    assert error.value.pointer == "/rec/" + key.replace("/", "~1")
    # Other engines take such keys as plain members
    nfl = make_schema({"rec": {"type": "object"}}, NFL)
    assert to_workflow_params(nfl, {"rec": {key: 1}}) == {"rec": {key: 1}}


@pytest.mark.parametrize("workflow", [{"descriptor_type": "CWL"}, NFL])
def test_two_members_for_one_input_are_rejected(workflow: dict[str, Any]) -> None:
    """Test that a server doesn't validate only one of two members of an input.

    An input renamed with ``x-ga4gh-parameter`` matches its key and its own
    name; with both in a request, one of them would reach the engine
    unchecked.

    Args:
        workflow: The workflow block of the schema.
    """
    schema = make_schema(
        {"a": {"type": "string", "x-ga4gh-parameter": {"name": "x"}}},
        workflow,
    )
    schema["properties"]["inputs"]["additionalProperties"] = False
    # The first member, not a string, would reach the engine unvalidated
    smuggled = {"a": {"nested": ["unchecked"]}, "x": "fine"}

    with pytest.raises(WorkflowParamsError, match="Several members") as error:
        from_workflow_params(schema, smuggled)
    assert error.value.pointer == "/x"
    with pytest.raises(WorkflowParamsError, match="Several members") as error:
        from_workflow_params(schema, {"x": "fine", "a": "other"})
    assert error.value.pointer == "/a"


def test_cwl_loader_directives_in_file_objects() -> None:
    """Test that a directive in a CWL File object of a request is rejected."""
    schema = make_schema({"reads": file_ref()}, {"descriptor_type": "CWL"})
    params = {
        "reads": {
            "class": "File",
            "location": "https://data.example.org/a.bam",
            "$import": "file:///etc/passwd",
        }
    }

    with pytest.raises(WorkflowParamsError, match=r"start with '\$'") as error:
        from_workflow_params(schema, params)
    assert error.value.pointer == "/reads/$import"


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
            "This field",
        ),
        ({"class": "File", "location": 1}, "/reads/location", "must be a string"),
        (
            {"class": "File", "location": "https://e.org/x", "path": "x"},
            "/reads/path",
            "This field",
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


def test_every_binding_of_an_input_is_matched() -> None:
    """Test that a key of any binding of an input is checked as that input."""
    schema = make_schema(
        {
            "a": {
                "anyOf": [
                    {"type": "integer", "x-ga4gh-parameter": {"name": "n1"}},
                    {**file_ref(), "x-ga4gh-parameter": {"name": "n2"}},
                ]
            }
        },
        NFL,
    )
    values = {"a": "https://e.org/x"}

    params = to_workflow_params(schema, values)

    assert params == {"n2": "https://e.org/x"}
    assert from_workflow_params(schema, params) == values
    assert reject(schema, {"n2": "file:///etc/passwd"}).pointer == "/n2"
    # The key of another binding for this value
    assert reject(schema, {"n1": "https://e.org/x"}).pointer == "/n1"


def test_bindings_from_unevaluated_properties() -> None:
    """Test that keys of bindings in ``unevaluatedProperties`` are matched."""
    schema = make_schema({}, NFL)
    schema["properties"]["inputs"] = {
        "type": "object",
        "anyOf": [{"properties": {"a": {"type": "integer"}}}, {"properties": {}}],
        "unevaluatedProperties": {
            **file_ref(),
            "x-ga4gh-parameter": {"name": "bam"},
        },
        "required": ["a"],
    }

    assert to_workflow_params(schema, {"a": "drs://e.org/y"}) == {
        "bam": "drs://e.org/y"
    }
    assert from_workflow_params(schema, {"bam": "drs://e.org/y"}) == {
        "a": "drs://e.org/y"
    }


def test_first_binding_decides_between_inputs() -> None:
    """Test that a key is matched with the input that binds to it first."""
    schema = make_schema(
        {
            "p": {"type": "integer", "x-ga4gh-parameter": {"name": "q"}},
            "q": {"type": "integer", "x-ga4gh-parameter": {"name": "p"}},
        },
        NFL,
    )

    assert from_workflow_params(schema, {"p": 1, "q": 2}) == {"q": 1, "p": 2}


@pytest.mark.parametrize("descriptor_type", ["NFL", "CWL"])
def test_unevaluated_keywords_of_sibling_subschemas(descriptor_type: str) -> None:
    """Test that ``unevaluated*`` don't see what sibling subschemas evaluate.

    Args:
        descriptor_type: Descriptor type of the schema.
    """
    schema = make_schema({}, {"descriptor_type": descriptor_type})
    schema["properties"]["inputs"] = {
        "allOf": [
            {"properties": {"x": {"type": "string"}, "y": {"type": "array"}}},
            {"properties": {"y": True}, "unevaluatedProperties": file_ref()},
            {
                "properties": {
                    "y": {
                        "allOf": [
                            {"prefixItems": [{"type": "string"}]},
                            {"unevaluatedItems": file_ref()},
                        ]
                    }
                }
            },
        ]
    }
    bad = "file:///etc/passwd"
    good = "https://e.org/x"
    cwl = descriptor_type == "CWL"

    def file(value: str) -> Any:
        """Give a file value as ``workflow_params`` take it.

        Args:
            value: The file reference.

        Returns:
            The value, as a CWL ``File`` object for CWL.
        """
        return {"class": "File", "location": value} if cwl else value

    assert reject(schema, {"x": file(bad)}).pointer == ("/x/location" if cwl else "/x")
    assert reject(schema, {"y": [file(bad)]}).pointer == (
        "/y/0/location" if cwl else "/y/0"
    )
    assert from_workflow_params(schema, {"x": file(good), "y": [file(good)]}) == {
        "x": good,
        "y": [good],
    }


def test_nested_unevaluated_keywords_evaluate_everything() -> None:
    """Test that ``unevaluated*`` of an in-place subschema evaluate the member."""
    schema = make_schema(
        {
            "rec": {
                "allOf": [{"unevaluatedProperties": {"type": "string"}}],
                "unevaluatedProperties": file_ref(),
            }
        },
        NFL,
    )

    assert from_workflow_params(schema, {"rec": {"a": "plain"}}) == {
        "rec": {"a": "plain"}
    }


def test_error_message_of_the_first_branch() -> None:
    """Test that the first branch with a message covers a failed ``anyOf``."""
    schema = make_schema(
        {
            "c": {
                "anyOf": [
                    {"enum": [1]},
                    {"enum": [2], "x-ga4gh-error-message": "First"},
                    {"enum": [3], "x-ga4gh-error-message": "Second"},
                ]
            },
            "d": {"oneOf": [{"type": "integer"}, {"type": "number"}]},
            "e": {"anyOf": [{"type": "integer"}, {"type": "boolean"}]},
        },
        NFL,
    )

    assert reject(schema, {"c": 4}).message == "First"
    assert reject(schema, {"e": "x"}).message == (
        "The value fails the keyword 'anyOf' of the schema."
    )
    # Valid against both branches: no branch failed
    assert reject(schema, {"d": 1}).message == (
        "The value fails the keyword 'oneOf' of the schema."
    )


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        ({}, "{} isn't on the allow-list of the deployment."),
        (
            {"schemes": ["https"]},
            "{} isn't one of the schemes of this file reference (https).",
        ),
    ],
)
def test_schemes_of_values_are_named_only_for_clients(
    annotation: dict[str, Any], message: str
) -> None:
    """Test that servers name a scheme only if it is forbidden.

    Args:
        annotation: Keys of ``x-ga4gh-file`` besides ``kind``.
        message: Expected message, with ``{}`` for the scheme.
    """
    schema = make_schema({"reads": file_ref(**annotation)}, NFL)

    server = reject(schema, {"reads": "secrettoken123:x"})
    with pytest.raises(TranslationError) as client:
        to_workflow_params(schema, {"reads": "secrettoken123:x"})

    assert server.message == message.format("The scheme of the value")
    assert client.value.message == message.format("The scheme 'secrettoken123'")
    forbidden = reject(schema, {"reads": "file:///etc/passwd"})
    assert forbidden.message == "File references can't use the scheme 'file'."


def test_deep_nesting_rejects_the_request() -> None:
    """Test that ``workflow_params`` too deep to validate are rejected."""
    schema = make_schema(
        {"a": {"$ref": "#/$defs/n"}},
        NFL,
        **{"$defs": {"n": {"type": "array", "items": {"$ref": "#/$defs/n"}}}},
    )
    nested: list[Any] = []
    for _ in range(sys.getrecursionlimit()):
        nested = [nested]

    error = reject(schema, {"a": nested})

    assert "too deeply nested" in error.message


@pytest.mark.parametrize("value", ["abc\n", "a b"])
def test_patterns_are_ecma_262(value: str) -> None:
    """Test that anchored patterns reject a trailing newline, as clients do.

    Python's ``$`` also matches before a trailing newline; ECMA-262's doesn't.

    Args:
        value: A value that the pattern must reject.
    """
    schema = make_schema(
        {"sample": {"type": "string", "pattern": "^[A-Za-z0-9_]+$"}}, NFL
    )

    with pytest.raises(TranslationError, match="does not match"):
        to_workflow_params(schema, {"sample": value})
    with pytest.raises(WorkflowParamsError, match="keyword .pattern."):
        from_workflow_params(schema, {"sample": value})


def test_unicode_property_escapes_in_patterns() -> None:
    r"""Test patterns that Python's ``re`` can't parse (``\p{L}``)."""
    schema = make_schema({"name": {"type": "string", "pattern": r"^\p{L}+$"}}, NFL)

    assert to_workflow_params(schema, {"name": "äbc"}) == {"name": "äbc"}
    assert from_workflow_params(schema, {"name": "äbc"}) == {"name": "äbc"}
    with pytest.raises(WorkflowParamsError, match="keyword .pattern."):
        from_workflow_params(schema, {"name": "a1"})


def test_pattern_properties_are_ecma_262() -> None:
    r"""Test ``patternProperties`` with ``\p{L}``, also for nested objects."""
    labels = {
        "type": "object",
        "patternProperties": {r"^\p{L}+$": {"type": "integer"}},
        "additionalProperties": False,
    }
    schema = make_schema({"labels": labels}, NFL)

    assert from_workflow_params(schema, {"labels": {"ä": 1}}) == {"labels": {"ä": 1}}
    with pytest.raises(WorkflowParamsError, match="keyword .additionalProperties."):
        from_workflow_params(schema, {"labels": {"1": 1}})


def test_unevaluated_properties_are_ecma_262() -> None:
    r"""Test that ``unevaluatedProperties`` matches names as ECMA-262.

    A name with a trailing newline doesn't match ``^[a-z]+$``, so it is
    unevaluated; ``\p{L}`` works.
    """
    options = {
        "type": "object",
        "patternProperties": {"^[a-z]+$": {"type": "string"}, r"^\p{Lu}$": {}},
        "unevaluatedProperties": False,
    }
    schema = make_schema({"opts": options}, NFL)

    assert to_workflow_params(schema, {"opts": {"abc": "x", "Ä": 1}}) == {
        "opts": {"abc": "x", "Ä": 1}
    }
    with pytest.raises(TranslationError, match="Unevaluated properties"):
        to_workflow_params(schema, {"opts": {"abc\n": "x"}})


@pytest.mark.parametrize(
    "inputs",
    [
        {"x": {"type": "string", "pattern": "("}},
        {
            "x": {
                "type": "object",
                "patternProperties": {"(": True},
                "unevaluatedProperties": False,
            }
        },
    ],
)
def test_invalid_patterns_fail_closed(inputs: dict[str, Any]) -> None:
    """Test that invalid patterns are errors of the schema.

    The ``regex`` format of the meta-schema rejects an invalid pattern of
    ``pattern`` or ``patternProperties`` before any value is matched, as for
    any schema that doesn't comply with the profile.

    Args:
        inputs: Properties of ``inputs`` with such a pattern.
    """
    schema = make_schema(inputs, NFL)
    value = "a" if inputs["x"]["type"] == "string" else {"a": 1}

    with pytest.raises(jsonschema.exceptions.ValidationError, match="regex"):
        to_workflow_params(schema, {"x": value})
    with pytest.raises(jsonschema.exceptions.ValidationError, match="regex"):
        from_workflow_params(schema, {"x": value})


def recursive_schema(keyword: str) -> dict[str, Any]:
    """Build an IO schema with a recursive input: a string or a list of them.

    Args:
        keyword: ``anyOf`` or ``oneOf``.

    Returns:
        The schema.
    """
    return make_schema(
        {"a": {"$ref": "#/$defs/n"}},
        NFL,
        **{
            "$defs": {
                "n": {
                    keyword: [
                        {"type": "string"},
                        {"type": "array", "items": {"$ref": "#/$defs/n"}},
                    ]
                }
            }
        },
    )


def nested_list(depth: int, leaves: int) -> list[Any]:
    """Build a list of strings, nested in lists.

    Args:
        depth: The number of nested lists.
        leaves: The number of strings in the innermost list.

    Returns:
        The value.
    """
    value: list[Any] = ["x"] * leaves
    for _ in range(depth - 1):
        value = [value]
    return value


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
def test_each_subschema_is_validated_once_per_value(
    monkeypatch: pytest.MonkeyPatch, keyword: str
) -> None:
    """Test that the validations don't grow with the depth of the values.

    The branches of ``anyOf`` and ``oneOf`` that apply at each level were
    found by validating the whole subtree again, so that the time grew with
    the size times the depth (issue #86). The test counts validations of
    subschemas instead of timing them (``test_performance.py`` times them).

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        keyword: ``anyOf`` or ``oneOf``.
    """
    leaves = 200
    schema = recursive_schema(keyword)
    original = wes._DESCEND
    counts = {}
    for depth in (1, 2, 40):
        values = {"a": nested_list(depth, leaves)}
        descend = Mock(wraps=original)
        monkeypatch.setattr(wes, "_DESCEND", descend)
        params = to_workflow_params(schema, values)
        assert from_workflow_params(schema, params) == values
        counts[depth] = descend.call_count

    per_level = counts[2] - counts[1]
    # Each list around the strings adds the same few validations (8), not a
    # validation of everything below it
    assert 0 < per_level < leaves
    assert counts[40] - counts[1] == 39 * per_level


def test_errors_deep_in_recursive_values() -> None:
    """Test that a failure deep in a recursive value is found and located."""
    values = nested_list(30, 3)
    leaf = values
    for _ in range(29):
        leaf = leaf[0]
    leaf[1] = 1

    error = reject(recursive_schema("anyOf"), {"a": values})

    assert error.pointer == "/a" + "/0" * 29 + "/1"
    assert error.message == "The value fails the keyword 'anyOf' of the schema."


def dynamic_scope_schema(first: str, second: str, keyword: str) -> dict[str, Any]:
    """Build an IO schema whose subschema ``s`` depends on the dynamic scope.

    ``s`` is valid for a string where ``a`` brings it into scope, and not
    where ``b`` does. The input applies both, in the order given.

    Args:
        first: ``a`` or ``b``.
        second: The other one.
        keyword: ``$dynamicRef``, or ``$ref``, which also resolves through
            the dynamic scope where it points to a ``$dynamicAnchor``.

    Returns:
        The schema.
    """
    anchor = {"$dynamicAnchor": "t"}
    return make_schema(
        {
            "v": {
                "allOf": [
                    {"not": {"not": {"$ref": f"urn:example:{first}"}}},
                    {"not": {"not": {"$ref": f"urn:example:{second}"}}},
                ]
            }
        },
        NFL,
        **{
            "$defs": {
                "s": {
                    "$id": "urn:example:s",
                    "$defs": {"t": anchor},
                    keyword: "#t",
                },
                "a": {
                    "$id": "urn:example:a",
                    "$defs": {"t": {**anchor, "type": "string"}},
                    "$ref": "urn:example:s",
                },
                "b": {
                    "$id": "urn:example:b",
                    "$defs": {"t": {**anchor, "type": "integer"}},
                    "$ref": "urn:example:s",
                },
            }
        },
    )


@pytest.mark.parametrize("keyword", ["$dynamicRef", "$ref"])
@pytest.mark.parametrize(("first", "second"), [("a", "b"), ("b", "a")])
def test_results_of_dynamic_references_are_not_kept(
    first: str, second: str, keyword: str
) -> None:
    """Test that a subschema that resolves dynamically is validated in each scope.

    Keeping the first result of ``s`` would accept the value.

    Args:
        first: The scope that validates ``s`` first.
        second: The other scope.
        keyword: The keyword of the reference in ``s``.
    """
    error = reject(dynamic_scope_schema(first, second, keyword), {"v": "x"})

    assert error.pointer == "/v"


@pytest.mark.parametrize(
    ("schema", "static"),
    [
        ({"$defs": {"n": {"$ref": "#/$defs/n"}}, "items": [{"$ref": "#n"}]}, True),
        ({"properties": {"a": {"$dynamicRef": "#t"}}}, False),
        ({"$defs": {"t": {"$dynamicAnchor": "t"}}}, False),
        ({"anyOf": [{"$ref": "urn:example:s"}]}, False),
        ({"$id": "urn:example:root", "$ref": "#/$defs/n"}, True),
        ({"$ref": "urn:example:s"}, False),
        ({"properties": {"a": {"$id": "urn:example:a"}}}, False),
    ],
)
def test_validity_is_kept_only_for_static_schemas(
    schema: dict[str, Any], static: bool
) -> None:
    """Test which schemas can't depend on the dynamic scope.

    Args:
        schema: The schema.
        static: Whether results can be kept for it.
    """
    assert wes._static(schema) is static


def test_validator_outside_of_a_translation() -> None:
    """Test that the validator works as plain Draft 2020-12 outside of one."""
    schema = {
        "$defs": {"t": {"$dynamicAnchor": "t", "type": "string"}},
        "anyOf": [{"$dynamicRef": "#t"}, {"type": "array"}],
    }
    validator = wes._MemoisingValidator(schema)

    assert validator.is_valid("x")
    assert not validator.is_valid(1)


@pytest.mark.parametrize("values", [{"a": ["x"]}, {"a": [1]}])
def test_validity_is_kept_only_during_a_translation(values: dict[str, Any]) -> None:
    """Test that the validity is dropped after a translation, also a failed one.

    The identities of values are reused once they are gone.

    Args:
        values: The input values, valid or not.
    """
    with contextlib.suppress(WorkflowParamsError):
        from_workflow_params(recursive_schema("anyOf"), values)

    assert wes._VALIDITY.get() is None
