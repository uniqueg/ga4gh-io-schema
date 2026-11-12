# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Translation of input values into the parameters of WES run requests.

Implements the engine bindings of the profile (see the page "Engine
bindings" of the specification): input values that are valid against the
``inputs`` of an IO schema become the ``workflow_params`` of a GA4GH
Workflow Execution Service (WES) run request, in the shape that the engine
of the schema's descriptor type expects, and, with the fields that come from
the Tool Registry Service (TRS), a full ``RunRequest``.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote

import jsonschema
from jsonschema.validators import Draft202012Validator
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

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

#: A location in the input values: keys of objects and indexes of arrays.
Path = tuple[str | int, ...]


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
    trs_url: str, tool_id: str, version_id: str, descriptor_type: str
) -> str:
    """Build the TRS URL of the plain primary descriptor of a tool version.

    Args:
        trs_url: Base URL of the TRS API, e.g.,
            ``https://trs.example.org/ga4gh/trs/v2``.
        tool_id: Id of the tool (``Tool.id``).
        version_id: Id of the tool version (``ToolVersion.id``).
        descriptor_type: TRS descriptor type, e.g., ``WDL``.

    Returns:
        The URL of ``GET /tools/{id}/versions/{version_id}/PLAIN_{type}/descriptor``,
        with the ids percent-encoded.
    """
    return (
        f"{trs_url.rstrip('/')}/tools/{quote(tool_id, safe='')}"
        f"/versions/{quote(version_id, safe='')}"
        f"/PLAIN_{descriptor_type}/descriptor"
    )


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
) -> None:
    """Check a value of a file reference (see :func:`check_file_value`).

    Args:
        annotation: The ``x-ga4gh-file`` annotation.
        value: The value.
        allowed: URI schemes of the allow-list, in lowercase.
        allow_absolute_paths: Whether absolute paths are allowed.
        path: Location of the value in the input values.

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
        if scheme in FORBIDDEN_SCHEMES:
            raise TranslationError(
                f"File references can't use the scheme '{scheme}'.", path
            )
        if isinstance(declared, list) and scheme not in declared:
            raise TranslationError(
                f"The scheme '{scheme}' isn't one of the schemes of this file "
                f"reference ({', '.join(declared)}).",
                path,
            )
        if scheme not in allowed:
            raise TranslationError(
                f"The scheme '{scheme}' isn't on the allow-list of the deployment.",
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
    ) -> None:
        """Prepare the translation.

        Args:
            schema: IO schema, valid against the profile.
            binding: Engine binding.
            allowed_schemes: URI schemes of the deployment's allow-list.
            allow_absolute_paths: Whether absolute paths are allowed.

        Raises:
            ValueError: If ``allowed_schemes`` names a forbidden scheme.
        """
        self.binding = binding
        self.allowed = _allow_list(allowed_schemes)
        self.allow_absolute_paths = allow_absolute_paths
        uri = schema["$id"] if isinstance(schema.get("$id"), str) else _DOCUMENT_URI
        registry: Registry = build_registry([get_schemas_dir()]).with_resource(
            uri, DRAFT202012.create_resource(schema)
        )
        root = _Scope(schema, registry.resolver(base_uri=uri))
        self.inputs = self._descend(root, schema["properties"]["inputs"])
        self.validator = Draft202012Validator(
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
        try:
            return self._translate(values)
        except Unresolvable as exc:
            # Fail closed: IO schemas must be bundled
            raise TranslationError(
                f"The schema references '{exc.ref}', which can't be resolved "
                "locally; IO schemas must be bundled."
            ) from exc

    def _translate(self, values: Any) -> dict[str, Any]:
        """Validate and translate the input values.

        Args:
            values: Input values.

        Returns:
            The ``workflow_params``.

        Raises:
            TranslationError: If the values can't be translated.
            referencing.exceptions.Unresolvable: If a reference of the schema
                can't be resolved locally.
        """
        self._validate(self.inputs, values)
        if not isinstance(values, dict):
            raise TranslationError("The input values must be a JSON object.")
        inputs = self._expand([self.inputs], values)
        params: dict[str, Any] = {}
        for key, value in values.items():
            scopes = self._expand(self._children(inputs, key, value), value)
            name = self._qualify(self._name(scopes, key))
            if name in params:
                raise TranslationError(
                    f"Two inputs bind to the engine parameter '{name}'.", (key,)
                )
            params[name] = self._value(scopes, value, (key,))
        return params

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
        custom = (
            error.schema.get("x-ga4gh-error-message")
            if isinstance(error.schema, dict)
            else None
        )
        message = custom if isinstance(custom, str) else error.message
        raise TranslationError(message, tuple(error.absolute_path))

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
                condition = self._descend(scope, schema["if"])
                valid = self._validator(condition).is_valid(value)
                if valid:
                    queue.append(condition)
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
                for sub in _subschemas(schema, keyword):
                    branch = self._descend(scope, sub)
                    if self._validator(branch).is_valid(value):
                        queue.append(branch)
        return found

    def _children(
        self, scopes: Iterable[_Scope], key: str | int, item: Any
    ) -> list[_Scope]:
        """Collect the subschemas of a member of an object or an array.

        ``unevaluatedProperties`` and ``unevaluatedItems`` apply only if no
        other keyword of any of the subschemas (which include the in-place
        applicators, such as ``allOf``) evaluates the member or item.

        Args:
            scopes: Subschemas that apply to the object or array.
            key: Key of the member, or index of the item.
            item: Value of the member or item.

        Returns:
            The subschemas of the member or item.
        """
        children: list[_Scope] = []
        unevaluated: list[_Scope] = []
        for scope in scopes:
            schema = scope.schema
            if isinstance(key, int):
                prefix = schema.get("prefixItems")
                if isinstance(prefix, list) and key < len(prefix):
                    children.append(self._descend(scope, prefix[key]))
                elif "items" in schema:
                    children.append(self._descend(scope, schema["items"]))
                if "contains" in schema:
                    contains = self._descend(scope, schema["contains"])
                    if self._validator(contains).is_valid(item):
                        children.append(contains)
                if "unevaluatedItems" in schema:
                    unevaluated.append(self._descend(scope, schema["unevaluatedItems"]))
                continue
            matched = False
            properties = schema.get("properties")
            if isinstance(properties, dict) and key in properties:
                children.append(self._descend(scope, properties[key]))
                matched = True
            patterns = schema.get("patternProperties")
            # The values passed validation, which compiled the same patterns
            for pattern, sub in patterns.items() if isinstance(patterns, dict) else ():
                if re.search(pattern, key):
                    children.append(self._descend(scope, sub))
                    matched = True
            if not matched and "additionalProperties" in schema:
                children.append(self._descend(scope, schema["additionalProperties"]))
            if "unevaluatedProperties" in schema:
                unevaluated.append(
                    self._descend(scope, schema["unevaluatedProperties"])
                )
        return children or unevaluated

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
                    self._children(applicable, index, item), item, (*path, index)
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, dict):
            if self.binding.descriptor_type == "CWL" and value.get("class") in (
                "File",
                "Directory",
            ):
                # The runner would stage it, unchecked
                raise TranslationError(
                    "CWL File and Directory objects aren't input values: give a "
                    "file reference as a string.",
                    path,
                )
            return {
                key: self._value(
                    self._children(applicable, key, item), item, (*path, key)
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
                annotation, value, self.allowed, self.allow_absolute_paths, path
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
