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
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable

#: Schemas shipped inside the installed package (see ``pyproject.toml``).
_PACKAGE_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
#: Schemas of a source checkout, used by editable installs.
_CHECKOUT_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


def get_schemas_dir() -> Path:
    """Return the directory holding the GA4GH IO Profile schemas.

    Installed packages ship the schemas as package data. Editable installs
    from a source checkout fall back to the repository's ``schemas/``
    directory.

    Returns:
        The directory that contains the meta-schema and its vocabularies.
    """
    if _PACKAGE_SCHEMAS_DIR.is_dir():
        return _PACKAGE_SCHEMAS_DIR
    return _CHECKOUT_SCHEMAS_DIR


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
    """Discover JSON schemas in directories and register them by ``$id``.

    Files that can't be read or parsed, or that lack an ``$id``, are skipped.

    Args:
        search_dirs: Directories to search recursively for ``*.json`` files.

    Returns:
        A registry that resolves each discovered schema by its ``$id``.
    """
    registry: Registry = Registry()
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
            except (json.JSONDecodeError, OSError, ValueError):
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
    ``format`` keywords of the meta-schema (e.g. ``uri``) are enforced, except
    ``regex``, because Python can't parse all ECMA-262 patterns.

    Args:
        target_schema: The JSON schema of the workflow or tool to validate.
        meta_schema: Optional overriding GA4GH IO Profile meta-schema dictionary.
        schema_dir: Optional directory to search for local schema references.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema violates the rules.
        jsonschema.exceptions.SchemaError: If the meta-schema itself is malformed.
    """
    # Auto-discover local schemas for offline/local resolution
    search_dirs = [get_schemas_dir()]
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

    validator = validator_cls(
        meta_schema_instance,
        registry=registry,
        format_checker=_format_checker(validator_cls),
    )
    try:
        validator.validate(target_schema)
    except Unresolvable as exc:
        raise jsonschema.exceptions.ValidationError(
            f"Unknown meta-schema or reference '{exc.ref}': name a meta-schema that "
            "the package ships (with its versioned '$id') in '$schema', or pass "
            "--meta-schema."
        ) from exc


def _format_checker(validator_cls: type[Validator]) -> jsonschema.FormatChecker:
    r"""Return the format checker of a validator class, without ``regex``.

    JSON Schema patterns are ECMA-262 regular expressions, which Python's
    ``re`` module, used by the ``regex`` format check, can't always parse
    (e.g. ``\p{L}``).

    Args:
        validator_cls: The validator class whose format checks to use.

    Returns:
        A format checker for every format of the class except ``regex``.
    """
    formats = [
        name for name in validator_cls.FORMAT_CHECKER.checkers if name != "regex"
    ]
    return jsonschema.FormatChecker(formats=formats)
