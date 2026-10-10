# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""GA4GH IO Schema validation utility.

This module provides core functions to load and validate workflow or tool
IO schemas against the GA4GH IO Profile meta-schema.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema


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


def validate_schema(target_schema: dict[str, Any], meta_schema: dict[str, Any]) -> None:
    """Validate a tool or workflow IO schema against a meta-schema.

    Args:
        target_schema: The JSON schema of the workflow or tool to validate.
        meta_schema: The GA4GH IO Profile meta-schema dictionary.

    Raises:
        jsonschema.exceptions.ValidationError: If the target schema violates the meta-schema rules.
        jsonschema.exceptions.SchemaError: If the provided meta-schema itself is malformed.
    """
    jsonschema.validate(instance=target_schema, schema=meta_schema)
