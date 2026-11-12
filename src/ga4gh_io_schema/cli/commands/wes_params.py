"""The ``wes-params`` subcommand: translate input values for a WES request."""

import argparse
import json
from collections.abc import Sequence
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
from ga4gh_io_schema.validator import UnresolvableReferenceError, validate_schema
from ga4gh_io_schema.wes import (
    DEFAULT_ALLOWED_SCHEMES,
    DESCRIPTOR_TYPES,
    FORBIDDEN_SCHEMES,
    TranslationError,
    build_run_request,
    get_binding,
    to_workflow_params,
    trs_descriptor_url,
)


def _scheme(value: str) -> str:
    """Parse a scheme of ``--allow-scheme``.

    Args:
        value: The argument.

    Returns:
        The scheme, in lowercase.

    Raises:
        argparse.ArgumentTypeError: If the scheme is forbidden.
    """
    scheme = value.lower()
    if scheme in FORBIDDEN_SCHEMES:
        raise argparse.ArgumentTypeError(f"the scheme '{scheme}' can't be allowed")
    return scheme


class WesParamsCommand(Command):
    """Translate input values into the ``workflow_params`` of a WES request."""

    name = "wes-params"
    help = (
        "Validate input values against an IO schema and translate them into "
        "WES workflow_params (or, with --request, a WES RunRequest)."
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
            "--values",
            required=True,
            help=(
                "Path to the input values (a JSON object, valid against the "
                "inputs of the schema), or '-' for standard input."
            ),
        )
        parser.add_argument(
            "--descriptor-type",
            choices=DESCRIPTOR_TYPES,
            metavar="TYPE",
            help=(
                f"Descriptor type ({', '.join(DESCRIPTOR_TYPES)}), if the schema "
                "has no x-ga4gh-workflow.descriptor_type; must match it otherwise."
            ),
        )
        parser.add_argument(
            "--type-version",
            metavar="VERSION",
            help=(
                "Version of the workflow language (descriptor_type_version, "
                "e.g., from TRS), if the schema has none; must match it "
                "otherwise."
            ),
        )
        parser.add_argument(
            "--entry-point",
            metavar="NAME",
            help=(
                "Entry point of the engine, if the schema has none; must match "
                "it otherwise."
            ),
        )
        parser.add_argument(
            "--allow-scheme",
            action="append",
            type=_scheme,
            metavar="SCHEME",
            help=(
                "URI scheme of the deployment's allow-list for file references; "
                "repeat for several. Default: "
                f"{', '.join(DEFAULT_ALLOWED_SCHEMES)}."
            ),
        )
        parser.add_argument(
            "--allow-absolute-paths",
            action="store_true",
            help=(
                "Allow absolute paths as file references (only for deployments "
                "with a shared file system)."
            ),
        )
        parser.add_argument(
            "--request",
            action="store_true",
            help=(
                "Write a WES RunRequest instead of the workflow_params; needs "
                "--workflow-url or --trs-url."
            ),
        )
        # Not a mutually exclusive group: its usage wouldn't wrap.
        parser.add_argument(
            "--workflow-url",
            metavar="URL",
            help="The workflow_url of the RunRequest.",
        )
        parser.add_argument(
            "--trs-url",
            metavar="URL",
            help=(
                "Base URL of the TRS API (e.g., "
                "https://trs.example.org/ga4gh/trs/v2); the workflow_url is the "
                "plain primary descriptor of the tool version that "
                "x-ga4gh-workflow names."
            ),
        )
        parser.set_defaults(_parser=parser)

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Translate the input values.

        Args:
            args: Parsed arguments.

        Returns:
            The ``workflow_params``, or the run request, as JSON.

        Raises:
            CliError: If the schema doesn't comply, if the values can't be
                translated, or if a file can't be read.
        """
        parser: argparse.ArgumentParser = args._parser
        if args.schema == STDIN and args.values == STDIN:
            parser.error("only one of --schema and --values can be '-'")
        if args.workflow_url and args.trs_url:
            parser.error("--workflow-url and --trs-url exclude each other")
        if args.request and not (args.workflow_url or args.trs_url):
            parser.error("--request needs --workflow-url or --trs-url")
        if not args.request and (args.workflow_url or args.trs_url):
            parser.error("--workflow-url and --trs-url need --request")
        schema = read_json(args.schema)
        values = read_json(args.values)
        allowed = args.allow_scheme or DEFAULT_ALLOWED_SCHEMES
        try:
            result = self._translate(args, schema, values, allowed)
        except UnresolvableReferenceError as exc:
            raise CliError(ErrorKind.META_SCHEMA, exc.message) from exc
        except RecursionError as exc:
            raise CliError(
                ErrorKind.IO,
                f"Too deeply nested to translate - {input_name(args.values)}",
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
                location=exc.json_path if exc.path else None,
            ) from exc
        return CommandResult(
            text=json.dumps(result, indent=2, ensure_ascii=False), data=result
        )

    @staticmethod
    def _translate(
        args: argparse.Namespace,
        schema: Any,
        values: Any,
        allowed: Sequence[str],
    ) -> dict[str, Any]:
        """Validate the schema, get the binding and translate the values.

        Args:
            args: Parsed arguments.
            schema: IO schema.
            values: Input values.
            allowed: URI schemes of the allow-list.

        Returns:
            The ``workflow_params``, or the run request.

        Raises:
            jsonschema.exceptions.ValidationError: If the schema doesn't
                comply.
            TranslationError: If the values can't be translated.
        """
        # The workflow block is read only from a schema that complies
        validate_schema(schema)
        binding = get_binding(
            schema,
            descriptor_type=args.descriptor_type,
            descriptor_type_version=args.type_version,
            entry_point=args.entry_point,
        )
        if not args.request:
            return to_workflow_params(
                schema, values, binding, allowed, args.allow_absolute_paths
            )
        workflow_url = args.workflow_url
        if workflow_url is None:
            block = schema.get("x-ga4gh-workflow", {})
            if "trs_tool_id" not in block or "trs_version_id" not in block:
                raise TranslationError(
                    "A workflow URL from TRS needs x-ga4gh-workflow.trs_tool_id "
                    "and trs_version_id."
                )
            workflow_url = trs_descriptor_url(
                args.trs_url,
                block["trs_tool_id"],
                block["trs_version_id"],
                binding.descriptor_type,
            )
        return build_run_request(
            schema, values, workflow_url, binding, allowed, args.allow_absolute_paths
        )


ROOT.register(WesParamsCommand())
