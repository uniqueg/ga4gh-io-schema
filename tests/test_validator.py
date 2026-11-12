# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the GA4GH IO Schema validator module."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from ga4gh_io_schema.validator import (
    build_registry,
    load_json,
    load_profile,
    validate_schema,
)


def test_load_json_success(tmp_path: Path) -> None:
    """Test successfully loading and parsing a valid JSON file.

    Args:
        tmp_path: Pytest fixture providing a temporary directory unique to the test invocation.
    """
    test_file = tmp_path / "valid.json"
    test_file.write_text('{"status": "success"}', encoding="utf-8")

    result = load_json(test_file)
    assert result == {"status": "success"}


def test_load_json_file_not_found() -> None:
    """Test that load_json raises FileNotFoundError for non-existent files."""
    with pytest.raises(FileNotFoundError):
        load_json("non_existent_file.json")


def test_load_json_invalid_json(tmp_path: Path) -> None:
    """Test that load_json raises JSONDecodeError for malformed JSON data.

    Args:
        tmp_path: Pytest fixture providing a temporary directory unique to the test invocation.
    """
    test_file = tmp_path / "invalid.json"
    test_file.write_text("{this is not valid json}", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_json(test_file)


def test_validate_schema_success() -> None:
    """Test validating a correct target schema against a valid meta-schema."""
    meta_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"inputs": {"type": "object"}},
        "required": ["inputs"],
    }
    target_schema: dict[str, Any] = {"inputs": {"sample_id": {"type": "string"}}}

    # Validation should pass silently without raising exceptions
    validate_schema(target_schema, meta_schema)


def test_validate_schema_validation_error() -> None:
    """Test that validate_schema raises ValidationError for a non-compliant target schema."""
    meta_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"inputs": {"type": "object"}},
        "required": ["inputs"],
    }
    target_schema: dict[str, Any] = {"outputs": {"output_vcf": {"type": "string"}}}

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_schema(target_schema, meta_schema)


def test_validate_schema_meta_schema_error() -> None:
    """Test that validate_schema raises SchemaError when the meta-schema itself is invalid."""
    meta_schema: dict[str, Any] = {"type": "invalid_data_type"}
    target_schema: dict[str, Any] = {}

    with pytest.raises(jsonschema.exceptions.SchemaError):
        validate_schema(target_schema, meta_schema)


def test_validate_schema_checks_formats() -> None:
    """Test that ``format`` keywords of the meta-schema are enforced."""
    meta_schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {"x-ga4gh-ontology": {"type": "string", "format": "uri"}},
    }

    validate_schema(
        {"x-ga4gh-ontology": "http://edamontology.org/format_1929"}, meta_schema
    )
    with pytest.raises(jsonschema.exceptions.ValidationError, match="is not a 'uri'"):
        validate_schema({"x-ga4gh-ontology": "not a uri"}, meta_schema)


def test_validate_schema_accepts_ecma_regex_patterns() -> None:
    """Test that ECMA-262 patterns that Python's ``re`` can't parse pass."""
    meta_schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {"pattern": {"type": "string", "format": "regex"}},
    }

    validate_schema({"pattern": "^\\p{L}+$"}, meta_schema)


def test_validate_schema_reports_foreign_meta_schema() -> None:
    """Test that a ``$schema`` naming another meta-schema is reported."""
    target_schema: dict[str, Any] = {
        "$schema": "https://example.org/schemas/unknown-meta-schema.json"
    }

    with pytest.raises(
        jsonschema.exceptions.ValidationError,
        match="not the GA4GH IO Profile meta-schema",
    ):
        validate_schema(target_schema)


def test_validate_schema_keeps_draft_format_checks() -> None:
    """Test that the formats of the meta-schema's draft are used (e.g. ``time``)."""
    meta_schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {"t": {"type": "string", "format": "time"}},
    }

    validate_schema({"t": "12:00:00Z"}, meta_schema)
    with pytest.raises(jsonschema.exceptions.ValidationError, match="is not a 'time'"):
        validate_schema({"t": "12:00:00"}, meta_schema)


