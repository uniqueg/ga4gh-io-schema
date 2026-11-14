"""The ``convert nextflow`` subcommand: convert an nf-schema file."""

import argparse
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
    read_text,
)
from ga4gh_io_schema.cli.convert import (
    CONVERT,
    add_output_options,
    conversion_result,
)
from ga4gh_io_schema.converters.nextflow import (
    ConversionError,
    SourceError,
    load_schema,
    sample_sheet_paths,
    to_ga4gh,
)
from ga4gh_io_schema.validator import validate_schema


def load_sample_sheets(source: Any, pipeline_dir: Path) -> dict[str, Any]:
    """Read the sample-sheet schemas that an nf-schema file names.

    As nf-schema does, the paths are relative to the directory of the
    pipeline; schemas that aren't there are left out (the conversion notes
    them).

    Args:
        source: The nf-schema file.
        pipeline_dir: Directory of the pipeline.

    Returns:
        The sample-sheet schemas, by the path that the source gives.

    Raises:
        SourceError: If a path leads out of the directory of the pipeline, or
            a schema isn't valid JSON.
        CliError: If a schema can't be read.
    """
    base = pipeline_dir.resolve()
    sheets: dict[str, Any] = {}
    for path in sample_sheet_paths(source):
        file = (base / path).resolve()
        if not file.is_relative_to(base):
            raise SourceError(
                f"The sample-sheet schema '{path}' is outside the directory of "
                f"the pipeline ({pipeline_dir})"
            )
        if file.is_file():
            sheets[path] = load_schema(read_text(file), str(file))
    return sheets


class NextflowCommand(Command):
    """Convert an nf-schema file (``nextflow_schema.json``) to an IO schema."""

    name = "nextflow"
    help = "Convert an nf-schema file (nextflow_schema.json) to an IO schema."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the arguments of the command to its parser.

        Args:
            parser: Parser of the command.
        """
        parser.add_argument(
            "schema",
            help=(
                "Path to the nf-schema file (nextflow_schema.json), or '-' for "
                "standard input."
            ),
        )
        parser.add_argument(
            "--pipeline-dir",
            metavar="DIR",
            type=Path,
            help=(
                "Directory of the pipeline, where the sample-sheet schemas "
                "named by 'schema' are looked for (default: the directory of "
                "the nf-schema file; the working directory for standard input)."
            ),
        )
        parser.add_argument(
            "--directory",
            metavar="NAME",
            action="append",
            default=[],
            help=(
                "Mark this parameter with 'format: path' (a file or a "
                "directory) as a reference to a directory, not a file. "
                "Repeatable."
            ),
        )
        add_output_options(parser, "the output directory (outdir) of the pipeline")

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Convert the schema, and check the result against the profile.

        In text mode, the notes of the conversion go to standard error.

        Args:
            args: Parsed arguments.

        Returns:
            The IO schema; with ``--json``, the schema and the notes.

        Raises:
            CliError: If a file can't be read, the schema can't be converted,
                or the result doesn't comply with the profile.
        """
        pipeline_dir = args.pipeline_dir or (
            Path.cwd() if args.schema == STDIN else Path(args.schema).parent
        )
        try:
            source = load_schema(read_text(args.schema), input_name(args.schema))
            conversion = to_ga4gh(
                source,
                load_sample_sheets(source, pipeline_dir),
                directories=args.directory,
                outputs=args.outputs,
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
        return conversion_result(conversion, args)


CONVERT.register(NextflowCommand())
