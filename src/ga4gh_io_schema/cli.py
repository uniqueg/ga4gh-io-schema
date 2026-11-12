# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for the GA4GH IO Schema validator."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import jsonschema

from ga4gh_io_schema.validator import load_json, validate_schema


def main(argv: Sequence[str] | None = None) -> None:
    """Execute the CLI.

    Exits with status 0 if the schema complies with the meta-schema, and with
    status 1 and an error message on standard error otherwise.

    Args:
        argv: Command-line arguments; defaults to those of the process.
    """
    parser = argparse.ArgumentParser(
        description="Validate a workflow/tool IO schema against the GA4GH IO Profile meta-schema."
    )
    parser.add_argument(
        "schema",
        type=Path,
        help="Path to the tool or workflow IO schema to validate.",
    )
    parser.add_argument(
        "--meta-schema",
        "-m",
        type=Path,
        help=(
            "Path to another meta-schema file to validate against. If omitted, "
            "the GA4GH IO Profile meta-schema that the package ships is used."
        ),
    )

    args = parser.parse_args(argv)

    try:
        target_schema = load_json(args.schema)

        meta_schema = None
        schema_dir = None

        if args.meta_schema:
            meta_schema = load_json(args.meta_schema)
            schema_dir = args.meta_schema.parent
            if not isinstance(meta_schema, (dict, bool)):
                raise jsonschema.exceptions.SchemaError(
                    "The meta-schema must be a JSON object or a boolean."
                )

        validate_schema(
            target_schema=target_schema, meta_schema=meta_schema, schema_dir=schema_dir
        )
        if args.meta_schema:
            target = f"the meta-schema '{args.meta_schema}'"
        else:
            target = "the GA4GH IO Profile"
        print(f"Success: '{args.schema}' complies with {target}.")
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {e}", file=sys.stderr)
        sys.exit(1)
    except jsonschema.exceptions.ValidationError as e:
        location = "" if e.json_path == "$" else f" (at {e.json_path})"
        print(f"Validation Error: {e.message}{location}", file=sys.stderr)
        sys.exit(1)
    except jsonschema.exceptions.SchemaError as e:
        print(f"Meta-schema Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