def test_validate_schema_uses_profile_whatever_schema_says() -> None:
    """Test that the profile applies even if ``$schema`` names it correctly.

    A schema that names the profile in ``$schema`` but lacks ``inputs`` must
    fail, which shows that validation doesn't stop at the ``$schema`` check.
    """
    target_schema: dict[str, Any] = {
        "$schema": load_profile()["$id"],
        "properties": {"outputs": {}},
    }

    with pytest.raises(jsonschema.exceptions.ValidationError, match="'inputs'"):
        validate_schema(target_schema)


def test_validate_schema_rejects_non_object() -> None:
    """Test that a JSON document that isn't an object is reported."""
    with pytest.raises(jsonschema.exceptions.ValidationError, match="JSON object"):
        validate_schema([])  # type: ignore[arg-type]


def test_validate_schema_checks_schema_of_custom_meta_schema() -> None:
    """Test that ``$schema`` must name a custom meta-schema that has an ``$id``."""
    meta_schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.org/schemas/meta",
    }

    validate_schema({"$schema": "https://example.org/schemas/meta"}, meta_schema)
    with pytest.raises(
        jsonschema.exceptions.ValidationError, match="not the meta-schema"
    ):
        validate_schema({"$schema": "https://example.org/schemas/other"}, meta_schema)


def test_validate_schema_reports_unresolvable_reference_of_meta_schema() -> None:
    """Test that a reference a custom meta-schema can't resolve is reported."""
    meta_schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "https://example.org/schemas/missing",
    }

    with pytest.raises(
        jsonschema.exceptions.ValidationError, match="directory of the meta-schema"
    ):
        validate_schema({}, meta_schema)


def test_build_registry_skips_unusable_files(tmp_path: Path) -> None:
    """Test that missing directories and unusable files are skipped.

    Schemas without ``$schema`` are registered as Draft 2020-12.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
    """
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "no-id.json").write_text('{"type": "string"}', encoding="utf-8")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    (tmp_path / "int-id.json").write_text('{"$id": 5}', encoding="utf-8")
    (tmp_path / "ok.json").write_text(
        '{"$id": "https://example.org/schemas/ok", "type": "string"}',
        encoding="utf-8",
    )

    registry = build_registry([tmp_path / "missing", tmp_path])

    assert list(registry) == ["https://example.org/schemas/ok"]


def test_validate_schema_accepts_boolean_meta_schema() -> None:
    """Test that a boolean meta-schema (valid JSON Schema) is supported."""
    validate_schema({}, True)


def _schema_with_schemes(schemes: list[str]) -> dict[str, Any]:
    """Return an IO schema with one file reference that allows given schemes.

    Args:
        schemes: The value of ``schemes`` of the file reference.

    Returns:
        The IO schema.
    """
    return {
        "$schema": load_profile()["$id"],
        "properties": {
            "inputs": {
                "properties": {
                    "reads": {
                        "type": "string",
                        "x-ga4gh-file": {"kind": "file", "schemes": schemes},
                    }
                }
            }
        },
    }


@pytest.mark.parametrize(
    "scheme",
    [
        "javascript",
        "vbscript",
        "livescript",
        "data",
        "blob",
        "filesystem",
        "file",
        "jar",
        "view-source",
        "about",
        "HTTPS",
        "s3:",
    ],
)
def test_validate_schema_rejects_file_scheme(scheme: str) -> None:
    """Test that browser, local and malformed schemes of file references fail.

    Args:
        scheme: A scheme that the profile rejects.
    """
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_schema(_schema_with_schemes(["https", scheme]))


def test_validate_schema_accepts_file_schemes() -> None:
    """Test that common schemes of file references pass."""
    validate_schema(_schema_with_schemes(["drs", "https", "s3", "gs", "ftp"]))
