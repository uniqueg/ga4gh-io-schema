# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""GA4GH IO Schema validation utility.

This module provides core functions to load and validate workflow or tool
IO schemas against the GA4GH IO Profile meta-schema.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema.validators import validator_for
from referencing import Registry, Resource


def load_json(file_path: Path | str) -> dict[str, Any]:
    """Load and parse a JSON file from the filesystem.

    Args:
        file_path: The path to the JSON file to load.

    Returns:
        The parsed JSON data represented as a dictionary.

    Raises:
        FileNotFoundError: If the specified file cannot be found on disk.
        json.JSONDecodeError: If the file contains malformed or invalid JSON data.
    """
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_registry(search_dirs: list[Path]) -> Registry:
    """Recursively discover JSON schemas in directories and register them by $id."""
    registry = Registry()
    for search_dir in search_dirs:
        if not search_dir.exists() or not search_dir.is_dir():
            continue
        for path in search_dir.rglob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "$id" in data:
                    resource = Resource.from_contents(data)
                    registry = registry.with_resource(
                        uri=data["$id"], resource=resource
                    )
            except json.JSONDecodeError, OSError, ValueError:
                continue
    return registry


def validate_schema(
    target_schema: dict[str, Any],
    meta_schema: dict[str, Any] | None = None,
    schema_dir: Path | None = None,
) -> None:
    """Validate a tool or workflow IO schema against a meta-schema.

    If meta_schema is explicitly provided, it forces validation against it.
    Otherwise, the meta-schema is inferred from the target schema's '$schema' property.
    Local vocabulary and extension references are resolved automatically.

    Args:
        target_schema: The JSON schema of the workflow or tool to validate.
        meta_schema: Optional overriding GA4GH IO Profile meta-schema dictionary.
        schema_dir: Optional directory to search for local schema references.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema violates the rules.
        jsonschema.exceptions.SchemaError: If the meta-schema itself is malformed.
    """
    # Auto-discover local schemas for offline/local resolution
    repo_schemas_dir = Path(__file__).parent.parent.parent / "schemas"
    search_dirs = [repo_schemas_dir]
    if schema_dir and schema_dir.exists():
        search_dirs.append(schema_dir)

    registry = build_registry(search_dirs)

    if meta_schema is None:
        if "$schema" not in target_schema:
            raise jsonschema.exceptions.ValidationError(
                "No --meta-schema was provided, and the target schema lacks a '$schema' property."
            )

        validator_cls = validator_for(target_schema)
        # Create a proxy schema that resolves to the target's requested URI using our registry
        meta_schema_instance = {"$ref": target_schema["$schema"]}
    else:
        validator_cls = validator_for(meta_schema)
        validator_cls.check_schema(meta_schema)
        meta_schema_instance = meta_schema

    validator = validator_cls(meta_schema_instance, registry=registry)
    validator.validate(target_schema)
