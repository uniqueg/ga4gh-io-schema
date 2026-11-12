"""Building blocks of the command-line interface.

Every subcommand of ``ga4gh-io-schema`` is a :class:`Command` in a
:class:`CommandGroup`. Modules in :mod:`ga4gh_io_schema.cli.commands` add
their commands to :data:`ROOT` (or to a group in it, e.g. ``convert``) when
they are imported; the dispatcher imports all of them, so a new command needs
no change to the dispatcher.
"""

import argparse
import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, ClassVar

#: Input argument that stands for standard input.
STDIN = "-"
#: Value of ``--output`` that stands for standard output (the default).
STDOUT = "-"


class ExitCode(IntEnum):
    """Exit status of the command-line interface (see :data:`EXIT_STATUS`)."""

    SUCCESS = 0
    INVALID = 1
    USAGE = 2
    IO_ERROR = 3
    INTERNAL = 4


#: Meaning of each exit status, for the help and the documentation.
EXIT_STATUS: dict[ExitCode, str] = {
    ExitCode.SUCCESS: "success",
    ExitCode.INVALID: "the input doesn't comply (e.g., a validation error)",
    ExitCode.USAGE: "wrong arguments, or no subcommand",
    ExitCode.IO_ERROR: (
        "a file can't be read or written, or can't be used (e.g., invalid JSON "
        "or a malformed meta-schema)"
    ),
    ExitCode.INTERNAL: "an unexpected error",
}


class ErrorKind(StrEnum):
    """Machine-readable kind of a :class:`CliError`.

    The kind sets the label of the error in text mode and the exit status
    (see :data:`ERROR_KINDS`).
    """

    VALIDATION = "validation"
    IO = "io"
    META_SCHEMA = "meta-schema"
    INTERNAL = "internal"


#: Label in text mode and exit status of each kind of error.
ERROR_KINDS: dict[ErrorKind, tuple[str, ExitCode]] = {
    ErrorKind.VALIDATION: ("Validation Error", ExitCode.INVALID),
    ErrorKind.IO: ("Error", ExitCode.IO_ERROR),
    ErrorKind.META_SCHEMA: ("Meta-schema Error", ExitCode.IO_ERROR),
    ErrorKind.INTERNAL: ("An unexpected error occurred", ExitCode.INTERNAL),
}


class CliError(Exception):
    """Failure of a command, reported on standard error.

    Attributes:
        kind: Kind of the error.
        message: Description of the error.
        location: JSON path of the offending value, if any.
    """

    def __init__(
        self, kind: ErrorKind, message: str, location: str | None = None
    ) -> None:
        """Initialise the error.

        Args:
            kind: Kind of the error.
            message: Description of the error.
            location: JSON path of the offending value, if any.
        """
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.location = location

    @property
    def exit_code(self) -> ExitCode:
        """Exit status of the command, set by the kind of the error."""
        return ERROR_KINDS[self.kind][1]

    def to_text(self) -> str:
        """Render the error as a line of text.

        Returns:
            The label of the kind, the message and, if known, the location.
        """
        location = f" (at {self.location})" if self.location else ""
        return f"{ERROR_KINDS[self.kind][0]}: {self.message}{location}"

    def to_json(self) -> str:
        """Render the error as a JSON object on one line.

        Returns:
            An object with the kind, message, location and exit code.
        """
        return json.dumps(
            {
                "error": {
                    "kind": str(self.kind),
                    "message": self.message,
                    "location": self.location,
                },
                "exitCode": int(self.exit_code),
            }
        )


@dataclass(frozen=True)
class CommandResult:
    """Result of a successful command, written to the output.

    Attributes:
        text: The result in text mode (e.g., a message or a converted file).
        data: The result with ``--json``; if omitted, ``--json`` writes
            ``{"output": text}``.
    """

    text: str
    data: dict[str, Any] | None = None

    def to_json(self) -> str:
        """Render the result as a JSON object on one line.

        Returns:
            ``data``, or ``{"output": text}`` if there's no ``data``.
        """
        return json.dumps(self.data if self.data is not None else {"output": self.text})


