"""Convert Snakemake configuration schemas to IO schemas.

Snakemake workflows validate their configuration with a JSON Schema
(``snakemake.utils.validate``, typically ``workflow/schemas/config.schema.yaml``)
and often their sample sheets with one schema per row. :func:`to_ga4gh`
turns these into an IO schema: the configuration becomes ``inputs``, upgraded
to JSON Schema Draft 2020-12; strings that look like paths become file
references (``x-ga4gh-file``), by documented heuristics that options can
override; each sample-sheet schema becomes the ``x-ga4gh-tabular-schema`` of
the property that holds the sheet. Snakemake schemas don't describe outputs,
so ``outputs`` is left empty.

The conversion reports every decision that changes the meaning of the
schema, or that the author should check, as a :class:`Note`.
"""

import copy
import json
import math
import re
import urllib.parse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from ga4gh_io_schema.validator import load_profile

#: Location in a JSON document, as keys and indexes.
Pointer = tuple[str | int, ...]

#: Most values (objects, arrays and scalars) that a source may hold; bounds
#: the work for documents that YAML aliases blow up (or make cyclic).
MAX_VALUES = 100_000

#: Names of the property of the configuration that holds the sample sheet, if
#: a sample-sheet schema is given without a property.
SHEET_NAMES = ("samples", "sample_sheet", "samplesheet", "sample_table")

#: Last parts of property names that make a string a directory, or a file.
DIRECTORY_WORDS = frozenset({"directory", "folder"})
FILE_WORDS = frozenset(
    {
        "bam",
        "bed",
        "cram",
        "csv",
        "fa",
        "fasta",
        "fastq",
        "file",
        "fna",
        "fq",
        "gff",
        "gtf",
        "json",
        "path",
        "samplesheet",
        "sheet",
        "tsv",
        "vcf",
        "yaml",
        "yml",
    }
)

#: Extensions of default values that make a string a file.
_FILE_EXTENSION = re.compile(
    r"\.(?:bai|bam|bcf|bed|crai|cram|csi|csv|fa|fasta|fastq|fna|fq|gff3?|gtf|"
    r"json|tbi|tsv|txt|vcf|ya?ml)(?:\.(?:bgz|bz2|gz|xz|zst))?$",
    re.IGNORECASE,
)
#: Media types of default values, by extension.
_MEDIA_TYPES = {".csv": "text/csv", ".tsv": "text/tab-separated-values"}
#: Phrases of descriptions that make a string a file or a directory.
_DESCRIPTION_PATH = re.compile(r"\b(?:path|url|uri)s?\s+(?:to|of)\b", re.IGNORECASE)
_DESCRIPTION_DIRECTORY = re.compile(
    r"\b(?:director(?:y|ies)|folders?)\b", re.IGNORECASE
)
_DESCRIPTION_FILE = re.compile(r"\bfiles?\b", re.IGNORECASE)

#: ``$schema`` of the drafts of JSON Schema, with or without ``#``.
_DRAFT_URI = re.compile(
    r"^https?://json-schema\.org/"
    r"(?:draft-0(?P<old>[3467])/schema|draft/(?P<new>2019-09|2020-12)/schema)#?$"
)

# Keywords of the drafts whose values are instance data, copied unchanged.
_DATA = frozenset({"const", "default", "enum", "examples"})
# Keywords whose value is a schema.
_SINGLE = frozenset(
    {
        "additionalProperties",
        "contains",
        "contentSchema",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
        "x-ga4gh-tabular-schema",
    }
)
# Keywords whose value is a list of schemas.
_ARRAYS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
# Keywords whose value maps names to schemas (``properties`` is handled apart).
_MAPS = frozenset({"dependentSchemas", "patternProperties"})
# Keywords that a file reference must not have, and are dropped from it.
_NOT_ON_FILES = ("format", "contentMediaType", "contentEncoding", "contentSchema")
# In-place applicators: a file reference can't have them, so they prevent it.
_APPLICATORS = (
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "$ref",
    "$dynamicRef",
)
# Draft 4 bounds and their exclusive flags.
_EXCLUSIVE = {"maximum": "exclusiveMaximum", "minimum": "exclusiveMinimum"}
# Characters that references keep as they are in the segments of pointers
# (unreserved characters, sub-delimiters, ":" and "@" of RFC 3986).
_POINTER_SAFE = "!$&'()*+,;=:@"
# Command-line flag of each option, where it differs from the option.
_FLAGS = {"sheet": "sample-sheet"}
_JSON_PATH_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


