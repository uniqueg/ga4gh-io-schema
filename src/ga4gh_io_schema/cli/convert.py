"""The ``convert`` group, and parts that its subcommands share.

Each module of a converter in :mod:`ga4gh_io_schema.cli.commands` registers
its command in :data:`CONVERT`, which this module declares once.
"""

import argparse
import json
import sys

from ga4gh_io_schema.cli.base import ROOT, CommandResult
from ga4gh_io_schema.converters.common import Conversion, notes_as_dicts

#: Help of the ``convert`` group.
CONVERT_HELP = "Convert the parameter descriptions of workflow languages."

#: Group of the ``convert`` subcommands, one per source format.
CONVERT = ROOT.group("convert", CONVERT_HELP)


def conversion_result(
    conversion: Conversion, args: argparse.Namespace
) -> CommandResult:
    """Report a conversion: the notes, and the IO schema as the result.

    In text mode, the notes go to standard error, one line each, and the
    result is the indented IO schema; with ``--json``, the result holds the
    schema and the notes.

    Args:
        conversion: The IO schema and the notes of the conversion.
        args: Parsed arguments, with ``json``.

    Returns:
        The result of the command.
    """
    if not args.json:
        for note in conversion.notes:
            print(note.to_text(), file=sys.stderr)
    return CommandResult(
        text=json.dumps(conversion.schema, indent=2),
        data={
            "schema": conversion.schema,
            "notes": notes_as_dicts(conversion.notes),
        },
    )
