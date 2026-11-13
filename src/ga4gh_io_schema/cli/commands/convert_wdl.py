"""The ``convert wdl`` subcommand: convert a WDL workflow or task."""

import argparse
from pathlib import Path

from ga4gh_io_schema.cli.base import (
    STDIN,
    CliError,
    Command,
    CommandResult,
    ErrorKind,
    read_text,
)
from ga4gh_io_schema.cli.convert import CONVERT, conversion_result
from ga4gh_io_schema.converters import wdl


class WdlCommand(Command):
    """Convert the inputs and outputs of a WDL workflow or task."""

    name = "wdl"
    help = "Convert the inputs and outputs of a WDL workflow or task to an IO schema."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the arguments of the command to its parser.

        Args:
            parser: Parser of the command.
        """
        parser.add_argument(
            "source",
            help="Path to the WDL document, or '-' for standard input.",
        )
        parser.add_argument(
            "--task",
            "-t",
            help=(
                "Convert this task instead of the workflow (needed for a "
                "document without a workflow and with several tasks)."
            ),
        )
        parser.add_argument(
            "--nested-inputs",
            action="store_true",
            help=(
                "Include the optional inputs of calls that the workflow doesn't "
                "set (e.g., 'align.threads'), as hidden parameters."
            ),
        )
        parser.add_argument(
            "--import-path",
            "-p",
            action="append",
            default=[],
            type=Path,
            metavar="DIR",
            help=(
                "Directory to search imports in and read them from, besides "
                "the directory of the document; can be repeated."
            ),
        )

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Convert the document.

        Notes of the conversion go to standard error, or, with ``--json``,
        into the result.

        Args:
            args: Parsed arguments.

        Returns:
            The IO schema.

        Raises:
            CliError: If miniwdl isn't installed, the document can't be read,
                loaded or converted.
        """
        text = read_text(args.source)
        # The checksum covers the bytes; reading text translates line endings
        # Pipes can't be read twice: their checksum is that of the text
        checksum = None
        if args.source != STDIN and Path(args.source).is_file():
            try:
                checksum = wdl.descriptor_checksum(Path(args.source).read_bytes())
            except OSError as exc:
                raise CliError(ErrorKind.IO, f"Can't read - {exc}") from exc
        try:
            conversion = wdl.convert(
                args.source,
                text,
                task=args.task,
                nested_inputs=args.nested_inputs,
                import_paths=args.import_path,
                checksum=checksum,
            )
        except wdl.MissingDependencyError as exc:
            raise CliError(ErrorKind.IO, str(exc)) from exc
        except wdl.ImportReadError as exc:
            raise CliError(ErrorKind.IO, exc.message) from exc
        except wdl.SourceError as exc:
            raise CliError(ErrorKind.VALIDATION, exc.message) from exc
        except wdl.ConversionError as exc:
            raise CliError(ErrorKind.VALIDATION, exc.message, exc.location) from exc
        return conversion_result(conversion, args)


CONVERT.register(WdlCommand())
