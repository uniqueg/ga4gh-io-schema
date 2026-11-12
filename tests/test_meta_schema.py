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


def _recursive_keywords() -> set[str]:
    """Return the keywords whose values the Draft 2020-12 meta-schema recurses into.

    These are the keywords of the Draft 2020-12 meta-schemas whose schema
    contains a ``$dynamicRef`` to ``#meta``, e.g., ``items`` or ``$defs``.

    Returns:
        The names of the keywords.
    """
    keywords = set()
    for uri, contents in REGISTRY.items():
        if not uri.startswith(DRAFT_2020_12):
            continue
        for name, schema in contents.contents.get("properties", {}).items():
            if any(node.get("$dynamicRef") == "#meta" for node in _walk(schema)):
                keywords.add(name)
    return keywords


def test_subschemas_cover_every_applicator() -> None:
    """Test that the profile's rules reach every kind of subschema.

    Every keyword whose values the Draft 2020-12 meta-schema validates as
    schemas must apply ``$defs/node`` to them as well.
    """
    keywords = _recursive_keywords()
    assert {"items", "properties", "$defs", "contentSchema"} <= keywords
    subschemas = load_profile()["$defs"]["node"]["$defs"]["subschemas"]
    assert keywords <= set(subschemas["properties"])


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
