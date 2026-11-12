# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the structure of the meta-schema and its vocabularies.

The rules of ``$defs/node`` reach nested schemas through explicit ``$ref``s
in ``$defs/node/$defs/subschemas``, not through ``$dynamicRef``, so that
validators that support ``$dynamicAnchor`` only at the root of a schema
(e.g., Ajv) enforce them too (see ``tests/js/``).
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema_specifications import REGISTRY

from ga4gh_io_schema.validator import load_json, load_profile

SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMA_FILES = sorted(SCHEMAS_DIR.rglob("*.schema.json"))
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/"


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    """Yield every JSON object in a JSON value, depth first.

    Args:
        value: A JSON value.

    Yields:
        Each object in the value, the value itself included.
    """
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _recursion_paths(
    schema: Any, document: dict[str, Any], path: tuple[str | int, ...] = ()
) -> Iterator[tuple[str | int, ...]]:
    """Yield the paths in a schema to its ``$dynamicRef``s to ``#meta``.

    Local ``$ref``s (e.g., to ``#/$defs/schemaArray``) are followed, without
    adding to the path, so that the path names where the recursion applies.

    Args:
        schema: A schema of a Draft 2020-12 meta-schema, or part of one.
        document: The meta-schema that holds it, to resolve local ``$ref``s.
        path: The path to ``schema``.

    Yields:
        Each path, e.g., ``("items",)`` for the schema of ``allOf``.
    """
    if isinstance(schema, dict):
        if schema.get("$dynamicRef") == "#meta":
            yield path
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = document["$defs"][ref.removeprefix("#/$defs/")]
            yield from _recursion_paths(target, document, path)
        for key, value in schema.items():
            yield from _recursion_paths(value, document, (*path, key))
    elif isinstance(schema, list):
        for index, item in enumerate(schema):
            yield from _recursion_paths(item, document, (*path, index))


def _recursive_keywords() -> dict[str, set[tuple[str | int, ...]]]:
    """Return the keywords whose values the Draft 2020-12 meta-schema recurses into.

    These are the keywords of the Draft 2020-12 meta-schemas whose schema
    has a ``$dynamicRef`` to ``#meta``, e.g., ``items`` or ``$defs``.

    Returns:
        For each keyword, the paths to its ``$dynamicRef``s.
    """
    keywords = {}
    for uri, resource in REGISTRY.items():
        if not uri.startswith(DRAFT_2020_12):
            continue
        document = resource.contents
        for name, schema in document.get("properties", {}).items():
            paths = set(_recursion_paths(schema, document))
            if paths:
                keywords[name] = paths
    return keywords


def _lookup(value: Any, path: tuple[str | int, ...]) -> Any:
    """Return the part of a JSON value at a path.

    Args:
        value: A JSON value.
        path: Keys and indexes.

    Returns:
        The part at the path.
    """
    for key in path:
        value = value[key]
    return value


def test_subschemas_cover_every_applicator() -> None:
    """Test that the profile's rules reach every kind of subschema.

    Every keyword whose values the Draft 2020-12 meta-schema validates as
    schemas must apply ``$defs/node`` (``{"$ref": "#"}``) to them at the
    same place, e.g., to the items of ``allOf`` and the values of
    ``properties``.
    """
    keywords = _recursive_keywords()
    assert {"items", "allOf", "properties", "$defs", "contentSchema"} <= set(keywords)
    subschemas = load_profile()["$defs"]["node"]["$defs"]["subschemas"]
    for name, paths in keywords.items():
        for path in paths:
            assert _lookup(subschemas["properties"][name], path) == {"$ref": "#"}, (
                name,
                path,
            )
    assert subschemas["properties"]["x-ga4gh-tabular-schema"] == {"$ref": "#"}


@pytest.mark.parametrize(
    "path", SCHEMA_FILES, ids=lambda path: str(path.relative_to(SCHEMAS_DIR))
)
def test_schemas_have_no_dynamic_references(path: Path) -> None:
    """Test that no schema of the profile uses dynamic references.

    The keywords have string values; a ``$dynamicRef`` with a schema as its
    value is a property name (e.g., ``"$dynamicRef": false`` in the
    properties that a file reference must not have).

    Args:
        path: A schema file of the profile.
    """
    for node in _walk(load_json(path)):
        assert not isinstance(node.get("$dynamicRef"), str)
        assert not isinstance(node.get("$dynamicAnchor"), str)


def test_profile_declares_a_dialect() -> None:
    """Test that the meta-schema declares its vocabularies (``$vocabulary``).

    Validators that treat ``$schema`` as a dialect (e.g.,
    @hyperjump/json-schema) then accept IO schemas, which name the profile
    in ``$schema``, for the validation of values. The vocabularies of Draft
    2020-12 are required, as in its meta-schema; the profile's own
    vocabulary is optional, so that validators that don't know it still
    process IO schemas (its keywords are annotations of values).
    """
    profile = load_profile()
    vocabulary = profile["$vocabulary"]
    standard = REGISTRY.contents(f"{DRAFT_2020_12}schema")["$vocabulary"]
    own = {uri: required for uri, required in vocabulary.items() if uri not in standard}

    assert {uri: vocabulary.get(uri) for uri in standard} == standard
    assert list(own.values()) == [False]
    base = profile["$id"].rsplit("/", 1)[0]
    assert next(iter(own)).startswith(f"{base}/vocabularies/")
