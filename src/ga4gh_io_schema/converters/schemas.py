"""Parts of the converters whose sources are JSON Schemas (Snakemake, nf-schema).

:class:`SchemaConverter` converts a JSON Schema of Draft 4, 6, 7, 2019-09 or
2020-12 to Draft 2020-12, rewrites its local references to where their
targets end up in the IO schema, and reports what changes its meaning as
:class:`~ga4gh_io_schema.converters.common.Note` objects. The converters
subclass it and add the keywords and the structure of their source format.
The module also has the checks that these converters share: that a parsed
document is JSON data (:func:`check_json`), and whether a schema can be a
file reference (:func:`file_reference_problem`).
"""

import copy
import json
import math
import re
import urllib.parse
from typing import Any

from ga4gh_io_schema.converters.common import (
    MAX_SOURCE_VALUES,
    ConversionError,
    Note,
    Pointer,
    SourceError,
    json_path,
)

#: ``$schema`` of the drafts of JSON Schema, with or without ``#``.
_DRAFT_URI = re.compile(
    r"^https?://json-schema\.org/"
    r"(?:draft-0(?P<old>[3467])/schema|draft/(?P<new>2019-09|2020-12)/schema)#?$"
)

#: Keywords of the drafts whose values are instance data, copied unchanged.
DATA_KEYWORDS = frozenset({"const", "default", "enum", "examples"})
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
#: Keywords that a file reference must not have; converters drop them.
NOT_ON_FILES = ("format", "contentMediaType", "contentEncoding", "contentSchema")
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
# Keywords of Draft 2020-12 whose value maps names to schemas.
_NAME_MAPS = frozenset({"$defs", "dependentSchemas", "patternProperties", "properties"})
#: Keywords of all drafts (before the upgrade) whose value maps names to
#: schemas.
SOURCE_NAME_MAPS = _NAME_MAPS | {"definitions", "dependencies"}
# Keywords that are kept next to "$ref" of drafts before 2019-09: the
# reference, annotations and definitions (targets of references). Identifiers
# are dropped: those drafts ignore them next to "$ref".
_NEXT_TO_REF = frozenset(
    {
        "$comment",
        "$defs",
        "$ref",
        "$schema",
        "default",
        "definitions",
        "deprecated",
        "description",
        "examples",
        "readOnly",
        "title",
        "writeOnly",
    }
)
# Draft 4 bounds and their exclusive flags.
_EXCLUSIVE = {"maximum": "exclusiveMaximum", "minimum": "exclusiveMinimum"}
# Characters that references keep as they are in the segments of pointers
# (unreserved characters, sub-delimiters, ":" and "@" of RFC 3986).
_POINTER_SAFE = "!$&'()*+,;=:@"


