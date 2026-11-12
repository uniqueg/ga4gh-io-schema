"""Convert the inputs and outputs of WDL workflows and tasks to IO schemas.

:func:`load_document` parses a WDL document (versions 1.0, 1.1 and 1.2) with
`miniwdl <https://github.com/chanzuckerberg/miniwdl>`_, the optional
dependency of the ``wdl`` extra, and resolves its imports; :func:`to_ga4gh`
turns the inputs and outputs of its workflow, or of one of its tasks, into an
IO schema. WDL types become JSON Schema types (``File`` and ``Directory``
become file references), literal defaults become ``default``, and the
conventional keys of ``parameter_meta`` become annotations. The workflow or
task name goes into the entry point of ``x-ga4gh-workflow``, the declared WDL
type of each parameter into ``x-ga4gh-parameter``.

The conversion reports every decision that changes the meaning of the
schema, or that the author should check, as a :class:`Note`.
"""

import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema

from ga4gh_io_schema.validator import load_profile

#: Location in a JSON document, as keys and indexes.
Pointer = tuple[str | int, ...]

#: Versions of WDL that the converter accepts.
SUPPORTED_VERSIONS = ("1.0", "1.1", "1.2")

#: How to install the optional dependency.
INSTALL_HINT = "pip install 'ga4gh-io-schema[wdl]'"

#: Keys of ``parameter_meta`` objects that the converter maps.
META_KEYS = frozenset(
    {"description", "help", "label", "category", "choices", "suggestions"}
)

#: Values of the ``category`` key of ``parameter_meta`` that hide a parameter.
HIDDEN_CATEGORIES = frozenset({"advanced"})

#: Start of a URI with an authority (e.g., ``https://``, ``s3://``, ``drs://``);
#: other values with a colon (e.g., ``C:/data`` or ``sample:1.bam``) are paths.
_URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+://")
#: Imports that name a remote document: any scheme followed by ``//``, also
#: of one letter, so unlike :data:`_URI`, which needs two (``C://`` is a path).
_REMOTE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
#: Names that a JSON path can use without brackets.
_JSON_PATH_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class MissingDependencyError(ImportError):
    """miniwdl, the optional dependency of the ``wdl`` extra, isn't installed."""


class SourceError(ValueError):
    """A WDL document can't be loaded: syntax, types, imports or version.

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


class ImportReadError(SourceError):
    """An import of a WDL document can't be read: not found, or not UTF-8."""