class SourceError(ValueError):
    """A source can't be read: invalid JSON or YAML, or not JSON data.

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
    """A source schema can't be converted, as it is or with the given options.

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

    def to_text(self) -> str:
        """Render the note as a line of text.

        Returns:
            ``Note:``, the message and the location.
        """
        return f"Note: {self.message} (at {self.location})"

    def to_dict(self) -> dict[str, str]:
        """Render the note as a JSON object.

        Returns:
            The message and the location.
        """
        return {"message": self.message, "location": self.location}


@dataclass(frozen=True)
class SampleSheet:
    """Schema of the rows of a sample sheet, and where the sheet is configured.

    Attributes:
        schema: Schema of one row, as ``snakemake.utils.validate`` applies it
            to each row of the sheet.
        property: Dotted path of the string property of the configuration
            that holds the path of the sheet (e.g., ``samples``, or
            ``data.units``); if ``None``, one of :data:`SHEET_NAMES` at the
            top level.
    """

    schema: Any
    property: str | None = None


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
    path = "$"
    for element in pointer:
        if isinstance(element, int):
            path += f"[{element}]"
        elif _JSON_PATH_NAME.match(element):
            path += f".{element}"
        else:
            escaped = element.replace("\\", "\\\\").replace("'", "\\'")
            path += f"['{escaped}']"
    return path


