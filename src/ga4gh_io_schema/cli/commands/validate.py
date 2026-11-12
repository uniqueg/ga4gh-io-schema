"""The ``validate`` subcommand: check an IO schema against the profile."""

import argparse
from pathlib import Path

import jsonschema

from ga4gh_io_schema.cli.base import (
    ROOT,
    CliError,
    Command,
    CommandResult,
    ExitCode,
    input_name,
    read_json,
)
from ga4gh_io_schema.validator import validate_schema


class ValidateCommand(Command):
    """Validate a tool or workflow IO schema against the GA4GH IO Profile."""

    name = "validate"
    help = "Validate an IO schema against the GA4GH IO Profile meta-schema."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the arguments of the command to its parser.

        Args:
            parser: Parser of the command.
        """
        parser.add_argument(
            "schema",
            help="Path to the tool or workflow IO schema, or '-' for standard input.",
        )
        parser.add_argument(
            "--meta-schema",
            "-m",
            type=Path,
            help=(
                "Path to another meta-schema file to validate against. If "
                "omitted, the GA4GH IO Profile meta-schema that the package "
                "ships is used."
            ),
        )

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Validate the schema.

        Args:
            args: Parsed arguments.

        Returns:
            The confirmation that the schema complies.

        Raises:
            CliError: If the schema doesn't comply, if a file can't be read or
                if the meta-schema is malformed.
        """
        target_schema = read_json(args.schema)
        meta_schema = None
        schema_dir = None
        if args.meta_schema:
            meta_schema = read_json(str(args.meta_schema))
            schema_dir = args.meta_schema.parent
            if not isinstance(meta_schema, (dict, bool)):
                raise _meta_schema_error(
                    "The meta-schema must be a JSON object or a boolean."
                )

        try:
            validate_schema(
                target_schema=target_schema,
                meta_schema=meta_schema,
                schema_dir=schema_dir,
            )
        except jsonschema.exceptions.ValidationError as exc:
            raise CliError(
                kind="validation",
                label="Validation Error",
                message=exc.message,
                exit_code=ExitCode.INVALID,
                location=None if exc.json_path == "$" else exc.json_path,
            ) from exc
        except jsonschema.exceptions.SchemaError as exc:
            raise _meta_schema_error(exc.message) from exc

        schema = input_name(args.schema)
        if args.meta_schema:
            target = f"the meta-schema '{args.meta_schema}'"
        else:
            target = "the GA4GH IO Profile"
        return CommandResult(
            text=f"Success: '{schema}' complies with {target}.",
            data={
                "valid": True,
                "schema": schema,
                "metaSchema": str(args.meta_schema) if args.meta_schema else None,
            },
        )


def _meta_schema_error(message: str) -> CliError:
    """Create the error for a malformed meta-schema.

    Args:
        message: Description of the error.

    Returns:
        The error.
    """
    return CliError(
        kind="meta-schema",
        label="Meta-schema Error",
        message=message,
        exit_code=ExitCode.IO_ERROR,
    )


ROOT.register(ValidateCommand())
