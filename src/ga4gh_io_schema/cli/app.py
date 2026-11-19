"""Dispatcher of the command-line interface ``ga4gh-io-schema``."""

import argparse
import functools
import importlib
import pkgutil
import re
import sys
from collections.abc import Sequence

from ga4gh_io_schema.cli import commands
from ga4gh_io_schema.cli.base import (
    EXIT_STATUS,
    ROOT,
    STDOUT,
    CliError,
    Command,
    CommandGroup,
    CommandResult,
    ErrorKind,
    ExitCode,
)

#: Name of the command, also in the help of the subcommands.
PROG = "ga4gh-io-schema"

_EPILOG = (
    "Exit status: "
    + ", ".join(f"{int(code)} = {meaning}" for code, meaning in EXIT_STATUS.items())
    + "."
)

# ANSI escape sequences, which argparse adds to the help on some terminals
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def load_commands() -> None:
    """Import every module of :mod:`ga4gh_io_schema.cli.commands`.

    Each module adds its commands to :data:`~ga4gh_io_schema.cli.base.ROOT`
    when it's imported; importing a module again has no effect.
    """
    for module in pkgutil.iter_modules(commands.__path__):
        # The names come from the package's own directory, not from input.
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        importlib.import_module(f"{commands.__name__}.{module.name}")


def build_parser(
    root: CommandGroup,
    width: int | None = None,
    parsers: list[argparse.ArgumentParser] | None = None,
) -> argparse.ArgumentParser:
    """Build the argument parser of a group of commands.

    Args:
        root: Group whose commands and nested groups become subcommands.
        width: Width of the help text; by default, that of the terminal.
        parsers: If given, every parser that is built (the parser of
            ``root`` first, then those of its commands and groups, depth
            first) is appended to it.

    Returns:
        The parser of ``root``.
    """
    formatter = functools.partial(argparse.HelpFormatter, width=width)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--output",
        "-o",
        default=STDOUT,
        help="Write the result to this file instead of standard output ('-').",
    )
    shared.add_argument(
        "--json",
        action="store_true",
        help=(
            "Write the result to the output, and errors to standard error, as "
            "JSON objects."
        ),
    )
    parser = argparse.ArgumentParser(
        prog=PROG, description=root.help, epilog=_EPILOG, formatter_class=formatter
    )
    collected = [] if parsers is None else parsers
    collected.append(parser)
    _add_subcommands(parser, root, shared, formatter, collected)
    return parser


def _add_subcommands(
    parser: argparse.ArgumentParser,
    group: CommandGroup,
    shared: argparse.ArgumentParser,
    formatter: functools.partial[argparse.HelpFormatter],
    parsers: list[argparse.ArgumentParser],
) -> None:
    """Add the commands and nested groups of a group to its parser.

    Args:
        parser: Parser of the group.
        group: Group whose commands and nested groups to add.
        shared: Parser with the options that every command has.
        formatter: Help formatter of all parsers.
        parsers: List that every new parser is appended to.
    """
    subparsers = parser.add_subparsers(
        title="commands",
        metavar="COMMAND",
        dest="_subcommand",
        required=True,
    )
    for name in sorted({*group.commands, *group.groups}):
        if name in group.commands:
            command = group.commands[name]
            subparser = subparsers.add_parser(
                name,
                help=command.help,
                description=command.help,
                parents=[shared],
                formatter_class=formatter,
            )
            command.configure(subparser)
            subparser.set_defaults(_command=command)
            parsers.append(subparser)
        else:
            nested = group.groups[name]
            subparser = subparsers.add_parser(
                name,
                help=nested.help,
                description=nested.help,
                formatter_class=formatter,
            )
            parsers.append(subparser)
            _add_subcommands(subparser, nested, shared, formatter, parsers)


def main(argv: Sequence[str] | None = None, root: CommandGroup | None = None) -> int:
    """Run ``ga4gh-io-schema``.

    Writes the result of the command to standard output (or ``--output``),
    and errors to standard error; ``--json`` writes both as JSON objects.

    Args:
        argv: Command-line arguments; defaults to those of the process.
        root: Group of commands to run; defaults to all commands of
            :mod:`ga4gh_io_schema.cli.commands`.

    Returns:
        The exit status (see :class:`~ga4gh_io_schema.cli.base.ExitCode`).
        Wrong arguments, ``--help`` and a missing subcommand exit through
        ``argparse`` instead.
    """
    if root is None:
        load_commands()
        root = ROOT
    args = build_parser(root).parse_args(argv)
    command: Command = args._command
    try:
        _write(command.run(args), args)
    except CliError as exc:
        error = exc
    except Exception as exc:
        error = CliError(ErrorKind.INTERNAL, str(exc))
    else:
        return int(ExitCode.SUCCESS)
    print(error.to_json() if args.json else error.to_text(), file=sys.stderr)
    return int(error.exit_code)


def _write(result: CommandResult, args: argparse.Namespace) -> None:
    """Write the result of a command to its output.

    Args:
        result: Result of the command.
        args: Parsed arguments, with ``output`` and ``json``.

    Raises:
        CliError: If the output file can't be written.
    """
    text = result.to_json() if args.json else result.text
    if args.output == STDOUT:
        print(text)
        return
    try:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(f"{text}\n")
    except OSError as exc:
        raise CliError(ErrorKind.IO, f"Can't write - {exc}") from exc


def render_reference(
    root: CommandGroup | None = None, width: int = 79, level: int = 2
) -> str:
    """Render the help of every command as Markdown.

    The documentation's CLI reference is generated with this function, so
    that it can't drift from the parser.

    Args:
        root: Group whose commands to document; defaults to all commands of
            :mod:`ga4gh_io_schema.cli.commands`.
        width: Width of the help text.
        level: Level of the section headings.

    Returns:
        One section per command (and group), each with its help text.
    """
    if root is None:
        load_commands()
        root = ROOT
    parsers: list[argparse.ArgumentParser] = []
    build_parser(root, width=width, parsers=parsers)
    heading = "#" * level
    sections = []
    for parser in parsers:
        help_text = _ANSI_ESCAPE.sub("", parser.format_help()).rstrip()
        sections.append(f"{heading} `{parser.prog}`\n\n```text\n{help_text}\n```\n")
    return "\n".join(sections)