def load_schema(text: str, name: str) -> Any:
    """Parse a schema written in JSON or YAML, as Snakemake reads it.

    Like Snakemake, this tries JSON first, then YAML (with PyYAML, from the
    ``snakemake`` extra). Unlike PyYAML's defaults, dates stay strings, so
    that every schema is JSON data; values that JSON can't represent (e.g.,
    keys that aren't strings) are errors.

    Args:
        text: The schema.
        name: Name of the source in messages (e.g., its path).

    Returns:
        The parsed schema.

    Raises:
        SourceError: If the text isn't valid JSON or YAML, isn't JSON data,
            holds more than :data:`MAX_VALUES` values, or is YAML and PyYAML
            isn't installed.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _load_yaml(text, name)
    _check_json(data, name)
    return data


def _load_yaml(text: str, name: str) -> Any:
    """Parse YAML with the safe loader of PyYAML, without timestamps.

    Args:
        text: The YAML document.
        name: Name of the source in messages.

    Returns:
        The parsed document.

    Raises:
        SourceError: If PyYAML isn't installed or the YAML is invalid.
    """
    try:
        import yaml
    except ImportError as exc:
        raise SourceError(
            f"Reading YAML needs PyYAML - install 'ga4gh-io-schema[snakemake]': {name}"
        ) from exc

    class Loader(yaml.SafeLoader):
        """Safe loader that reads dates and times as strings."""

    Loader.yaml_implicit_resolvers = {
        first: [
            (tag, pattern)
            for tag, pattern in resolvers
            if tag != "tag:yaml.org,2002:timestamp"
        ]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    loader = Loader(text)
    try:
        return loader.get_single_data()
    except yaml.YAMLError as exc:
        raise SourceError(f"Invalid YAML - {name}: {exc}") from exc
    finally:
        loader.dispose()


def _check_json(data: Any, name: str) -> None:
    """Check that a parsed document is JSON data.

    Args:
        data: The parsed document.
        name: Name of the source in messages.

    Raises:
        SourceError: If a key isn't a string, a value isn't JSON (e.g., a
            date, or not a finite number), or there are too many values.
    """
    # Each value comes with a link to its location (the link of its parent and
    # its key), so that deep documents don't copy their paths at every level.
    stack: list[tuple[Any, Any]] = [(data, None)]
    count = 0
    while stack:
        value, link = stack.pop()
        count += 1
        if count > MAX_VALUES:
            raise SourceError(
                f"Too large - {name}: more than {MAX_VALUES} values "
                "(e.g., through YAML aliases)"
            )
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise SourceError(
                        f"Not JSON data - {name}: the key {key!r} isn't a "
                        f"string (at {_link_path(link)})"
                    )
                stack.append((item, (link, key)))
        elif isinstance(value, list):
            stack.extend((item, (link, index)) for index, item in enumerate(value))
        elif isinstance(value, float) and not math.isfinite(value):
            raise SourceError(
                f"Not JSON data - {name}: {value!r} isn't a finite number "
                f"(at {_link_path(link)})"
            )
        elif value is not None and not isinstance(value, (str, int, float)):
            raise SourceError(
                f"Not JSON data - {name}: a value of type "
                f"'{type(value).__name__}' (at {_link_path(link)})"
            )


def _link_path(link: Any) -> str:
    """Render the location of a value of :func:`_check_json` as a JSON path.

    Args:
        link: ``None`` for the root, or the link of the parent and the key.

    Returns:
        The JSON path.
    """
    parts: list[str | int] = []
    while link is not None:
        link, key = link
        parts.append(key)
    return json_path(tuple(reversed(parts)))


def to_ga4gh(
    config_schema: Any,
    sample_sheets: Sequence[SampleSheet] = (),
    *,
    files: Iterable[str] = (),
    directories: Iterable[str] = (),
    plain: Iterable[str] = (),
    guess: bool = True,
) -> Conversion:
    """Convert a Snakemake configuration schema to an IO schema.

    Properties are named by dotted paths of property names from the root of
    the configuration (e.g., ``ref.fasta``); the columns of a sample sheet by
    the path of the sheet's property and the column (e.g., ``samples.fq1``).
    Only properties reached through ``properties`` from a root can be named.

    Args:
        config_schema: The configuration schema (any draft from 4 on).
        sample_sheets: Schemas of the rows of sample sheets.
        files: Properties to mark as file references of kind ``file``.
        directories: Properties to mark as file references of kind
            ``directory``.
        plain: Properties to keep as they are, whatever the heuristics say.
        guess: Whether to mark other strings that look like paths as file
            references (see the converter documentation for the rules).

    Returns:
        The IO schema, valid against the GA4GH IO Profile unless the source
        uses ``x-ga4gh-*`` keywords wrongly, and the notes of the conversion.

    Raises:
        ConversionError: If a schema can't be converted, or the options name
            properties that don't exist or can't be file references.
    """
    return _Converter(files, directories, plain, guess).convert(
        config_schema, list(sample_sheets)
    )


class _Converter:
    """State of one conversion: the options, the notes, the current source."""

    def __init__(
        self,
        files: Iterable[str],
        directories: Iterable[str],
        plain: Iterable[str],
        guess: bool,
    ) -> None:
        """Check and store the options.

        Args:
            files: Properties to mark as files.
            directories: Properties to mark as directories.
            plain: Properties to keep unmarked.
            guess: Whether to apply the heuristics.

        Raises:
            ConversionError: If a property is named by more than one option.
        """
        self.notes: list[Note] = []
        self.guess = guess
        self.options: dict[str, str] = {}
        for option, names in (
            ("file", files),
            ("directory", directories),
            ("plain", plain),
        ):
            for name in names:
                if self.options.get(name, option) != option:
                    raise ConversionError(
                        f"'{name}' is named by both --{self.options[name]} and "
                        f"--{option}."
                    )
                self.options[name] = option
        # Properties that can be named, and their location in the IO schema
        self.seen: dict[str, Pointer] = {}
        # The source that is being converted (the configuration schema, or a
        # sample-sheet schema): its root, its draft, and where its root
        # ends up in the IO schema (and where its definitions end up).
        self.root: Any = None
        self.draft = 2020
        self.prefix: Pointer = ()
        self.defs_prefix: Pointer = ()
        self.embedded = 0

    def note(self, message: str, pointer: Pointer) -> None:
        """Add a note.

        Args:
            message: The note.
            pointer: Location in the IO schema that it concerns.
        """
        self.notes.append(Note(message, json_path(pointer)))

    def convert(self, config: Any, sheets: list[SampleSheet]) -> Conversion:
        """Convert the configuration schema and the sample-sheet schemas.

        Args:
            config: The configuration schema.
            sheets: The sample-sheet schemas.

        Returns:
            The IO schema and the notes.

        Raises:
            ConversionError: If a schema can't be converted.
        """
        if not isinstance(config, dict):
            raise ConversionError("The config schema must be a JSON object.")
        named = self._sheet_properties(config, sheets)
        inputs_at: Pointer = ("properties", "inputs")
        self._begin(config, prefix=inputs_at, defs_prefix=())
        inputs = self._schema(config, inputs_at, "", root=True)
        defs = inputs.pop("$defs", None)
        inputs.setdefault("type", "object")
        in_config = dict(self.seen)
        for name, sheet in named:
            if name in in_config:  # if not, it's reported below
                self._attach(inputs, name, in_config[name], sheet)
        unknown = sorted(name for name in self.options if name not in self.seen)
        if unknown:
            name = unknown[0]
            option = _FLAGS.get(self.options[name], self.options[name])
            raise ConversionError(
                f"No property '{name}' (--{option}) in the config "
                "schema or the sample-sheet schemas; only properties reached "
                "through 'properties' from the root can be named."
            )
        outputs_at: Pointer = ("properties", "outputs")
        self.note(
            "Snakemake config schemas don't describe outputs: 'outputs' is "
            "left empty; add the outputs of the workflow by hand.",
            outputs_at,
        )
        schema: dict[str, Any] = {
            "$schema": load_profile()["$id"],
            # The engine binding; the TRS fields are known only once the
            # workflow is published (see the converter documentation)
            "x-ga4gh-workflow": {"descriptor_type": "SMK"},
            "type": "object",
            "properties": {
                "inputs": inputs,
                "outputs": {"type": "object", "properties": {}},
            },
        }
        if defs is not None:
            schema["$defs"] = defs
        return Conversion(schema=schema, notes=self.notes)

    def _sheet_properties(
        self, config: dict[str, Any], sheets: list[SampleSheet]
    ) -> list[tuple[str, SampleSheet]]:
        """Find the property of each sample sheet, and mark it as a file.

        Args:
            config: The configuration schema.
            sheets: The sample-sheet schemas.

        Returns:
            The property of each sheet, and the sheet.

        Raises:
            ConversionError: If the property of a sheet can't be told, or is
                named by other options or by two sheets.
        """
        named: list[tuple[str, SampleSheet]] = []
        unnamed = [sheet for sheet in sheets if sheet.property is None]
        if len(unnamed) > 1:
            raise ConversionError(
                "Name the property of each sample sheet: --sample-sheet PROPERTY=PATH."
            )
        for sheet in sheets:
            name = sheet.property
            if name is None:
                properties = config.get("properties")
                found = [
                    candidate
                    for candidate in SHEET_NAMES
                    if isinstance(properties, dict) and candidate in properties
                ]
                if len(found) != 1:
                    raise ConversionError(
                        "Can't tell which property of the config schema holds "
                        f"the sample sheet (candidates: {', '.join(found) or 'none'}"
                        "); name it: --sample-sheet PROPERTY=PATH."
                    )
                name = found[0]
            option = self.options.get(name)
            if option == "sheet":
                raise ConversionError(f"Two sample sheets for '{name}'.")
            if option is not None and option != "file":
                raise ConversionError(
                    f"'{name}' holds a sample sheet, and is named by --{option}."
                )
            self.options[name] = "sheet"
            named.append((name, sheet))
        return named

    def _attach(
        self, inputs: dict[str, Any], name: str, pointer: Pointer, sheet: SampleSheet
    ) -> None:
        """Convert a sample-sheet schema into the tabular hint of its property.

        Args:
            inputs: The converted inputs.
            name: Dotted path of the property of the sheet.
            pointer: Location of the property in the IO schema.
            sheet: The sample-sheet schema.

        Raises:
            ConversionError: If the property isn't a file, or has a tabular
                hint already, or the schema can't be converted.
        """
        node: Any = inputs
        for part in pointer[2:]:  # from the inputs
            node = node[part]
        reference = node.get("x-ga4gh-file")
        if not isinstance(reference, dict) or reference.get("kind") != "file":
            raise ConversionError(
                f"'{name}' holds a sample sheet, but isn't a file reference.",
                json_path(pointer),
            )
        if "x-ga4gh-tabular-schema" in node:
            raise ConversionError(
                f"'{name}' has an 'x-ga4gh-tabular-schema' already.",
                json_path(pointer),
            )
        items_at: Pointer = (*pointer, "x-ga4gh-tabular-schema", "items")
        self._begin(sheet.schema, prefix=items_at, defs_prefix=items_at)
        items = self._schema(sheet.schema, items_at, name, root=True)
        node["x-ga4gh-tabular-schema"] = {"type": "array", "items": items}
        self.note(
            "The sample-sheet schema is the experimental tabular hint of "
            f"'{name}': an array with one item per row.",
            (*pointer, "x-ga4gh-tabular-schema"),
        )

    def _begin(self, root: Any, prefix: Pointer, defs_prefix: Pointer) -> None:
        """Start the conversion of a source.

        Args:
            root: Root schema of the source.
            prefix: Location of the root in the IO schema.
            defs_prefix: Location of the ``$defs`` of the root in the IO
                schema.

        Raises:
            ConversionError: If the source is a Draft 3 schema.
        """
        self.root = root
        self.prefix = prefix
        self.defs_prefix = defs_prefix
        self.embedded = 0
        self.draft = 2020
        if not isinstance(root, dict):
            return
        uri = root.get("$schema")
        match = _DRAFT_URI.match(uri) if isinstance(uri, str) else None
        if match is None:
            shown = "no '$schema'" if uri is None else f"the '$schema' {uri!r}"
            self.note(
                f"The source has {shown}, which names no draft of JSON Schema: "
                "read as Draft 2020-12.",
                prefix,
            )
            return
        if match["old"] == "3":
            raise ConversionError(
                "Draft 3 schemas can't be converted; upgrade the schema to Draft "
                "4 or later first.",
                json_path(prefix),
            )
        self.draft = int(match["old"] or match["new"][:4])

    def _schema(
        self, node: Any, pointer: Pointer, name: str | None, root: bool = False
    ) -> Any:
        """Convert a schema to Draft 2020-12.

        Args:
            node: The schema in the source.
            pointer: Location of the converted schema in the IO schema.
            name: Dotted path of the property whose schema it is, ``""`` for
                a root, or ``None`` if it can't be named.
            root: Whether it's the root of the source.

        Returns:
            The converted schema.

        Raises:
            ConversionError: If the schema isn't an object or a boolean.
        """
        if isinstance(node, bool):
            return node
        if not isinstance(node, dict):
            raise ConversionError(
                "Not a schema: an object or a boolean was expected.",
                json_path(pointer),
            )
        identifier = node.get("id" if self.draft == 4 else "$id")
        boundary = (
            not root and isinstance(identifier, str) and not identifier.startswith("#")
        )
        if boundary:
            # An embedded schema resource: its references are relative to
            # its own identifier, so they are kept as they are.
            self.embedded += 1
        try:
            return self._keywords(node, pointer, name, root)
        finally:
            if boundary:
                self.embedded -= 1

    def _keywords(
        self, node: dict[str, Any], pointer: Pointer, name: str | None, root: bool
    ) -> dict[str, Any]:
        """Convert the keywords of a schema to Draft 2020-12.

        Args:
            node: The schema in the source.
            pointer: Location of the converted schema in the IO schema.
            name: Dotted path of the property, ``""`` or ``None`` (see
                :meth:`_schema`).
            root: Whether it's the root of the source.

        Returns:
            The converted schema.
        """
        result: dict[str, Any] = {}
        tuple_items = isinstance(node.get("items"), list)
        id_keyword = "id" if self.draft == 4 else "$id"
        for key, value in node.items():
            at = (*pointer, key)
            if root and key == "$schema":
                continue
            if root and key == id_keyword and isinstance(value, str):
                if not value.startswith("#"):
                    self.note(
                        f"'{key}' of the source ('{value}') dropped: it names "
                        "the source, not the IO schema.",
                        pointer,
                    )
                    continue
            if key in _DATA:
                result[key] = copy.deepcopy(value)
            elif key == "$ref":
                result[key] = self._ref(value, pointer)
            elif key in ("definitions", "$defs") and isinstance(value, dict):
                defs_at = (*self.defs_prefix, "$defs") if root else (*pointer, "$defs")
                self._merge(result, "$defs", self._map(value, defs_at), pointer)
            elif key == "dependencies" and isinstance(value, dict):
                self._dependencies(result, value, pointer)
            elif key == "items" and tuple_items:
                result["prefixItems"] = self._list(value, (*pointer, "prefixItems"))
            elif key == "additionalItems":
                if tuple_items:
                    result["items"] = self._schema(value, (*pointer, "items"), None)
                else:
                    self.note(
                        "'additionalItems' dropped: without a list in 'items', "
                        "it has no effect.",
                        pointer,
                    )
            elif key in _EXCLUSIVE.values() and isinstance(value, bool):
                self._exclusive(result, node, key, pointer)
            elif key in _EXCLUSIVE and node.get(_EXCLUSIVE[key]) is True:
                continue  # replaced by the exclusive bound
            elif key == "properties" and isinstance(value, dict):
                result[key] = {
                    child: self._property(
                        child, sub, (*at, child), _child_name(name, child)
                    )
                    for child, sub in value.items()
                }
            elif key in _MAPS and isinstance(value, dict):
                # Merged: "dependencies" may have added to "dependentSchemas"
                self._merge(result, key, self._map(value, at), pointer)
            elif key == "dependentRequired" and isinstance(value, dict):
                self._merge(result, key, copy.deepcopy(value), pointer)
            elif key in _ARRAYS and isinstance(value, list):
                result[key] = self._list(value, at)
            elif key in _SINGLE:
                result[key] = self._schema(value, at, None)
            elif key == id_keyword and isinstance(value, str) and self.draft < 2019:
                # Draft 4 "id", and fragments of "$id" (Drafts 6 and 7), which
                # are plain-name anchors
                if value.startswith("#"):
                    result["$anchor"] = value[1:]
                else:
                    result["$id"] = value
            elif key in ("$recursiveRef", "$recursiveAnchor"):
                self.note(
                    f"'{key}' (Draft 2019-09) kept, but Draft 2020-12 ignores "
                    "it; replace it with '$dynamicRef' and '$dynamicAnchor'.",
                    pointer,
                )
                result[key] = copy.deepcopy(value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _map(self, value: dict[str, Any], pointer: Pointer) -> dict[str, Any]:
        """Convert the schemas of a keyword that maps names to schemas.

        Args:
            value: Value of the keyword.
            pointer: Location of the keyword in the IO schema.

        Returns:
            The converted schemas, by name.
        """
        return {
            name: self._schema(sub, (*pointer, name), None)
            for name, sub in value.items()
        }

    def _list(self, value: list[Any], pointer: Pointer) -> list[Any]:
        """Convert the schemas of a keyword whose value is a list of schemas.

        Args:
            value: Value of the keyword.
            pointer: Location of the keyword in the IO schema.

        Returns:
            The converted schemas.
        """
        return [
            self._schema(sub, (*pointer, index), None)
            for index, sub in enumerate(value)
        ]

    def _merge(
        self,
        result: dict[str, Any],
        key: str,
        entries: dict[str, Any],
        pointer: Pointer,
    ) -> None:
        """Merge entries into a keyword of a converted schema.

        Args:
            result: The converted schema.
            key: The keyword (e.g., ``$defs``).
            entries: Entries to add.
            pointer: Location of the schema in the IO schema.

        Raises:
            ConversionError: If an entry exists already (e.g., in both
                ``definitions`` and ``$defs``).
        """
        target = result.setdefault(key, {})
        for name, entry in entries.items():
            if name in target:
                raise ConversionError(
                    f"'{name}' is defined twice, e.g. in both 'definitions' and "
                    f"'$defs', or in 'dependencies' and '{key}'.",
                    json_path((*pointer, key)),
                )
            target[name] = entry

    def _dependencies(
        self, result: dict[str, Any], value: dict[str, Any], pointer: Pointer
    ) -> None:
        """Split ``dependencies`` (Drafts 4 to 7) in two Draft 2020-12 keywords.

        Args:
            result: The converted schema.
            value: Value of ``dependencies``.
            pointer: Location of the schema in the IO schema.
        """
        for name, dependency in value.items():
            if isinstance(dependency, list):
                self._merge(
                    result,
                    "dependentRequired",
                    {name: copy.deepcopy(dependency)},
                    pointer,
                )
            else:
                at = (*pointer, "dependentSchemas", name)
                self._merge(
                    result,
                    "dependentSchemas",
                    {name: self._schema(dependency, at, None)},
                    pointer,
                )

    def _exclusive(
        self, result: dict[str, Any], node: dict[str, Any], key: str, pointer: Pointer
    ) -> None:
        """Convert a boolean exclusive bound of Draft 4 to a number.

        Args:
            result: The converted schema.
            node: The schema in the source.
            key: ``exclusiveMaximum`` or ``exclusiveMinimum``.
            pointer: Location of the schema in the IO schema.
        """
        bound = "maximum" if key == "exclusiveMaximum" else "minimum"
        if node[key] and bound in node:
            result[key] = copy.deepcopy(node[bound])
        elif node[key]:
            self.note(f"'{key}: true' without '{bound}' dropped.", pointer)

    def _ref(self, value: Any, pointer: Pointer) -> Any:
        """Rewrite a reference to where its target is in the IO schema.

        Args:
            value: Value of ``$ref``.
            pointer: Location of the schema with the reference.

        Returns:
            The rewritten reference.
        """
        if not isinstance(value, str) or self.embedded:
            return copy.deepcopy(value)
        if not value.startswith("#"):
            self.note(
                f"The reference '{value}' to another document is kept, but the "
                "IO schema can't resolve it; include the referenced schema "
                "in the source first.",
                pointer,
            )
            return value
        fragment = value[1:]
        if fragment and not fragment.startswith("/"):
            return value  # a plain-name anchor
        segments = [
            urllib.parse.unquote(part).replace("~1", "/").replace("~0", "~")
            for part in fragment.split("/")[1:]
        ]
        target = self._map_pointer(segments)
        return "#" + "".join(
            "/"
            + urllib.parse.quote(
                str(part).replace("~", "~0").replace("/", "~1"), safe=_POINTER_SAFE
            )
            for part in target
        )

    def _map_pointer(self, segments: list[str]) -> Pointer:
        """Map a JSON pointer of the source to the IO schema.

        The pointer is followed through the source, and each keyword is
        renamed as the conversion renames it (e.g., ``definitions`` to
        ``$defs``); the part after a keyword whose value isn't a schema (or
        that doesn't exist) is kept as it is.

        Args:
            segments: Segments of the pointer in the source.

        Returns:
            The segments of the pointer in the IO schema.
        """
        node: Any = self.root
        mapped: list[str | int] = []
        rest = list(segments)
        while rest and isinstance(node, dict) and rest[0] in node:
            key = rest.pop(0)
            value = node[key]
            tuple_items = isinstance(node.get("items"), list)
            if key in ("definitions", "$defs", "properties", "dependencies") or (
                key in _MAPS
            ):
                renamed = "$defs" if key == "definitions" else key
                if not rest or not isinstance(value, dict) or rest[0] not in value:
                    mapped.append(renamed)
                    break
                name = rest.pop(0)
                node = value[name]
                if key == "dependencies":
                    renamed = (
                        "dependentRequired"
                        if isinstance(node, list)
                        else "dependentSchemas"
                    )
                mapped.extend((renamed, name))
            elif key in _ARRAYS or (key == "items" and tuple_items):
                renamed = "prefixItems" if key == "items" else key
                mapped.append(renamed)
                if not rest or not isinstance(value, list):
                    break
                index = rest.pop(0)
                mapped.append(index)
                node = value[int(index)] if _is_index(index, value) else None
            elif key in _SINGLE or key == "additionalItems":
                mapped.append(
                    "items" if key == "additionalItems" and tuple_items else key
                )
                node = value
            else:
                mapped.append(key)
                break
        mapped.extend(rest)
        if mapped[:1] == ["$defs"] and segments[:1] in (["definitions"], ["$defs"]):
            return (*self.defs_prefix, *mapped)
        return (*self.prefix, *mapped)

    def _property(
        self, child: str, sub: Any, pointer: Pointer, name: str | None
    ) -> Any:
        """Convert the schema of a property, and mark it if it's a file.

        Args:
            child: Name of the property.
            sub: Its schema in the source.
            pointer: Location of the converted schema in the IO schema.
            name: Dotted path of the property, or ``None`` if it can't be
                named.

        Returns:
            The converted schema.

        Raises:
            ConversionError: If an option names the property, and it can't
                be a file reference.
        """
        if name is not None:
            self.seen.setdefault(name, pointer)
        converted = self._schema(sub, pointer, name)
        option = self.options.get(name) if name is not None else None
        if option == "plain" or not isinstance(converted, dict):
            if option in ("file", "directory", "sheet"):
                raise ConversionError(
                    f"'{name}' can't be a file reference: its schema is a boolean.",
                    json_path(pointer),
                )
            return converted
        if "x-ga4gh-file" in converted:
            return converted
        if option == "sheet":
            kind, reason = "file", "it holds a sample sheet"
        elif option in ("file", "directory"):
            kind, reason = option, f"named with --{option}"
        elif self.guess:
            kind, reason = _guess(child, converted)
        else:
            kind = reason = None
        if kind is None:
            return converted
        return self._mark(converted, kind, str(reason), pointer, name, option)

    def _mark(
        self,
        schema: dict[str, Any],
        kind: str,
        reason: str,
        pointer: Pointer,
        name: str | None,
        option: str | None,
    ) -> dict[str, Any]:
        """Mark a string schema as a file reference.

        Args:
            schema: The converted schema.
            kind: ``file`` or ``directory``.
            reason: Why it's marked.
            pointer: Location of the schema in the IO schema.
            name: Dotted path of the property, or ``None``.
            option: The option that names the property, if any.

        Returns:
            The marked schema, or the schema unchanged if it can't be marked
            and no option asks for it.

        Raises:
            ConversionError: If an option asks for the mark, and the schema
                can't be a file reference.
        """
        problem = _unmarkable(schema)
        if problem is not None:
            if option is not None:
                raise ConversionError(
                    f"'{name}' can't be a file reference: {problem}.",
                    json_path(pointer),
                )
            self.note(
                f"Looks like a {kind} ({reason}), but isn't marked as a file "
                f"reference: {problem}.",
                pointer,
            )
            return schema
        marked = {
            key: value for key, value in schema.items() if key not in _NOT_ON_FILES
        }
        reference: dict[str, Any] = {"kind": kind}
        default = schema.get("default")
        if kind == "file" and isinstance(default, str):
            extension = default[default.rfind(".") :].lower()
            if extension in _MEDIA_TYPES:
                reference["mediaType"] = _MEDIA_TYPES[extension]
        marked["x-ga4gh-file"] = reference
        message = f"Marked as a file reference ({kind}): {reason}."
        dropped = [key for key in _NOT_ON_FILES if key in schema]
        if dropped:
            message += (
                " Dropped "
                + ", ".join(f"'{key}'" for key in dropped)
                + ": file references can't have it."
            )
        if option is None:
            message += (
                f" Keep it a plain string with --plain {name}."
                if name is not None
                else " It can't be named on the command line: edit the result "
                "to undo it."
            )
        if dropped or option not in ("file", "directory"):
            self.note(message, pointer)
        return marked


def _child_name(parent: str | None, child: str) -> str | None:
    """Return the dotted path of a property.

    Args:
        parent: Dotted path of the parent, ``""`` for a root, or ``None``.
        child: Name of the property.

    Returns:
        The dotted path, or ``None`` if the parent can't be named.
    """
    if parent is None:
        return None
    return child if parent == "" else f"{parent}.{child}"


def _is_index(segment: str, value: list[Any]) -> bool:
    """Tell whether a pointer segment is an index of a list.

    Args:
        segment: The segment.
        value: The list.

    Returns:
        Whether the segment is a decimal index within the list.
    """
    return segment.isdecimal() and int(segment) < len(value)


def _words(name: str) -> list[str]:
    """Split a property name into lowercase words, without trailing digits.

    Args:
        name: The name, e.g. ``genomeFasta``, ``fastq_1`` or ``fq2``.

    Returns:
        The words, e.g. ``["genome", "fasta"]``, ``["fastq"]`` or ``["fq"]``.
    """
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    words = (word.rstrip("0123456789") for word in re.split(r"[\W_]+", spaced))
    return [word.lower() for word in words if word]


def _guess(name: str, schema: dict[str, Any]) -> tuple[str | None, str | None]:
    """Tell whether a property looks like a file or a directory.

    The rules are tried in turn: the name, the default, the description.

    Args:
        name: Name of the property.
        schema: Its converted schema.

    Returns:
        ``file`` or ``directory`` and the reason, or ``None`` twice.
    """
    types = schema.get("type")
    if types != "string" and not (isinstance(types, list) and "string" in types):
        return None, None
    words = _words(name)
    last = words[-1] if words else ""
    if last.endswith("dir") or last in DIRECTORY_WORDS:
        return "directory", f"its name ends with '{last}'"
    if last in FILE_WORDS:
        return "file", f"its name ends with '{last}'"
    if name.lower() in SHEET_NAMES:
        return "file", "its name is that of a sample sheet"
    default = schema.get("default")
    if isinstance(default, str) and default.endswith("/"):
        return "directory", f"its default '{default}' ends with '/'"
    if isinstance(default, str) and _FILE_EXTENSION.search(default):
        return "file", f"its default '{default}' has a file extension"
    description = schema.get("description")
    if isinstance(description, str) and _DESCRIPTION_PATH.search(description):
        if _DESCRIPTION_DIRECTORY.search(description) and not _DESCRIPTION_FILE.search(
            description
        ):
            return "directory", "its description names a path to a directory"
        return "file", "its description names a path"
    return None, None


def _unmarkable(schema: dict[str, Any]) -> str | None:
    """Tell why a schema can't be a file reference.

    Args:
        schema: The converted schema.

    Returns:
        The reason, or ``None`` if it can be one.
    """
    if schema.get("type") != "string":
        return f'its type is {json.dumps(schema.get("type"))}, not "string"'
    for keyword in _APPLICATORS:
        if keyword in schema:
            return f"it has '{keyword}'"
    return None
