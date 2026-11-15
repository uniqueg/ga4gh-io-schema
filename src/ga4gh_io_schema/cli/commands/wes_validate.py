"""The ``wes-validate`` subcommand: check the ``workflow_params`` of a request."""

import argparse
import json
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
    read_json,
)
from ga4gh_io_schema.cli.commands.wes_params import add_translation_arguments
from ga4gh_io_schema.validator import UnresolvableReferenceError, validate_schema
from ga4gh_io_schema.wes import (
    DEFAULT_ALLOWED_SCHEMES,
    TranslationError,
    error_response,
    from_workflow_params,
    get_binding,
)


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
        try:
            values = self._translate(args, schema, params)
        except UnresolvableReferenceError as exc:
            raise CliError(ErrorKind.META_SCHEMA, exc.message) from exc
        except RecursionError as exc:
            raise CliError(
                ErrorKind.IO,
                "Too deeply nested to translate - "
                f"{input_name(args.schema)} or {input_name(args.params)}",
            ) from exc
        except jsonschema.exceptions.ValidationError as exc:
            raise CliError(
                ErrorKind.VALIDATION,
                f"The schema doesn't comply with the GA4GH IO Profile: {exc.message}",
                location=None if exc.json_path == "$" else exc.json_path,
            ) from exc
        except TranslationError as exc:
            raise CliError(
                ErrorKind.VALIDATION,
                exc.message,
                location=exc.pointer if exc.path else None,
                extra={"errorResponse": error_response(exc)},
            ) from exc
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
        # The workflow block is read only from a schema that complies
        validate_schema(schema)
        binding = get_binding(
            schema,
            descriptor_type=args.descriptor_type,
            descriptor_type_version=args.type_version,
            entry_point=args.entry_point,
        )
        return from_workflow_params(
            schema,
            params,
            binding,
            args.allow_scheme or DEFAULT_ALLOWED_SCHEMES,
            args.allow_absolute_paths,
            args.allow_paths,
        )


ROOT.register(WesValidateCommand())
