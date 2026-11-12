# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Runner of the conformance suite (``tests/conformance/``) for this package.

The suite is language-neutral: other implementations run the same files
with their own runner (see ``docs/specification/conformance.md``). This
module runs the cases of the conformance class "Validator" against
``validate_schema()``: every schema document in ``valid/`` must be
accepted, and every one in ``invalid/`` rejected.
"""

from pathlib import Path

import jsonschema
import pytest

from ga4gh_io_schema.validator import load_json, validate_schema

SUITE_DIR = Path(__file__).resolve().parent / "conformance"
SCHEMA_DOCUMENTS = SUITE_DIR / "schema-documents"
VALID = sorted((SCHEMA_DOCUMENTS / "valid").glob("*.schema.json"))
INVALID = sorted((SCHEMA_DOCUMENTS / "invalid").glob("*.schema.json"))


def test_suite_has_cases() -> None:
    """Test that the suite has positive and negative schema documents."""
    assert VALID
    assert INVALID


@pytest.mark.parametrize("folder", ["valid", "invalid"])
def test_suite_files_are_schema_documents(folder: str) -> None:
    """Test that the suite holds only schema documents and license files.

    A runner of another implementation picks up ``*.schema.json`` files only,
    so a case with another name would be skipped silently.

    Args:
        folder: Folder of the suite (``valid`` or ``invalid``).
    """
    for path in (SCHEMA_DOCUMENTS / folder).iterdir():
        assert path.name.endswith((".schema.json", ".schema.json.license")), path


@pytest.mark.parametrize("path", VALID, ids=lambda path: path.name)
def test_validator_accepts_valid_case(path: Path) -> None:
    """Test that the validator accepts a positive case of the suite.

    Args:
        path: Schema document that conforms to the profile.
    """
    validate_schema(load_json(path))


@pytest.mark.parametrize("path", INVALID, ids=lambda path: path.name)
def test_validator_rejects_invalid_case(path: Path) -> None:
    """Test that the validator rejects a negative case of the suite.

    Args:
        path: Schema document that doesn't conform to the profile.
    """
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_schema(load_json(path))
