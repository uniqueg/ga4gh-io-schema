# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
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
    # Changed to a required positional argument
    parser.add_argument(
        "schema",
        type=Path,
        help="Path to the tool or workflow IO schema to validate.",
    )
    # Changed to an optional override flag
    parser.add_argument(
        "--meta-schema",
        "-m",
        type=Path,
        help="Path to a custom meta-schema file. If omitted, uses the '$schema' property from the target schema.",
    )

    args = parser.parse_args()

    try:
        target_schema = load_json(args.schema)

        meta_schema = None
        schema_dir = None

        if args.meta_schema:
            meta_schema = load_json(args.meta_schema)
            schema_dir = args.meta_schema.parent

        validate_schema(
            target_schema=target_schema, meta_schema=meta_schema, schema_dir=schema_dir
        )
        print(f"Success: '{args.schema}' complies with the GA4GH IO Profile.")
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
