# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Parser converting Nextflow `nf-schema` files to the GA4GH IO Profile."""

from pathlib import Path
from typing import Any

from ga4gh_io_schema.parsers.base import AbstractParser
from ga4gh_io_schema.validator import load_json

GA4GH_META_SCHEMA_URI = "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json"

# nf-schema UI keywords and their GA4GH vocabulary equivalents.
KEYWORD_MAP = {
    "fa_icon": "x-ga4gh-fa-icon",
    "hidden": "x-ga4gh-hidden",
    "errorMessage": "x-ga4gh-error-message",
}

# Engine directives that cannot be honoured by cloud clients (e.g., local file checks).
STRIPPED_KEYWORDS = frozenset({"exists"})

# Keywords whose values map names to subschemas, so their keys are not keywords.
_NAMED_SUBSCHEMAS = frozenset(
    {"properties", "patternProperties", "definitions", "$defs", "dependentSchemas"}
)

# Keywords whose values are instance data and must be copied verbatim.
_DATA_KEYWORDS = frozenset({"const", "default", "enum", "examples"})


class NfSchemaParser(AbstractParser):
    """Convert an `nf-schema` (JSON Schema Draft 7) file to a GA4GH IO Profile."""

    def parse(self, path: Path | str) -> dict[str, Any]:
        """Read a `nextflow_schema.json` file.

        Args:
            path: Path to the `nextflow_schema.json` file.

        Returns:
            The parsed nf-schema.
        """
        return load_json(path)

    def to_ga4gh(self, source: dict[str, Any]) -> dict[str, Any]:
        """Translate an nf-schema into a GA4GH IO Profile schema.

        Pipeline parameters (top-level `properties` and `allOf` groups) are moved
        under `properties.inputs`; parameter groups are kept as root-level `$defs`
        so that their references resolve unchanged.

        Args:
            source: The parsed nf-schema.

        Returns:
            A new GA4GH IO Profile schema; `source` is not modified.
        """
        schema = _convert(source)
        schema.pop("$schema", None)
        if "definitions" in schema:
            schema["$defs"] = schema.pop("definitions")

        inputs: dict[str, Any] = {"type": "object"}
        for keyword in ("allOf", "properties", "required"):
            if keyword in schema:
                inputs[keyword] = schema.pop(keyword)

        result: dict[str, Any] = {"$schema": GA4GH_META_SCHEMA_URI}
        result.update(schema)
        result["type"] = "object"
        result["properties"] = {"inputs": inputs}
        result["required"] = ["inputs"]
        return result


def _convert(node: Any) -> Any:
    """Recursively rename, strip and rewrite nf-schema keywords in a subschema."""
    if isinstance(node, list):
        return [_convert(item) for item in node]
    if not isinstance(node, dict):
        return node

    converted: dict[str, Any] = {}
    for key, value in node.items():
        if key in STRIPPED_KEYWORDS:
            continue
        if key in _DATA_KEYWORDS:
            converted[key] = value
        elif key in _NAMED_SUBSCHEMAS and isinstance(value, dict):
            converted[key] = {name: _convert(sub) for name, sub in value.items()}
        elif key == "$ref" and isinstance(value, str):
            converted[key] = value.replace("#/definitions/", "#/$defs/", 1)
        else:
            converted[KEYWORD_MAP.get(key, key)] = _convert(value)
    return converted
