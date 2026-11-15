"""The ``wes-validate`` subcommand: check the ``workflow_params`` of a request."""

import argparse
import json
from typing import Any

from ga4gh_io_schema.cli.base import (
    ROOT,
    STDIN,
    Command,
    CommandResult,
    read_json,
)
from ga4gh_io_schema.cli.commands.wes_params import (
    add_translation_arguments,
    binding_from_arguments,
    translation_errors,
)
from ga4gh_io_schema.wes import DEFAULT_ALLOWED_SCHEMES, from_workflow_params


class WesValidateCommand(Command):
    """Translate the ``workflow_params`` of a WES request back, and validate them."""

    name = "wes-validate"
    help = (
        "Translate the workflow_params of a WES run request back into input "
        "values and validate them against an IO schema, as a WES server does."
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
            "--params",
            required=True,
            help=(
                "Path to the workflow_params of the request (a JSON object), or "
                "'-' for standard input."
            ),
        )
        add_translation_arguments(parser)
        parser.add_argument(
            "--allow-paths",
            action="store_true",
            help=(
                "Accept CWL File and Directory objects that give 'path' instead "
                "of 'location'."
            ),
        )
        parser.set_defaults(_parser=parser)

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Translate and validate the ``workflow_params``.

        Args:
            args: Parsed arguments.

        Returns:
            The input values, as JSON.

        Raises:
            CliError: If the schema doesn't comply, if the request is
                rejected (with the WES ``ErrorResponse`` as
                ``errorResponse`` with ``--json``), or if a file can't be
                read.
        """
        parser: argparse.ArgumentParser = args._parser
        if args.schema == STDIN and args.params == STDIN:
            parser.error("only one of --schema and --params can be '-'")
        schema = read_json(args.schema)
        params = read_json(args.params)
        with translation_errors(args.schema, args.params, server=True):
            values = self._translate(args, schema, params)
        return CommandResult(
            text=json.dumps(values, indent=2, ensure_ascii=False), data=values
        )

    @staticmethod
    def _translate(
        args: argparse.Namespace, schema: Any, params: Any
    ) -> dict[str, Any]:
        """Validate the schema, get the binding and translate the parameters.

        Args:
            args: Parsed arguments.
            schema: IO schema.
            params: The ``workflow_params``.

        Returns:
            The input values.

        Raises:
            jsonschema.exceptions.ValidationError: If the schema doesn't
                comply.
            TranslationError: If the binding can't be used, or if the request
                is rejected.
        """
        return from_workflow_params(
            schema,
            params,
            binding_from_arguments(args, schema),
            args.allow_scheme or DEFAULT_ALLOWED_SCHEMES,
            args.allow_absolute_paths,
            args.allow_paths,
        )


ROOT.register(WesValidateCommand())
