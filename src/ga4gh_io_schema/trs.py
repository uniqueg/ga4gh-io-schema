# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Discovery of the IO schema among the files of a TRS tool version.

Implements the matching rules of "Discovery by clients" (see the page "TRS"
of the adoption guide) for the list that ``GET
/tools/{id}/versions/{version_id}/{type}/files`` returns: a list of TRS
``ToolFile`` entries, all of whose fields are optional. Entries are compared
by ``file_type`` and normalised ``path`` only; other fields (e.g.,
``checksum``) are ignored, and so are entries without a file type or a
usable path.

The IO schema is the one entry of type ``IO_SCHEMA``, the file type that the
profile proposes for TRS, at any path. Without one, it is the entry of type
``OTHER`` with the path ``ga4gh-io.schema.json`` in the directory of the
primary descriptor, the convention for TRS servers without ``IO_SCHEMA``.

Fetching the file, and checking it, is left to the caller (see the page
"TRS" of the adoption guide): ``GET
/tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}`` with
the path of the entry as listed.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Any, Literal

#: The TRS file type of IO schemas that the profile proposes.
IO_SCHEMA_FILE_TYPE = "IO_SCHEMA"
#: The TRS file type of IO schemas on TRS servers without ``IO_SCHEMA``.
OTHER_FILE_TYPE = "OTHER"
#: The TRS file type of the primary descriptor.
PRIMARY_DESCRIPTOR_FILE_TYPE = "PRIMARY_DESCRIPTOR"
#: The name of the IO schema file next to the primary descriptor.
SCHEMA_FILE_NAME = "ga4gh-io.schema.json"


@dataclass(frozen=True)
class SchemaFile:
    """The entry of the IO schema in the files of a TRS tool version.

    Attributes:
        path: The path of the entry, as listed (not normalised), for
            ``.../{type}/descriptor/{relative_path}``.
        file_type: The file type of the entry: ``IO_SCHEMA`` or ``OTHER``.
    """

    path: str
    file_type: Literal["IO_SCHEMA", "OTHER"]


def normalise_path(path: Any) -> str | None:
    """Normalise the path of a TRS file entry for comparison.

    Empty segments and ``.`` segments are removed, so that, e.g.,
    ``./wdl/main.wdl``, ``/wdl/main.wdl`` and ``wdl//main.wdl`` all become
    ``wdl/main.wdl``. Paths are compared case-sensitively.

    Args:
        path: The ``path`` of a ``ToolFile`` entry, if any.

    Returns:
        The normalised path, or ``None`` if the path isn't a string, is
        empty after normalisation, or has a ``..`` segment (which may leave
        the files of the tool version).
    """
    if not isinstance(path, str):
        return None
    segments = [segment for segment in path.split("/") if segment not in ("", ".")]
    if not segments or ".." in segments:
        return None
    return "/".join(segments)


def find_primary_descriptor_path(files: Any) -> str | None:
    """Find the path of the primary descriptor in the files of a TRS tool version.

    For the ``workflow_url`` of run requests (see
    :func:`ga4gh_io_schema.wes.trs_descriptor_url` and "Workflow URLs in
    TRS" of the page "Engine bindings"), which takes a path without empty,
    ``.`` or ``..`` segments.

    Args:
        files: The answer of ``GET .../{type}/files``: a list of ``ToolFile``
            entries; anything else has no primary descriptor.

    Returns:
        The normalised path (see :func:`normalise_path`) of the first entry
        of type ``PRIMARY_DESCRIPTOR`` with a usable path (as
        :func:`find_schema_file` counts them), e.g., ``main.wdl`` for
        ``./main.wdl`` and ``wdl/main.wdl`` for ``wdl//main.wdl``; a path
        with a leading ``/`` as listed, for which ``trs_descriptor_url``
        gives the URL without a path. ``None`` if there is no such entry.
    """
    if not isinstance(files, list):
        return None
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        normalised = normalise_path(path)
        if entry.get("file_type") == PRIMARY_DESCRIPTOR_FILE_TYPE and normalised:
            # A leading "/" keeps the URL without a path (servers differ)
            return path if path.startswith("/") else normalised
    return None


def find_schema_file(files: Any) -> SchemaFile | None:
    """Find the entry of the IO schema in the files of a TRS tool version.

    Args:
        files: The answer of ``GET .../{type}/files``: a list of ``ToolFile``
            entries; anything else has no IO schema.

    Returns:
        The entry of type ``IO_SCHEMA``, if there is exactly one; else, if
        there is none, the entry of type ``OTHER`` whose normalised path is
        ``ga4gh-io.schema.json`` in the directory of the primary descriptor
        (the entries of type ``PRIMARY_DESCRIPTOR``, which must all be in
        the same directory). ``None`` if no entry matches, or if several
        entries of type ``IO_SCHEMA``, or several of type ``OTHER`` at that
        path (e.g., ``ga4gh-io.schema.json`` and ``./ga4gh-io.schema.json``),
        match: a client doesn't guess between them.
    """
    if not isinstance(files, list):
        return None
    # (file type, normalised path, path as listed) of the usable entries
    entries = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        file_type = entry.get("file_type")
        normalised = normalise_path(entry.get("path"))
        if isinstance(file_type, str) and normalised is not None:
            entries.append((file_type, normalised, entry["path"]))
    typed = [path for file_type, _, path in entries if file_type == IO_SCHEMA_FILE_TYPE]
    if typed:
        return SchemaFile(typed[0], IO_SCHEMA_FILE_TYPE) if len(typed) == 1 else None
    directories = {
        posixpath.dirname(normalised)
        for file_type, normalised, _ in entries
        if file_type == PRIMARY_DESCRIPTOR_FILE_TYPE
    }
    if len(directories) != 1:
        return None
    expected = posixpath.join(directories.pop(), SCHEMA_FILE_NAME)
    other = [
        path
        for file_type, normalised, path in entries
        if file_type == OTHER_FILE_TYPE and normalised == expected
    ]
    return SchemaFile(other[0], OTHER_FILE_TYPE) if len(other) == 1 else None
