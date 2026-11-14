"""Convert nf-schema parameter schemas (``nextflow_schema.json``) to IO schemas.

Nextflow pipelines describe their parameters with a JSON Schema,
``nextflow_schema.json``, checked by the nf-schema plugin (Draft 2020-12) or
its predecessor nf-validation (Draft 7). :func:`to_ga4gh` turns it into an
IO schema: the parameters become ``inputs``, upgraded to JSON Schema Draft
2020-12, with their groups kept as ``$defs`` of the IO schema; nf-schema's
keywords become those of the profile (e.g., ``format: file-path`` a file
reference, ``help_text`` a Markdown ``description``, ``hidden``
``x-ga4gh-hidden``), and the schema of a sample sheet (``schema``) the
experimental ``x-ga4gh-tabular-schema`` hint. Engine-local checks (e.g.,
``exists``) are dropped. nf-schema doesn't describe outputs, so ``outputs``
holds only the file outputs given as options.

The conversion reports every decision that changes the meaning of the
schema, or that the author should check, as a :class:`Note`.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ga4gh_io_schema.converters.common import (
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
    DATA_KEYWORDS,
    NOT_ON_FILES,
    SOURCE_NAME_MAPS,
    SchemaConverter,
    check_json,
    file_reference_problem,
    pointer_reference,
)
from ga4gh_io_schema.validator import load_profile

#: Kinds of file references, by the ``format`` of nf-schema.
FILE_FORMATS = {"file-path": "file", "directory-path": "directory", "path": "file"}

#: Keywords of nf-schema that are dropped, with one note for all places, and
#: why.
DROPPED = {
    "fa_icon": (
        "the profile has no icon keyword since version 0.3: icons are a "
        "choice of the portal"
    ),
    "exists": (
        "Nextflow checks it where the pipeline runs, on the paths that the "
        "pipeline sees, and skips it for object-store paths (e.g., S3, Azure "
        "or Google Cloud URIs); the profile leaves such checks to the engine"
    ),
    "meta": (
        "it maps a column of a sample sheet to the meta map of the "
        "pipeline's channels, which is part of the pipeline, not of its inputs"
    ),
}

#: Keywords of nf-schema (``uniqueEntries``) and nf-validation (``unique``)
#: that require unique values across the rows of a sample sheet.
UNIQUE_KEYWORDS = ("uniqueEntries", "unique")

# Media types, as the profile's mediaType allows them.
_MEDIA_TYPE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}$"
)


def load_schema(text: str, name: str) -> Any:
    """Parse an nf-schema file (JSON).

    Args:
        text: The schema.
        name: Name of the source in messages (e.g., its path).

    Returns:
        The parsed schema.

    Raises:
        SourceError: If the text isn't valid JSON, holds values that aren't
            JSON data (e.g., ``NaN``), or holds too many values.
    """
    try:
        data = json.loads(text)
    # ValueError: also numbers that Python won't parse (too many digits)
    except ValueError as exc:
        raise SourceError(f"Invalid JSON - {name}: {exc}") from exc
    check_json(data, name)
    return data


def sample_sheet_paths(schema: Any) -> list[str]:
    """List the sample-sheet schemas that an nf-schema file names.

    The paths are the values of the ``schema`` keyword (e.g.,
    ``assets/schema_input.json``), relative to the directory of the pipeline,
    as nf-schema reads them; instance data (e.g., ``default``) and property
    names aren't searched.

    Args:
        schema: The nf-schema file.

    Returns:
        The paths, sorted, each once.
    """
    paths: set[str] = set()
    # Each value comes with whether it maps names to schemas.
    stack: list[tuple[Any, bool]] = [(schema, False)]
    while stack:
        node, names = stack.pop()
        if isinstance(node, list):
            stack.extend((item, False) for item in node)
        elif isinstance(node, dict) and names:
            stack.extend((value, False) for value in node.values())
        elif isinstance(node, dict):
            if isinstance(node.get("schema"), str):
                paths.add(node["schema"])
            stack.extend(
                (value, key in SOURCE_NAME_MAPS)
                for key, value in node.items()
                if key not in DATA_KEYWORDS
            )
    return sorted(paths)


def to_ga4gh(
    schema: Any,
    sample_sheets: Mapping[str, Any] | None = None,
    *,
    directories: Iterable[str] = (),
    outputs: Sequence[Output] = (),
) -> Conversion:
    """Convert an nf-schema file to an IO schema.

    Args:
        schema: The nf-schema file (``nextflow_schema.json``; Draft 7 or
            2020-12, or any other draft from 4 on).
        sample_sheets: The sample-sheet schemas, by the value of the
            ``schema`` keyword that names them (see
            :func:`sample_sheet_paths`); one that isn't given gets no tabular
            hint, with a note.
        directories: Parameters with ``format: path`` (a file or a
            directory) that are directories; the others are files.
        outputs: File outputs of the pipeline, found by glob relative to its
            output directory (nf-schema doesn't describe outputs).

    Returns:
        The IO schema, valid against the GA4GH IO Profile unless the source
        uses ``x-ga4gh-*`` keywords wrongly, or an output's glob is invalid,
        and the notes of the conversion.

    Raises:
        ConversionError: If the schema can't be converted, ``directories``
            names a parameter that doesn't exist or hasn't ``format: path``,
            or two outputs have the same name.
    """
    return _Converter(sample_sheets or {}, directories).convert(schema, outputs)


class _Converter(SchemaConverter):
    """State of one conversion: the options, the notes, the current source."""

    def __init__(self, sheets: Mapping[str, Any], directories: Iterable[str]) -> None:
        """Store the options.

        Args:
            sheets: The sample-sheet schemas, by path.
            directories: Parameters with ``format: path`` that are
                directories.
        """
        super().__init__()
        self.sheets = sheets
        self.directories = set(directories)
        # Parameters, and whether they have "format: path"
        self.parameters: dict[str, bool] = {}
        # Places of the sample-sheet schemas to convert, and their paths
        self.pending: list[tuple[Pointer, str]] = []
        # Places of the keywords that get one note for all places
        self.places: dict[str, list[Pointer]] = {}
        # Where each sample-sheet schema is converted (the first time)
        self.attached: dict[str, Pointer] = {}
        # Whether a sample-sheet schema is being converted
        self.in_sheet = False

    def convert(self, source: Any, outputs: Sequence[Output]) -> Conversion:
        """Convert the nf-schema file and its sample-sheet schemas.

        Args:
            source: The nf-schema file.
            outputs: The file outputs of the pipeline.

        Returns:
            The IO schema and the notes.

        Raises:
            ConversionError: If the schema can't be converted, or an option
                is wrong.
        """
        if not isinstance(source, dict):
            raise ConversionError("The nf-schema must be a JSON object.")
        inputs_at: Pointer = ("properties", "inputs")
        self._begin(source, prefix=inputs_at, defs_prefix=())
        inputs = self._schema(source, inputs_at, "", root=True)
        defs = inputs.pop("$defs", None)
        inputs.setdefault("type", "object")
        for name in sorted(self.directories):
            if not self.parameters.get(name, False):
                raise ConversionError(
                    f"No parameter '{name}' with 'format: path' (--directory)."
                )
        schema: dict[str, Any] = {
            "$schema": load_profile()["$id"],
            # The engine binding; the TRS fields are known only once the
            # pipeline is published (see the converter documentation)
            "x-ga4gh-workflow": {"descriptor_type": "NFL"},
            "type": "object",
            "properties": {
                "inputs": inputs,
                "outputs": outputs_schema(outputs),
            },
        }
        if defs is not None:
            schema["$defs"] = defs
        for pointer, path in self.pending:
            self._attach(schema, pointer, path)
        self._check_references(schema, schema, (), {})
        self._summarise()
        if not outputs:
            self.note(
                "nf-schema doesn't describe outputs: 'outputs' is left empty; "
                "name the file outputs of the pipeline with --out-file, "
                "--out-files or --out-dir.",
                ("properties", "outputs"),
            )
        return Conversion(schema=schema, notes=self.notes)

    def _summarise(self) -> None:
        """Add one note for each keyword that is dropped or kept everywhere."""
        for keyword, places in self.places.items():
            where = "here" if len(places) == 1 else f"here and {len(places) - 1} more"
            if keyword == "pattern":
                message = (
                    f"Kept 'pattern' of file references ({where}): it applies "
                    "to the value, so values whose last part isn't the file "
                    "name (e.g., DRS identifiers) fail it; remove it where "
                    "such values must work."
                )
            else:
                message = f"Dropped '{keyword}' ({where}): {DROPPED[keyword]}."
            self.note(message, places[0])

    def _attach(self, schema: dict[str, Any], pointer: Pointer, path: str) -> None:
        """Convert a sample-sheet schema into the tabular hint of a parameter.

        Args:
            schema: The IO schema.
            pointer: Location of the file reference in the IO schema.
            path: Path of the sample-sheet schema, as the source names it.
        """
        node: Any = schema
        for part in pointer:
            if isinstance(node, list) and isinstance(part, int) and part < len(node):
                node = node[part]
            elif isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return  # in a keyword that was dropped (and noted)
        at: Pointer = (*pointer, "x-ga4gh-tabular-schema")
        if path in self.attached:
            node["x-ga4gh-tabular-schema"] = {
                "$ref": pointer_reference(self.attached[path])
            }
            self.note(
                f"The sample-sheet schema '{path}' is a tabular hint at another "
                "place too: referenced, not converted again.",
                at,
            )
            return
        if path not in self.sheets:
            self.note(
                f"The sample-sheet schema '{path}' wasn't found (the command "
                "looks for it in the directory of the pipeline, --pipeline-dir): "
                "no tabular hint.",
                pointer,
            )
            return
        self.attached[path] = at
        self.in_sheet = True
        try:
            self._begin(self.sheets[path], prefix=at, defs_prefix=at)
            node["x-ga4gh-tabular-schema"] = self._schema(
                self.sheets[path], at, None, root=True
            )
        finally:
            self.in_sheet = False
        self.note(
            f"The sample-sheet schema '{path}' is the experimental tabular hint "
            "of the parameter: a schema of the whole sheet, for clients; it "
            "isn't checked against the sheet.",
            at,
        )

    def _parameter(self, pointer: Pointer) -> str | None:
        """Tell the parameter whose schema is at a location, if any.

        Parameters are the properties of the root of the nf-schema file, and
        those of its groups (the schemas of ``$defs`` or ``definitions``).

        Args:
            pointer: Location of a schema in the IO schema.

        Returns:
            The name of the parameter, or ``None``.
        """
        # At (properties, inputs, properties, NAME) or ($defs, GROUP,
        # properties, NAME): the conversion puts nothing else at such places
        if self.in_sheet or len(pointer) != 4 or pointer[2] != "properties":
            return None
        return str(pointer[3])

    def _keywords(
        self, node: dict[str, Any], pointer: Pointer, name: str | None, root: bool
    ) -> dict[str, Any]:
        """Convert the keywords of a schema, with those of nf-schema.

        Args:
            node: The schema in the source.
            pointer: Location of the converted schema in the IO schema.
            name: Dotted path of the property, ``""`` or ``None`` (see
                :meth:`_schema`).
            root: Whether it's the root of the source.

        Returns:
            The converted schema.
        """
        result = super()._keywords(node, pointer, name, root)
        parameter = self._parameter(pointer)
        if parameter is not None:
            self.parameters[parameter] = result.get("format") == "path"
        for keyword in DROPPED:
            if keyword in result:
                del result[keyword]
                self.places.setdefault(keyword, []).append(pointer)
        for keyword in UNIQUE_KEYWORDS:
            if keyword in result:
                del result[keyword]
                self.note(
                    f"Dropped '{keyword}': it requires the combination of the "
                    "values of some columns to be unique across the rows, "
                    "which isn't 'uniqueItems' (that requires whole rows to "
                    "differ); the profile has no equivalent.",
                    pointer,
                )
        self._help_text(result, pointer)
        self._rename(result, "hidden", "x-ga4gh-hidden", bool, pointer)
        self._rename(result, "errorMessage", "x-ga4gh-error-message", str, pointer)
        return self._file(result, pointer, parameter)

    def _help_text(self, result: dict[str, Any], pointer: Pointer) -> None:
        """Append ``help_text`` to the description, as Markdown.

        Args:
            result: The converted schema.
            pointer: Location of the schema in the IO schema.
        """
        if "help_text" not in result:
            return
        text = result.pop("help_text")
        if not isinstance(text, str):
            self.note("Dropped 'help_text': not a string.", pointer)
            return
        parts = [
            part
            for part in (result.get("description"), text)
            if isinstance(part, str) and part
        ]
        result["description"] = "\n\n".join(parts)
        result.setdefault("x-ga4gh-description-format", "markdown")

    def _rename(
        self,
        result: dict[str, Any],
        keyword: str,
        target: str,
        kind: type,
        pointer: Pointer,
    ) -> None:
        """Rename a keyword of nf-schema to its keyword of the profile.

        Args:
            result: The converted schema.
            keyword: The keyword of nf-schema.
            target: The keyword of the profile.
            kind: Type of the values that the profile allows.
            pointer: Location of the schema in the IO schema.
        """
        if keyword not in result:
            return
        value = result.pop(keyword)
        if not isinstance(value, kind):
            self.note(
                f"Dropped '{keyword}': '{target}' takes a {kind.__name__}, not "
                f"{json.dumps(value)}.",
                pointer,
            )
        elif target in result:
            self.note(f"Dropped '{keyword}': the schema has '{target}'.", pointer)
        else:
            result[target] = value

    def _file(
        self, result: dict[str, Any], pointer: Pointer, parameter: str | None
    ) -> dict[str, Any]:
        """Mark a schema with a path ``format`` as a file reference.

        Also converts ``mimetype`` and ``schema`` (a sample sheet), which
        only file references can have.

        Args:
            result: The converted schema.
            pointer: Location of the schema in the IO schema.
            parameter: The parameter whose schema it is, if any.

        Returns:
            The schema, marked if it has a path ``format``.

        Raises:
            ConversionError: If ``--directory`` names a parameter that
                hasn't ``format: path``.
        """
        extras = {
            key: result.pop(key) for key in ("mimetype", "schema") if key in result
        }
        form = result.get("format")
        if form == "file-path-pattern":
            del result["format"]
            self.note(
                "Dropped 'format: file-path-pattern': a glob isn't a reference "
                "to one file; kept as a plain string.",
                pointer,
            )
        kind = FILE_FORMATS.get(form) if isinstance(form, str) else None
        problem = None if kind is None else file_reference_problem(result)
        if kind is not None and "x-ga4gh-file" in result:
            problem = "it has 'x-ga4gh-file' already"
        if kind is None or problem is not None:
            if parameter in self.directories:
                raise ConversionError(
                    f"'{parameter}' (--directory) can't be a directory: it "
                    f"isn't marked as a file reference with 'format: path'.",
                    json_path(pointer),
                )
            if problem is not None:
                self.note(
                    f"Not marked as a file reference ('format: {form}'): {problem}.",
                    pointer,
                )
            self._drop_extras(extras, pointer)
            return result
        if form == "path":
            kind = self._path_kind(parameter, pointer)
        elif parameter in self.directories:
            raise ConversionError(
                f"'{parameter}' (--directory) has 'format: {form}', not "
                "'format: path'.",
                json_path(pointer),
            )
        dropped = [key for key in NOT_ON_FILES[1:] if key in result]
        if dropped:
            self.note(
                "Dropped "
                + ", ".join(f"'{key}'" for key in dropped)
                + ": file references can't have it.",
                pointer,
            )
        marked = {
            key: value for key, value in result.items() if key not in NOT_ON_FILES
        }
        marked["x-ga4gh-file"] = self._reference(
            kind, extras, pointer, "x-ga4gh-tabular-schema" in marked
        )
        if "pattern" in marked:
            self.places.setdefault("pattern", []).append(pointer)
        return marked

    def _path_kind(self, parameter: str | None, pointer: Pointer) -> str:
        """Tell the kind of a schema with ``format: path`` (file or directory).

        Args:
            parameter: The parameter whose schema it is, if any.
            pointer: Location of the schema in the IO schema.

        Returns:
            ``directory`` if ``--directory`` names the parameter, else
            ``file``.
        """
        if parameter in self.directories:
            return "directory"
        hint = (
            f"name it with --directory {parameter}"
            if parameter is not None
            else "edit the result"
        )
        self.note(
            "Marked as a file reference (file): 'format: path' is a file or a "
            f"directory; if it's a directory, {hint}.",
            pointer,
        )
        return "file"

    def _reference(
        self, kind: str, extras: dict[str, Any], pointer: Pointer, hint: bool
    ) -> dict[str, Any]:
        """Build the file reference, with the media type and the sample sheet.

        Args:
            kind: ``file`` or ``directory``.
            extras: ``mimetype`` and ``schema`` of the schema, if it has them.
            pointer: Location of the schema in the IO schema.
            hint: Whether the schema has an ``x-ga4gh-tabular-schema``
                already, which wins over ``schema``.

        Returns:
            The value of ``x-ga4gh-file``.
        """
        reference: dict[str, Any] = {"kind": kind}
        mimetype = extras.get("mimetype")
        if mimetype is not None:
            if (
                kind == "file"
                and isinstance(mimetype, str)
                and _MEDIA_TYPE.match(mimetype)
            ):
                reference["mediaType"] = mimetype
            else:
                self.note(
                    f"Dropped 'mimetype': {json.dumps(mimetype)} isn't the "
                    "media type of a file.",
                    pointer,
                )
        sheet = extras.get("schema")
        if sheet is None:
            return reference
        if hint:
            self.note(
                "Dropped 'schema': the schema has 'x-ga4gh-tabular-schema'.",
                pointer,
            )
        elif kind == "file" and isinstance(sheet, str) and not self.in_sheet:
            self.pending.append((pointer, sheet))
        else:
            self.note(
                "Dropped 'schema': only files of parameters can have a "
                "sample-sheet schema (given by its path).",
                pointer,
            )
        return reference

    def _drop_extras(self, extras: dict[str, Any], pointer: Pointer) -> None:
        """Report ``mimetype`` and ``schema`` of a schema that isn't a file.

        Args:
            extras: ``mimetype`` and ``schema`` of the schema, if it has them.
            pointer: Location of the schema in the IO schema.
        """
        for key in extras:
            self.note(
                f"Dropped '{key}': only file references (e.g., 'format: "
                "file-path') can have it.",
                pointer,
            )
