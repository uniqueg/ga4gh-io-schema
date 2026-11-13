"""The ``convert cwl`` subcommand: convert a CWL document to an IO schema."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

from ga4gh_io_schema.cli.base import (
    STDIN,
    CliError,
    Command,
    CommandResult,
    ErrorKind,
    input_name,
    read_error,
    read_text,
)
from ga4gh_io_schema.cli.convert import CONVERT
from ga4gh_io_schema.converters.common import notes_as_dicts
from ga4gh_io_schema.validator import validate_schema

#: Top-level modules of the optional dependencies of the converter.
OPTIONAL_MODULES = frozenset({"cwl_utils", "schema_salad", "ruamel"})


class ConvertCwlCommand(Command):
    """Convert the inputs and outputs of a CWL document to an IO schema."""

    name = "cwl"
    help = (
        "Convert the inputs and outputs of a CWL document (v1.0 to v1.2) to an "
        "IO schema."
    )

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the arguments of the command to its parser.

        Args:
            parser: Parser of the command.
        """
        parser.add_argument(
            "document",
            help=(
                "Path to the CWL document (YAML or JSON), or '-' for standard input."
            ),
        )
        parser.add_argument(
            "--process",
            "-p",
            help=(
                "ID of the process to convert in a packed document with a "
                "$graph; defaults to 'main', or to the only process of the graph."
            ),
        )
        parser.add_argument(
            "--root",
            type=Path,
            help=(
                "Directory whose files the document may import or include "
                "($import, $include); defaults to the directory of the document "
                "(the working directory for standard input). Other local files "
                "are not read."
            ),
        )

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Convert the document.

        What can't be converted is reported as warnings: on standard error,
        or, with ``--json``, in the ``warnings`` of the result.

        Args:
            args: Parsed arguments.

        Returns:
            The IO schema, as indented JSON.

        Raises:
            CliError: If the document can't be read or converted, or if
                ``cwl-utils`` is not installed.
        """
        try:
            from ga4gh_io_schema import cwl
        except ImportError as exc:
            # Only a missing dependency gets the hint; other faults are bugs
            if (exc.name or "").split(".")[0] not in OPTIONAL_MODULES:
                raise
            raise CliError(
                ErrorKind.IO,
                "The CWL converter needs the optional dependency cwl-utils; "
                "install it with: pip install 'ga4gh-io-schema[cwl]'",
            ) from exc

        root = args.root
        if root is None and args.document == STDIN:
            root = Path.cwd()
        parser = cwl.CwlParser(process=args.process, root=root)
        try:
            if args.document == STDIN:
                # Relative references resolve against the working directory
                process = parser.parse_string(
                    read_text(STDIN), (Path.cwd() / "stdin.cwl").as_uri()
                )
            else:
                process = parser.parse(args.document)
            schema = parser.to_ga4gh(process)
        except (OSError, UnicodeDecodeError) as exc:
            raise read_error(exc, args.document) from exc
        except cwl.CwlSyntaxError as exc:
            raise CliError(
                ErrorKind.IO, f"{input_name(args.document)}: {exc.message}"
            ) from exc
        except cwl.CwlConversionError as exc:
            raise CliError(ErrorKind.VALIDATION, exc.message, exc.location) from exc
        _check(schema)

        if not args.json:
            for note in parser.notes:
                print(note.to_text("Warning"), file=sys.stderr)
        # Defaults are finite (NaN and infinities are left out), so this is
        # strict JSON
        output = json.dumps(schema, indent=2, allow_nan=False)
        return CommandResult(
            text=output,
            data={"output": output, "warnings": notes_as_dicts(parser.notes)},
        )


def _check(schema: dict[str, Any]) -> None:
    """Check that a converted schema complies with the profile.

    Args:
        schema: The converted schema.

    Raises:
        CliError: If it doesn't, which is a fault of the converter.
    """
    try:
        validate_schema(schema)
    except RecursionError as exc:
        raise CliError(
            ErrorKind.VALIDATION, "Types nested too deeply to validate."
        ) from exc
    except jsonschema.exceptions.ValidationError as exc:
        raise CliError(
            ErrorKind.INTERNAL,
            f"The converted schema doesn't comply with the profile: {exc.message}",
            location=exc.json_path,
        ) from exc


CONVERT.register(ConvertCwlCommand())
