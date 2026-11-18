# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Translation between input values and the parameters of WES run requests.

Implements the engine bindings of the profile (see the page "Engine
bindings" of the specification): input values that are valid against the
``inputs`` of an IO schema become the ``workflow_params`` of a GA4GH
Workflow Execution Service (WES) run request, in the shape that the engine
of the schema's descriptor type expects, and, with the fields that come from
the Tool Registry Service (TRS), a full ``RunRequest``. In the other
direction, a WES server translates the ``workflow_params`` of a request back
into input values and validates them, with errors located in
``workflow_params``.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote

import jsonschema
from jsonschema.validators import Draft202012Validator
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from ga4gh_io_schema.patterns import ValuesValidator, search
from ga4gh_io_schema.validator import (
    _format_checker,
    build_registry,
    get_schemas_dir,
    validate_schema,
)

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    # `referencing` defines the class in a private module only
    from referencing._core import Resolver

#: Descriptor types with an engine binding in this version of the profile.
DESCRIPTOR_TYPES = ("CWL", "NFL", "SMK", "WDL")
#: Schemes that file references may use if the caller names no allow-list.
DEFAULT_ALLOWED_SCHEMES = ("drs", "https")
#: Schemes that file references never use: they run code in a browser or
#: refer to local data (the list that the meta-schema rejects in ``schemes``).
FORBIDDEN_SCHEMES = frozenset(
    {
        "about",
        "blob",
        "data",
        "file",
        "filesystem",
        "jar",
        "javascript",
        "livescript",
        "vbscript",
        "view-source",
    }
)

# A value has a scheme if it starts with one and a colon (see "File
# references", "Values").
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")
# C0 control characters and DEL
_UNSAFE_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
# Applicators whose dynamic scope the translator doesn't model
_UNSUPPORTED = ("$dynamicRef",)
# Base URI of an IO schema without an `$id`, for its local references
_DOCUMENT_URI = "urn:ga4gh-io-schema:document"
# Members of JSON Path that need no quotes (as in jsonschema's `json_path`)
_PLAIN_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Classes of CWL objects for files and directories
_CWL_CLASSES = ("File", "Directory")
# Applicators along the evaluation path of a failure, by whether their
# subschemas apply to the same location as the schema itself, and by whether
# the schema path names one of several subschemas (by key or index) or the
# only one
_SAME_LOCATION_NAMED = ("allOf", "anyOf", "oneOf", "dependentSchemas")
_SAME_LOCATION_SINGLE = ("not", "if", "then", "else")
_NEW_LOCATION_NAMED = ("properties", "patternProperties", "prefixItems")
_NEW_LOCATION_SINGLE = (
    "items",
    "additionalProperties",
    "contains",
    "unevaluatedItems",
    "unevaluatedProperties",
    "propertyNames",
)
# References followed in a row while searching the evaluation path of a
# failure; a cycle of references stops here
_MAX_REFERENCES = 32

#: A location in the input values: keys of objects and indexes of arrays.
Path = tuple[str | int, ...]


#: Key of the validity of a subschema for a value (see :func:`_validity_key`)
_ValidityKey = tuple[int, str, int]

# Validity of subschemas for values during a translation (see
# `_Translator.bind`); `None` outside of one, and for schemas whose results
# may depend on the dynamic scope (see `_static`)
_VALIDITY: ContextVar[dict[_ValidityKey, bool] | None] = ContextVar(
    "_VALIDITY", default=None
)


def _validity_key(schema: Any, resolver: Resolver, value: Any) -> _ValidityKey:
    """Get the key of the validity of a subschema for a value.

    Args:
        schema: The subschema.
        resolver: Resolver of the schema that applies the subschema.
        value: The value.

    Returns:
        The identity of the subschema, the base URI against which it
        resolves references, and the identity of the value.
    """
    # `referencing` has no public accessor of the base URI; the tests of the
    # translation fail if it goes away
    base_uri: str = resolver._base_uri
    return (id(schema), base_uri, id(value))


def _static(schema: Any) -> bool:
    """Check that the results of a schema can't depend on the dynamic scope.

    The validity of a subschema for a value is kept by the subschema, its
    base URI and the value, not by the path that led to it. Only
    ``$dynamicRef``, and ``$ref`` to a ``$dynamicAnchor``, resolve through
    the dynamic scope; and a reference may reach different documents on
    different paths where an embedded ``$id`` takes a URI that is already
    registered (e.g., that of a vocabulary of the profile). A schema without
    these keywords below its root, and with references that start with
    ``#`` only, which then stay in the document, is safe to keep results
    for.

    Args:
        schema: The IO schema.

    Returns:
        Whether the schema has no ``$dynamicRef`` and no ``$dynamicAnchor``
        anywhere and no ``$id`` below the root (also as names of
        properties, to be safe), and only references that start with ``#``.
    """
    # Each node, and whether it is the root
    stack: list[tuple[Any, bool]] = [(schema, True)]
    while stack:
        node, root = stack.pop()
        if isinstance(node, list):
            stack.extend((item, False) for item in node)
        elif isinstance(node, dict):
            if {"$dynamicRef", "$dynamicAnchor"} & node.keys():
                return False
            if "$id" in node and not root:
                return False
            reference = node.get("$ref")
            if isinstance(reference, str) and not reference.startswith("#"):
                return False
            stack.extend((value, False) for value in node.values())
    return True


def _memoised_descend(
    self: Draft202012Validator,
    instance: Any,
    schema: Any,
    path: str | int | None = None,
    schema_path: str | int | None = None,
    resolver: Resolver | None = None,
) -> Iterator[jsonschema.exceptions.ValidationError]:
    """Validate a value against a subschema, once per translation.

    Replaces :meth:`Draft202012Validator.descend` in
    :data:`_MemoisingValidator`. The translation asks, at every level of the
    values, which branches of ``anyOf`` and ``oneOf`` and which conditions
    of ``if`` and ``contains`` a value is valid against; validating the whole
    value again for each would take time that grows with the size times the
    depth of the values (issue #86). During a translation, the validity of
    each subschema for each value is therefore kept, and a subschema that a
    value is known to be valid against isn't validated again. Failures are
    validated again, to report their errors.

    Relies on jsonschema descending into every subschema through
    ``descend``, with this signature, as its keywords and ``$ref`` do; the
    tests of the translation count the calls.

    Args:
        self: The validator.
        instance: The value.
        schema: The subschema.
        path: Location of the value relative to that of the validator.
        schema_path: Location of the subschema relative to that of the
            validator.
        resolver: Resolver of the subschema, if not that of the validator.

    Returns:
        The errors, as :meth:`Draft202012Validator.descend` gives them.
    """
    known = _VALIDITY.get()
    errors = _DESCEND(self, instance, schema, path, schema_path, resolver)
    if known is None:
        return errors
    # `_resolver` is private, and not in the stubs, but the only resolver in
    # scope (as in `ga4gh_io_schema.patterns`)
    key = _validity_key(
        schema,
        resolver or self._resolver,  # type: ignore[attr-defined]
        instance,
    )
    if known.get(key):
        return iter(())
    return _recorded(errors, known, key)


def _recorded(
    errors: Iterator[jsonschema.exceptions.ValidationError],
    known: dict[_ValidityKey, bool],
    key: _ValidityKey,
) -> Iterator[jsonschema.exceptions.ValidationError]:
    """Pass on the errors of a validation, and keep whether there were any.

    Args:
        errors: The errors of validating a value against a subschema.
        known: The validity of subschemas for values.
        key: The key of the subschema and the value.

    Yields:
        The errors.
    """
    for error in errors:
        # Before the error goes out: the caller may stop at the first one
        known[key] = False
        yield error
    known.setdefault(key, True)


_DESCEND = Draft202012Validator.descend
#: Validator of the input values, which keeps the validity of subschemas
#: during a translation (see :func:`_memoised_descend`)
_MemoisingValidator = jsonschema.validators.extend(ValuesValidator)
_MemoisingValidator.descend = _memoised_descend


class TranslationError(ValueError):
    """Input values can't be translated into ``workflow_params``.

    Raised if the values aren't valid against the schema, if a file
    reference breaks the rules for its values, or if the schema has no
    engine binding that can be used.

    Attributes:
        message: Description of the error, without the offending value.
        path: Location of the offending value in the input values, if any.
    """

    def __init__(self, message: str, path: Sequence[str | int] = ()) -> None:
        """Initialise the error.

        Args:
            message: Description of the error.
            path: Location of the offending value in the input values.
        """
        super().__init__(message)
        self.message = message
        self.path: Path = tuple(path)

    @property
    def pointer(self) -> str:
        """Location of the offending value as a JSON Pointer (RFC 6901).

        The empty string stands for the input values as a whole.
        """
        return "".join(
            "/" + str(part).replace("~", "~0").replace("/", "~1") for part in self.path
        )

    @property
    def json_path(self) -> str:
        """Location of the offending value as a JSON Path, e.g., ``$.reads[0]``."""
        parts = ["$"]
        for part in self.path:
            if isinstance(part, int):
                parts.append(f"[{part}]")
            elif _PLAIN_KEY.match(part):
                parts.append(f".{part}")
            else:
                parts.append("[" + repr(part) + "]")
        return "".join(parts)


class WorkflowParamsError(TranslationError):
    """The ``workflow_params`` of a WES run request are rejected.

    Raised by :func:`from_workflow_params`. Unlike in the parent class, the
    location of the error is in ``workflow_params``, not in the input
    values: its first segment is the key of a member of ``workflow_params``
    (e.g., ``/variant_calling.input_bam``), and the location of a CWL file
    value ends with ``location`` (or ``path``). The message is the schema's
    ``x-ga4gh-error-message`` where it covers the failure, or else one built
    from the keyword that failed; it doesn't repeat the value.
    """


@dataclass(frozen=True)
class EngineBinding:
    """The parts of the workflow block that the translation uses.

    Attributes:
        descriptor_type: TRS descriptor type, also the WES ``workflow_type``;
            one of :data:`DESCRIPTOR_TYPES`.
        descriptor_type_version: Version of the workflow language, the WES
            ``workflow_type_version``; needed for a run request only.
        entry_point: Entry point of the engine; required for ``WDL``.
    """

    descriptor_type: str
    descriptor_type_version: str | None = None
    entry_point: str | None = None

    def __post_init__(self) -> None:
        """Check that the binding can be used.

        Raises:
            TranslationError: If the descriptor type has no engine binding, or
                if a ``WDL`` binding lacks the entry point.
        """
        if self.descriptor_type not in DESCRIPTOR_TYPES:
            raise TranslationError(
                f"The descriptor type '{self.descriptor_type}' has no engine "
                f"binding; supported: {', '.join(DESCRIPTOR_TYPES)}."
            )
        if self.descriptor_type == "WDL" and not self.entry_point:
            raise TranslationError(
                "WDL needs the entry point (x-ga4gh-workflow.entry_point): "
                "the name of the workflow, or of the task."
            )


def get_binding(
    schema: dict[str, Any],
    descriptor_type: str | None = None,
    descriptor_type_version: str | None = None,
    entry_point: str | None = None,
) -> EngineBinding:
    """Get the engine binding of an IO schema.

    The fields come from the schema's ``x-ga4gh-workflow``; the arguments
    fill in fields that the schema lacks (e.g., the descriptor type version
    from TRS), and must match those that it has.

    Args:
        schema: IO schema, valid against the profile.
        descriptor_type: TRS descriptor type, e.g., ``WDL``.
        descriptor_type_version: Version of the workflow language.
        entry_point: Entry point of the engine.

    Returns:
        The engine binding.

    Raises:
        TranslationError: If an argument differs from the schema, if neither
            names the descriptor type, or if the binding can't be used (see
            :class:`EngineBinding`).
    """
    block = schema.get("x-ga4gh-workflow")
    declared = block if isinstance(block, dict) else {}
    fields: dict[str, str | None] = {}
    for name, given in (
        ("descriptor_type", descriptor_type),
        ("descriptor_type_version", descriptor_type_version),
        ("entry_point", entry_point),
    ):
        value = declared.get(name)
        if given is not None and value is not None and given != value:
            raise TranslationError(
                f"The {name} '{given}' differs from '{value}' in x-ga4gh-workflow."
            )
        fields[name] = value if value is not None else given
    if fields["descriptor_type"] is None:
        raise TranslationError(
            "The descriptor type is unknown: the schema has no "
            "x-ga4gh-workflow.descriptor_type, and none was given."
        )
    return EngineBinding(
        descriptor_type=fields["descriptor_type"],
        descriptor_type_version=fields["descriptor_type_version"],
        entry_point=fields["entry_point"],
    )


def to_workflow_params(
    schema: dict[str, Any],
    values: Any,
    binding: EngineBinding | None = None,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allow_absolute_paths: bool = False,
) -> dict[str, Any]:
    """Translate input values into the ``workflow_params`` of a WES request.

    Validates the schema against the GA4GH IO Profile and the values against
    its ``inputs``, checks the values of file references, then applies the
    engine binding.

    Args:
        schema: IO schema.
        values: Input values: a JSON object, an instance of ``inputs``.
        binding: Engine binding; by default, that of the schema's
            ``x-ga4gh-workflow`` (see :func:`get_binding`).
        allowed_schemes: URI schemes of the deployment's allow-list, which
            values of file references may use.
        allow_absolute_paths: Whether values of file references may be
            absolute paths (only for deployments with a shared file system).

    Returns:
        The ``workflow_params``.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the profile.
        TranslationError: If the values can't be translated.
        ValueError: If ``allowed_schemes`` names a forbidden scheme.
    """
    binding = _prepare(schema, binding)
    return _Translator(
        schema, binding, allowed_schemes, allow_absolute_paths
    ).translate(values)


def build_run_request(
    schema: dict[str, Any],
    values: Any,
    workflow_url: str,
    binding: EngineBinding | None = None,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allow_absolute_paths: bool = False,
) -> dict[str, Any]:
    """Build a WES ``RunRequest`` from input values.

    Sets ``workflow_params`` (see :func:`to_workflow_params`),
    ``workflow_type``, ``workflow_type_version`` and ``workflow_url``; the
    other fields (e.g., ``tags``) are left to the caller.

    Args:
        schema: IO schema.
        values: Input values: a JSON object, an instance of ``inputs``.
        workflow_url: URL of the workflow, e.g., of its primary descriptor in
            TRS (see :func:`trs_descriptor_url`). For CWL, the entry point is
            appended as the fragment.
        binding: Engine binding; by default, that of the schema's
            ``x-ga4gh-workflow`` (see :func:`get_binding`).
        allowed_schemes: URI schemes of the deployment's allow-list.
        allow_absolute_paths: Whether values of file references may be
            absolute paths.

    Returns:
        The run request, with ``workflow_params`` as a JSON object.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the profile.
        TranslationError: If the values can't be translated, if the
            descriptor type version is unknown, or if a CWL entry point
            meets a ``workflow_url`` that already has a fragment.
        ValueError: If ``allowed_schemes`` names a forbidden scheme.
    """
    binding = _prepare(schema, binding)
    if binding.descriptor_type_version is None:
        raise TranslationError(
            "The descriptor type version is unknown: set "
            "x-ga4gh-workflow.descriptor_type_version, or take it from the "
            "TRS tool version (descriptor_type_version)."
        )
    if binding.descriptor_type == "CWL" and binding.entry_point:
        if "#" in workflow_url:
            raise TranslationError(
                "The workflow URL has a fragment, so the CWL entry point can't "
                "be appended to it."
            )
        workflow_url = f"{workflow_url}#{binding.entry_point.removeprefix('#')}"
    params = _Translator(
        schema, binding, allowed_schemes, allow_absolute_paths
    ).translate(values)
    return {
        "workflow_params": params,
        "workflow_type": binding.descriptor_type,
        "workflow_type_version": binding.descriptor_type_version,
        "workflow_url": workflow_url,
    }


def from_workflow_params(
    schema: dict[str, Any],
    workflow_params: Any,
    binding: EngineBinding | None = None,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allow_absolute_paths: bool = False,
    allow_paths: bool = False,
) -> dict[str, Any]:
    """Translate the ``workflow_params`` of a WES request back into input values.

    Validates the schema against the GA4GH IO Profile, reverses the engine
    binding (see "From ``workflow_params`` back to input values" of the
    page "Engine bindings"), then validates the input values against
    ``inputs`` and checks every file value, as :func:`to_workflow_params`
    does. Nothing is fetched over the network: references of the schema that
    can't be resolved locally are rejected.

    Each member of ``workflow_params`` is matched with the input that binds
    to its key; a member that matches no input keeps its name, so that the
    schema decides whether it is allowed (e.g., by
    ``additionalProperties``), unless its name is that of an input, which
    binds to another key. For ``CWL``, a ``File`` or ``Directory`` object at
    a file reference becomes its ``location`` (or its ``path``, if
    ``allow_paths``); objects with ``contents`` or other fields, objects of
    the wrong class, and objects where no file reference applies are
    rejected.

    Args:
        schema: IO schema, from a trusted source.
        workflow_params: The ``workflow_params`` of the request, parsed.
        binding: Engine binding; by default, that of the schema's
            ``x-ga4gh-workflow``. A server builds it from the request's
            ``workflow_type`` and ``workflow_type_version`` with
            :func:`get_binding`.
        allowed_schemes: URI schemes of the deployment's allow-list, which
            values of file references may use.
        allow_absolute_paths: Whether values of file references may be
            absolute paths (only for deployments with a shared file system).
        allow_paths: Whether a CWL ``File`` or ``Directory`` object may give
            its file as ``path`` instead of ``location``.

    Returns:
        The input values, an instance of ``inputs``.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the profile.
        WorkflowParamsError: If the request is rejected; see
            :func:`error_response` for the body of the response.
        ValueError: If ``allowed_schemes`` names a forbidden scheme.
    """
    try:
        binding = _prepare(schema, binding)
    except TranslationError as exc:
        raise WorkflowParamsError(exc.message) from exc
    translator = _Translator(
        schema, binding, allowed_schemes, allow_absolute_paths, server=True
    )
    try:
        return _ReverseTranslator(translator, allow_paths).translate(workflow_params)
    except RecursionError as exc:
        # Servers limit the depth of requests before; this is the backstop
        raise WorkflowParamsError(
            "workflow_params are too deeply nested to validate."
        ) from exc


def error_response(error: TranslationError) -> dict[str, Any]:
    """Build the body of a WES ``ErrorResponse`` for a rejected request.

    The ``msg`` names the location of the error as a JSON Pointer, followed
    by the message (e.g., ``/condition: Condition must be control or
    treatment``); an error of the request as a whole (an empty pointer) is
    named ``workflow_params``.

    Args:
        error: The error, typically a :class:`WorkflowParamsError`, whose
            location is in ``workflow_params``.

    Returns:
        The body: ``msg`` and ``status_code`` 400.
    """
    location = error.pointer if error.path else "workflow_params"
    return {"msg": f"{location}: {error.message}", "status_code": 400}


def _prepare(schema: dict[str, Any], binding: EngineBinding | None) -> EngineBinding:
    """Validate the schema and get its engine binding.

    Args:
        schema: IO schema.
        binding: Engine binding given by the caller, if any.

    Returns:
        The given binding, or that of the schema.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the profile.
        TranslationError: If the schema's binding can't be used.
    """
    # The workflow block is read only from a schema that complies
    validate_schema(schema)
    return binding if binding is not None else get_binding(schema)


def trs_descriptor_url(
    trs_url: str,
    tool_id: str,
    version_id: str,
    descriptor_type: str,
    primary_descriptor_path: str | None = None,
) -> str:
    """Build the TRS URL of the plain primary descriptor of a tool version.

    With the path of the primary descriptor, the URL is that of
    ``GET .../PLAIN_{type}/descriptor/{relative_path}`` for the primary
    descriptor, so that relative imports of a multi-file workflow (e.g., a
    WDL ``import "tasks/sub.wdl"``) resolve (RFC 3986) to files that TRS
    serves under ``.../descriptor/``. Without it, the URL is that of
    ``GET .../PLAIN_{type}/descriptor``, which suits single-file workflows
    only (see "Workflow URLs in TRS" of the page "Engine bindings").

    Args:
        trs_url: Base URL of the TRS API, e.g.,
            ``https://trs.example.org/ga4gh/trs/v2``.
        tool_id: Id of the tool (``Tool.id``).
        version_id: Id of the tool version (``ToolVersion.id``).
        descriptor_type: TRS descriptor type, e.g., ``WDL``.
        primary_descriptor_path: Path of the primary descriptor as TRS lists
            it (``ToolFile.path`` of the ``PRIMARY_DESCRIPTOR``), e.g.,
            ``x-ga4gh-workflow.primary_descriptor_path``. A path with a
            leading ``/`` gives the URL without path: TRS servers differ in
            how they serve such paths, and the path without the ``/`` is
            not one that TRS listed.

    Returns:
        The URL, with the ids, the descriptor type and each segment of the
        path percent-encoded.

    Raises:
        ValueError: If the path is empty, or has empty, ``.`` or ``..``
            segments, which would change where relative imports resolve.
    """
    url = (
        f"{trs_url.rstrip('/')}/tools/{quote(tool_id, safe='')}"
        f"/versions/{quote(version_id, safe='')}"
        f"/PLAIN_{quote(descriptor_type, safe='')}/descriptor"
    )
    if primary_descriptor_path is None or primary_descriptor_path.startswith("/"):
        return url
    segments = primary_descriptor_path.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise ValueError(
            "The primary descriptor path must be a relative file path without "
            f"empty, '.' or '..' segments, not {primary_descriptor_path!r}."
        )
    return f"{url}/{'/'.join(quote(segment, safe='') for segment in segments)}"


def check_file_value(
    annotation: dict[str, Any],
    value: str,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    allow_absolute_paths: bool = False,
) -> None:
    """Check a value of a file reference of an input.

    Applies the rules of "File references", "Values": a value is an absolute
    URI whose scheme is on the deployment's allow-list and, if the annotation
    has ``schemes``, on that list too; or, without ``schemes``, a path
    without ``..`` segments, which is absolute only where allowed. Schemes
    that run code in a browser or refer to local data
    (:data:`FORBIDDEN_SCHEMES`) are always rejected.

    Args:
        annotation: The ``x-ga4gh-file`` annotation of the file reference.
        value: The value.
        allowed_schemes: URI schemes of the deployment's allow-list.
        allow_absolute_paths: Whether the value may be an absolute path
            (only for deployments with a shared file system).

    Raises:
        TranslationError: If the value breaks a rule; the message doesn't
            repeat the value.
        ValueError: If ``allowed_schemes`` names a forbidden scheme.
    """
    _check_file_value(
        annotation, value, _allow_list(allowed_schemes), allow_absolute_paths, ()
    )


def _allow_list(schemes: Iterable[str]) -> frozenset[str]:
    """Normalise an allow-list of URI schemes.

    Args:
        schemes: URI schemes, in any case.

    Returns:
        The schemes, in lowercase.

    Raises:
        ValueError: If a scheme is forbidden (see :data:`FORBIDDEN_SCHEMES`).
    """
    allowed = frozenset(scheme.lower() for scheme in schemes)
    forbidden = sorted(allowed & FORBIDDEN_SCHEMES)
    if forbidden:
        raise ValueError(f"These schemes can't be allowed: {', '.join(forbidden)}")
    return allowed


def _check_file_value(
    annotation: dict[str, Any],
    value: str,
    allowed: frozenset[str],
    allow_absolute_paths: bool,
    path: Path,
    server: bool = False,
) -> None:
    """Check a value of a file reference (see :func:`check_file_value`).

    Args:
        annotation: The ``x-ga4gh-file`` annotation.
        value: The value.
        allowed: URI schemes of the allow-list, in lowercase.
        allow_absolute_paths: Whether absolute paths are allowed.
        path: Location of the value in the input values.
        server: Whether the value comes from a request to a server, whose
            messages name only forbidden schemes, not any part of the value.

    Raises:
        TranslationError: If the value breaks a rule.
    """
    declared = annotation.get("schemes")
    if _UNSAFE_CHARACTERS.search(value) or value != value.strip():
        # URL parsers strip or drop these, which would hide a scheme
        raise TranslationError(
            "File references can't contain control characters, or start or "
            "end with whitespace.",
            path,
        )
    match = _SCHEME.match(value)
    if match:
        scheme = match.group(1).lower()
        # A scheme that isn't forbidden may be any text before a colon
        named = "The scheme of the value" if server else f"The scheme '{scheme}'"
        if scheme in FORBIDDEN_SCHEMES:
            raise TranslationError(
                f"File references can't use the scheme '{scheme}'.", path
            )
        if isinstance(declared, list) and scheme not in declared:
            raise TranslationError(
                f"{named} isn't one of the schemes of this file "
                f"reference ({', '.join(declared)}).",
                path,
            )
        if scheme not in allowed:
            raise TranslationError(
                f"{named} isn't on the allow-list of the deployment.",
                path,
            )
        return
    if isinstance(declared, list):
        raise TranslationError(
            "This file reference takes only absolute URIs with the schemes "
            f"{', '.join(declared)}, not paths.",
            path,
        )
    if not value:
        raise TranslationError("A file reference can't be empty.", path)
    # Also percent-encoded: a path can end up in a URI reference (CWL)
    if ".." in re.split(r"[/\\]", unquote(value)):
        raise TranslationError("Paths can't have '..' segments.", path)
    if value.startswith("~"):
        raise TranslationError("Paths can't start with '~'.", path)
    if re.match(r"[/\\]{2}", value):
        # A network-path reference or UNC path names a host
        raise TranslationError("Paths can't start with two slashes.", path)
    if value.startswith(("/", "\\")) and not allow_absolute_paths:
        raise TranslationError(
            "Absolute paths are allowed only in deployments with a shared file system.",
            path,
        )


@dataclass(frozen=True)
class _Scope:
    """A subschema, with the resolver of its base URI.

    Attributes:
        schema: The subschema.
        resolver: Resolver for the references of the subschema.
    """

    schema: Any
    resolver: Resolver


class _Translator:
    """Validates and translates the input values of one IO schema."""

    def __init__(
        self,
        schema: dict[str, Any],
        binding: EngineBinding,
        allowed_schemes: Iterable[str],
        allow_absolute_paths: bool,
        server: bool = False,
    ) -> None:
        """Prepare the translation.

        Args:
            schema: IO schema, valid against the profile.
            binding: Engine binding.
            allowed_schemes: URI schemes of the deployment's allow-list.
            allow_absolute_paths: Whether absolute paths are allowed.
            server: Whether the values come from a request to a server,
                whose error messages must not repeat the value (see
                :func:`from_workflow_params`).

        Raises:
            ValueError: If ``allowed_schemes`` names a forbidden scheme.
        """
        self.binding = binding
        self.server = server
        # Subschemas applied in place to a value, by schema and value
        self._in_place_cache: dict[tuple[int, int, int], tuple[Any, list[_Scope]]] = {}
        self.allowed = _allow_list(allowed_schemes)
        self.allow_absolute_paths = allow_absolute_paths
        uri = schema["$id"] if isinstance(schema.get("$id"), str) else _DOCUMENT_URI
        registry: Registry = build_registry([get_schemas_dir()]).with_resource(
            uri, DRAFT202012.create_resource(schema)
        )
        root = _Scope(schema, registry.resolver(base_uri=uri))
        self.inputs = self._descend(root, schema["properties"]["inputs"])
        # Whether the validity of subschemas can be kept during a translation
        self._static = _static(schema)
        self.validator = _MemoisingValidator(
            schema,
            registry=registry,
            format_checker=_format_checker(Draft202012Validator),
        )

    def translate(self, values: Any) -> dict[str, Any]:
        """Validate and translate the input values.

        Args:
            values: Input values.

        Returns:
            The ``workflow_params``.

        Raises:
            TranslationError: If the values can't be translated, or if the
                schema has a reference that can't be resolved locally.
        """
        return {name: value for _, name, value in self.bind(values)}

    def bind(self, values: Any) -> list[tuple[str, str, Any]]:
        """Validate and translate the input values, member by member.

        Args:
            values: Input values.

        Returns:
            For each member of the values, its name in the values, its key in
            ``workflow_params`` and its translated value.

        Raises:
            TranslationError: If the values can't be translated, or if the
                schema has a reference that can't be resolved locally.
        """
        self._in_place_cache.clear()
        # The values outlive the memo, so the identities of their parts
        # aren't reused while it is kept
        token = _VALIDITY.set({} if self._static else None)
        try:
            with _fail_closed():
                return self._bind(values)
        finally:
            _VALIDITY.reset(token)

    def input_keys(self) -> dict[str, list[str]]:
        """Get the keys in ``workflow_params`` that the inputs can bind to.

        Collects the properties that any subschema of ``inputs`` declares,
        and for each the keys that it can bind to, whatever the value: every
        ``x-ga4gh-parameter.name`` of its subschemas, and its own name.
        :meth:`bind` gives the key for a given value.

        Returns:
            The keys of each property of ``inputs``, by its name; the first
            is the key of the first binding in the schema.

        Raises:
            TranslationError: If the schema has a reference that can't be
                resolved locally.
        """
        with _fail_closed():
            inputs = self._closure([self.inputs])
            names = dict.fromkeys(
                name
                for scope in inputs
                if isinstance(scope.schema.get("properties"), dict)
                for name in scope.schema["properties"]
            )
            keys: dict[str, list[str]] = {}
            for name in names:
                scopes = self._closure(self._children(inputs, name, None, None))
                bound = [
                    scope.schema["x-ga4gh-parameter"]["name"]
                    for scope in scopes
                    if isinstance(scope.schema.get("x-ga4gh-parameter"), dict)
                    and isinstance(scope.schema["x-ga4gh-parameter"].get("name"), str)
                ]
                keys[name] = [
                    self._qualify(key) for key in dict.fromkeys([*bound, name])
                ]
            return keys

    def _bind(self, values: Any) -> list[tuple[str, str, Any]]:
        """Validate and translate the input values, member by member.

        Args:
            values: Input values.

        Returns:
            For each member, its name, its key and its translated value.

        Raises:
            TranslationError: If the values can't be translated.
            referencing.exceptions.Unresolvable: If a reference of the schema
                can't be resolved locally.
        """
        self._validate(self.inputs, values)
        if not isinstance(values, dict):
            raise TranslationError("The input values must be a JSON object.")
        inputs = self._expand([self.inputs], values)
        bound: list[tuple[str, str, Any]] = []
        names: set[str] = set()
        for key, value in values.items():
            scopes = self._expand(self._children(inputs, key, value, values), value)
            name = self._qualify(self._name(scopes, key))
            if name in names:
                raise TranslationError(
                    f"Two inputs bind to the engine parameter '{name}'.", (key,)
                )
            names.add(name)
            bound.append((key, name, self._value(scopes, value, (key,))))
        return bound

    def _validate(self, scope: _Scope, values: Any) -> None:
        """Validate the input values against ``inputs``.

        Args:
            scope: Schema of ``inputs``.
            values: Input values.

        Raises:
            TranslationError: If the values aren't valid, with the schema's
                ``x-ga4gh-error-message`` where it has one.
        """
        validator = self._validator(scope)
        error = jsonschema.exceptions.best_match(validator.iter_errors(values))
        if error is None:
            return
        if self.server:
            message = self._server_message(scope, error)
        else:
            custom = _error_message(error.schema)
            message = custom if custom is not None else error.message
        raise TranslationError(message, tuple(error.absolute_path))

    def _server_message(
        self, scope: _Scope, error: jsonschema.exceptions.ValidationError
    ) -> str:
        """Build the message of a failure for a server.

        Args:
            scope: Schema that the values were validated against.
            error: The failure.

        Returns:
            The ``x-ga4gh-error-message`` that covers the failure, or else a
            message built from the keyword that failed, without the value.

        Raises:
            referencing.exceptions.Unresolvable: If a reference of the schema
                can't be resolved locally.
        """
        chain = self._evaluation_path(scope, error)
        for schema in chain if chain is not None else [error.schema]:
            custom = _error_message(schema)
            if custom is not None:
                return custom
        keyword = error.validator
        if keyword is None:
            # The schema `false`, which has no keywords
            return "The schema doesn't allow a value here."
        # The value of the keyword: a list for `anyOf`, `oneOf` and
        # `required` (the checks of its type are for type checkers)
        value = error.validator_value
        if keyword in ("anyOf", "oneOf") and error.context and isinstance(value, list):
            # No branch accepts the value: the first branch with a message
            # covers the failure
            for branch in value:
                custom = _error_message(branch)
                if custom is not None:
                    return custom
        if (
            keyword == "required"
            and isinstance(value, list)
            and isinstance(error.instance, dict)
        ):
            missing = next(name for name in value if name not in error.instance)
            if not error.absolute_path:
                # A property of `inputs`: name its key in `workflow_params`
                missing = self.input_keys().get(missing, [missing])[0]
            return f"The required member '{missing}' is missing."
        return f"The value fails the keyword '{keyword}' of the schema."

    def _evaluation_path(
        self, scope: _Scope, error: jsonschema.exceptions.ValidationError
    ) -> list[Any] | None:
        """Find the schemas that a failure passed at its own location.

        Follows the schema path of the failure from the schema that was
        validated, through references, to the schema with the keyword that
        failed. The schemas are those since the last keyword that moved to
        another location (e.g., ``properties``); the first of them with an
        ``x-ga4gh-error-message`` covers the failure (see "Error messages"
        in "Keywords").

        Args:
            scope: Schema that the values were validated against.
            error: The failure.

        Returns:
            The schemas, outermost first, or ``None`` if the path can't be
            followed.

        Raises:
            referencing.exceptions.Unresolvable: If a reference of the schema
                can't be resolved locally.
        """
        path = list(error.absolute_schema_path)
        last = len(path) - 1
        # Depth first: the subschema that the path names, or the target of
        # `$ref` next to it
        stack: list[tuple[_Scope, int, tuple[Any, ...], int]] = [
            (scope, 0, (scope.schema,), 0)
        ]
        while stack:
            current, index, chain, references = stack.pop()
            schema = current.schema
            if not isinstance(schema, dict):
                continue
            if index == last and schema is error.schema:
                return list(chain)
            if isinstance(schema.get("$ref"), str) and references < _MAX_REFERENCES:
                resolved = current.resolver.lookup(schema["$ref"])
                target = _Scope(resolved.contents, resolved.resolver)
                stack.append((target, index, (*chain, target.schema), references + 1))
            if index >= last:
                continue
            step = _step(schema, path, index)
            if step is None:
                continue
            sub, consumed, moves = step
            child = self._descend(current, sub)
            stack.append(
                (
                    child,
                    index + consumed,
                    (child.schema,) if moves else (*chain, child.schema),
                    0,
                )
            )
        return None

    def _validator(self, scope: _Scope) -> Draft202012Validator:
        """Get a validator of a subschema.

        Args:
            scope: The subschema.

        Returns:
            A validator that resolves the references of the subschema
            against its base URI.
        """
        # `_resolver` keeps the base URI of the subschema; jsonschema has no
        # public way to validate a subschema in the context of its document.
        return self.validator.evolve(schema=scope.schema, _resolver=scope.resolver)

    def _valid(self, scope: _Scope, schema: Any, value: Any) -> bool:
        """Check whether a value is valid against a subschema of a schema.

        Within :meth:`bind`, a known result is reused, also a failure, which
        :func:`_memoised_descend` validates again to report its errors.

        Args:
            scope: The schema.
            schema: The subschema, which ``scope`` applies in place.
            value: The value.

        Returns:
            Whether the value is valid against the subschema.
        """
        known = _VALIDITY.get()
        key = _validity_key(schema, scope.resolver, value)
        if known is not None and key in known:
            return known[key]
        errors = self._validator(scope).descend(value, schema)
        return next(errors, None) is None

    def _expand(self, scopes: Iterable[_Scope], value: Any) -> list[_Scope]:
        """Collect the subschemas that apply to a value at one location.

        Follows ``$ref`` and ``allOf``; the branches of ``anyOf`` and
        ``oneOf`` that the value is valid against; ``if`` and ``then`` if the
        value is valid against ``if``, ``else`` otherwise; and the
        ``dependentSchemas`` of the members that an object has.

        Args:
            scopes: Subschemas at the location.
            value: Value at the location.

        Returns:
            The subschemas that apply, in the order of the schema.

        Raises:
            TranslationError: If a subschema uses ``$dynamicRef``, which the
                translation doesn't model (fail closed).
            referencing.exceptions.Unresolvable: If a reference can't be
                resolved locally.
        """
        found: list[_Scope] = []
        seen: set[int] = set()
        queue = deque(scopes)
        while queue:
            scope = queue.popleft()
            schema = scope.schema
            if not isinstance(schema, dict) or id(schema) in seen:
                continue
            # Subschemas are never copied, so the identity of one is stable
            seen.add(id(schema))
            found.append(scope)
            for keyword in _UNSUPPORTED:
                if keyword in schema:
                    raise TranslationError(
                        f"The schema uses '{keyword}', which the translation "
                        "doesn't support."
                    )
            if "if" in schema:
                valid = self._valid(scope, schema["if"], value)
                if valid:
                    queue.append(self._descend(scope, schema["if"]))
                branch = "then" if valid else "else"
                if branch in schema:
                    queue.append(self._descend(scope, schema[branch]))
            dependent = schema.get("dependentSchemas")
            if isinstance(dependent, dict) and isinstance(value, dict):
                queue.extend(
                    self._descend(scope, sub)
                    for name, sub in dependent.items()
                    if name in value
                )
            if isinstance(schema.get("$ref"), str):
                resolved = scope.resolver.lookup(schema["$ref"])
                queue.append(_Scope(resolved.contents, resolved.resolver))
            queue.extend(
                self._descend(scope, sub) for sub in _subschemas(schema, "allOf")
            )
            for keyword in ("anyOf", "oneOf"):
                queue.extend(
                    self._descend(scope, sub)
                    for sub in _subschemas(schema, keyword)
                    if self._valid(scope, sub, value)
                )
        return found

    def _closure(self, scopes: Iterable[_Scope]) -> list[_Scope]:
        """Collect the subschemas that may apply at one location, for any value.

        Follows ``$ref`` and every in-place applicator (``allOf``, ``anyOf``,
        ``oneOf``, ``if``, ``then``, ``else`` and ``dependentSchemas``),
        whatever the value.

        Args:
            scopes: Subschemas at the location.

        Returns:
            The subschemas, in the order of the schema.

        Raises:
            referencing.exceptions.Unresolvable: If a reference can't be
                resolved locally.
        """
        found: list[_Scope] = []
        seen: set[int] = set()
        queue = deque(scopes)
        while queue:
            scope = queue.popleft()
            schema = scope.schema
            if not isinstance(schema, dict) or id(schema) in seen:
                continue
            seen.add(id(schema))
            found.append(scope)
            if isinstance(schema.get("$ref"), str):
                resolved = scope.resolver.lookup(schema["$ref"])
                queue.append(_Scope(resolved.contents, resolved.resolver))
            for keyword in ("allOf", "anyOf", "oneOf"):
                queue.extend(
                    self._descend(scope, sub) for sub in _subschemas(schema, keyword)
                )
            queue.extend(
                self._descend(scope, schema[keyword])
                for keyword in ("if", "then", "else")
                if keyword in schema
            )
            dependent = schema.get("dependentSchemas")
            if isinstance(dependent, dict):
                queue.extend(self._descend(scope, sub) for sub in dependent.values())
        return found

    def _children(
        self,
        scopes: Iterable[_Scope],
        key: str | int,
        item: Any,
        parent: Any,
    ) -> list[_Scope]:
        """Collect the subschemas of a member of an object or an array.

        The ``unevaluatedProperties`` or ``unevaluatedItems`` of a subschema
        apply only if neither the subschema nor the subschemas that it applies
        in place (e.g., through ``allOf``) evaluate the member or item.

        Args:
            scopes: Subschemas that apply to the object or array.
            key: Key of the member, or index of the item.
            item: Value of the member or item.
            parent: The object or array; or ``None`` for any value, for which
                ``unevaluatedProperties`` and ``unevaluatedItems`` always
                apply (to collect every subschema that may apply).

        Returns:
            The subschemas of the member or item.

        Raises:
            referencing.exceptions.Unresolvable: If a reference can't be
                resolved locally.
        """
        keyword = (
            "unevaluatedItems" if isinstance(key, int) else "unevaluatedProperties"
        )
        children: list[_Scope] = []
        for scope in scopes:
            children.extend(self._evaluating(scope, key, item))
            if keyword not in scope.schema:
                continue
            if parent is None or not any(
                self._evaluating(other, key, item)
                or (other is not scope and keyword in other.schema)
                for other in self._in_place(scope, parent)
            ):
                children.append(self._descend(scope, scope.schema[keyword]))
        return children

    def _in_place(self, scope: _Scope, parent: Any) -> list[_Scope]:
        """Get the subschemas that a schema applies in place to a value.

        Cached for the members of one object or array, so that the cost
        doesn't grow with the square of their number.

        Args:
            scope: The schema.
            parent: The object or array.

        Returns:
            The subschemas (see :meth:`_expand`).

        Raises:
            referencing.exceptions.Unresolvable: If a reference can't be
                resolved locally.
        """
        cache_key = (id(scope.schema), id(scope.resolver), id(parent))
        cached = self._in_place_cache.get(cache_key)
        # The cache keeps the value, so its id isn't reused while cached
        if cached is None:
            cached = (parent, self._expand([scope], parent))
            self._in_place_cache[cache_key] = cached
        return cached[1]

    def _evaluating(self, scope: _Scope, key: str | int, item: Any) -> list[_Scope]:
        """Collect the subschemas of a member or item that a schema names.

        Covers ``prefixItems``, ``items`` and ``contains`` (if the item is
        valid against it) of arrays, and ``properties``,
        ``patternProperties`` and ``additionalProperties`` of objects; not
        the in-place applicators or the ``unevaluated*`` keywords.

        Args:
            scope: Schema of the object or array.
            key: Key of the member, or index of the item.
            item: Value of the member or item.

        Returns:
            The subschemas.
        """
        schema = scope.schema
        children: list[_Scope] = []
        if isinstance(key, int):
            prefix = schema.get("prefixItems")
            if isinstance(prefix, list) and key < len(prefix):
                children.append(self._descend(scope, prefix[key]))
            elif "items" in schema:
                children.append(self._descend(scope, schema["items"]))
            if "contains" in schema and self._valid(scope, schema["contains"], item):
                children.append(self._descend(scope, schema["contains"]))
            return children
        matched = False
        properties = schema.get("properties")
        if isinstance(properties, dict) and key in properties:
            children.append(self._descend(scope, properties[key]))
            matched = True
        patterns = schema.get("patternProperties")
        # The values passed validation, which compiled the same patterns
        for pattern, sub in patterns.items() if isinstance(patterns, dict) else ():
            if search(pattern, key):
                children.append(self._descend(scope, sub))
                matched = True
        if not matched and "additionalProperties" in schema:
            children.append(self._descend(scope, schema["additionalProperties"]))
        return children

    @staticmethod
    def _descend(scope: _Scope, schema: Any) -> _Scope:
        """Enter a subschema, which may set its own base URI with ``$id``.

        Args:
            scope: Schema that contains the subschema.
            schema: The subschema.

        Returns:
            The subschema with its resolver.
        """
        if isinstance(schema, dict) and isinstance(schema.get("$id"), str):
            resource = DRAFT202012.create_resource(schema)
            return _Scope(schema, scope.resolver.in_subresource(resource))
        return _Scope(schema, scope.resolver)

    def _value(self, scopes: Iterable[_Scope], value: Any, path: Path) -> Any:
        """Translate a value and the values nested in it.

        Args:
            scopes: Subschemas at the location of the value.
            value: The value.
            path: Location of the value in the input values.

        Returns:
            The value for the engine.

        Raises:
            TranslationError: If a file reference breaks the rules.
        """
        applicable = self._expand(scopes, value)
        if isinstance(value, list):
            return [
                self._value(
                    self._children(applicable, index, item, value),
                    item,
                    (*path, index),
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, dict):
            if (
                self.binding.descriptor_type == "CWL"
                and value.get("class") in _CWL_CLASSES
            ):
                # The runner would stage it, unchecked
                raise TranslationError(
                    "CWL File and Directory objects aren't input values: give a "
                    "file reference as a string.",
                    path,
                )
            return {
                key: self._value(
                    self._children(applicable, key, item, value), item, (*path, key)
                )
                for key, item in value.items()
            }
        if not isinstance(value, str):
            return value
        annotations = [
            scope.schema["x-ga4gh-file"]
            for scope in applicable
            if isinstance(scope.schema.get("x-ga4gh-file"), dict)
        ]
        if not annotations:
            return value
        # Every file reference that applies must accept the value
        for annotation in annotations:
            _check_file_value(
                annotation,
                value,
                self.allowed,
                self.allow_absolute_paths,
                path,
                self.server,
            )
        kinds = {annotation.get("kind") for annotation in annotations}
        if len(kinds) > 1:
            raise TranslationError(
                "File references of different kinds apply to this value.", path
            )
        if self.binding.descriptor_type == "CWL":
            kind = "Directory" if kinds == {"directory"} else "File"
            return {"class": kind, "location": value}
        return value

    @staticmethod
    def _name(scopes: Iterable[_Scope], key: str) -> str:
        """Get the engine name of an input.

        Args:
            scopes: Subschemas that apply to the input.
            key: Name of the property of ``inputs``.

        Returns:
            ``x-ga4gh-parameter.name``, or the name of the property.
        """
        for scope in scopes:
            parameter = scope.schema.get("x-ga4gh-parameter")
            if isinstance(parameter, dict) and isinstance(parameter.get("name"), str):
                return parameter["name"]
        return key

    def _qualify(self, name: str) -> str:
        """Qualify an engine name as the descriptor type requires.

        Args:
            name: Name of the parameter, relative to the entry point.

        Returns:
            The key in ``workflow_params``.
        """
        if self.binding.descriptor_type == "WDL":
            return f"{self.binding.entry_point}.{name}"
        return name


class _ReverseTranslator:
    """Translates ``workflow_params`` back into input values, and validates them."""

    def __init__(self, translator: _Translator, allow_paths: bool) -> None:
        """Prepare the translation.

        Args:
            translator: Translator of the schema, for servers.
            allow_paths: Whether CWL objects may give ``path`` instead of
                ``location``.
        """
        self.translator = translator
        self.cwl = translator.binding.descriptor_type == "CWL"
        self.allow_paths = allow_paths
        # Key in `workflow_params` of each member of the values
        self.keys: dict[str, str] = {}
        # Location in the values of each CWL object that became a string,
        # with the field that held the string and the class of the object
        self.files: dict[Path, tuple[str, str]] = {}

    def translate(self, params: Any) -> dict[str, Any]:
        """Translate and validate ``workflow_params``.

        Args:
            params: The ``workflow_params``.

        Returns:
            The input values.

        Raises:
            WorkflowParamsError: If the request is rejected.
        """
        self.keys = {}
        self.files = {}
        if not isinstance(params, dict):
            raise WorkflowParamsError("workflow_params must be a JSON object.")
        try:
            input_keys = self.translator.input_keys()
        except TranslationError as exc:
            raise WorkflowParamsError(exc.message) from exc
        values = self._match(params, input_keys)
        try:
            bound = self.translator.bind(values)
        except TranslationError as exc:
            raise self._error(exc.message, exc.path) from exc
        self._check_keys(bound, input_keys)
        self._check_files({name: value for name, _, value in bound})
        return values

    def _match(
        self, params: dict[str, Any], input_keys: dict[str, list[str]]
    ) -> dict[str, Any]:
        """Match the members of ``workflow_params`` with inputs (rules 1 and 2).

        Args:
            params: The ``workflow_params``.
            input_keys: The keys of each input, by its name.

        Returns:
            The input values, not yet validated.

        Raises:
            WorkflowParamsError: If a member matches several inputs, or
                matches none but has the name of one, or if a CWL object
                can't be replaced.
        """
        inputs: dict[str, list[str]] = {}
        for name, keys in input_keys.items():
            for key in keys:
                inputs.setdefault(key, []).append(name)
        values: dict[str, Any] = {}
        for key, value in params.items():
            matched = inputs.get(key, [])
            if len(matched) > 1:
                # The input whose first binding is the key, if only one
                first = [name for name in matched if input_keys[name][0] == key]
                matched = first if len(first) == 1 else matched
            if len(matched) > 1:
                raise WorkflowParamsError(
                    f"Several inputs bind to the key '{key}'.", (key,)
                )
            name = matched[0] if matched else key
            if not matched and name in input_keys:
                # Under its own name, it would be taken for that input
                raise WorkflowParamsError(
                    "This member matches no input: the input of this name binds "
                    f"to the key '{input_keys[name][0]}'.",
                    (key,),
                )
            self.keys[name] = key
            values[name] = self._files(value, (name,)) if self.cwl else value
        return values

    def _check_keys(
        self, bound: list[tuple[str, str, Any]], input_keys: dict[str, list[str]]
    ) -> None:
        """Check that each input binds to the key that it came under.

        Args:
            bound: The members of the values, with their keys for the value
                (see :meth:`_Translator.bind`).
            input_keys: The keys of each input, by its name.

        Raises:
            WorkflowParamsError: If an input binds to another key for its
                value (e.g., through ``anyOf``).
        """
        for name, key, _ in bound:
            if name in input_keys and key != self.keys[name]:
                raise WorkflowParamsError(
                    f"For this value, the input binds to the key '{key}'.",
                    (self.keys[name],),
                )

    def _check_files(self, translated: dict[str, Any]) -> None:
        """Check that each CWL object was at a file reference of its class.

        Args:
            translated: The values, translated again (by member name).

        Raises:
            WorkflowParamsError: If no file reference applies at an object,
                or one of the other kind.
        """
        for path, (_, kind) in self.files.items():
            target: Any = translated
            for part in path:
                target = target[part]
            if not isinstance(target, dict):
                raise self._error(
                    f"CWL {kind} objects are accepted only where the schema has "
                    "a file reference.",
                    path,
                    file_field=False,
                )
            if target["class"] != kind:
                raise self._error(
                    f"The file reference takes a {target['class']}, not a {kind}.",
                    (*path, "class"),
                    file_field=False,
                )

    def _files(self, value: Any, path: Path) -> Any:
        """Replace the CWL ``File`` and ``Directory`` objects in a value.

        Args:
            value: Value of a member of ``workflow_params``.
            path: Location of the value in the input values.

        Returns:
            The value, with each object replaced by its ``location`` (or
            ``path``).

        Raises:
            WorkflowParamsError: If an object can't be replaced.
        """
        if isinstance(value, list):
            return [
                self._files(item, (*path, index)) for index, item in enumerate(value)
            ]
        if not isinstance(value, dict):
            return value
        kind = value.get("class")
        if kind not in _CWL_CLASSES:
            return {key: self._files(item, (*path, key)) for key, item in value.items()}
        if "contents" in value:
            # The data of the file would bypass the checks of file references
            raise self._error(
                f"CWL {kind} objects with 'contents' aren't accepted: give a file "
                "reference.",
                (*path, "contents"),
                file_field=False,
            )
        if "location" in value:
            field = "location"
        elif "path" in value and self.allow_paths:
            field = "path"
        else:
            accepted = "'location' or 'path'" if self.allow_paths else "'location'"
            raise self._error(
                f"A CWL {kind} object needs {accepted}.", path, file_field=False
            )
        others = sorted(set(value) - {"class", field})
        if others:
            # E.g., `secondaryFiles` or `listing` would carry more files
            raise self._error(
                f"This field of CWL {kind} objects isn't accepted.",
                (*path, others[0]),
                file_field=False,
            )
        if not isinstance(value[field], str):
            raise self._error(
                f"The {field} of a CWL {kind} object must be a string.",
                (*path, field),
                file_field=False,
            )
        self.files[path] = (field, kind)
        return value[field]

    def _error(
        self, message: str, path: Sequence[str | int], file_field: bool = True
    ) -> WorkflowParamsError:
        """Locate an error of the input values in ``workflow_params``.

        Args:
            message: Description of the error.
            path: Location of the error in the input values.
            file_field: Whether a location at a CWL object that became a
                string gets the field that held the string.

        Returns:
            The error, located in ``workflow_params``.
        """
        if not path:
            return WorkflowParamsError(message)
        located: list[str | int] = [self.keys[str(path[0])], *path[1:]]
        if file_field and tuple(path) in self.files:
            located.append(self.files[tuple(path)][0])
        return WorkflowParamsError(message, located)


@contextmanager
def _fail_closed() -> Iterator[None]:
    """Reject schemas with references that can't be resolved locally.

    Yields:
        Nothing; the block runs inside.

    Raises:
        TranslationError: If the block meets such a reference.
    """
    try:
        yield
    except Unresolvable as exc:
        # Fail closed: IO schemas must be bundled
        raise TranslationError(
            f"The schema references '{exc.ref}', which can't be resolved "
            "locally; IO schemas must be bundled."
        ) from exc


def _error_message(schema: Any) -> str | None:
    """Get the ``x-ga4gh-error-message`` of a schema.

    Args:
        schema: The schema.

    Returns:
        The message, or ``None`` if the schema has none.
    """
    message = schema.get("x-ga4gh-error-message") if isinstance(schema, dict) else None
    return message if isinstance(message, str) else None


def _step(
    schema: dict[str, Any], path: list[Any], index: int
) -> tuple[Any, int, bool] | None:
    """Follow a schema path into a subschema.

    Args:
        schema: Schema at the current position of the path.
        path: Schema path of a failure.
        index: Current position in the path.

    Returns:
        The subschema that the path names, how many segments of the path it
        takes, and whether the subschema applies at another location of the
        instance; or ``None`` if the path doesn't name a subschema of the
        schema.
    """
    keyword = path[index]
    if keyword not in schema:
        return None
    if keyword in _SAME_LOCATION_SINGLE or keyword in _NEW_LOCATION_SINGLE:
        return schema[keyword], 1, keyword in _NEW_LOCATION_SINGLE
    if keyword in _SAME_LOCATION_NAMED or keyword in _NEW_LOCATION_NAMED:
        container = schema[keyword]
        name = path[index + 1]
        if isinstance(container, dict) and name in container:
            return container[name], 2, keyword in _NEW_LOCATION_NAMED
        if isinstance(container, list) and isinstance(name, int):
            return container[name], 2, keyword in _NEW_LOCATION_NAMED
    return None


def _subschemas(schema: dict[str, Any], keyword: str) -> list[Any]:
    """Get the subschemas of an applicator such as ``allOf``.

    Args:
        schema: Schema with the applicator.
        keyword: Name of the applicator.

    Returns:
        The subschemas, or an empty list.
    """
    subschemas = schema.get(keyword)
    return subschemas if isinstance(subschemas, list) else []
