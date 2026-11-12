"""The ``convert cwl`` subcommand: convert a CWL document to an IO schema."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

from ga4gh_io_schema.cli.base import (
    ROOT,
    STDIN,
    CliError,
    Command,
    CommandResult,
    ErrorKind,
    input_name,
    read_text,
)
from ga4gh_io_schema.validator import validate_schema

#: Help of the ``convert`` group, the same in every converter module.
CONVERT_HELP = "Convert the parameter descriptions of workflow languages to IO schemas."


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
            raise CliError(
                ErrorKind.IO,
                "The CWL converter needs the optional dependency cwl-utils; "
                "install it with: pip install 'ga4gh-io-schema[cwl]'",
            ) from exc

        if args.document == STDIN:
            text = read_text(STDIN)
            # Relative references resolve against the working directory
            uri = (Path.cwd() / "stdin.cwl").as_uri()
        else:
            text = _read_file(Path(args.document))
            uri = Path(args.document).resolve().as_uri()
        parser = cwl.CwlParser(process=args.process)
        try:
            schema = parser.to_ga4gh(parser.parse_string(text, uri))
        except cwl.CwlSyntaxError as exc:
            raise CliError(
                ErrorKind.IO, f"{input_name(args.document)}: {exc.message}"
            ) from exc
        except cwl.CwlConversionError as exc:
            raise CliError(ErrorKind.VALIDATION, exc.message, exc.location) from exc
        _check(schema)

        warnings = cwl.notes_as_dicts(parser.notes)
        if not args.json:
            for warning in warnings:
                print(
                    f"Warning: {warning['message']} (at {warning['location']})",
                    file=sys.stderr,
                )
        output = json.dumps(schema, indent=2)
        return CommandResult(text=output, data={"output": output, "warnings": warnings})


def _read_file(path: Path) -> str:
    """Read a CWL document without translating its line ends.

    :func:`~ga4gh_io_schema.cli.base.read_text` translates them, which would
    change the checksum of the document in ``x-ga4gh-workflow``.

    Args:
        path: Path of the document.

    Returns:
        The text of the document.

    Raises:
        CliError: If the file can't be read or isn't UTF-8, with the messages
            of :func:`~ga4gh_io_schema.cli.base.read_text`.
    """
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError as exc:
        raise CliError(ErrorKind.IO, f"File not found - {exc}") from exc
    except UnicodeDecodeError as exc:
        raise CliError(ErrorKind.IO, f"Not UTF-8 text - {path}: {exc}") from exc
    except OSError as exc:
        raise CliError(ErrorKind.IO, f"Can't read - {exc}") from exc


def _check(schema: dict[str, Any]) -> None:
    """Check that a converted schema complies with the profile.

    Args:
        schema: The converted schema.

    Raises:
        CliError: If it doesn't, which is a fault of the converter.
    """
    try:
        validate_schema(schema)
    except jsonschema.exceptions.ValidationError as exc:
        raise CliError(
            ErrorKind.INTERNAL,
            f"The converted schema doesn't comply with the profile: {exc.message}",
            location=exc.json_path,
        ) from exc


ROOT.group("convert", help=CONVERT_HELP).register(ConvertCwlCommand())
