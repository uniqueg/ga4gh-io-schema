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
from enum import IntEnum
from pathlib import Path
from typing import Any, ClassVar

#: Input argument that stands for standard input.
STDIN = "-"


class ExitCode(IntEnum):
    """Exit status of the command-line interface.

    Attributes:
        SUCCESS: The command succeeded (e.g., the schema is valid).
        INVALID: The input doesn't comply (e.g., a validation error).
        USAGE: The arguments are wrong (reported by ``argparse``).
        IO_ERROR: A file can't be read or written, or isn't valid JSON, or the
            meta-schema given instead of the profile is malformed.
        INTERNAL: An unexpected error, i.e. a bug.
    """

    SUCCESS = 0
    INVALID = 1
    USAGE = 2
    IO_ERROR = 3
    INTERNAL = 4


class CliError(Exception):
    """Failure of a command, reported on standard error.

    Attributes:
        kind: Machine-readable kind of the error (e.g., ``validation``).
        label: Prefix of the error message in text mode.
        message: Description of the error.
        location: JSON path of the offending value, if any.
        exit_code: Exit status of the command.
    """

    def __init__(
        self,
        kind: str,
        label: str,
        message: str,
        exit_code: ExitCode,
        location: str | None = None,
    ) -> None:
        """Initialise the error.

        Args:
            kind: Machine-readable kind of the error (e.g., ``validation``).
            label: Prefix of the error message in text mode.
            message: Description of the error.
            exit_code: Exit status of the command.
            location: JSON path of the offending value, if any.
        """
        super().__init__(message)
        self.kind = kind
        self.label = label
        self.message = message
        self.exit_code = exit_code
        self.location = location

    def to_text(self) -> str:
        """Render the error as a line of text.

        Returns:
            The label, the message and, if known, the location.
        """
        location = f" (at {self.location})" if self.location else ""
        return f"{self.label}: {self.message}{location}"

    def to_json(self) -> str:
        """Render the error as a JSON object on one line.

        Returns:
            An object with the kind, message, location and exit code.
        """
        return json.dumps(
            {
                "error": {
                    "kind": self.kind,
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
        text: The result in text mode.
        data: The result with ``--json``, serialised as a JSON object.
    """

    text: str
    data: dict[str, Any]


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
            ValueError: If the group already has a command or group of that
                name.
        """
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


#: Top-level group: the subcommands of ``ga4gh-io-schema``.
ROOT = CommandGroup(
    name="ga4gh-io-schema",
    help="Tools for the GA4GH IO Profile of JSON Schema.",
)


def input_name(source: str) -> str:
    """Name an input in messages.

    Args:
        source: Path of the input, or ``-`` for standard input.

    Returns:
        The path, or ``<stdin>``.
    """
    return "<stdin>" if source == STDIN else source


def read_json(source: str) -> Any:
    """Read a JSON document from a file or from standard input.

    Args:
        source: Path of the file, or ``-`` for standard input.

    Returns:
        The parsed document.

    Raises:
        CliError: If the input can't be read or isn't valid JSON.
    """
    try:
        if source == STDIN:
            return json.load(sys.stdin)
        with Path(source).open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise io_error(f"File not found - {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise io_error(f"Invalid JSON - {input_name(source)}: {exc}") from exc
    except OSError as exc:
        raise io_error(f"Can't read - {exc}") from exc


def io_error(message: str) -> CliError:
    """Create the error for a file that can't be read or written.

    Args:
        message: Description of the error.

    Returns:
        The error.
    """
    return CliError(
        kind="io", label="Error", message=message, exit_code=ExitCode.IO_ERROR
    )
