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

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from ga4gh_io_schema.converters.common import (
    MAX_SOURCE_VALUES,
    Conversion,
    ConversionError,
    Note,  # noqa: F401 - part of the API of this module (see common)
    Output,
    Pointer,
    SourceError,
    json_path,
    outputs_schema,
)
from ga4gh_io_schema.converters.schemas import (
    NOT_ON_FILES,
    SchemaConverter,
    check_json,
    file_reference_problem,
)
from ga4gh_io_schema.validator import load_profile

#: Most values (objects, arrays and scalars) that a source may hold; bounds
#: the work for documents that YAML aliases blow up (or make cyclic).
MAX_VALUES = MAX_SOURCE_VALUES

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


# Command-line flag of each option, where it differs from the option.
_FLAGS = {"sheet": "sample-sheet"}


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
    # ValueError: also numbers that Python won't parse (too many digits)
    except ValueError:
        data = _load_yaml(text, name)
    check_json(data, name, MAX_VALUES)
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
            f"Reading YAML needs PyYAML - install the extra 'snakemake' "
            f"(in a clone: pip install '.[snakemake]'): {name}"
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
    # ValueError: e.g., integers with too many digits for Python
    except (yaml.YAMLError, ValueError) as exc:
        raise SourceError(f"Invalid YAML - {name}: {exc}") from exc
    finally:
        loader.dispose()


def to_ga4gh(
    config_schema: Any,
    sample_sheets: Sequence[SampleSheet] = (),
    *,
    files: Iterable[str] = (),
    directories: Iterable[str] = (),
    plain: Iterable[str] = (),
    guess: bool = True,
    outputs: Sequence[Output] = (),
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
        outputs: File outputs of the workflow, found by glob (Snakemake
            schemas don't describe outputs).

    Returns:
        The IO schema, valid against the GA4GH IO Profile unless the source
        uses ``x-ga4gh-*`` keywords wrongly, or an output's glob is invalid,
        and the notes of the conversion.

    Raises:
        ConversionError: If a schema can't be converted, the options name
            properties that don't exist or can't be file references, or two
            outputs have the same name.
    """
    return _Converter(files, directories, plain, guess).convert(
        config_schema, list(sample_sheets), list(outputs)
    )


class _Converter(SchemaConverter):
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
        super().__init__()
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

    def convert(
        self, config: Any, sheets: list[SampleSheet], outputs: list[Output]
    ) -> Conversion:
        """Convert the configuration schema and the sample-sheet schemas.

        Args:
            config: The configuration schema.
            sheets: The sample-sheet schemas.
            outputs: The file outputs of the workflow.

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
        schema: dict[str, Any] = {
            "$schema": load_profile()["$id"],
            # The engine binding; the TRS fields are known only once the
            # workflow is published (see the converter documentation)
            "x-ga4gh-workflow": {"descriptor_type": "SMK"},
            "type": "object",
            "properties": {
                "inputs": inputs,
                "outputs": outputs_schema(outputs),
            },
        }
        if defs is not None:
            schema["$defs"] = defs
        self._check_references(schema, schema, (), {})
        if not outputs:
            self.note(
                "Snakemake config schemas don't describe outputs: 'outputs' is "
                "left empty; name the file outputs of the workflow with "
                "--out-file, --out-files or --out-dir.",
                ("properties", "outputs"),
            )
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
        converted = super()._property(child, sub, pointer, name)
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
        kind: str | None
        reason: str | None
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
        problem = file_reference_problem(schema)
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
            key: value for key, value in schema.items() if key not in NOT_ON_FILES
        }
        reference: dict[str, Any] = {"kind": kind}
        default = schema.get("default")
        if kind == "file" and isinstance(default, str):
            extension = default[default.rfind(".") :].lower()
            if extension in _MEDIA_TYPES:
                reference["mediaType"] = _MEDIA_TYPES[extension]
        marked["x-ga4gh-file"] = reference
        message = f"Marked as a file reference ({kind}): {reason}."
        dropped = [key for key in NOT_ON_FILES if key in schema]
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