def check_json(data: Any, name: str, limit: int = MAX_SOURCE_VALUES) -> None:
    """Check that a parsed document is JSON data.

    Args:
        data: The parsed document.
        name: Name of the source in messages.
        limit: Most values (objects, arrays and scalars) that it may hold.

    Raises:
        SourceError: If a key isn't a string, a value isn't JSON (e.g., a
            date, or not a finite number), or there are more values than
            ``limit``.
    """
    # Each value comes with a link to its location (the link of its parent and
    # its key), so that deep documents don't copy their paths at every level.
    stack: list[tuple[Any, Any]] = [(data, None)]
    count = 0
    while stack:
        value, link = stack.pop()
        count += 1
        if count > limit:
            raise SourceError(
                f"Too large - {name}: more than {limit} values "
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
    """Render the location of a value of :func:`check_json` as a JSON path.

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


class SchemaConverter:
    """Conversion of JSON Schemas to Draft 2020-12, and the notes about it.

    The conversion of a source starts with :meth:`_begin`, which reads its
    draft; :meth:`_schema` then converts a schema of it. Subclasses convert
    the properties of a schema (:meth:`_property`) and may convert more
    keywords (by extending :meth:`_keywords`).

    Attributes:
        notes: Decisions of the conversion, in the order made.
        root: Root of the source (or embedded schema resource) being
            converted.
        draft: Draft of the source: ``4``, ``6``, ``7``, ``2019`` or ``2020``.
        prefix: Location of the root of the source in the IO schema.
        defs_prefix: Location of the ``$defs`` of the root in the IO schema.
    """

    def __init__(self) -> None:
        """Start without notes and without a source."""
        self.notes: list[Note] = []
        self.root: Any = None
        self.draft = 2020
        self.prefix: Pointer = ()
        self.defs_prefix: Pointer = ()

    def note(self, message: str, pointer: Pointer) -> None:
        """Add a note.

        Args:
            message: The note.
            pointer: Location in the IO schema that it concerns.
        """
        self.notes.append(Note(message, json_path(pointer)))

    def _check_references(
        self,
        node: Any,
        resource: Any,
        pointer: Pointer,
        anchors: dict[str, Pointer],
        names: bool = False,
    ) -> None:
        """Report JSON-pointer references of the IO schema that point to nothing.

        Also checks that no schema resource defines an anchor twice (e.g.,
        a main schema and a sample-sheet schema).

        Args:
            node: A schema of the IO schema, or a part of one.
            resource: Root of the schema resource that the node is in.
            pointer: Location of the node.
            anchors: Anchors of the resource, and where they are.
            names: Whether the node maps names to schemas (e.g., the value
                of ``properties``), so that its keys aren't keywords.

        Raises:
            ConversionError: If an anchor is defined twice in a resource.
        """
        if isinstance(node, list):
            for index, item in enumerate(node):
                self._check_references(item, resource, (*pointer, index), anchors)
            return
        if not isinstance(node, dict):
            return
        if names:
            for key, value in node.items():
                self._check_references(value, resource, (*pointer, key), anchors)
            return
        identifier = node.get("$id")
        if pointer and isinstance(identifier, str) and not identifier.startswith("#"):
            resource, anchors = node, {}
        anchor = node.get("$anchor")
        if isinstance(anchor, str):
            if anchor in anchors:
                raise ConversionError(
                    f"The anchor '{anchor}' is defined twice (also at "
                    f"{json_path(anchors[anchor])}), e.g. in the main schema "
                    "and a sample-sheet schema; rename one.",
                    json_path(pointer),
                )
            anchors[anchor] = pointer
        for keyword in ("$ref", "$dynamicRef"):
            ref = node.get(keyword)
            if isinstance(ref, str) and ref.startswith("#/"):
                target: Any = resource
                for part in ref[2:].split("/"):
                    part = urllib.parse.unquote(part)
                    part = part.replace("~1", "/").replace("~0", "~")
                    if isinstance(target, dict) and part in target:
                        target = target[part]
                    elif isinstance(target, list) and _is_index(part, target):
                        target = target[int(part)]
                    else:
                        self.note(
                            f"The reference '{ref}' points to nothing in the IO "
                            "schema; fix it by hand.",
                            pointer,
                        )
                        break
        for key, value in node.items():
            if key not in DATA_KEYWORDS:
                self._check_references(
                    value,
                    resource,
                    (*pointer, key),
                    anchors,
                    names=key in _NAME_MAPS,
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
            not root
            and isinstance(identifier, str)
            and not identifier.startswith("#")
            # Drafts before 2019-09 ignore identifiers next to "$ref"
            and not (self.draft < 2019 and "$ref" in node)
        )
        if not boundary:
            return self._keywords(node, pointer, name, root)
        # An embedded schema resource: its pointers are relative to its own
        # root, which keeps its identifier, so they are mapped within it.
        saved = (self.root, self.prefix, self.defs_prefix)
        self.root, self.prefix, self.defs_prefix = node, (), ()
        try:
            return self._keywords(node, pointer, name, root)
        finally:
            self.root, self.prefix, self.defs_prefix = saved

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
        if self.draft < 2019 and "$ref" in node:
            # Before Draft 2019-09, keywords next to "$ref" are ignored; in
            # Draft 2020-12 they apply, so assertions among them are dropped.
            ignored = [
                key
                for key in node
                if key not in _NEXT_TO_REF and not key.startswith("x-")
            ]
            if ignored:
                self.note(
                    "Dropped "
                    + ", ".join(f"'{key}'" for key in ignored)
                    + " next to '$ref': drafts before 2019-09 ignore them, and "
                    "Draft 2020-12 would apply them.",
                    pointer,
                )
                node = {key: value for key, value in node.items() if key not in ignored}
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
            if key in DATA_KEYWORDS:
                result[key] = copy.deepcopy(value)
            elif key == "$ref" or (
                key == "$dynamicRef" and isinstance(value, str) and value[:2] == "#/"
            ):
                # A "$dynamicRef" with a JSON pointer works like "$ref"
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
                        child, sub, (*at, child), child_name(name, child)
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
        if not isinstance(value, str):
            return copy.deepcopy(value)
        if not value.startswith("#"):
            self.note(
                f"The reference '{value}' to another document is kept as it "
                "is; unless it names a schema embedded in the source (by its "
                "'$id'), the IO schema can't resolve it: include the "
                "referenced schema in the source first.",
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
        return pointer_reference(self._map_pointer(segments))

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
        """Convert the schema of a property.

        Subclasses extend this, e.g., to mark the property as a file
        reference.

        Args:
            child: Name of the property.
            sub: Its schema in the source.
            pointer: Location of the converted schema in the IO schema.
            name: Dotted path of the property, or ``None`` if it can't be
                named.

        Returns:
            The converted schema.
        """
        return self._schema(sub, pointer, name)


def pointer_reference(pointer: Pointer) -> str:
    """Render a location as a local reference (a JSON pointer fragment).

    Args:
        pointer: Keys and indexes from the root of the document.

    Returns:
        The reference, e.g. ``#/$defs/a~1b``.
    """
    return "#" + "".join(
        "/"
        + urllib.parse.quote(
            str(part).replace("~", "~0").replace("/", "~1"), safe=_POINTER_SAFE
        )
        for part in pointer
    )


def child_name(parent: str | None, child: str) -> str | None:
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
    # The length check first: Python won't convert strings of too many digits
    return (
        segment.isdecimal()
        and len(segment) <= len(str(len(value)))
        and int(segment) < len(value)
    )


def file_reference_problem(schema: dict[str, Any]) -> str | None:
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
