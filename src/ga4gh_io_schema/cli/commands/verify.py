"""The ``verify`` subcommand: check the workflow block of a schema."""

import argparse
import sys
from pathlib import Path

from ga4gh_io_schema.cli.base import (
    ROOT,
    STDIN,
    CliError,
    Command,
    CommandResult,
    ErrorKind,
    read_error,
    read_json,
)
from ga4gh_io_schema.workflow import check_workflow

#: Message for a schema whose checksum couldn't be compared.
UNVERIFIED = (
    "The schema is unverified: no checksum of x-ga4gh-workflow could be "
    "compared with the primary descriptor (no checksum in the schema, no "
    "supported algorithm, or no descriptor)."
)


class VerifyCommand(Command):
    """Check ``x-ga4gh-workflow`` of an IO schema against a workflow version."""

    name = "verify"
    help = (
        "Check the workflow block (x-ga4gh-workflow) of an IO schema against "
        "the TRS ids, the descriptor type and the primary descriptor of a "
        "workflow version."
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
            "--trs-tool-id", metavar="ID", help="Id of the tool in TRS."
        )
        parser.add_argument(
            "--trs-version-id", metavar="ID", help="Id of the tool version."
        )
        parser.add_argument(
            "--descriptor-type", metavar="TYPE", help="TRS descriptor type, e.g., WDL."
        )
        parser.add_argument(
            "--descriptor",
            metavar="PATH",
            help=(
                "Path to the primary descriptor, whose bytes are hashed, or "
                "'-' for standard input."
            ),
        )
        parser.add_argument(
            "--file-wrapper",
            metavar="PATH",
            help=(
                "Path to the TRS FileWrapper of the primary descriptor (JSON, "
                "with checksum and content), or '-' for standard input; not "
                "with --descriptor."
            ),
        )
        parser.add_argument(
            "--require-verified",
            action="store_true",
            help=(
                "Fail if no checksum could be compared, not only on a mismatch "
                "(e.g., in the CI of a workflow repository)."
            ),
        )
        parser.set_defaults(_parser=parser)

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Check the workflow block.

        Args:
            args: Parsed arguments.

        Returns:
            Whether the schema is verified, as text or as JSON.

        Raises:
            CliError: If a field mismatches, if the schema is unverified and
                ``--require-verified`` is given (each with the result as
                JSON members with ``--json``), or if a file can't be read.
        """
        parser: argparse.ArgumentParser = args._parser
        if args.descriptor is not None and args.file_wrapper is not None:
            parser.error("--descriptor and --file-wrapper can't be used together")
        inputs = [args.schema, args.descriptor, args.file_wrapper]
        if inputs.count(STDIN) > 1:
            parser.error(
                "only one of --schema, --descriptor and --file-wrapper can be '-'"
            )
        schema = read_json(args.schema)
        if not isinstance(schema, dict):
            raise CliError(ErrorKind.VALIDATION, "The schema isn't a JSON object.")
        wrapper = None if args.file_wrapper is None else read_json(args.file_wrapper)
        if wrapper is not None and not isinstance(wrapper, dict):
            raise CliError(ErrorKind.VALIDATION, "The FileWrapper isn't a JSON object.")
        content = None if args.descriptor is None else _read_bytes(args.descriptor)
        result = check_workflow(
            schema,
            trs_tool_id=args.trs_tool_id,
            trs_version_id=args.trs_version_id,
            descriptor_type=args.descriptor_type,
            descriptor=wrapper,
            content=content,
        )
        if result.mismatches:
            message = " ".join(mismatch.message for mismatch in result.mismatches)
            raise CliError(
                ErrorKind.VALIDATION,
                f"The schema may not match the workflow: {message}",
                extra=result.to_dict(),
            )
        if not result.verified and args.require_verified:
            raise CliError(ErrorKind.VALIDATION, UNVERIFIED, extra=result.to_dict())
        text = (
            f"The schema is verified ({', '.join(result.compared)})."
            if result.verified
            else UNVERIFIED
        )
        return CommandResult(text=text, data=result.to_dict())


def _read_bytes(source: str) -> bytes:
    """Read the bytes of a file or of standard input.

    Args:
        source: Path of the file, or ``-`` for standard input.

    Returns:
        The bytes.

    Raises:
        CliError: If the input can't be read.
    """
    try:
        if source == STDIN:
            if sys.stdin is None:
                raise CliError(ErrorKind.IO, "Can't read - standard input is closed")
            return sys.stdin.buffer.read()
        return Path(source).read_bytes()
    except OSError as exc:
        raise read_error(exc, source) from exc


ROOT.register(VerifyCommand())
