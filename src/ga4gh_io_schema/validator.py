# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""GA4GH IO Schema validation utility.

This module provides core functions to load and validate workflow or tool
IO schemas against the GA4GH IO Profile meta-schema.
"""

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

#: Schemas shipped inside the installed package (see ``pyproject.toml``).
_PACKAGE_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
#: Schemas of a source checkout, used by editable installs.
_CHECKOUT_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
#: File name of the GA4GH IO Profile meta-schema in the schemas directory.
PROFILE_FILE = "ga4gh-io-profile.schema.json"


class UnresolvableReferenceError(jsonschema.exceptions.ValidationError):
    """A reference of the meta-schema can't be resolved locally.

    A subclass of ``ValidationError``, so that callers that catch validation
    errors also catch it, but a fault of the meta-schema, not of the schema.
    """


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
    Schemas without ``$schema`` are registered as JSON Schema Draft 2020-12.

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
                if isinstance(data, dict) and isinstance(data.get("$id"), str):
                    resource = Resource.from_contents(
                        data, default_specification=DRAFT202012
                    )
                    registry = registry.with_resource(
                        uri=data["$id"], resource=resource
                    )
            # RecursionError: JSON nested too deeply to parse
            except (json.JSONDecodeError, OSError, RecursionError, ValueError):
                continue
    return registry


def validate_schema(
    target_schema: dict[str, Any],
    meta_schema: dict[str, Any] | bool | None = None,
    schema_dir: Path | None = None,
) -> None:
    """Validate a tool or workflow IO schema against a meta-schema.

    By default, the schema is validated against the GA4GH IO Profile
    meta-schema that the package ships, whatever its ``$schema`` names; a
    missing ``$schema``, or one that names another meta-schema, is an error.
    If ``meta_schema`` is given, the schema is validated against it instead,
    and its ``$schema`` must name the ``$id`` of that meta-schema, if it has
    one. References to the shipped schemas and to schemas in ``schema_dir``
    are resolved locally. ``format`` keywords of the meta-schema (e.g.
    ``uri``) are enforced, except ``regex``, because Python can't parse all
    ECMA-262 patterns.

    Args:
        target_schema: The JSON schema of the workflow or tool to validate.
        meta_schema: Optional meta-schema to use instead of the GA4GH IO
            Profile meta-schema.
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
        meta_schema = load_profile()
        name = "the GA4GH IO Profile meta-schema"
    else:
        name = "the meta-schema"

    if not isinstance(target_schema, dict):
        raise jsonschema.exceptions.ValidationError("The schema must be a JSON object.")
    if isinstance(meta_schema, dict) and "$id" in meta_schema:
        _check_schema_keyword(target_schema, meta_schema["$id"], name)

    validator_cls = validator_for(meta_schema)
    validator_cls.check_schema(meta_schema)
    validator = validator_cls(
        meta_schema,
        registry=registry,
        format_checker=_format_checker(validator_cls),
    )
    try:
        validator.validate(target_schema)
    except Unresolvable as exc:
        raise UnresolvableReferenceError(
            f"The meta-schema references '{exc.ref}', which can't be resolved "
            "locally: put it in the directory of the meta-schema."
        ) from exc


def load_profile() -> dict[str, Any]:
    """Load the GA4GH IO Profile meta-schema that the package ships.

    Returns:
        The meta-schema.
    """
    return load_json(get_schemas_dir() / PROFILE_FILE)


def _check_schema_keyword(
    target_schema: dict[str, Any], expected: str, name: str
) -> None:
    """Check that a schema's ``$schema`` names the expected meta-schema.

    The profile's meta-schema checks the value of ``$schema`` (``const``),
    but doesn't require it, because some validators (e.g.,
    @hyperjump/json-schema) remove ``$schema`` before they check a schema
    against its dialect; this check is what rejects a missing ``$schema``.
    It runs first so that a missing or foreign ``$schema`` gets a clear
    message, and it also applies to custom meta-schemas.

    Args:
        target_schema: The JSON schema of the workflow or tool to validate.
        expected: The ``$id`` of the meta-schema.
        name: How to refer to the meta-schema in error messages.

    Raises:
        jsonschema.exceptions.ValidationError: If ``$schema`` is missing or
            names another meta-schema.
    """
    if "$schema" not in target_schema:
        raise jsonschema.exceptions.ValidationError(
            f"The schema lacks a '$schema' property; set it to '{expected}'."
        )
    actual = target_schema["$schema"]
    if actual != expected:
        raise jsonschema.exceptions.ValidationError(
            f"'$schema' is '{actual}', not {name} '{expected}'."
        )


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
    # Copy the draft's own checker: FormatChecker(formats=...) would take the
    # functions from the global registry, which holds other drafts' variants.
    checker = copy.copy(validator_cls.FORMAT_CHECKER)
    checker.checkers = {
        name: check
        for name, check in validator_cls.FORMAT_CHECKER.checkers.items()
        if name != "regex"
    }
    return checker
