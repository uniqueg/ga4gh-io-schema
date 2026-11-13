"""Convert the inputs and outputs of CWL documents to IO schemas.

A :class:`CwlParser` reads a CWL ``CommandLineTool``, ``Workflow``,
``ExpressionTool`` or ``Operation`` (CWL v1.0 to v1.2, also packed, with a
``$graph``) with the parser of `cwl-utils <https://github.com/common-workflow-language/cwl-utils>`_
and translates its inputs and outputs into an IO schema. The parser of
``cwl-utils`` resolves the type shorthands (``File?``, ``File[]``), namespace
prefixes, ``$import`` and ``SchemaDefRequirement``; this module maps the
resolved types to JSON Schema and file references (see the CWL rows of
``docs/specification/files.md``).

``cwl-utils`` is an optional dependency (``pip install
'ga4gh-io-schema[cwl]'``); importing this module without it raises
:class:`ImportError`.

JavaScript expressions are never evaluated. Where an expression, or another
construct without an equivalent in the profile, affects the schema (e.g., a
``format`` given as an expression, or an optional secondary file), the
converter leaves it out and records a :class:`ConversionNote`.

The parser never fetches remote resources, and doesn't check that the files
a document refers to exist; it reads local files that the document imports
(``$import``, ``$include``), as every CWL loader does.
"""

import hashlib
import math
import re
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cwl_utils.errors import GraphTargetMissingException
from cwl_utils.parser import LoadingOptions, load_document_by_yaml
from cwl_utils.utils import get_value_from_uri
from jsonschema import Draft202012Validator
from ruamel.yaml import YAMLError
from schema_salad.exceptions import ValidationException
from schema_salad.fetcher import DefaultFetcher
from schema_salad.utils import yaml_no_ts

from ga4gh_io_schema.validator import load_profile

#: Classes of CWL documents that have inputs and outputs.
PROCESS_CLASSES = frozenset(
    {"CommandLineTool", "ExpressionTool", "Operation", "Workflow"}
)

#: JSON Schema types of the primitive CWL types.
PRIMITIVE_TYPES = {
    "boolean": "boolean",
    "int": "integer",
    "long": "integer",
    "float": "number",
    "double": "number",
    "string": "string",
    "null": "null",
}

#: CWL types that are files: ``stdin`` (inputs of a ``CommandLineTool``),
#: ``stdout`` and ``stderr`` (its outputs) are shorthands for ``File``.
FILE_TYPES = frozenset({"File", "stdin", "stdout", "stderr"})

#: Secondary file patterns that the profile accepts; the same pattern as
#: ``secondaryFiles`` of ``schemas/vocabularies/file.schema.json`` (the tests
#: check that converted schemas comply with the meta-schema).
SECONDARY_FILE_PATTERN = re.compile(r"\^*[.]*[A-Za-z0-9_+-][A-Za-z0-9_.+-]*")

#: Most schemas (types, values of defaults) that a conversion may create;
#: named types are inlined, so a small document could otherwise expand to
#: a very large schema.
MAX_NODES = 10_000

#: Most characters of text (titles, descriptions, names, enum symbols,
#: patterns, ontology terms and string values) that a conversion may copy
#: into a schema; named types are inlined with their texts.
MAX_TEXT = 1_000_000

#: Most values (mappings, lists and scalars) of a document and the files it
#: imports, once their YAML aliases are expanded, as the parser of
#: ``cwl-utils`` does.
MAX_DOCUMENT_NODES = 100_000

# Ontology terms that the profile accepts
_HTTP_IRI = re.compile(r"https?://")
# Format checks of the meta-schema (``ontology`` has ``format: uri``)
_FORMATS = Draft202012Validator.FORMAT_CHECKER
# Absolute URIs, as defined for the values of file references
_URI_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
# Keys of JSON paths that need no brackets, as in the paths of jsonschema
_PLAIN_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


@dataclass(frozen=True)
class ConversionNote:
    """Part of a CWL document that the converter couldn't convert.

    Attributes:
        location: JSON path of the affected schema in the converted IO schema.
        message: What was left out or changed, and why.
    """

    location: str
    message: str


