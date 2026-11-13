"""Parts that the converters share: notes, errors, results and JSON paths.

Each converter reports the decisions of a conversion as :class:`Note` objects,
whose locations are JSON paths in the notation of the validator
(:func:`json_path`), and fails with a :class:`SourceError` (the source can't
be read) or a :class:`ConversionError` (it can't be converted). The converter
modules import these names, so that they're also available there (e.g.,
``ga4gh_io_schema.converters.wdl.Note``).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

#: Location in a JSON document, as keys and indexes.
Pointer = tuple[str | int, ...]

#: Most values (objects, arrays and scalars) that a source document may hold,
#: with the documents it imports and once its YAML aliases are expanded;
#: bounds the work for documents that aliases blow up (or make cyclic).
MAX_SOURCE_VALUES = 100_000

# Keys that a JSON path can use without brackets: the pattern of the JSON
# paths of jsonschema (``ValidationError.json_path``), so that the locations
# of notes and errors match those that the validator reports.
_PLAIN_KEY = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


class SourceError(ValueError):
    """A source can't be read or parsed.

    Attributes:
        message: Description of the error.
    """

    def __init__(self, message: str) -> None:
        """Initialise the error.

        Args:
            message: Description of the error.
        """
        super().__init__(message)
        self.message = message


class ConversionError(ValueError):
    """A source can't be converted, as it is or with the given options.

    Attributes:
        message: Description of the error.
        location: JSON path of the offending schema in the IO schema, if any.
    """

    def __init__(self, message: str, location: str | None = None) -> None:
        """Initialise the error.

        Args:
            message: Description of the error.
            location: JSON path of the offending schema in the IO schema.
        """
        super().__init__(message)
        self.message = message
        self.location = location


@dataclass(frozen=True)
class Note:
    """Decision of the conversion that the author should know about.

    Attributes:
        message: What the converter did, and why.
        location: JSON path of the schema in the IO schema that it concerns.
    """

    message: str
    location: str

    def to_text(self, label: str = "Note") -> str:
        """Render the note as a line of text.

        Args:
            label: Label of the line.

        Returns:
            The label, the message and the location.
        """
        return f"{label}: {self.message} (at {self.location})"

    def to_dict(self) -> dict[str, str]:
        """Render the note as a JSON object.

        Returns:
            The message and the location.
        """
        return {"message": self.message, "location": self.location}


@dataclass(frozen=True)
class Conversion:
    """Result of a conversion.

    Attributes:
        schema: The IO schema.
        notes: Decisions that the author should check, in the order made.
    """

    schema: dict[str, Any]
    notes: list[Note]


def json_path(pointer: Pointer) -> str:
    """Render a location as a JSON path, as the validator reports locations.

    Args:
        pointer: Keys and indexes from the root of the document.

    Returns:
        The JSON path, e.g. ``$.properties.inputs['x-ga4gh-file']``.
    """
    return child_path("$", *pointer)


def child_path(location: str, *keys: str | int) -> str:
    """Extend a JSON path by keys and indexes, as the validator renders them.

    Args:
        location: The JSON path.
        *keys: Keys and indexes to append.

    Returns:
        The extended path, e.g. ``$.properties['args.py'][0]``.
    """
    for key in keys:
        if isinstance(key, int):
            location += f"[{key}]"
        elif _PLAIN_KEY.match(key):
            location += f".{key}"
        else:
            escaped = key.replace("\\", "\\\\").replace("'", "\\'")
            location += f"['{escaped}']"
    return location


def notes_as_dicts(notes: Iterable[Note]) -> list[dict[str, str]]:
    """Render notes as JSON objects.

    Args:
        notes: The notes.

    Returns:
        One object per note, with ``message`` and ``location``.
    """
    return [note.to_dict() for note in notes]