class ConversionError(ValueError):
    """A WDL document can't be converted, as it is or with the given options.

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
        The JSON path, e.g. ``$.properties.inputs.properties['call.threads']``.
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


def miniwdl() -> ModuleType:
    """Import miniwdl, the optional dependency of the ``wdl`` extra.

    Returns:
        The ``WDL`` package of miniwdl.

    Raises:
        MissingDependencyError: If miniwdl isn't installed.
    """
    try:
        import WDL
    except ImportError as exc:
        raise MissingDependencyError(
            f"Converting WDL needs miniwdl; install it with: {INSTALL_HINT}"
        ) from exc
    return WDL


def load_document(
    source: str | Path,
    text: str,
    import_paths: Sequence[str | Path] = (),
) -> Any:
    """Parse and type-check a WDL document, with its imports.

    Imports are read from local files only, and only from the directory of
    the document and the directories of ``import_paths`` (and below them):
    a document can't make the converter read other files or fetch URLs.

    Args:
        source: Path of the document, or ``-`` for standard input; relative
            imports of a document from standard input are resolved against
            the current directory.
        text: Content of the document.
        import_paths: Further directories that imports are searched in and
            may be read from, e.g. the root of a repository whose documents
            import ``../tasks/…``.

    Returns:
        The document (a ``WDL.Tree.Document``).

    Raises:
        MissingDependencyError: If miniwdl isn't installed.
        SourceError: If the document or an import can't be read or parsed,
            doesn't type-check, or has an unsupported version of WDL.
    """
    wdl = miniwdl()
    if str(source) == "-":
        main_path = os.path.join(os.getcwd(), "stdin")
        uri = "-"
    else:
        main_path = os.path.abspath(source)
        uri = str(source)
    roots = [os.path.realpath(os.path.dirname(main_path))]
    roots += [os.path.realpath(path) for path in import_paths]

    async def read_source(uri: str, path: list[str], importer: Any) -> Any:
        """Read the document, or one of its imports, for miniwdl.

        Args:
            uri: The path of the document, or the URI of the import.
            path: Directories that imports are searched in.
            importer: The importing document; ``None`` for the document.

        Returns:
            The text and the absolute path (a ``ReadSourceResult``).

        Raises:
            SourceError: If the import is remote, or outside the allowed
                directories.
        """
        if importer is None:
            return wdl.Tree.ReadSourceResult(source_text=text, abspath=main_path)
        if _REMOTE.match(uri) and not uri.startswith("file://"):
            raise SourceError(
                f"Remote import '{uri}' isn't supported: download it and import "
                "it from a local file"
            )
        resolved = await wdl.Tree.resolve_file_import(uri, path, importer)
        real = os.path.realpath(resolved)
        if not any(real == root or real.startswith(root + os.sep) for root in roots):
            raise SourceError(
                f"Import '{uri}' is outside the directory of the document and "
                "the import paths: add its directory with --import-path"
            )
        return wdl.Tree.ReadSourceResult(
            source_text=Path(real).read_text(encoding="utf-8"), abspath=resolved
        )

    try:
        document = wdl.load(
            uri, path=[str(path) for path in import_paths], read_source=read_source
        )
    except wdl.Error.ImportError as exc:
        raise _import_error(exc) from exc
    except wdl.Error.SyntaxError as exc:
        raise SourceError(f"WDL syntax error{_position(exc.pos)}: {exc}") from exc
    except wdl.Error.ValidationError as exc:
        raise SourceError(f"Invalid WDL{_position(exc.pos)}: {exc}") from exc
    except wdl.Error.MultipleValidationErrors as exc:
        first = exc.exceptions[0]
        raise SourceError(
            f"Invalid WDL{_position(first.pos)}: {first} "
            f"(and {len(exc.exceptions) - 1} more errors)"
        ) from exc
    version = document.wdl_version
    if version not in SUPPORTED_VERSIONS:
        raise SourceError(
            f"WDL version '{version or 'draft-2'}' isn't supported; supported "
            f"versions: {', '.join(SUPPORTED_VERSIONS)}"
        )
    return document


def _position(pos: Any) -> str:
    """Describe a position in a WDL document for messages.

    Args:
        pos: The position (a ``WDL.Error.SourcePosition``).

    Returns:
        `` in <uri> at line <n>, column <n>``.
    """
    return f" in {pos.uri} at line {pos.line}, column {pos.column}"


def _import_error(exc: BaseException) -> SourceError:
    """Describe a failed import, with the innermost cause.

    Args:
        exc: The ``WDL.Error.ImportError``, which may wrap others.

    Returns:
        An :class:`ImportReadError` if the import can't be read, else a
        :class:`SourceError`, with the message of the innermost error.
    """
    cause: BaseException = exc
    while cause.__cause__ is not None:
        cause = cause.__cause__
    if isinstance(cause, SourceError):
        return cause
    if isinstance(cause, FileNotFoundError):
        return ImportReadError(f"{exc}: file not found")
    if isinstance(cause, OSError):
        return ImportReadError(f"{exc}: {cause.strerror or cause}")
    if isinstance(cause, UnicodeDecodeError):
        return ImportReadError(f"{exc}: not UTF-8 text")
    # A syntax or type error of the imported document
    return SourceError(f"{exc}: {cause}")


def descriptor_checksum(content: str | bytes) -> str:
    """Compute the SHA-256 checksum of a WDL document, for drift detection.

    Args:
        content: The bytes of the document, as TRS serves them, or its text,
            which is encoded in UTF-8.

    Returns:
        The hex-encoded SHA-256 digest.
    """
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def to_ga4gh(
    document: Any,
    task: str | None = None,
    nested_inputs: bool = False,
    checksum: str | None = None,
) -> Conversion:
    """Convert the inputs and outputs of a WDL workflow or task to an IO schema.

    Args:
        document: The document, from :func:`load_document`.
        task: Name of the task to convert instead of the workflow; needed for
            documents without a workflow and with several tasks.
        nested_inputs: Whether to include the optional inputs of calls that
            the workflow doesn't set (e.g., ``align.threads``), as hidden
            parameters; required inputs of calls that the workflow doesn't
            set are always included.
        checksum: SHA-256 checksum of the document (see
            :func:`descriptor_checksum`), for ``x-ga4gh-workflow``.

    Returns:
        The IO schema, and the notes of the conversion.

    Raises:
        MissingDependencyError: If miniwdl isn't installed.
        ConversionError: If the document has no workflow or task to convert,
            or a type that has no equivalent.
    """
    return _Converter(miniwdl(), document).convert(task, nested_inputs, checksum)


def convert(
    source: str | Path,
    text: str,
    task: str | None = None,
    nested_inputs: bool = False,
    import_paths: Sequence[str | Path] = (),
    checksum: str | None = None,
) -> Conversion:
    """Load a WDL document and convert it to an IO schema.

    Combines :func:`load_document`, :func:`descriptor_checksum` and
    :func:`to_ga4gh`.

    Args:
        source: Path of the document, or ``-`` for standard input.
        text: Content of the document.
        task: See :func:`to_ga4gh`.
        nested_inputs: See :func:`to_ga4gh`.
        import_paths: See :func:`load_document`.
        checksum: SHA-256 checksum of the bytes of the document; by default,
            that of ``text`` in UTF-8, which differs from the bytes if
            reading the file changed its line endings.

    Returns:
        The IO schema, and the notes of the conversion.

    Raises:
        MissingDependencyError: If miniwdl isn't installed.
        SourceError: If the document can't be loaded.
        ConversionError: If the document can't be converted.
    """
    document = load_document(source, text, import_paths)
    if checksum is None:
        checksum = descriptor_checksum(text)
    return to_ga4gh(document, task, nested_inputs, checksum)


class _Converter:
    """Conversion of one WDL document.

    Attributes:
        wdl: The ``WDL`` package of miniwdl.
        document: The document.
        notes: Notes of the conversion so far.
        null_values: Whether optional items of lists of the parameter being
            converted may be ``null`` (inputs), or not (outputs, whose
            normalisers drop them).
    """

    def __init__(self, wdl: ModuleType, document: Any) -> None:
        """Initialise the conversion.

        Args:
            wdl: The ``WDL`` package of miniwdl.
            document: The document.
        """
        self.wdl = wdl
        self.document = document
        self.notes: list[Note] = []
        self.null_values = True

    def note(self, message: str, pointer: Pointer) -> None:
        """Add a note.

        Args:
            message: What the converter did, and why.
            pointer: Location of the schema in the IO schema.
        """
        self.notes.append(Note(message=message, location=json_path(pointer)))

    def convert(
        self, task: str | None, nested_inputs: bool, checksum: str | None
    ) -> Conversion:
        """Convert the workflow or task.

        Args:
            task: See :func:`to_ga4gh`.
            nested_inputs: See :func:`to_ga4gh`.
            checksum: See :func:`to_ga4gh`.

        Returns:
            The IO schema, and the notes of the conversion.
        """
        entry = self._entry(task)
        workflow: dict[str, Any] = {
            "descriptor_type": "WDL",
            "descriptor_type_version": self.document.wdl_version,
            "entry_point": entry.name,
        }
        if checksum is not None:
            workflow["checksum"] = [{"type": "sha-256", "checksum": checksum}]
        schema: dict[str, Any] = {
            "$schema": load_profile()["$id"],
            "title": entry.name,
        }
        description = self._meta_value(entry.meta.get("description"))
        if isinstance(description, str) and description:
            schema["description"] = description
        schema["x-ga4gh-workflow"] = workflow
        schema["type"] = "object"
        schema["properties"] = {
            "inputs": self._inputs(entry, nested_inputs),
            "outputs": self._outputs(entry),
        }
        return Conversion(schema=schema, notes=self.notes)

    def _entry(self, task: str | None) -> Any:
        """Choose the workflow or task to convert.

        Args:
            task: Name of the task, if one is chosen.

        Returns:
            The workflow or task (a ``WDL.Tree.Workflow`` or ``WDL.Tree.Task``).

        Raises:
            ConversionError: If the task doesn't exist, a task is chosen in a
                document with a workflow, or there's no single workflow or
                task to convert.
        """
        tasks = self.document.tasks
        workflow = self.document.workflow
        if task is not None and workflow is not None:
            raise ConversionError(
                f"The document has a workflow ({workflow.name}), which is its "
                "entry point: --task is only for documents without a workflow"
            )
        if task is not None:
            for candidate in tasks:
                if candidate.name == task:
                    return candidate
            raise ConversionError(f"The document has no task '{task}'")
        if workflow is not None:
            return workflow
        if len(tasks) == 1:
            return tasks[0]
        if not tasks:
            raise ConversionError("The document has no workflow and no task")
        names = ", ".join(sorted(candidate.name for candidate in tasks))
        raise ConversionError(
            f"The document has no workflow and several tasks ({names}): choose "
            "one with --task"
        )

    def _inputs(self, entry: Any, nested_inputs: bool) -> dict[str, Any]:
        """Convert the inputs of the workflow or task.

        Args:
            entry: The workflow or task.
            nested_inputs: See :func:`to_ga4gh`.

        Returns:
            The schema of ``inputs``.
        """
        properties: dict[str, Any] = {}
        required: list[str] = []
        for decl in self._declared_inputs(entry):
            pointer: Pointer = ("properties", "inputs", "properties", decl.name)
            properties[decl.name] = self._parameter(
                decl, entry.parameter_meta, pointer, is_input=True
            )
            if decl.expr is None and not decl.type.optional:
                required.append(decl.name)
        nested_required = {
            binding.name for binding in entry.required_inputs if "." in binding.name
        }
        nested = [
            binding
            for binding in entry.available_inputs
            if "." in binding.name
            and not binding.name.rpartition(".")[2].startswith("_")
            and (nested_inputs or binding.name in nested_required)
        ]
        for binding in nested:
            decl = binding.value
            pointer = ("properties", "inputs", "properties", binding.name)
            parent_meta = getattr(decl.parent, "parameter_meta", {})
            schema = self._parameter(decl, parent_meta, pointer, is_input=True)
            if binding.name in nested_required:
                required.append(binding.name)
                self.note(
                    "A required input of a call that the workflow doesn't set; "
                    "it is a parameter of the workflow",
                    pointer,
                )
            else:
                schema["x-ga4gh-hidden"] = True
            properties[binding.name] = schema
        if nested and self.document.wdl_version == "1.2":
            self.note(
                "The workflow has inputs of calls, which WDL 1.2 allows only if "
                "the hints section sets allow_nested_inputs: true; the converter "
                "can't check hints",
                ("properties", "inputs"),
            )
        elif nested and not self._allows_nested_inputs(entry):
            self.note(
                "The workflow has inputs of calls, but its meta section doesn't "
                "set allowNestedInputs: engines that follow WDL 1.1 reject them",
                ("properties", "inputs"),
            )
        inputs: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            inputs["required"] = required
        inputs["additionalProperties"] = False
        return inputs

    def _declared_inputs(self, entry: Any) -> list[Any]:
        """Return the inputs of the workflow or task itself.

        Without an input section, the declarations of a workflow or task
        that the engine lets clients set are its inputs (miniwdl accepts
        such documents, as engines do).

        Args:
            entry: The workflow or task.

        Returns:
            The declarations of the inputs (``WDL.Tree.Decl``), in order.
        """
        if entry.inputs is not None:
            return list(entry.inputs)
        decls = [
            binding.value
            for binding in entry.available_inputs
            if "." not in binding.name and not binding.name.startswith("_")
        ]
        if decls:
            self.note(
                "The workflow or task has no input section; its declarations "
                "that clients may set are its inputs",
                ("properties", "inputs"),
            )
        return decls

    def _allows_nested_inputs(self, entry: Any) -> bool:
        """Check whether a workflow may receive inputs of its calls.

        Args:
            entry: The workflow.

        Returns:
            Whether the WDL version is 1.0 (whose engines accept inputs of
            calls), or ``allowNestedInputs`` of the ``meta`` section is true.
        """
        if self.document.wdl_version == "1.0":
            return True
        return self._meta_value(entry.meta.get("allowNestedInputs")) is True

    def _outputs(self, entry: Any) -> dict[str, Any]:
        """Convert the outputs of the workflow or task.

        Args:
            entry: The workflow or task.

        Returns:
            The schema of ``outputs``.
        """
        properties: dict[str, Any] = {}
        required: list[str] = []
        for decl in entry.outputs or []:
            pointer: Pointer = ("properties", "outputs", "properties", decl.name)
            properties[decl.name] = self._parameter(
                decl, entry.parameter_meta, pointer, is_input=False
            )
            if not decl.type.optional:
                required.append(decl.name)
        outputs: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            outputs["required"] = required
        outputs["additionalProperties"] = False
        return outputs

    def _parameter(
        self,
        decl: Any,
        parameter_meta: dict[str, Any],
        pointer: Pointer,
        is_input: bool,
    ) -> dict[str, Any]:
        """Convert one input or output declaration.

        Args:
            decl: The declaration (a ``WDL.Tree.Decl``).
            parameter_meta: The ``parameter_meta`` section that describes it.
            pointer: Location of its schema in the IO schema.
            is_input: Whether it is an input; outputs get no defaults, and
                neither they nor the items of their lists allow ``null``:
                normalisers leave out the ``null`` values that engines report
                there.

        Returns:
            The schema of the parameter.
        """
        self.null_values = is_input
        schema = self._type(decl.type, pointer, nullable=False)
        self._apply_meta(
            schema, parameter_meta.get(decl.name), decl.type, pointer, is_input
        )
        if is_input and decl.expr is not None:
            self._default(schema, decl, pointer)
        schema["x-ga4gh-parameter"] = {"type": str(decl.type)}
        return schema

    def _type(self, wdl_type: Any, pointer: Pointer, nullable: bool) -> dict[str, Any]:
        """Convert a WDL type to a schema.

        Args:
            wdl_type: The type (a ``WDL.Type.Base``).
            pointer: Location of the schema in the IO schema.
            nullable: Whether an optional type also accepts ``null``: values
                in maps, pairs and structs may be ``null`` if their type is
                optional, and so may items of lists of inputs; optional
                inputs and outputs are left out instead, and normalisers
                drop the ``null`` items of lists of outputs.

        Returns:
            The schema.

        Raises:
            ConversionError: If the type has no equivalent.
        """
        types = self.wdl.Type
        schema: dict[str, Any]
        if isinstance(wdl_type, types.File):
            schema = {"type": "string", "x-ga4gh-file": {"kind": "file"}}
        elif isinstance(wdl_type, types.Directory):
            schema = {"type": "string", "x-ga4gh-file": {"kind": "directory"}}
        elif isinstance(wdl_type, types.String):
            schema = {"type": "string"}
        elif isinstance(wdl_type, types.Int):
            schema = {"type": "integer"}
        elif isinstance(wdl_type, types.Float):
            schema = {"type": "number"}
        elif isinstance(wdl_type, types.Boolean):
            schema = {"type": "boolean"}
        elif isinstance(wdl_type, types.Array):
            schema = {
                "type": "array",
                "items": self._type(
                    wdl_type.item_type, (*pointer, "items"), self.null_values
                ),
            }
            if wdl_type.nonempty:
                schema["minItems"] = 1
        elif isinstance(wdl_type, types.Map):
            schema = self._map(wdl_type, pointer)
        elif isinstance(wdl_type, types.Pair):
            schema = {
                "type": "object",
                "properties": {
                    "left": self._type(
                        wdl_type.left_type, (*pointer, "properties", "left"), True
                    ),
                    "right": self._type(
                        wdl_type.right_type, (*pointer, "properties", "right"), True
                    ),
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            }
        elif isinstance(wdl_type, types.StructInstance):
            schema = self._struct(wdl_type, pointer)
        else:
            raise ConversionError(
                f"The WDL type {wdl_type} has no equivalent in an IO schema",
                json_path(pointer),
            )
        if nullable and wdl_type.optional:
            return _nullable(schema)
        return schema

    def _map(self, wdl_type: Any, pointer: Pointer) -> dict[str, Any]:
        """Convert a ``Map`` type to an object schema.

        JSON objects have string keys, so WDL allows only keys that coerce
        to and from ``String`` in inputs and outputs: ``String``, ``File``
        and ``Directory``.

        Args:
            wdl_type: The type (a ``WDL.Type.Map``).
            pointer: Location of the schema in the IO schema.

        Returns:
            The schema.

        Raises:
            ConversionError: If the keys aren't of one of these types.
        """
        types = self.wdl.Type
        key_type, value_type = wdl_type.item_type
        schema: dict[str, Any] = {"type": "object"}
        if isinstance(key_type, (types.File, types.Directory)):
            self.note(
                f"The keys of {wdl_type} refer to files, but object keys can't "
                "be file references; they are plain strings",
                pointer,
            )
        elif not isinstance(key_type, types.String):
            raise ConversionError(
                f"The keys of {wdl_type} have no equivalent in JSON, whose "
                "object keys are strings",
                json_path(pointer),
            )
        schema["additionalProperties"] = self._type(
            value_type, (*pointer, "additionalProperties"), True
        )
        return schema

    def _struct(self, wdl_type: Any, pointer: Pointer) -> dict[str, Any]:
        """Convert a struct type to an object schema.

        The ``meta`` and ``parameter_meta`` sections of the struct (WDL 1.2)
        describe the object and its members.

        Args:
            wdl_type: The type (a ``WDL.Type.StructInstance``).
            pointer: Location of the schema in the IO schema.

        Returns:
            The schema.
        """
        typedef = self.document.struct_typedefs.get(wdl_type.type_name)
        meta = getattr(typedef, "meta", None) or {}
        member_meta = getattr(typedef, "parameter_meta", None) or {}
        schema: dict[str, Any] = {"type": "object"}
        description = self._meta_value(meta.get("description"))
        if isinstance(description, str) and description:
            schema["description"] = description
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, member_type in wdl_type.members.items():
            member_pointer = (*pointer, "properties", name)
            member = self._type(member_type, member_pointer, True)
            self._apply_meta(
                member, member_meta.get(name), member_type, member_pointer, False
            )
            properties[name] = member
            if not member_type.optional:
                required.append(name)
        schema["properties"] = properties
        if required:
            schema["required"] = required
        schema["additionalProperties"] = False
        return schema

    def _meta_value(self, value: Any) -> Any:
        """Turn a value of a ``meta`` or ``parameter_meta`` section into JSON.

        miniwdl keeps strings, arrays and objects as Python values, but
        booleans, numbers and ``null`` as literal expressions.

        Args:
            value: The value.

        Returns:
            The value as JSON data.
        """
        if isinstance(value, dict):
            return {key: self._meta_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._meta_value(item) for item in value]
        if isinstance(value, self.wdl.Expr.Base):
            # Meta values are literals; the text of the expression otherwise
            return getattr(value.literal, "json", str(value))
        return value

    def _apply_meta(
        self,
        schema: dict[str, Any],
        meta: Any,
        wdl_type: Any,
        pointer: Pointer,
        is_input: bool,
    ) -> None:
        """Map the ``parameter_meta`` of a parameter to annotations.

        A string is the description. Of an object, ``description`` and
        ``help`` become the description, ``label`` the title, the
        ``category`` ``advanced`` hides the parameter, and, for inputs of
        primitive types, ``choices`` become ``enum`` and ``suggestions``
        ``examples``. Other keys are dropped with a note.

        Args:
            schema: The schema of the parameter, changed in place.
            meta: The entry of ``parameter_meta``, if any.
            wdl_type: The WDL type of the parameter.
            pointer: Location of the schema in the IO schema.
            is_input: Whether the parameter is an input.
        """
        if meta is None:
            return
        value = self._meta_value(meta)
        if isinstance(value, str):
            schema["description"] = value
            return
        if not isinstance(value, dict):
            self.note(
                "The parameter_meta entry is neither a string nor an object; "
                "it is dropped",
                pointer,
            )
            return
        dropped = sorted(set(value) - META_KEYS)
        texts = [
            value[key]
            for key in ("description", "help")
            if isinstance(value.get(key), str) and value[key]
        ]
        if texts:
            schema["description"] = "\n\n".join(texts)
        label = value.get("label")
        if isinstance(label, str) and label:
            schema["title"] = label
        if value.get("category") in HIDDEN_CATEGORIES:
            schema["x-ga4gh-hidden"] = True
        for key, keyword in (("choices", "enum"), ("suggestions", "examples")):
            if key not in value:
                continue
            values = value[key]
            if is_input and self._fits(values, schema, wdl_type):
                schema[keyword] = values
            else:
                dropped.append(key)
        if dropped:
            self.note(
                "parameter_meta keys without an equivalent are dropped: "
                + ", ".join(dropped),
                pointer,
            )

    def _fits(self, values: Any, schema: dict[str, Any], wdl_type: Any) -> bool:
        """Check whether ``choices`` or ``suggestions`` can be converted.

        Args:
            values: The values.
            schema: The schema of the parameter.
            wdl_type: The WDL type of the parameter.

        Returns:
            Whether the values are a non-empty list of values of a primitive
            type other than ``File`` and ``Directory`` that the schema
            accepts.
        """
        types = self.wdl.Type
        primitive = (types.String, types.Int, types.Float, types.Boolean)
        if not isinstance(wdl_type, primitive) or not isinstance(values, list):
            return False
        validator = jsonschema.Draft202012Validator({"type": schema["type"]})
        return bool(values) and all(validator.is_valid(item) for item in values)

    def _default(self, schema: dict[str, Any], decl: Any, pointer: Pointer) -> None:
        """Convert the default of an input, if it is a literal.

        Args:
            schema: The schema of the input, changed in place.
            decl: The declaration.
            pointer: Location of the schema in the IO schema.
        """
        if isinstance(decl.expr, self.wdl.Expr.Null):
            return
        literal = decl.expr.literal
        if literal is None:
            self.note(
                f"The default is an expression ({decl.expr}) that the engine "
                "evaluates; it is left out, and the input is optional",
                pointer,
            )
            return
        value = literal.json
        types = self.wdl.Type
        if isinstance(decl.type, (types.File, types.Directory)):
            if not _URI.match(value):
                self.note(
                    f"The default '{value}' is a path, which the engine resolves "
                    "on the execution side; it is left out, and the input is "
                    "optional",
                    pointer,
                )
                return
        elif _has_file_values(decl.type, value, types):
            self.note(
                "The default contains file references, which aren't converted; "
                "it is left out, and the input is optional",
                pointer,
            )
            return
        if not jsonschema.Draft202012Validator(schema).is_valid(value):
            self.note(
                f"The default {json.dumps(value)} isn't valid against the schema "
                "of the input (WDL coerces it); it is left out, and the input is "
                "optional",
                pointer,
            )
            return
        schema["default"] = value


def _has_file_values(wdl_type: Any, value: Any, types: ModuleType) -> bool:
    """Check whether a value holds strings in places of files or directories.

    Args:
        wdl_type: The WDL type of the value.
        value: The value, as JSON data.
        types: The ``WDL.Type`` module of miniwdl.

    Returns:
        Whether the value, or an item, key, side or member of it, is a string
        where the type has ``File`` or ``Directory``.
    """
    if isinstance(wdl_type, (types.File, types.Directory)):
        return isinstance(value, str)
    if isinstance(wdl_type, types.Array) and isinstance(value, list):
        return any(_has_file_values(wdl_type.item_type, item, types) for item in value)
    if isinstance(wdl_type, types.Map) and isinstance(value, dict):
        key_type, value_type = wdl_type.item_type
        return any(
            _has_file_values(key_type, key, types)
            or _has_file_values(value_type, item, types)
            for key, item in value.items()
        )
    if isinstance(wdl_type, types.Pair) and isinstance(value, dict):
        return _has_file_values(
            wdl_type.left_type, value.get("left"), types
        ) or _has_file_values(wdl_type.right_type, value.get("right"), types)
    if isinstance(wdl_type, types.StructInstance) and isinstance(value, dict):
        return any(
            _has_file_values(member_type, value.get(name), types)
            for name, member_type in wdl_type.members.items()
        )
    return False


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a schema also accept ``null``.

    Args:
        schema: The schema.

    Returns:
        The schema with ``null`` added to its type, or, for file references
        (whose type must be ``string``), ``anyOf`` the schema and ``null``.
    """
    if "x-ga4gh-file" in schema:
        return {"anyOf": [schema, {"type": "null"}]}
    return {**schema, "type": [schema["type"], "null"]}