class CwlConversionError(ValueError):
    """The CWL document can't be read or converted.

    Attributes:
        message: Description of the error.
        location: JSON path of the affected schema, if any.
    """

    def __init__(self, message: str, location: str | None = None) -> None:
        """Initialise the error.

        Args:
            message: Description of the error.
            location: JSON path of the affected schema, if any.
        """
        super().__init__(message)
        self.message = message
        self.location = location


class _LocalFetcher(DefaultFetcher):
    """Fetcher of the parser that reads only regular files under a directory.

    It has no HTTP session, so remote references aren't fetched, and it
    refuses local files outside ``root`` (e.g., ``/proc/self/environ``).
    """

    def __init__(self, root: Path) -> None:
        """Initialise the fetcher.

        Args:
            root: Directory whose files (at any depth) may be read.
        """
        super().__init__({}, None)
        self.root = root.resolve()
        self.values = MAX_DOCUMENT_NODES

    def count(self, document: Any) -> None:
        """Count the values of a document towards :data:`MAX_DOCUMENT_NODES`.

        The limit holds for a document and all the files that it imports
        together.

        Args:
            document: The document, as loaded from YAML.

        Raises:
            ValidationException: If the documents have too many values.
            RecursionError: If the document is nested too deeply to count.
        """
        self.values -= _expanded_size(document, {})
        if self.values < 0:
            raise ValidationException(
                f"The document and the files it imports have more than "
                f"{MAX_DOCUMENT_NODES} values once YAML aliases are expanded."
            )

    def _allowed(self, url: str) -> Path:
        """Return the local path of a URL, if it may be read.

        Args:
            url: URL of the file.

        Returns:
            The resolved path of the file.

        Raises:
            ValidationException: If the URL isn't a regular file under the
                root.
        """
        split = urllib.parse.urlsplit(url)
        if split.scheme != "file":
            raise ValidationException(f"Not fetched (not a local file): {url}")
        try:
            path = Path(urllib.request.url2pathname(split.path)).resolve()
            allowed = path.is_relative_to(self.root) and path.is_file()
        except (OSError, ValueError):  # e.g., a NUL character
            allowed = False
        if not allowed:
            raise ValidationException(f"Not read (not a file under {self.root}): {url}")
        return path

    def fetch_text(self, url: str, content_types: list[str] | None = None) -> str:
        """Read a local file under the root.

        Args:
            url: URL of the file.
            content_types: Ignored; for the interface of the fetcher.

        Returns:
            The text of the file.

        Raises:
            ValidationException: If the file may not be read, isn't UTF-8,
                is nested too deeply, or makes the documents too large.
        """
        path = self._allowed(url)
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationException(f"Not UTF-8 text - {url}: {exc}") from exc
        # The parser expands the YAML aliases of imported files too
        try:
            self.count(yaml_no_ts().load(text))
        except YAMLError:
            pass  # Plain text ($include), or reported by the parser
        except RecursionError as exc:
            raise ValidationException(f"Too deeply nested to read - {url}") from exc
        return text

    def check_exists(self, url: str) -> bool:
        """Tell whether a referenced file may be read.

        Args:
            url: URL of the file.

        Returns:
            Whether it is a regular file under the root.
        """
        try:
            self._allowed(url)
        except ValidationException:
            return False
        return True


class CwlSyntaxError(CwlConversionError):
    """The CWL document isn't valid YAML or JSON, or is nested too deeply."""