class Command(ABC):
    """Subcommand of the command-line interface.

    Attributes:
        name: Name of the subcommand on the command line.
        help: One-line description, shown in the help of the parent command.
    """

    name: ClassVar[str]
    help: ClassVar[str]

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the arguments of the command to its parser.

        The shared options (``--output`` and ``--json``) are already there.

        Args:
            parser: Parser of the command.
        """

    @abstractmethod
    def run(self, args: argparse.Namespace) -> CommandResult:
        """Run the command.

        Args:
            args: Parsed arguments.

        Returns:
            The result to write to the output.

        Raises:
            CliError: If the command fails.
        """


@dataclass
class CommandGroup:
    """Group of subcommands (e.g., ``convert`` with one command per format).

    Attributes:
        name: Name of the group on the command line.
        help: One-line description, shown in the help of the parent command.
        commands: Commands of the group, by name.
        groups: Nested groups, by name.
    """

    name: str
    help: str
    commands: dict[str, Command] = field(default_factory=dict)
    groups: dict[str, "CommandGroup"] = field(default_factory=dict)

    def register(self, command: Command) -> Command:
        """Add a command to the group.

        Args:
            command: Command to add.

        Returns:
            The command, so that the call can be used as an expression.

        Raises:
            TypeError: If the command lacks a ``name`` or ``help``.
            ValueError: If the group already has a command or group of that
                name.
        """
        for attribute in ("name", "help"):
            if not isinstance(getattr(command, attribute, None), str):
                raise TypeError(
                    f"{type(command).__name__} must set the class attribute "
                    f"'{attribute}'."
                )
        self._check_free(command.name)
        self.commands[command.name] = command
        return command

    def group(self, name: str, help: str) -> "CommandGroup":
        """Get a nested group, creating it if needed.

        Modules that add commands to the same group each call this, in any
        order.

        Args:
            name: Name of the group.
            help: One-line description of the group, used if it's created.

        Returns:
            The nested group.

        Raises:
            ValueError: If the group already has a command of that name.
        """
        if name not in self.groups:
            self._check_free(name)
            self.groups[name] = CommandGroup(name=name, help=help)
        return self.groups[name]

    def _check_free(self, name: str) -> None:
        """Check that no command or group of the group has a name.

        Args:
            name: Name to check.

        Raises:
            ValueError: If the name is taken.
        """
        if name in self.commands or name in self.groups:
            raise ValueError(f"'{self.name} {name}' is already registered.")


#: Top-level group: the subcommands of ``ga4gh-io-schema``. Modules add to it
#: only when they're imported; tests build their own groups.
ROOT = CommandGroup(
    name="ga4gh-io-schema",
    help="Tools for the GA4GH IO Profile of JSON Schema.",
)


def input_name(source: str | Path) -> str:
    """Name an input in messages.

    Args:
        source: Path of the input, or the string ``-`` for standard input.

    Returns:
        The path, or ``<stdin>``.
    """
    return "<stdin>" if source == STDIN else str(source)


def read_text(source: str | Path) -> str:
    """Read text from a file or from standard input.

    Args:
        source: Path of the file, or the string ``-`` for standard input (a
            ``Path("-")`` is a file named ``-``).

    Returns:
        The text.

    Raises:
        CliError: If the input can't be read or isn't UTF-8.
    """
    try:
        if isinstance(source, str) and source == STDIN:
            # As UTF-8, like files, whatever the locale
            return sys.stdin.buffer.read().decode("utf-8")
        return Path(source).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CliError(ErrorKind.IO, f"File not found - {exc}") from exc
    except UnicodeDecodeError as exc:
        raise CliError(
            ErrorKind.IO, f"Not UTF-8 text - {input_name(source)}: {exc}"
        ) from exc
    except OSError as exc:
        raise CliError(ErrorKind.IO, f"Can't read - {exc}") from exc


def read_json(source: str | Path) -> Any:
    """Read a JSON document from a file or from standard input.

    Args:
        source: Path of the file, or the string ``-`` for standard input.

    Returns:
        The parsed document.

    Raises:
        CliError: If the input can't be read or isn't valid JSON.
    """
    text = read_text(source)
    try:
        return json.loads(text)
    # RecursionError: too deeply nested
    except (json.JSONDecodeError, RecursionError) as exc:
        raise CliError(
            ErrorKind.IO, f"Invalid JSON - {input_name(source)}: {exc}"
        ) from exc
