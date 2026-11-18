"""The ``convert`` group, and parts that its subcommands share.

Each module of a converter in :mod:`ga4gh_io_schema.cli.commands` registers
its command in :data:`CONVERT`, which this module declares once.
"""

import argparse
import functools
import json
import sys

from ga4gh_io_schema.cli.base import ROOT, CommandResult
from ga4gh_io_schema.converters.common import Conversion, Output, notes_as_dicts

#: Help of the ``convert`` group.
CONVERT_HELP = "Convert the parameter descriptions of workflow languages."

#: Group of the ``convert`` subcommands, one per source format.
CONVERT = ROOT.group("convert", CONVERT_HELP)

#: Output options: the option, and the kind and arity of its outputs.
OUTPUT_OPTIONS = {
    "out-file": ("file", False, "a file"),
    "out-files": ("file", True, "a list of files"),
    "out-dir": ("directory", False, "a directory"),
}


def output_argument(value: str, kind: str, many: bool) -> Output:
    """Parse the value of an output option: ``NAME=GLOB``.

    Args:
        value: The value.
        kind: ``file`` or ``directory``.
        many: Whether the output is a list of files.

    Returns:
        The output.

    Raises:
        argparse.ArgumentTypeError: If the name or the glob is empty.
    """
    name, _, glob = value.partition("=")
    if not name or not glob:
        raise argparse.ArgumentTypeError(f"'{value}' isn't NAME=GLOB")
    return Output(name=name, glob=glob, kind=kind, many=many)


def add_output_options(parser: argparse.ArgumentParser, base: str) -> None:
    """Add the options that name file outputs (``--out-file`` and the like).

    The outputs go to ``outputs`` of the parsed arguments, in the order of
    the options.

    Args:
        parser: Parser of the command.
        base: What the globs are relative to (e.g., "the working directory
            of the run").
    """
    for option, (kind, many, what) in OUTPUT_OPTIONS.items():
        parser.add_argument(
            f"--{option}",
            metavar="OUT",
            dest="outputs",
            action="append",
            default=[],
            type=functools.partial(output_argument, kind=kind, many=many),
            help=(
                f"Add an output, OUT is NAME=GLOB: {what} found by GLOB, relative "
                f"to {base} (e.g., results/*.bam). Repeatable."
            ),
        )


def conversion_result(
    conversion: Conversion,
    args: argparse.Namespace,
    *,
    label: str = "Note",
    allow_nan: bool = True,
) -> CommandResult:
    """Report a conversion: the notes, and the IO schema as the result.

    In text mode, the notes go to standard error, one line each, and the
    result is the indented IO schema; with ``--json``, the result holds the
    schema and the notes. Every converter reports this way, so that their
    ``--json`` results have the same shape.

    Args:
        conversion: The IO schema and the notes of the conversion.
        args: Parsed arguments, with ``json``.
        label: Label of the lines of the notes in text mode, e.g.,
            ``Warning``.
        allow_nan: Whether the text of the schema may contain ``NaN`` and
            infinities; if not, such a value is an error (``ValueError``).

    Returns:
        The result of the command.
    """
    text = json.dumps(conversion.schema, indent=2, allow_nan=allow_nan)
    if not args.json:
        for note in conversion.notes:
            print(note.to_text(label), file=sys.stderr)
    return CommandResult(
        text=text,
        data={
            "schema": conversion.schema,
            "notes": notes_as_dicts(conversion.notes),
        },
    )
