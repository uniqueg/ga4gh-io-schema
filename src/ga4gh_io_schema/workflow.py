# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Check the workflow block of an IO schema against the workflow version.

Implements step 2 of the guide for portals and clients ("Check the workflow
block") and the comparison of checksums of the section "Drift" of the page
"Workflow identity": the TRS ids and the descriptor type in
``x-ga4gh-workflow`` are compared with the tool version that the schema was
fetched for, and its ``checksum`` with the checksums of the primary
descriptor, from TRS (``FileWrapper.checksum``) or computed over the
descriptor. A schema with a mismatch must not be used silently; a schema
whose checksum can't be compared is unverified.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

#: Algorithms that :func:`check_workflow` computes over a descriptor, by
#: their Hash Name String in the GA4GH Checksum Hash Algorithm Registry.
HASH_ALGORITHMS: Mapping[str, Callable[[bytes], Any]] = {
    "md5": lambda data: hashlib.md5(data, usedforsecurity=False),
    "sha-1": lambda data: hashlib.sha1(data, usedforsecurity=False),
    "sha-256": hashlib.sha256,
    "sha-512": hashlib.sha512,
}

#: Fields of ``x-ga4gh-workflow`` that name the workflow version in TRS.
ID_FIELDS = ("trs_tool_id", "trs_version_id", "descriptor_type")


@dataclass(frozen=True)
class Mismatch:
    """A field of ``x-ga4gh-workflow`` that doesn't match the workflow.

    Attributes:
        field: The field: ``trs_tool_id``, ``trs_version_id``,
            ``descriptor_type`` or ``checksum``.
        schema: The value in the schema; for ``checksum``, the digest of
            one entry.
        workflow: The value of the workflow version; for ``checksum``, the
            digest of the descriptor by the same algorithm.
        algorithm: The algorithm of a ``checksum``, in lower case; ``None``
            for the other fields.
    """

    field: str
    schema: str
    workflow: str
    algorithm: str | None = None

    @property
    def message(self) -> str:
        """Describe the mismatch.

        Returns:
            A sentence that names the field and both values.
        """
        if self.algorithm is None:
            return (
                f"x-ga4gh-workflow.{self.field} is {self.schema!r}, "
                f"not {self.workflow!r}."
            )
        return (
            f"x-ga4gh-workflow.checksum ({self.algorithm}) is {self.schema!r}, "
            f"but the primary descriptor has {self.workflow!r}."
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the mismatch to JSON.

        Returns:
            The fields and the message.
        """
        return {
            "field": self.field,
            "schema": self.schema,
            "workflow": self.workflow,
            "algorithm": self.algorithm,
            "message": self.message,
        }


@dataclass(frozen=True)
class WorkflowCheck:
    """Result of the check of the workflow block.

    Attributes:
        mismatches: The fields that don't match the workflow version. With
            any, the schema must not be used silently: a client refuses it,
            or warns that it may not match the workflow.
        compared: The algorithms whose checksums were compared, in lower
            case.
    """

    mismatches: tuple[Mismatch, ...] = ()
    compared: tuple[str, ...] = field(default=())

    @property
    def verified(self) -> bool:
        """Whether the schema is verified.

        Returns:
            ``True`` if a checksum of the schema was compared with the
            primary descriptor and nothing mismatches; ``False`` if
            something mismatches, or if no checksum could be compared (no
            checksum in the schema, no supported algorithm, or no
            descriptor): such a schema is unverified, and may be used.
        """
        return bool(self.compared) and not self.mismatches

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to JSON.

        Returns:
            ``verified``, the ``mismatches`` and the ``compared``
            algorithms.
        """
        return {
            "verified": self.verified,
            "mismatches": [mismatch.to_dict() for mismatch in self.mismatches],
            "compared": list(self.compared),
        }


def check_workflow(
    schema: Mapping[str, Any],
    trs_tool_id: str | None = None,
    trs_version_id: str | None = None,
    descriptor_type: str | None = None,
    descriptor: Mapping[str, Any] | None = None,
    checksums: Iterable[Mapping[str, Any]] = (),
    content: bytes | str | None = None,
) -> WorkflowCheck:
    """Check the workflow block of an IO schema against a workflow version.

    Compares ``trs_tool_id``, ``trs_version_id`` and ``descriptor_type`` of
    ``x-ga4gh-workflow``, where the schema has them, with those given; and
    each ``checksum`` of the schema with the checksums of the primary
    descriptor by the same algorithm: those from TRS, and those computed
    over the descriptor's content for the algorithms of
    :data:`HASH_ALGORITHMS`. Algorithm names and digests are compared case
    insensitively. The schema isn't validated against the profile (step 3
    of the guide); fields of the wrong type are skipped.

    Args:
        schema: The IO schema.
        trs_tool_id: The id of the tool in TRS that the schema was fetched
            for (``Tool.id``), if known.
        trs_version_id: The id of the tool version (``ToolVersion.id``), if
            known.
        descriptor_type: The TRS descriptor type that the schema was fetched
            for, if known.
        descriptor: The TRS ``FileWrapper`` of the primary descriptor, if
            any: its ``checksum`` entries and its ``content`` are used.
        checksums: Further checksums of the primary descriptor, in the
            format of TRS (``{"type": …, "checksum": …}``).
        content: The primary descriptor as TRS serves it, if not in
            ``descriptor``: bytes, or text that is encoded in UTF-8.

    Returns:
        The mismatches, and whether the schema is verified.
    """
    block = schema.get("x-ga4gh-workflow")
    if not isinstance(block, Mapping):
        block = {}
    given = {
        "trs_tool_id": trs_tool_id,
        "trs_version_id": trs_version_id,
        "descriptor_type": descriptor_type,
    }
    mismatches = [
        Mismatch(key, block[key], value)
        for key, value in given.items()
        if value is not None and isinstance(block.get(key), str) and block[key] != value
    ]
    references = _references(descriptor, checksums, content, _entries(block))
    compared: list[str] = []
    for algorithm, digest in _entries(block):
        if algorithm not in references:
            continue
        if algorithm not in compared:
            compared.append(algorithm)
        mismatches.extend(
            Mismatch("checksum", digest, reference, algorithm)
            for reference in references[algorithm]
            if reference != digest
        )
    return WorkflowCheck(tuple(mismatches), tuple(compared))


def _entries(block: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Get the checksums of the workflow block.

    Args:
        block: The workflow block.

    Returns:
        The algorithm and digest of each well-formed entry, in lower case.
    """
    entries = block.get("checksum")
    return _checksums(entries if isinstance(entries, list) else [])


def _checksums(entries: Iterable[Any]) -> list[tuple[str, str]]:
    """Normalise checksums in the format of TRS.

    Args:
        entries: Objects with ``type`` and ``checksum``.

    Returns:
        The algorithm and digest of each well-formed entry, in lower case.
    """
    return [
        (entry["type"].lower(), entry["checksum"].lower())
        for entry in entries
        if isinstance(entry, Mapping)
        and isinstance(entry.get("type"), str)
        and isinstance(entry.get("checksum"), str)
    ]


def _references(
    descriptor: Mapping[str, Any] | None,
    checksums: Iterable[Mapping[str, Any]],
    content: bytes | str | None,
    wanted: Iterable[tuple[str, str]],
) -> dict[str, list[str]]:
    """Collect the checksums of the primary descriptor, by algorithm.

    Args:
        descriptor: The ``FileWrapper`` of the descriptor, if any.
        checksums: Further checksums from TRS.
        content: The content of the descriptor, if not in ``descriptor``.
        wanted: The checksums of the schema, whose algorithms are computed
            over the content.

    Returns:
        The distinct digests of each algorithm, in lower case.
    """
    entries = list(checksums)
    if descriptor is not None:
        wrapped = descriptor.get("checksum")
        entries.extend(wrapped if isinstance(wrapped, list) else [])
        if content is None and isinstance(descriptor.get("content"), str):
            content = descriptor["content"]
    found = _checksums(entries)
    if content is not None:
        data = content.encode("utf-8") if isinstance(content, str) else content
        found.extend(
            (algorithm, HASH_ALGORITHMS[algorithm](data).hexdigest())
            for algorithm in dict.fromkeys(algorithm for algorithm, _ in wanted)
            if algorithm in HASH_ALGORITHMS
        )
    references: dict[str, list[str]] = {}
    for algorithm, digest in found:
        digests = references.setdefault(algorithm, [])
        if digest not in digests:
            digests.append(digest)
    return references
