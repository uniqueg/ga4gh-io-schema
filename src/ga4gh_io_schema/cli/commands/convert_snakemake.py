"""The ``convert snakemake`` subcommand: convert a Snakemake config schema."""

import argparse
import json
import sys

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
from ga4gh_io_schema.converters.snakemake import (
    ConversionError,
    SampleSheet,
    SourceError,
    load_schema,
    to_ga4gh,
)
from ga4gh_io_schema.validator import validate_schema

#: Help of the ``convert`` group. Each converter module gets the group with
#: ``ROOT.group("convert", CONVERT_HELP)`` (get or create), in any order; keep
#: the text the same in every module.
CONVERT_HELP = "Convert the parameter descriptions of workflow languages."


def sample_sheet_argument(value: str) -> tuple[str | None, str]:
    """Parse the value of ``--sample-sheet``: ``[PROPERTY=]PATH``.

    Args:
        value: The value.

    Returns:
        The property (or ``None``) and the path.

    Raises:
        argparse.ArgumentTypeError: If the path is empty or standard input.
    """
    name, sep, path = value.partition("=")
    if not sep or not name or "/" in name:
        name, path = "", value
    if path in ("", STDIN):
        raise argparse.ArgumentTypeError(
            f"'{value}' names no file (standard input is for the config schema)"
        )
    return name or None, path


class SnakemakeCommand(Command):
    """Convert a Snakemake configuration schema to an IO schema."""

    name = "snakemake"
    help = (
        "Convert a Snakemake config schema (and sample-sheet schemas) to an IO schema."
    )

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the arguments of the command to its parser.

        Args:
            parser: Parser of the command.
        """
        parser.add_argument(
            "schema",
            help=(
                "Path to the config schema (YAML or JSON, e.g., "
                "workflow/schemas/config.schema.yaml), or '-' for standard input."
            ),
        )
        # Short metavars: the usage of nested commands is indented far
        parser.add_argument(
            "-s",
            "--sample-sheet",
            metavar="SHEET",
            action="append",
            default=[],
            type=sample_sheet_argument,
            help=(
                "Schema of the rows of a sample sheet, as [PROPERTY=]PATH: the "
                "property of the config that holds the path of the sheet "
                "(default: one of samples, sample_sheet, samplesheet, "
                "sample_table) and the path of the schema. Repeatable."
            ),
        )
        for option, kind in (("file", "a file"), ("directory", "a directory")):
            parser.add_argument(
                f"--{option}",
                metavar="NAME",
                action="append",
                default=[],
                help=(
                    "Mark this property (a dotted path, e.g., ref.fasta, or "
                    f"samples.fq1 for a column) as a reference to {kind}. "
                    "Repeatable."
                ),
            )
        parser.add_argument(
            "--plain",
            metavar="NAME",
            action="append",
            default=[],
            help="Keep this property a plain string. Repeatable.",
        )
        parser.add_argument(
            "--no-guess",
            action="store_true",
            help=(
                "Mark only the properties named with --file, --directory and "
                "--sample-sheet, not those that look like paths."
            ),
        )

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Convert the schema, and check the result against the profile.

        In text mode, the notes of the conversion go to standard error.

        Args:
            args: Parsed arguments.

        Returns:
            The IO schema; with ``--json``, the schema and the notes.

        Raises:
            CliError: If a file can't be read, a schema can't be converted, or
                the result doesn't comply with the profile.
        """
        try:
            config = load_schema(read_text(args.schema), input_name(args.schema))
            sheets = [
                SampleSheet(schema=load_schema(read_text(path), path), property=name)
                for name, path in args.sample_sheet
            ]
            conversion = to_ga4gh(
                config,
                sheets,
                files=args.file,
                directories=args.directory,
                plain=args.plain,
                guess=not args.no_guess,
            )
            validate_schema(conversion.schema)
        except SourceError as exc:
            raise CliError(ErrorKind.IO, exc.message) from exc
        except ConversionError as exc:
            raise CliError(ErrorKind.VALIDATION, exc.message, exc.location) from exc
        except RecursionError as exc:
            raise CliError(ErrorKind.IO, "Too deeply nested to convert") from exc
        except jsonschema.exceptions.ValidationError as exc:
            raise CliError(
                ErrorKind.VALIDATION,
                f"The converted schema doesn't comply with the GA4GH IO Profile: "
                f"{exc.message}",
                location=None if exc.json_path == "$" else exc.json_path,
            ) from exc
        if not args.json:
            for note in conversion.notes:
                print(note.to_text(), file=sys.stderr)
        return CommandResult(
            text=json.dumps(conversion.schema, indent=2),
            data={
                "schema": conversion.schema,
                "notes": [note.to_dict() for note in conversion.notes],
            },
        )


ROOT.group("convert", CONVERT_HELP).register(SnakemakeCommand())