class CwlParser:
    """Converter of CWL documents to IO schemas.

    The two steps follow the converter interface of the package: :meth:`parse`
    (or :meth:`parse_string`) reads a document, and :meth:`to_ga4gh`
    translates it.

    Attributes:
        process: ID of the process to convert in a document with a
            ``$graph`` (e.g., ``main``); by default, ``main``, or the only
            process of the graph.
        notes: What the last call of :meth:`to_ga4gh` couldn't convert.
        workflow: ``x-ga4gh-workflow`` of the document that the parser read
            last: the descriptor type and version, the SHA-256 checksum of
            the document and, for a document with a ``$graph``, the entry
            point (e.g., ``#main``). The TRS identifiers and the path of
            the primary descriptor aren't known to the converter.
    """

    def __init__(self, process: str | None = None, root: Path | None = None) -> None:
        """Initialise the parser.

        Args:
            process: ID of the process to convert in a document with a
                ``$graph``, with or without a leading ``#``.
            root: Directory whose files the document may import or include
                (``$import``, ``$include``); by default, the directory of the
                document.
        """
        self.process = process.lstrip("#") if process else None
        self.root = root
        self.notes: list[ConversionNote] = []
        self.workflow: dict[str, Any] | None = None

    def parse(self, path: Path | str) -> Any:
        """Read a CWL document from a file.

        Args:
            path: Path of the CWL document (YAML or JSON).

        Returns:
            The process, as an object of the parser of ``cwl-utils``.

        Raises:
            OSError: If the file can't be read.
            UnicodeDecodeError: If the file isn't UTF-8 text.
            CwlConversionError: If the document isn't a valid CWL process.
        """
        resolved = Path(path).resolve()
        # Decoded from the bytes, without translating line ends, so that the
        # checksum is that of the file
        return self.parse_string(
            resolved.read_bytes().decode("utf-8"), resolved.as_uri()
        )

    def parse_string(self, text: str, uri: str) -> Any:
        """Read a CWL document from a string.

        Args:
            text: The CWL document (YAML or JSON).
            uri: URI of the document, against which the parser resolves
                relative references (e.g., ``$import``). Without
                :attr:`root`, the document may read the files under the
                directory of its path (``/`` for ``file:///tool.cwl``).

        Returns:
            The process, as an object of the parser of ``cwl-utils``. The
            parser keeps what :meth:`to_ga4gh` needs for ``x-ga4gh-workflow``
            in :attr:`workflow`.

        Raises:
            CwlConversionError: If the document isn't valid YAML or JSON, or
                isn't a valid CWL process.
        """
        self.workflow = None
        try:
            document = yaml_no_ts().load(text)
        except YAMLError as exc:
            raise CwlSyntaxError(f"Invalid YAML - {exc}") from exc
        except RecursionError as exc:
            raise CwlSyntaxError("Too deeply nested to read.") from exc
        if not isinstance(document, dict):
            raise CwlConversionError("A CWL document must be a YAML or JSON object.")
        # Remote references aren't fetched; local files only under the root
        fetcher = _LocalFetcher(self._root(uri))
        try:
            fetcher.count(document)
        except RecursionError as exc:
            raise CwlSyntaxError("Too deeply nested to read.") from exc
        except ValidationException as exc:
            raise CwlConversionError(str(exc)) from exc
        process_id = self.process
        if "$graph" in document:
            graph = document["$graph"]
            if not isinstance(graph, list) or not all(
                isinstance(item, dict) and isinstance(item.get("id"), str)
                for item in graph
            ):
                raise CwlConversionError(
                    "Invalid CWL document - $graph must be a list of objects "
                    "with an 'id'."
                )
            if process_id is None and len(graph) == 1:
                process_id = graph[0]["id"].lstrip("#")
        elif process_id is not None:
            raise CwlConversionError(
                f"The document has no $graph to select process {process_id!r} from."
            )
        options = LoadingOptions(
            fetcher=fetcher,
            fileuri=uri,
            # Don't check that referenced files exist (e.g., default files)
            no_link_check=True,
        )
        try:
            process = load_document_by_yaml(document, uri, options, process_id)
        except (ValidationException, GraphTargetMissingException) as exc:
            raise CwlConversionError(f"Invalid CWL document - {exc}") from exc
        except RecursionError as exc:
            raise CwlSyntaxError("Too deeply nested to read.") from exc
        if getattr(process, "class_", None) not in PROCESS_CLASSES:
            raise CwlConversionError(
                "The document is not a CWL process; expected one of "
                f"{', '.join(sorted(PROCESS_CLASSES))}."
            )
        workflow: dict[str, Any] = {
            "descriptor_type": "CWL",
            # The parser of cwl-utils accepts only known versions (e.g., v1.2)
            "descriptor_type_version": str(document["cwlVersion"]),
        }
        workflow["checksum"] = [
            {
                "type": "sha-256",
                "checksum": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        ]
        if "$graph" in document:
            workflow["entry_point"] = f"#{process_id or 'main'}"
        self.workflow = workflow
        return process

    def _root(self, uri: str) -> Path:
        """Return the directory whose files a document may read.

        Args:
            uri: URI of the document.

        Returns:
            :attr:`root`, or the directory of the document.
        """
        if self.root is not None:
            return self.root
        path = urllib.request.url2pathname(urllib.parse.urlsplit(uri).path)
        return Path(path).parent

    def to_ga4gh(self, source: Any) -> dict[str, Any]:
        """Translate a CWL process into an IO schema.

        What can't be converted is left out and recorded in :attr:`notes`.

        Args:
            source: The process, as returned by :meth:`parse`.

        Returns:
            An IO schema that complies with the GA4GH IO Profile.

        Raises:
            CwlConversionError: If a type of the process can't be converted
                (e.g., an unknown or recursive named type).
        """
        self.notes = []
        converter = _Converter(source.loadingOptions, self.notes)
        try:
            return self._schema(source, converter)
        except RecursionError as exc:
            raise CwlConversionError("Types nested too deeply to convert.") from exc

    def _schema(self, source: Any, converter: "_Converter") -> dict[str, Any]:
        """Build the IO schema of a process.

        Args:
            source: The process.
            converter: Converter of its types.

        Returns:
            The IO schema.
        """
        schema: dict[str, Any] = {"$schema": load_profile()["$id"]}
        converter.text(schema, source, "$")
        schema["x-ga4gh-workflow"] = dict(self.workflow or {"descriptor_type": "CWL"})
        schema["type"] = "object"
        schema["properties"] = {
            "inputs": converter.parameters(
                source.inputs, "$.properties.inputs", is_input=True
            ),
            "outputs": converter.parameters(
                source.outputs, "$.properties.outputs", is_input=False
            ),
        }
        return schema


class _Converter:
    """Translation of the types of one CWL process.

    Attributes:
        index: Objects of the document by ID, from the parser of
            ``cwl-utils``; named types are looked up in it.
        notes: List that the notes of the conversion are appended to.
    """

    def __init__(self, options: Any, notes: list[ConversionNote]) -> None:
        """Initialise the converter.

        Args:
            options: Loading options of the process, with its index.
            notes: List to append the notes of the conversion to.
        """
        self.index: dict[str, Any] = options.idx
        self.notes = notes
        self.budget = MAX_NODES
        self.text_budget = MAX_TEXT

    def spend(self, location: str) -> None:
        """Count one schema or value towards :data:`MAX_NODES`.

        Args:
            location: JSON path of the schema being converted.

        Raises:
            CwlConversionError: If the conversion has created too many.
        """
        self.budget -= 1
        if self.budget < 0:
            raise CwlConversionError(
                f"The converted schema would be too large (more than "
                f"{MAX_NODES} types and values); is a named type used many "
                "times, or a default value expanded from YAML aliases?",
                location,
            )

    def spend_text(self, location: str, *texts: str) -> None:
        """Count characters of copied texts towards :data:`MAX_TEXT`.

        Args:
            location: JSON path of the schema being converted.
            *texts: The texts.

        Raises:
            CwlConversionError: If the conversion has copied too much text.
        """
        self.text_budget -= sum(len(text) for text in texts)
        if self.text_budget < 0:
            raise CwlConversionError(
                f"The converted schema would be too large (more than {MAX_TEXT} "
                "characters of text); is a named type with long texts or many "
                "symbols used many times?",
                location,
            )

    def text(self, schema: dict[str, Any], element: Any, location: str) -> None:
        """Copy ``label`` and ``doc`` of a CWL element to a schema.

        Args:
            schema: The schema, which gets ``title`` and ``description``.
            element: Process, parameter, field or type with ``label`` and
                ``doc``.
            location: JSON path of the schema.
        """
        _add_text(schema, element)
        self.spend_text(
            location, schema.get("title", ""), schema.get("description", "")
        )

    def note(self, location: str, message: str) -> None:
        """Record what couldn't be converted.

        Args:
            location: JSON path of the affected schema.
            message: What was left out, and why.
        """
        self.notes.append(ConversionNote(location=location, message=message))

    def parameters(
        self, parameters: Sequence[Any], location: str, is_input: bool
    ) -> dict[str, Any]:
        """Convert the inputs or the outputs of a process.

        Args:
            parameters: Input or output parameters of the process.
            location: JSON path of the converted object.
            is_input: Whether the parameters are inputs.

        Returns:
            An object schema with one property per parameter, which rejects
            unknown properties (for outputs: the normalised outputs object
            has only the declared outputs).
        """
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in parameters:
            name = get_value_from_uri(parameter.id)
            optional, schema = self.field(
                parameter, _child(location, "properties", name), is_input
            )
            schema["x-ga4gh-parameter"] = {"type": _type_name(parameter.type_)}
            properties[name] = schema
            if not optional:
                required.append(name)
        result: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            result["required"] = required
        result["additionalProperties"] = False
        return result

    def field(
        self,
        parameter: Any,
        location: str,
        is_input: bool,
        names: tuple[str, ...] = (),
    ) -> tuple[bool, dict[str, Any]]:
        """Convert a parameter or a field of a record.

        Args:
            parameter: Input or output parameter, or a field of a record.
            location: JSON path of the converted schema.
            is_input: Whether the parameter is an input, or a field of an
                input record.
            names: Named types that contain the field, to detect recursion.

        Returns:
            Whether the parameter is optional (its type allows ``null``, or it
            is an input with a default), and its schema.
        """
        optional, type_ = _without_null(parameter.type_)
        files = _Files(self.file_annotation(parameter, location, is_input), is_input)
        schema = self.type_schema(type_, location, files, names)
        if files.annotation and not files.applied:
            self.note(
                location,
                "'format' and 'secondaryFiles' apply only to files; the type "
                "has no File (outside records), so they are left out.",
            )
        self.text(schema, parameter, location)
        default = getattr(parameter, "default", None)
        if is_input and default is not None:
            optional = True
            converted, value = self.default(default, location)
            if converted:
                schema["default"] = value
        return optional, schema

    def file_annotation(
        self, parameter: Any, location: str, is_input: bool
    ) -> dict[str, Any]:
        """Convert ``format`` and ``secondaryFiles`` of a parameter.

        Args:
            parameter: Parameter or field of a record.
            location: JSON path of the converted schema.
            is_input: Whether the parameter is an input.

        Returns:
            The keys of ``x-ga4gh-file`` for the files of the parameter (e.g.,
            ``ontology``), without ``kind``.
        """
        annotation: dict[str, Any] = {}
        ontology = self.ontology(getattr(parameter, "format", None), location)
        if ontology is not None:
            annotation["ontology"] = ontology
        patterns = self.secondary_files(
            getattr(parameter, "secondaryFiles", None), location, is_input
        )
        if patterns:
            annotation["secondaryFiles"] = patterns
        self.spend_text(location, ontology or "", *patterns)
        return annotation

    def ontology(self, format_: Any, location: str) -> str | None:
        """Convert the ``format`` of a parameter to an ontology term.

        Args:
            format_: ``format`` of the parameter: an IRI, a list of IRIs or an
                expression.
            location: JSON path of the converted schema.

        Returns:
            The IRI of the format, or ``None`` if there's none, or if it
            can't be converted.
        """
        if format_ is None:
            return None
        if isinstance(format_, list):
            if len(format_) != 1:
                self.note(
                    location,
                    f"'format' lists {len(format_)} formats; 'ontology' takes "
                    "one term, so it is left out.",
                )
                return None
            format_ = format_[0]
        if not isinstance(format_, str) or _is_expression(format_):
            self.note(
                location,
                f"'format' is an expression ({format_!r}), which isn't "
                "evaluated; it is left out.",
            )
            return None
        if not _HTTP_IRI.match(format_) or not _FORMATS.conforms(format_, "uri"):
            self.note(
                location,
                f"'format' {format_!r} is not an http(s) IRI (is its namespace "
                "prefix missing from $namespaces?); it is left out.",
            )
            return None
        return format_

    def secondary_files(
        self, secondary_files: Any, location: str, is_input: bool
    ) -> list[str]:
        """Convert the ``secondaryFiles`` of a parameter to patterns.

        Args:
            secondary_files: ``secondaryFiles`` of the parameter: patterns
                (CWL v1.0), objects with ``pattern`` and ``required`` (CWL
                v1.1 and later), or an expression.
            location: JSON path of the converted schema.
            is_input: Whether the parameter is an input; secondary files of
                outputs are optional unless they are required explicitly.

        Returns:
            The patterns of the required secondary files that the profile
            can express.
        """
        if secondary_files is None:
            return []
        entries = (
            secondary_files if isinstance(secondary_files, list) else [secondary_files]
        )
        patterns: list[str] = []
        for entry in entries:
            if isinstance(entry, str):
                pattern, required = entry, None
            else:
                pattern, required = entry.pattern, entry.required
            if isinstance(pattern, str) and pattern.endswith("?"):
                pattern, required = pattern[:-1], False
            if not isinstance(pattern, str) or _is_expression(pattern):
                self.note(
                    location,
                    f"Secondary file {pattern!r} is an expression, which isn't "
                    "evaluated; it is left out.",
                )
                continue
            if required is None:
                required = is_input
            if isinstance(required, str):
                self.note(
                    location,
                    f"Whether secondary file {pattern!r} is required is an "
                    f"expression ({required!r}), which isn't evaluated; it is "
                    "left out.",
                )
                continue
            if not required:
                self.note(
                    location,
                    f"Secondary file {pattern!r} is optional; the profile has "
                    "only required secondary files, so it is left out.",
                )
                continue
            if not SECONDARY_FILE_PATTERN.fullmatch(pattern):
                self.note(
                    location,
                    f"Secondary file pattern {pattern!r} is not a suffix that "
                    "the profile accepts; it is left out.",
                )
                continue
            if pattern not in patterns:
                patterns.append(pattern)
        return patterns

    def type_schema(
        self,
        type_: Any,
        location: str,
        files: "_Files",
        names: tuple[str, ...],
    ) -> dict[str, Any]:
        """Convert a CWL type to a schema.

        Args:
            type_: The type: a name, a union (list) or an array, enum or
                record schema.
            location: JSON path of the converted schema.
            files: The file annotation of the parameter, and whether the
                type is that of an input.
            names: Named types that contain this one, to detect recursion.

        Returns:
            The schema of the type.

        Raises:
            CwlConversionError: If the type is unknown or recursive, or the
                schema would be too large.
        """
        self.spend(location)
        if isinstance(type_, list):
            return self.union(type_, location, files, names)
        if isinstance(type_, str):
            return self.named_type(type_, location, files, names)
        kind = getattr(type_, "type_", None)
        if kind == "array":
            return {
                "type": "array",
                "items": self.type_schema(
                    type_.items, f"{location}.items", files, names
                ),
            }
        if kind == "enum":
            if not type_.symbols:
                raise CwlConversionError("An enum without symbols.", location)
            schema: dict[str, Any] = {
                "type": "string",
                "enum": [get_value_from_uri(symbol) for symbol in type_.symbols],
            }
            self.spend_text(location, *schema["enum"])
            self.text(schema, type_, location)
            return schema
        if kind == "record":
            return self.record(type_, location, files.is_input, names)
        raise CwlConversionError(f"Unknown CWL type: {type_!r}", location)

    def union(
        self,
        types: list[Any],
        location: str,
        files: "_Files",
        names: tuple[str, ...],
    ) -> dict[str, Any]:
        """Convert a union of CWL types to ``anyOf``.

        Args:
            types: Types of the union.
            location: JSON path of the converted schema.
            files: The file annotation of the parameter, and whether the
                type is that of an input.
            names: Named types that contain this one.

        Returns:
            The schema of the only type, or ``anyOf`` with one branch per type.
            Unions of outputs lose ``null``: output values are never
            ``null``, normalisers leave such values out.
        """
        if not files.is_input and "null" in types and len(types) > 1:
            types = [member for member in types if member != "null"]
        if not types:
            raise CwlConversionError("A union without types.", location)
        if len(types) == 1:
            return self.type_schema(types[0], location, files, names)
        return {
            "anyOf": [
                self.type_schema(
                    member,
                    f"{location}.anyOf[{number}]",
                    files,
                    names,
                )
                for number, member in enumerate(types)
            ]
        }

    def named_type(
        self,
        name: str,
        location: str,
        files: "_Files",
        names: tuple[str, ...],
    ) -> dict[str, Any]:
        """Convert a primitive, file or named CWL type.

        Args:
            name: Name of the type (e.g., ``int``, ``File`` or the ID of a
                type of a ``SchemaDefRequirement``).
            location: JSON path of the converted schema.
            files: The file annotation of the parameter, and whether the
                type is that of an input.
            names: Named types that contain this one.

        Returns:
            The schema of the type; named types are inlined.

        Raises:
            CwlConversionError: If the type is unknown or recursive.
        """
        if name in PRIMITIVE_TYPES:
            return {"type": PRIMITIVE_TYPES[name]}
        if name in FILE_TYPES:
            files.applied = True
            return {
                "type": "string",
                "x-ga4gh-file": {"kind": "file", **files.annotation},
            }
        if name == "Directory":
            return {"type": "string", "x-ga4gh-file": {"kind": "directory"}}
        if name == "Any":
            self.note(
                location,
                "Type 'Any' allows any value but null; values that are files "
                "are not checked as file references.",
            )
            return {"not": {"type": "null"}}
        if name in names:
            raise CwlConversionError(
                f"Recursive CWL type {get_value_from_uri(name)!r} can't be converted.",
                location,
            )
        entry = self.index.get(name)
        target = entry[0] if isinstance(entry, tuple) else entry
        if getattr(target, "type_", None) not in ("array", "enum", "record"):
            raise CwlConversionError(
                f"Unknown CWL type: {get_value_from_uri(name) or name!r}", location
            )
        return self.type_schema(target, location, files, (*names, name))

    def record(
        self, record: Any, location: str, is_input: bool, names: tuple[str, ...]
    ) -> dict[str, Any]:
        """Convert a CWL record to an object schema.

        Args:
            record: The record schema.
            location: JSON path of the converted schema.
            is_input: Whether the record is the type of an input.
            names: Named types that contain this one.

        Returns:
            An object schema with one property per field, which rejects
            unknown properties.
        """
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in record.fields or []:
            name = get_value_from_uri(field.name)
            self.spend_text(location, name)
            optional, properties[name] = self.field(
                field, _child(location, "properties", name), is_input, names
            )
            if not optional:
                required.append(name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        schema["additionalProperties"] = False
        self.text(schema, record, location)
        return schema

    def default(self, value: Any, location: str) -> tuple[bool, Any]:
        """Convert the default value of an input.

        Files and directories become their location, if it is a URI that
        isn't local (e.g., ``https``); files next to the CWL document and
        file literals can't be referred to by an IO schema.

        Args:
            value: Default value of the input.
            location: JSON path of the converted schema.

        Returns:
            Whether the value could be converted, and the converted value.
        """
        try:
            return True, self._value(value, location)
        except _UnconvertibleDefault as exc:
            self.note(
                location,
                f"The default value can't be converted ({exc}); it is left out, "
                "and the input stays optional.",
            )
            return False, None

    def _value(self, value: Any, location: str) -> Any:
        """Convert a value of a CWL input to a value of the IO schema.

        Args:
            value: The value, as loaded by the parser of ``cwl-utils``.
            location: JSON path of the schema of the input.

        Returns:
            The converted value.

        Raises:
            _UnconvertibleDefault: If the value contains a file that can't be
                referred to, or a number that isn't finite (JSON has none).
            CwlConversionError: If the value is too large.
        """
        self.spend(location)
        if isinstance(value, float) and not math.isfinite(value):
            raise _UnconvertibleDefault(f"{value} is not a finite number")
        class_ = getattr(value, "class_", None)
        if class_ in ("File", "Directory"):
            return _file_location(class_, getattr(value, "location", None))
        if isinstance(value, dict):
            if value.get("class") in ("File", "Directory"):
                return _file_location(value["class"], value.get("location"))
            return {key: self._value(item, location) for key, item in value.items()}
        if isinstance(value, list):
            return [self._value(item, location) for item in value]
        if isinstance(value, str):
            self.spend_text(location, value)
        return value


@dataclass
class _Files:
    """The file annotation of a parameter, while its type is converted.

    Attributes:
        annotation: Keys of ``x-ga4gh-file`` (e.g., ``ontology``) for the
            files of the parameter; they apply to files in its type, arrays
            and unions, but not in records.
        is_input: Whether the parameter is an input.
        applied: Whether a file of the type got the annotation.
    """

    annotation: dict[str, Any]
    is_input: bool
    applied: bool = False


class _UnconvertibleDefault(Exception):
    """A default value refers to a file that an IO schema can't refer to."""


def _file_location(class_: str, location: Any) -> str:
    """Convert the location of a file or directory of a default value.

    Args:
        class_: ``File`` or ``Directory``.
        location: Location of the file or directory, if any.

    Returns:
        The location, if it is an absolute URI with a scheme other than
        ``file``.

    Raises:
        _UnconvertibleDefault: If the location is missing (e.g., a file
            literal), relative, or a local file.
    """
    if not isinstance(location, str) or not _URI_SCHEME.match(location):
        raise _UnconvertibleDefault(f"a {class_} without an absolute location")
    if location.lower().startswith("file:"):
        raise _UnconvertibleDefault(
            f"a {class_} next to the CWL document, {Path(location).name!r}"
        )
    return location


def _type_name(type_: Any) -> str:
    """Write a CWL type as in a CWL document, for ``x-ga4gh-parameter``.

    Args:
        type_: The type, as loaded by the parser of ``cwl-utils``.

    Returns:
        The type in the short notation of CWL, e.g., ``File[]?``; named
        types by their name, anonymous records and enums as ``record`` and
        ``enum``.
    """
    if isinstance(type_, list):
        rest = [member for member in type_ if member != "null"]
        if len(rest) == 1 and len(type_) == 2:
            return f"{_type_name(rest[0])}?"
        return f"[{', '.join(_type_name(member) for member in type_)}]"
    if isinstance(type_, str):
        return get_value_from_uri(type_) or type_
    kind = getattr(type_, "type_", None)
    if kind == "array":
        return f"{_type_name(type_.items)}[]"
    name = getattr(type_, "name", None)
    if isinstance(name, str) and not name.startswith("_:"):
        return get_value_from_uri(name) or name
    return str(kind)


def _expanded_size(node: Any, sizes: dict[int, int]) -> int:
    """Count the values of a YAML document as if its aliases were expanded.

    Aliases share one object, so the count is memoised by identity: it
    takes time in the size of the document, not of its expansion.

    Args:
        node: A value of the document.
        sizes: Expanded sizes of the mappings and lists counted so far.

    Returns:
        The number of values of the expansion, or a number just above
        :data:`MAX_DOCUMENT_NODES` once it exceeds that.

    Raises:
        RecursionError: If the document is nested too deeply.
    """
    if not isinstance(node, (dict, list)):
        return 1
    key = id(node)
    if key in sizes:
        return sizes[key]
    children = node.values() if isinstance(node, dict) else node
    size = 1
    for child in children:
        size += _expanded_size(child, sizes)
        if size > MAX_DOCUMENT_NODES:
            break
    sizes[key] = size
    return size


def _without_null(type_: Any) -> tuple[bool, Any]:
    """Remove ``null`` from the type of a parameter or field.

    Args:
        type_: The type.

    Returns:
        Whether the type allowed ``null`` (the parameter is optional), and the
        type without it.
    """
    if type_ == "null":
        return True, "null"
    if not isinstance(type_, list) or "null" not in type_:
        return False, type_
    rest = [member for member in type_ if member != "null"]
    if not rest:
        return True, "null"
    return True, rest[0] if len(rest) == 1 else rest


def _add_text(schema: dict[str, Any], element: Any) -> None:
    """Copy ``label`` and ``doc`` of a CWL element to a schema.

    Args:
        schema: The schema, which gets ``title`` and ``description``.
        element: Process, parameter, field or type with ``label`` and ``doc``.
    """
    label = getattr(element, "label", None)
    if isinstance(label, str) and label:
        schema["title"] = label
    doc = getattr(element, "doc", None)
    if isinstance(doc, list):
        doc = "\n".join(str(line) for line in doc)
    if isinstance(doc, str) and doc:
        schema["description"] = doc


def _is_expression(text: str) -> bool:
    """Tell whether a string contains a CWL expression.

    Args:
        text: The string.

    Returns:
        Whether it contains a parameter reference or an expression.
    """
    return "$(" in text or "${" in text


def _child(location: str, *keys: str) -> str:
    """Extend a JSON path by keys, in the notation of ``jsonschema``.

    Args:
        location: The JSON path.
        *keys: Keys to append.

    Returns:
        The extended path, e.g. ``$.properties['args.py']``.
    """
    for key in keys:
        if _PLAIN_KEY.fullmatch(key):
            location += f".{key}"
        else:
            escaped = key.replace("\\", "\\\\").replace("'", "\\'")
            location += f"['{escaped}']"
    return location


def notes_as_dicts(notes: Iterable[ConversionNote]) -> list[dict[str, str]]:
    """Render conversion notes as JSON objects.

    Args:
        notes: The notes.

    Returns:
        One object per note, with ``message`` and ``location``.
    """
    return [{"message": note.message, "location": note.location} for note in notes]
