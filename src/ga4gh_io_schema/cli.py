# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for the GA4GH IO Schema validator."""

import argparse
import sys
from pathlib import Path

import jsonschema

from ga4gh_io_schema.validator import load_json, validate_schema


def main() -> None:
    """Execute the CLI."""
    parser = argparse.ArgumentParser(
        description="Validate a workflow/tool IO schema against the GA4GH IO Profile meta-schema."
    )
    parser.add_argument(
        "--schema",
        type=Path,
        required=True,
        help="Path to the tool or workflow IO schema to validate.",
    )
    parser.add_argument(
        "--meta-schema",
        type=Path,
        required=True,
        help="Path to the GA4GH IO Profile meta-schema file.",
    )

    args = parser.parse_args()

    try:
        target_schema = load_json(args.schema)
        meta_schema = load_json(args.meta_schema)
        validate_schema(target_schema, meta_schema)
        print(f"Success: '{args.schema}' complies with '{args.meta_schema}'.")
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except jsonschema.exceptions.ValidationError as e:
        print(f"Validation Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
