# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""GA4GH IO Schema validation utility.

This module provides core functions to load and validate workflow or tool
IO schemas against the GA4GH IO Profile meta-schema.
"""

import copy
import functools
import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from ga4gh_io_schema.patterns import is_pattern

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

    The validator of a meta-schema is set up once and reused by later calls:
    validators are cached by the content of the meta-schema and by the state
    of ``schema_dir`` (paths, sizes, times and inodes of its ``*.json``
    files, which are listed on every call), so a meta-schema or a schema
    directory that changes between calls gets a new validator. The shipped
    schemas are read once per process. Schemas attached to the errors raised
    (e.g., ``ValidationError.schema``) are shared with the cache, and are
    copies of ``meta_schema``, not the object passed: don't change them.

    Args:
        target_schema: The JSON schema of the workflow or tool to validate.
        meta_schema: Optional meta-schema to use instead of the GA4GH IO
            Profile meta-schema.
        schema_dir: Optional directory to search for local schema references.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema violates the rules.
        jsonschema.exceptions.SchemaError: If the meta-schema itself is malformed.
    """
    schemas_dir = get_schemas_dir()
    meta: dict[str, Any] | bool
    if meta_schema is None:
        meta = _cached_profile(schemas_dir)
        name = "the GA4GH IO Profile meta-schema"
    else:
        meta = meta_schema
        name = "the meta-schema"

    if not isinstance(target_schema, dict):
        raise jsonschema.exceptions.ValidationError("The schema must be a JSON object.")
    if isinstance(meta, dict) and "$id" in meta:
        _check_schema_keyword(target_schema, meta["$id"], name)

    validator = _get_validator(meta_schema, schemas_dir, schema_dir)
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


@functools.cache
def _cached_profile(schemas_dir: Path) -> dict[str, Any]:
    """Load the GA4GH IO Profile meta-schema once per schemas directory.

    The result is shared between calls; unlike ``load_profile()``, callers
    must not change it.

    Args:
        schemas_dir: The directory that contains the meta-schema.

    Returns:
        The meta-schema.
    """
    return load_json(schemas_dir / PROFILE_FILE)


def _get_validator(
    meta_schema: dict[str, Any] | bool | None,
    schemas_dir: Path,
    schema_dir: Path | None,
) -> Validator:
    """Return the validator of a meta-schema, from the cache if possible.

    Args:
        meta_schema: The meta-schema, or ``None`` for the GA4GH IO Profile.
        schemas_dir: The directory of the shipped schemas.
        schema_dir: Optional directory to search for local schema references.

    Returns:
        A validator for the meta-schema.

    Raises:
        jsonschema.exceptions.SchemaError: If the meta-schema is malformed.
    """
    if not (schema_dir and schema_dir.is_dir()):
        schema_dir = None
    fingerprint = _fingerprint(schema_dir) if schema_dir else ()
    if meta_schema is None:
        return _cached_validator(None, schemas_dir, schema_dir, fingerprint)
    try:
        meta_key = json.dumps(meta_schema)
        # The validator is built from the JSON text; Python objects that JSON
        # changes (e.g., a tuple, or keys that aren't strings) must not be.
        is_json = json.loads(meta_key) == meta_schema
    except (TypeError, ValueError):
        is_json = False
    if not is_json:
        # Not JSON (e.g., a set in an unknown keyword): set up on every call.
        return _build_validator(meta_schema, schemas_dir, schema_dir)
    return _cached_validator(meta_key, schemas_dir, schema_dir, fingerprint)


#: The state of one file: path, size, modification and change time, inode.
_FileState = tuple[str, int, int, int, int]


def _fingerprint(directory: Path) -> tuple[_FileState, ...]:
    """Return the state of the ``*.json`` files of a directory.

    Only the files are listed and their metadata read, not their content;
    a change that keeps path, size, times and inode goes unnoticed. The
    change time and the inode can't be kept by copying tools (e.g.,
    ``cp -p``, ``rsync -a``), unlike the modification time.

    Args:
        directory: The directory to search recursively for ``*.json`` files.

    Returns:
        One entry per file; a file that can't be read has -1 for each value.
    """
    entries = []
    for path in directory.rglob("*.json"):
        try:
            stat = path.stat()
        except OSError:
            entries.append((str(path), -1, -1, -1, -1))
        else:
            entries.append(
                (
                    str(path),
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_ctime_ns,
                    stat.st_ino,
                )
            )
    return tuple(sorted(entries))


@functools.lru_cache(maxsize=32)
def _cached_validator(
    meta_key: str | None,
    schemas_dir: Path,
    schema_dir: Path | None,
    fingerprint: tuple[_FileState, ...],
) -> Validator:
    """Set up the validator of a meta-schema once per meta-schema and directory.

    Args:
        meta_key: The meta-schema as JSON text, or ``None`` for the GA4GH IO
            Profile.
        schemas_dir: The directory of the shipped schemas.
        schema_dir: Optional directory to search for local schema references.
        fingerprint: The state of ``schema_dir`` (see ``_fingerprint()``);
            part of the key of the cache only.

    Returns:
        A validator for the meta-schema.
    """
    meta_schema = (
        _cached_profile(schemas_dir) if meta_key is None else json.loads(meta_key)
    )
    return _build_validator(meta_schema, schemas_dir, schema_dir)


def _build_validator(
    meta_schema: dict[str, Any] | bool,
    schemas_dir: Path,
    schema_dir: Path | None,
) -> Validator:
    """Set up the validator of a meta-schema.

    Args:
        meta_schema: The meta-schema.
        schemas_dir: The directory of the shipped schemas.
        schema_dir: Optional directory to search for local schema references.

    Returns:
        A validator for the meta-schema.

    Raises:
        jsonschema.exceptions.SchemaError: If the meta-schema is malformed.
    """
    # Auto-discover local schemas for offline/local resolution
    search_dirs = [schemas_dir] if schema_dir is None else [schemas_dir, schema_dir]
    registry = build_registry(search_dirs)
    validator_cls = validator_for(meta_schema)
    # jsonschema checks boolean meta-schemas too; the stub of the protocol
    # allows objects only
    validator_cls.check_schema(meta_schema)  # type: ignore[arg-type]
    return validator_cls(
        meta_schema,
        registry=registry,
        format_checker=_format_checker(validator_cls),
    )


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
    r"""Return the format checker of a validator class, with ECMA-262 ``regex``.

    JSON Schema patterns are ECMA-262 regular expressions. The ``regex``
    check of jsonschema uses Python's ``re`` module, which rejects some
    valid patterns (e.g. ``\p{L}``) and accepts some invalid ones (e.g.
    ``\-`` in Unicode mode); this checker uses
    :func:`ga4gh_io_schema.patterns.is_pattern` instead, the engine that
    matches values.

    Args:
        validator_cls: The validator class whose format checks to use.

    Returns:
        A format checker for every format of the class, with ``regex``
        checked as ECMA-262 in Unicode mode.
    """
    # Copy the draft's own checker: FormatChecker(formats=...) would take the
    # functions from the global registry, which holds other drafts' variants.
    checker = copy.copy(validator_cls.FORMAT_CHECKER)
    checker.checkers = {
        **validator_cls.FORMAT_CHECKER.checkers,
        "regex": (is_pattern, ()),
    }
    return checker
