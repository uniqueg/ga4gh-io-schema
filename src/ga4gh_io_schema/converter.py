# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for converting ecosystem schemas to the GA4GH IO Profile."""

import argparse
import json
import sys
from pathlib import Path

from ga4gh_io_schema.parsers import PARSERS, get_parser


def main(argv: list[str] | None = None) -> None:
    """Execute the CLI.

    Args:
        argv: Command-line arguments; defaults to `sys.argv[1:]`.
    """
    parser = argparse.ArgumentParser(
        description="Convert an ecosystem-specific schema into a GA4GH IO Profile schema."
    )
    parser.add_argument(
        "--format",
        "-f",
        required=True,
        help=f"Source schema format. Supported: {', '.join(sorted(PARSERS))}.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to the source schema (e.g., nextflow_schema.json).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path to write the GA4GH IO Profile schema to. If omitted, prints to stdout.",
    )

    args = parser.parse_args(argv)

    try:
        source_parser = get_parser(args.format)
        result = source_parser.to_ga4gh(source_parser.parse(args.input))
    except NotImplementedError as e:
        parser.error(str(e))
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{args.input}' - {e}", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
