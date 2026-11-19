"""The ``outputs`` subcommand: normalise the outputs of a WES run."""

import argparse
import json

import jsonschema

from ga4gh_io_schema.cli.base import (
    ROOT,
    CliError,
    Command,
    CommandResult,
    ErrorKind,
    input_name,
    read_json,
)
from ga4gh_io_schema.outputs import NormalisationError, normalise_outputs


class OutputsCommand(Command):
    """Build the normalised outputs object of a WES run."""

    name = "outputs"
    help = (
        "Normalise the outputs of a WES run: key them by the outputs of an IO "
        "schema, validate them, and report what doesn't fit."
    )

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the arguments of the command to its parser.

        Args:
            parser: Parser of the command.
        """
        parser.add_argument(
            "--schema",
            required=True,
            help="Path to the IO schema, or '-' for standard input.",
        )
        parser.add_argument(
            "--run-log",
            required=True,
            help=(
                "Path to the WES RunLog of the run (GET /runs/{run_id}), or '-' "
                "for standard input."
            ),
        )
        parser.add_argument(
            "--output-dir",
            metavar="URI",
            help=(
                "URI of the output directory of the run, under which the server "
                "keeps its files; needed if the server lists files or reports "
                "paths."
            ),
        )
        parser.add_argument(
            "--local-dir",
            metavar="PATH",
            help=(
                "Local path of the output directory, as the engine reports it; "
                "paths and file: URIs under it become URIs under --output-dir."
            ),
        )
        parser.add_argument(
            "--files",
            metavar="PATH",
            help=(
                "Path to a JSON array of the files of the run (paths relative to "
                "the output directory, or URIs under it), if the run log doesn't "
                "list them; replaces its listing."
            ),
        )

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Normalise the outputs.

        Args:
            args: Parsed arguments.

        Returns:
            The normalised outputs object with the report, as JSON.

        Raises:
            CliError: If a file can't be read, the schema doesn't conform, or
                the outputs can't be normalised.
        """
        if args.schema == "-" and args.run_log == "-":
            raise CliError(
                ErrorKind.IO, "Only one of --schema and --run-log can be '-'."
            )
        schema = read_json(args.schema)
        run_log = read_json(args.run_log)
        files = None if args.files is None else read_json(args.files)
        try:
            result = normalise_outputs(
                schema,
                run_log,
                output_dir=args.output_dir,
                local_dir=args.local_dir,
                files=files,
            )
        except NormalisationError as exc:
            raise CliError(ErrorKind.VALIDATION, str(exc)) from exc
        except RecursionError as exc:
            raise CliError(
                ErrorKind.IO,
                "Too deeply nested to normalise - "
                f"{input_name(args.schema)} or {input_name(args.run_log)}",
            ) from exc
        except jsonschema.exceptions.ValidationError as exc:
            location = None if exc.json_path == "$" else exc.json_path
            raise CliError(
                ErrorKind.VALIDATION,
                f"The IO schema doesn't comply: {exc.message}",
                location=location,
            ) from exc
        report = result.to_json()
        return CommandResult(text=json.dumps(report, indent=2), data=report)


ROOT.register(OutputsCommand())
