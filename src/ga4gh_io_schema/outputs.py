"""Normalisation of the outputs of WES runs.

A WES server reports the outputs of a run in ``RunLog.outputs``, in a shape
that depends on the engine and the server. :func:`normalise_outputs` turns it
into the *normalised outputs object* of the run, keyed by the outputs of an IO
schema, as defined on the Outputs page of the specification: outputs are found
by name first and otherwise by ``x-ga4gh-output-glob`` among the files that the
server lists for the run; the object is validated against ``outputs`` (for a
run that completed) or property by property (for a run that didn't); and
everything that doesn't fit is reported instead of dropped silently.

The normaliser never fetches anything: it works on the run log, the files
that the server lists, and the options that the deployment gives.
"""

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import jsonschema
from jsonschema.protocols import Validator
from referencing import Registry, Resource
from referencing._core import Resolver
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from ga4gh_io_schema.validator import validate_schema

#: Final states of a WES 1.1 run; outputs are normalised only for these.
FINAL_STATES = frozenset(
    {"COMPLETE", "EXECUTOR_ERROR", "SYSTEM_ERROR", "CANCELED", "PREEMPTED"}
)
#: The state of a run that completed; its outputs must conform to the schema.
COMPLETE = "COMPLETE"

#: Conformance of the outputs of a run (see :attr:`NormalisedOutputs.conformance`).
CONFORMANT = "conformant"
NON_CONFORMANT = "non-conformant"
PARTIAL = "partial"

# A value has a scheme if it starts with one (see File references, Values).
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
# C0 and C1 control characters and DEL, which listed paths must not contain
# (Outputs, x-ga4gh-output-glob); the input checks of wes.py follow other
# rules (File references, Values), so the expressions aren't shared.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# A Windows path, whose drive letter would look like a scheme
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
# A percent sign that doesn't start a valid percent-encoded octet
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
# Base URI of a schema document without $id, to resolve its local references
_DOCUMENT_URI = "urn:ga4gh-io-schema:document"
# Most references followed in a row, against reference cycles
_MAX_REFS = 32
# Keywords that give a schema a shape that values are converted by
_SHAPE = frozenset({"x-ga4gh-file", "items", "properties", "additionalProperties"})


class NormalisationError(ValueError):
    """The outputs of a run can't be normalised (e.g., the run hasn't ended).

    Raised for faults of the input as a whole; problems with single outputs
    or listed files are reported in :class:`NormalisedOutputs` instead.
    """


@dataclass(frozen=True)
class OutputError:
    """A value of the normalised outputs object that fails validation.

    Attributes:
        output: The name of the output, or ``None`` for an error of the whole
            object (e.g., a missing required output).
        location: JSON path of the value in the normalised outputs object.
        message: Description of the error.
    """

    output: str | None
    location: str
    message: str


@dataclass(frozen=True)
class SkippedFile:
    """An entry of the run's file listing that the normaliser skipped.

    Attributes:
        entry: The entry as the server listed it.
        reason: Why it was skipped (e.g., a ``..`` segment).
    """

    entry: Any
    reason: str


@dataclass(frozen=True)
class UnconvertedOutput:
    """An output reported by name whose value can't be given as URIs.

    Attributes:
        output: The name of the output in the schema.
        value: The value that the engine reported.
        reason: Why it can't be converted (e.g., a local path outside the
            output directory).
    """

    output: str
    value: Any
    reason: str


@dataclass
class NormalisedOutputs:
    """The normalised outputs object of a run, with the report on it.

    Attributes:
        state: The WES state of the run.
        conformance: ``conformant`` or ``non-conformant`` for a run that
            completed (``COMPLETE``), ``partial`` for a run that ended in
            another final state.
        outputs: The normalised outputs object, keyed by the outputs of the
            schema; outputs that the run didn't produce are absent.
        errors: Validation errors. For a run that completed, errors of the
            object against ``outputs``; the object is kept as it is. For a
            run that didn't, errors of the outputs that were left out.
        removed: The outputs of a run that didn't complete that were left
            out because their values are invalid, by name.
        ambiguous: Outputs of one file whose glob matches several files, by
            name, with the URIs of the matches; the outputs are absent.
        unconverted: Outputs reported by name whose values can't be given as
            URIs (e.g., local paths); the outputs are absent.
        undeclared: Outputs that the engine reports by name but the schema
            doesn't declare, by their name in the engine, with their values.
        unmatched_files: URIs of listed files that no output found, sorted.
        skipped_files: Entries of the listing that failed the checks.
    """

    state: str
    conformance: str
    outputs: dict[str, Any]
    errors: list[OutputError] = field(default_factory=list)
    removed: dict[str, Any] = field(default_factory=dict)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)
    unconverted: list[UnconvertedOutput] = field(default_factory=list)
    undeclared: dict[str, Any] = field(default_factory=dict)
    unmatched_files: list[str] = field(default_factory=list)
    skipped_files: list[SkippedFile] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        """Return the result as a JSON-compatible object.

        Returns:
            An object with the camelCase keys ``state``, ``conformance``,
            ``outputs``, ``errors``, ``removed``, ``ambiguous``,
            ``unconverted``, ``undeclared``, ``unmatchedFiles`` and
            ``skippedFiles``.
        """
        return {
            "state": self.state,
            "conformance": self.conformance,
            "outputs": self.outputs,
            "errors": [
                {"output": e.output, "location": e.location, "message": e.message}
                for e in self.errors
            ],
            "removed": self.removed,
            "ambiguous": self.ambiguous,
            "unconverted": [
                {"output": u.output, "value": u.value, "reason": u.reason}
                for u in self.unconverted
            ],
            "undeclared": self.undeclared,
            "unmatchedFiles": self.unmatched_files,
            "skippedFiles": [
                {"entry": s.entry, "reason": s.reason} for s in self.skipped_files
            ],
        }


def normalise_outputs(
    schema: dict[str, Any],
    run_log: Mapping[str, Any],
    output_dir: str | None = None,
    local_dir: str | None = None,
    files: Sequence[Any] | None = None,
) -> NormalisedOutputs:
    """Build the normalised outputs object of a WES run.

    The shape of ``RunLog.outputs`` is detected:

    - an object keyed by output name (cwltool, Toil; Cromwell, miniwdl and
      Conquest with names qualified with the WDL workflow): outputs are found
      by name; CWL ``File`` and ``Directory`` objects give their
      ``location``;
    - an array of files (Sapporo: objects with ``file_name``, relative to
      the output directory; or strings, paths or URIs): a listing;
    - an object with only ``filesystem`` (and ``S3``), WESkit: ``filesystem``
      is a listing, relative to the working directory of the run; the
      presigned URLs of ``S3`` are ignored;
    - absent, ``null`` or ``{}`` (e.g., Nextflow and Snakemake on most
      servers): nothing.

    Args:
        schema: The IO schema; it must conform to the profile.
        run_log: The WES ``RunLog`` of the run, with ``state`` and, if the
            run has outputs, ``outputs``.
        output_dir: The URI of the output directory of the run (the URI
            prefix under which the server keeps its files, without a
            trailing ``/``, which is removed if given). Needed to match globs
            against a listing, and to turn paths into URIs.
        local_dir: The absolute local path of the output directory, as the
            engine sees it; absolute paths and ``file:`` URIs that the engine
            reports under it become URIs under ``output_dir``. Needs
            ``output_dir``.
        files: The files of the run, as paths relative to the output
            directory or as URIs under it; replaces the listing of the run
            log, if any (e.g., for servers that list files elsewhere).

    Returns:
        The normalised outputs object and the report on it.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema doesn't conform
            to the profile.
        NormalisationError: If the run hasn't ended, the run log has no
            supported shape, the options are inconsistent, or several
            outputs have the same name in the engine.
    """
    validate_schema(schema)
    state = _final_state(run_log)
    base = _check_output_dir(output_dir)
    local = _check_local_dir(local_dir, base)
    named, listing = _split_run_log(run_log.get("outputs"), schema)
    if files is not None:
        if isinstance(files, (str, bytes)) or not isinstance(files, Sequence):
            raise NormalisationError("The listing of files must be an array.")
        listing = list(files)
    if listing and base is None:
        raise NormalisationError(
            "The run lists files: give the URI of its output directory."
        )

    resolver = _resolver(schema)
    properties = _output_properties(schema)
    context = _Context(base=base, local=local)
    result = NormalisedOutputs(state=state, conformance=CONFORMANT, outputs={})

    checked = _check_listing(listing, base, result.skipped_files)
    covered: set[tuple[str, ...]] = set()
    engine_names = _engine_names(schema, properties)
    for name, prop in properties.items():
        engine_name = engine_names[name]
        if engine_name in named:
            _take_named(name, prop, named[engine_name], resolver, context, result)
        elif isinstance(prop, dict) and "x-ga4gh-output-glob" in prop:
            _take_glob(name, prop, checked, context, result, covered)

    for engine_name, value in named.items():
        if engine_name not in engine_names.values():
            result.undeclared[engine_name] = value
    found = set(_strings(result.outputs))
    result.unmatched_files = sorted(
        uri
        for uri in (_build_uri(base, s) for s in checked if s not in covered)
        if uri not in found
    )

    _validate(schema, state, result)
    return result


@dataclass(frozen=True)
class _Context:
    """Options for turning reported paths into URIs.

    Attributes:
        base: URI of the output directory, without a trailing ``/``.
        local: Local path of the output directory, without a trailing ``/``.
    """

    base: str | None
    local: str | None


class _Unconvertible(Exception):
    """A reported value can't be given as a URI."""


def _final_state(run_log: Mapping[str, Any]) -> str:
    """Return the state of a run that has ended.

    Args:
        run_log: The WES run log.

    Returns:
        The state.

    Raises:
        NormalisationError: If the run log isn't an object, or the run hasn't
            ended.
    """
    if not isinstance(run_log, Mapping):
        raise NormalisationError("The run log must be a JSON object.")
    state = run_log.get("state")
    if not isinstance(state, str) or state not in FINAL_STATES:
        raise NormalisationError(
            f"The run is in the state {state!r}, not in a final state "
            f"({', '.join(sorted(FINAL_STATES))}): outputs are normalised only "
            "for runs that have ended."
        )
    return state


def _check_output_dir(output_dir: str | None) -> str | None:
    """Check the URI of the output directory.

    Args:
        output_dir: The URI, if given.

    Returns:
        The URI without its trailing ``/``, if given.

    Raises:
        NormalisationError: If it isn't an absolute URI without query and
            fragment.
    """
    if output_dir is None:
        return None
    if not _SCHEME.match(output_dir) or "?" in output_dir or "#" in output_dir:
        raise NormalisationError(
            f"The output directory {output_dir!r} must be an absolute URI "
            "without query or fragment."
        )
    if output_dir.endswith("/"):
        output_dir = output_dir[:-1]
    return output_dir


def _check_local_dir(local_dir: str | None, base: str | None) -> str | None:
    """Check the local path of the output directory.

    Args:
        local_dir: The path, if given.
        base: The URI of the output directory, if given.

    Returns:
        The path without trailing ``/``, if given.

    Raises:
        NormalisationError: If it isn't absolute, or the URI of the output
            directory is missing.
    """
    if local_dir is None:
        return None
    if not local_dir.startswith("/"):
        raise NormalisationError(f"The local directory {local_dir!r} must be absolute.")
    if base is None:
        raise NormalisationError(
            "A local directory needs the URI of the output directory."
        )
    return local_dir.rstrip("/")


def _split_run_log(
    outputs: Any, schema: dict[str, Any]
) -> tuple[dict[str, Any], list[Any]]:
    """Split ``RunLog.outputs`` into outputs reported by name and a listing.

    Args:
        outputs: ``RunLog.outputs``.
        schema: The IO schema, whose engine names decide whether an object
            with ``filesystem`` is a WESkit listing.

    Returns:
        The outputs by name in the engine, and the listed files.

    Raises:
        NormalisationError: If the shape isn't supported.
    """
    if outputs is None:
        return {}, []
    if isinstance(outputs, list):
        return {}, [_sapporo_entry(entry) for entry in outputs]
    if not isinstance(outputs, dict):
        raise NormalisationError(
            "RunLog.outputs must be an object, an array or null, not "
            f"{type(outputs).__name__}."
        )
    names = set(_engine_names(schema, _output_properties(schema)).values())
    named = dict(outputs)
    if "S3" not in names:
        # WESkit's presigned URLs: credentials, never copied into a report
        named.pop("S3", None)
    if "filesystem" not in names and isinstance(named.get("filesystem"), list):
        return {k: v for k, v in named.items() if k != "filesystem"}, list(
            named["filesystem"]
        )
    return named, []


def _sapporo_entry(entry: Any) -> Any:
    """Return the path of an entry of a Sapporo listing.

    Args:
        entry: An object with ``file_name`` (and ``file_url``), or another
            entry, which is returned as it is.

    Returns:
        The ``file_name`` of a Sapporo object, or the entry.
    """
    if isinstance(entry, dict) and "file_name" in entry:
        name = entry["file_name"]
        # Without file_url, which may carry credentials (e.g., a token)
        return name if isinstance(name, str) else {"file_name": name}
    return entry


def _output_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the properties of ``outputs`` of an IO schema.

    Args:
        schema: The IO schema.

    Returns:
        The output schemas by name; empty if the schema has no outputs.
    """
    outputs = schema.get("properties", {}).get("outputs", {})
    properties = outputs.get("properties", {}) if isinstance(outputs, dict) else {}
    return properties if isinstance(properties, dict) else {}


def _engine_names(schema: dict[str, Any], properties: dict[str, Any]) -> dict[str, str]:
    """Return the name of each output in the engine.

    The name is ``x-ga4gh-parameter.name`` or the property name, qualified
    with the entry point for WDL.

    Args:
        schema: The IO schema.
        properties: Its output schemas by name.

    Returns:
        The engine names, by output name.

    Raises:
        NormalisationError: If two outputs have the same engine name.
    """
    workflow = schema.get("x-ga4gh-workflow", {})
    prefix = ""
    if workflow.get("descriptor_type") == "WDL" and workflow.get("entry_point"):
        prefix = f"{workflow['entry_point']}."
    names: dict[str, str] = {}
    for name, prop in properties.items():
        binding = prop.get("x-ga4gh-parameter", {}) if isinstance(prop, dict) else {}
        engine_name = prefix + binding.get("name", name)
        if engine_name in names.values():
            raise NormalisationError(
                f"Several outputs have the name {engine_name!r} in the engine."
            )
        names[name] = engine_name
    return names


def _registry(schema: dict[str, Any]) -> tuple[str, Registry]:
    """Return a registry of an IO schema, to resolve its references.

    Args:
        schema: The IO schema.

    Returns:
        The base URI of the schema (its ``$id``, or a URN if it has none),
        and a registry with the schema and its embedded resources.
    """
    base = schema.get("$id", _DOCUMENT_URI)
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    return base, Registry().with_resource(base, resource).crawl()


def _resolver(schema: dict[str, Any]) -> Resolver[Any]:
    """Return a resolver of the references of an IO schema.

    Args:
        schema: The IO schema.

    Returns:
        A ``referencing`` resolver whose base URI is that of the schema.
    """
    base, registry = _registry(schema)
    return registry.resolver(base_uri=base)


def _check_listing(
    listing: Iterable[Any], base: str | None, skipped: list[SkippedFile]
) -> list[tuple[str, ...]]:
    """Check the files that the server lists, and return the safe ones.

    Args:
        listing: The listed entries: paths relative to the output directory,
            or URIs under it.
        base: The URI of the output directory (given if there are entries).
        skipped: List that skipped entries are appended to.

    Returns:
        The segments of the relative path of each file that passed, without
        duplicates, in the order of the listing.
    """
    checked: dict[tuple[str, ...], None] = {}
    for entry in listing:
        try:
            if not isinstance(entry, str):
                raise _Unconvertible("not a path or URI")
            if _SCHEME.match(entry):
                segments = _uri_segments(entry, base or "")
            else:
                if entry.startswith("/"):
                    raise _Unconvertible("an absolute path")
                segments = tuple(entry.split("/"))
            _check_segments(segments)
        except _Unconvertible as exc:
            skipped.append(SkippedFile(entry=_redact(entry), reason=str(exc)))
            continue
        checked[segments] = None
    return list(checked)


def _redact(entry: Any) -> Any:
    """Remove the query and fragment of a listed URI, before reporting it.

    Queries of listed URIs (e.g., of presigned URLs) may carry credentials.

    Args:
        entry: The listed entry.

    Returns:
        The entry, without query and fragment if it is a URI.
    """
    if isinstance(entry, str) and _SCHEME.match(entry):
        return re.split(r"[?#]", entry, maxsplit=1)[0]
    return entry


def _uri_segments(uri: str, base: str) -> tuple[str, ...]:
    """Return the decoded segments of a listed URI under the output directory.

    Args:
        uri: The listed URI.
        base: The URI of the output directory, without a trailing ``/``.

    Returns:
        The percent-decoded segments of the rest of the URI.

    Raises:
        _Unconvertible: If the URI isn't under the output directory, has a
            query or fragment, or isn't validly percent-encoded.
    """
    prefix = f"{base}/"
    if not uri.startswith(prefix):
        raise _Unconvertible("not under the output directory")
    rest = uri[len(prefix) :]
    if "?" in rest or "#" in rest:
        raise _Unconvertible("a URI with a query or fragment")
    if _BAD_ESCAPE.search(rest):
        raise _Unconvertible("invalid percent-encoding")
    try:
        segments = tuple(unquote(s, errors="strict") for s in rest.split("/"))
    except UnicodeDecodeError as exc:
        raise _Unconvertible("percent-encoding that isn't UTF-8") from exc
    if any("/" in segment for segment in segments):
        # A %2F would hide several segments in one (e.g., x%2F..%2F..%2Fy)
        raise _Unconvertible("an encoded '/'")
    return segments


def _check_segments(segments: tuple[str, ...]) -> None:
    """Check the segments of a relative path from a run.

    Args:
        segments: The segments.

    Raises:
        _Unconvertible: If a segment is empty, ``.`` or ``..``, or contains a
            backslash or a control character, or the first segment contains a
            colon.
    """
    for segment in segments:
        if not segment:
            raise _Unconvertible("an empty segment")
        if segment in (".", ".."):
            raise _Unconvertible(f"a '{segment}' segment")
        if "\\" in segment:
            raise _Unconvertible("a backslash")
        if _CONTROL.search(segment):
            raise _Unconvertible("a control character")
    if ":" in segments[0]:
        raise _Unconvertible("a colon in the first segment")


def _build_uri(base: str | None, segments: tuple[str, ...]) -> str:
    """Build the URI of a file of the run from its relative path.

    Each segment is percent-encoded (all characters but the unreserved ones
    of RFC 3986, as UTF-8 with uppercase hex digits) and appended to the URI
    of the output directory.

    Args:
        base: The URI of the output directory.
        segments: The segments of the relative path.

    Returns:
        The URI.
    """
    return "/".join([str(base), *(quote(segment, safe="") for segment in segments)])


def _take_named(
    name: str,
    prop: Any,
    value: Any,
    resolver: Resolver[Any],
    context: _Context,
    result: NormalisedOutputs,
) -> None:
    """Add an output that the engine reports by name.

    Args:
        name: The name of the output.
        prop: Its schema.
        value: The reported value.
        resolver: Resolver of the references of the IO schema.
        context: Options for turning paths into URIs.
        result: The result to add to.
    """
    if value is None:
        return
    try:
        result.outputs[name] = _convert(value, prop, resolver, context)
    except _Unconvertible as exc:
        result.unconverted.append(
            UnconvertedOutput(output=name, value=value, reason=str(exc))
        )


def _convert(
    value: Any, schema: Any, resolver: Resolver[Any], context: _Context
) -> Any:
    """Convert a reported value into the shape of its schema.

    File references become URIs (the ``location`` of CWL ``File`` and
    ``Directory`` objects, paths under the output directory as URIs);
    arrays, records, objects of files, and ``anyOf`` or ``oneOf`` with one
    branch besides ``{"type": "null"}`` are converted item by item. ``null``
    items of arrays are left out; ``null`` values in objects are kept (they
    are allowed where the schema says so, e.g., an optional member of a WDL
    struct). Other values are kept as they are, also if they don't fit the
    schema, for validation to report.

    Args:
        value: The reported value, not ``null``.
        schema: Its schema.
        resolver: Resolver of the references of the IO schema.
        context: Options for turning paths into URIs.

    Returns:
        The converted value.

    Raises:
        _Unconvertible: If a file reference can't be given as a URI.
    """
    schema, resolver = _follow(schema, resolver)
    if not isinstance(schema, dict):
        return value
    if "x-ga4gh-file" in schema:
        return _convert_file(value, context)
    branch = _single_branch(schema)
    if branch is not None:
        return _convert(value, branch, resolver, context)
    if isinstance(value, list) and "prefixItems" not in schema:
        items = schema.get("items", True)
        return [
            _convert(item, items, resolver, context)
            for item in value
            if item is not None
        ]
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        return {
            key: None
            if item is None
            else _convert(item, properties.get(key, additional), resolver, context)
            for key, item in value.items()
        }
    return value


def _single_branch(schema: dict[str, Any]) -> Any:
    """Return the only branch of ``anyOf`` or ``oneOf`` that isn't ``null``.

    Args:
        schema: A schema without a shape of its own (no file reference).

    Returns:
        The branch, or ``None`` if the schema has a shape of its own, or no
        such single branch.
    """
    if _SHAPE & set(schema):
        return None
    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            others = [b for b in branches if b != {"type": "null"}]
            if len(others) == 1:
                return others[0]
    return None


def _follow(schema: Any, resolver: Resolver[Any]) -> tuple[Any, Resolver[Any]]:
    """Follow the ``$ref`` of a schema that has no shape of its own.

    Args:
        schema: The schema.
        resolver: Resolver for its references.

    Returns:
        The schema that describes the shape (``True`` if a reference can't be
        resolved, so that the value is kept as it is), and its resolver.
    """
    depth = 0
    while isinstance(schema, dict) and "$ref" in schema and not _SHAPE & set(schema):
        if depth >= _MAX_REFS:
            return True, resolver
        try:
            resolved = resolver.lookup(schema["$ref"])
        except Unresolvable:
            return True, resolver
        schema, resolver = resolved.contents, resolved.resolver
        depth += 1
    return schema, resolver


def _convert_file(value: Any, context: _Context) -> Any:
    """Convert a reported file reference into a URI.

    Args:
        value: The reported value: a string, or a CWL ``File`` or
            ``Directory`` object.
        context: Options for turning paths into URIs.

    Returns:
        The URI, or the value as it is if it is neither (for validation to
        report).

    Raises:
        _Unconvertible: If the value is a path or ``file:`` URI that can't be
            given as a URI of the output directory.
    """
    if isinstance(value, dict) and value.get("class") in ("File", "Directory"):
        value = value.get("location") or value.get("path")
        if not isinstance(value, str):
            raise _Unconvertible("a File or Directory object without location")
    if not isinstance(value, str):
        return value
    if _WINDOWS_PATH.match(value):
        raise _Unconvertible("a Windows path")
    if _SCHEME.match(value):
        if not value.lower().startswith("file:"):
            return value
        value = _file_uri_path(value)
    if value.startswith("/"):
        if context.local is None or not value.startswith(f"{context.local}/"):
            raise _Unconvertible("a local path outside the output directory")
        value = value[len(context.local) + 1 :]
    if context.base is None:
        raise _Unconvertible("a relative path, and no output directory given")
    segments = tuple(value.split("/"))
    _check_segments(segments)
    return _build_uri(context.base, segments)


def _file_uri_path(uri: str) -> str:
    """Return the local path of a ``file:`` URI.

    Args:
        uri: The URI.

    Returns:
        The percent-decoded path.

    Raises:
        _Unconvertible: If the URI names a host other than ``localhost``, or
            has a query or fragment.
    """
    parts = urlsplit(uri)
    if parts.netloc not in ("", "localhost") or parts.query or parts.fragment:
        raise _Unconvertible("a file URI of another host, or with a query")
    if _BAD_ESCAPE.search(parts.path):
        raise _Unconvertible("invalid percent-encoding")
    try:
        return unquote(parts.path, errors="strict")
    except UnicodeDecodeError as exc:
        raise _Unconvertible("percent-encoding that isn't UTF-8") from exc


def _take_glob(
    name: str,
    prop: dict[str, Any],
    checked: list[tuple[str, ...]],
    context: _Context,
    result: NormalisedOutputs,
    covered: set[tuple[str, ...]],
) -> None:
    """Add an output found by its ``x-ga4gh-output-glob``.

    Args:
        name: The name of the output.
        prop: Its schema, with the glob.
        checked: The listed files that passed the checks.
        context: Options with the URI of the output directory.
        result: The result to add to.
        covered: Set of listed files that an output found, updated.
    """
    is_array = prop.get("type") == "array"
    reference = (prop.get("items") if is_array else prop) or {}
    annotation = reference.get("x-ga4gh-file", {})
    glob = tuple(prop["x-ga4gh-output-glob"].split("/"))
    if annotation.get("kind") == "directory":
        candidates = sorted({s[:i] for s in checked for i in range(1, len(s))})
        matches = [c for c in candidates if _match(glob, c)]
        covered.update(s for s in checked for m in matches if s[: len(m)] == m)
    else:
        matches = [s for s in checked if _match(glob, s)]
        secondary = {
            (*m[:-1], _secondary_name(m[-1], pattern))
            for m in matches
            for pattern in annotation.get("secondaryFiles", [])
        }
        covered.update(matches)
        covered.update(secondary & set(checked))
        matches = [m for m in matches if m not in secondary]
    uris = [_build_uri(context.base, m) for m in sorted(matches, key="/".join)]
    if not uris:
        return
    if is_array:
        result.outputs[name] = uris
    elif len(uris) == 1:
        result.outputs[name] = uris[0]
    else:
        result.ambiguous[name] = uris


def _match(glob: tuple[str, ...], path: tuple[str, ...]) -> bool:
    """Match a glob against a relative path, segment by segment.

    Dynamic programming over the segments, so that the time is polynomial in
    the lengths of the glob and the path (globs come from untrusted schemas).

    Args:
        glob: The segments of the glob; ``**`` matches any number of segments.
        path: The segments of the path.

    Returns:
        Whether the glob matches the whole path.
    """
    # ends[j]: whether the glob segments so far match the first j segments
    ends = [True] + [False] * len(path)
    for segment in glob:
        if segment == "**":
            for j in range(1, len(path) + 1):
                ends[j] = ends[j] or ends[j - 1]
        else:
            ends = [False] + [
                ends[j] and _match_segment(segment, path[j]) for j in range(len(path))
            ]
    return ends[-1]


def _match_segment(glob: str, name: str) -> bool:
    """Match a segment of a glob against a segment of a path.

    ``*`` matches any characters (also none) and ``?`` exactly one; all other
    characters match themselves. Greedy matching with backtracking to the
    last ``*`` only, in time proportional to the product of the lengths.

    Args:
        glob: The segment of the glob.
        name: The segment of the path.

    Returns:
        Whether the glob matches the whole segment.
    """
    g = n = 0
    star, mark = -1, 0
    while n < len(name):
        if g < len(glob) and glob[g] in ("?", name[n]):
            g += 1
            n += 1
        elif g < len(glob) and glob[g] == "*":
            star, mark = g, n
            g += 1
        elif star >= 0:
            g = star + 1
            mark += 1
            n = mark
        else:
            return False
    return all(char == "*" for char in glob[g:])


def _secondary_name(name: str, pattern: str) -> str:
    """Return the name of a secondary file of a file.

    Args:
        name: The name of the file.
        pattern: A suffix pattern; each leading ``^`` removes one extension.

    Returns:
        The name of the secondary file.
    """
    suffix = pattern.lstrip("^")
    for _ in range(len(pattern) - len(suffix)):
        if "." in name:
            name = name[: name.rindex(".")]
    return name + suffix


def _strings(value: Any) -> Iterator[str]:
    """Yield the strings in a JSON value, at any depth.

    Args:
        value: The value.

    Yields:
        Each string.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _check_file_value(
    validator: Validator, annotation: Any, instance: Any, schema: dict[str, Any]
) -> Iterator[jsonschema.exceptions.ValidationError]:
    """Check an output value of a file reference (``x-ga4gh-file``).

    Output values are absolute URIs, with one of the annotation's
    ``schemes`` if it has any.

    Args:
        validator: The validator.
        annotation: The file reference annotation.
        instance: The value.
        schema: The schema with the annotation.

    Yields:
        An error if the value isn't an absolute URI, or its scheme isn't one
        of ``schemes``.
    """
    if not isinstance(instance, str) or not isinstance(annotation, dict):
        return
    match = _SCHEME.match(instance)
    if match is None:
        yield jsonschema.exceptions.ValidationError(
            f"{instance!r} is not an absolute URI"
        )
        return
    schemes = annotation.get("schemes")
    scheme = match.group(0)[:-1].lower()
    if isinstance(schemes, list) and scheme not in schemes:
        yield jsonschema.exceptions.ValidationError(
            f"The scheme {scheme!r} of {instance!r} is not one of {schemes!r}"
        )


_OutputsValidator = jsonschema.validators.extend(
    jsonschema.Draft202012Validator, {"x-ga4gh-file": _check_file_value}
)


def _validate(schema: dict[str, Any], state: str, result: NormalisedOutputs) -> None:
    """Validate the normalised outputs object, and set its conformance.

    Args:
        schema: The IO schema.
        state: The state of the run.
        result: The result to validate and update.
    """
    base, registry = _registry(schema)
    pointer = "#/properties/outputs"
    if state == COMPLETE:
        wrapper: dict[str, Any] = {"$ref": base + pointer}
        if "outputs" not in schema.get("properties", {}):
            wrapper = {"properties": {}}
    else:
        wrapper = {
            "properties": {
                name: {"$ref": f"{base}{pointer}/properties/{_escape(name)}"}
                for name in result.outputs
            }
        }
    validator = _OutputsValidator(
        wrapper,
        registry=registry,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )
    try:
        errors = sorted(
            validator.iter_errors(result.outputs), key=lambda e: list(map(str, e.path))
        )
    except Unresolvable as exc:
        raise NormalisationError(
            f"The IO schema references '{exc.ref}', which can't be resolved locally."
        ) from exc
    for error in errors:
        output = str(error.path[0]) if error.path else None
        result.errors.append(OutputError(output, error.json_path, error.message))
    if state != COMPLETE:
        result.conformance = PARTIAL
        for error in result.errors:
            if error.output in result.outputs:
                result.removed[error.output] = result.outputs.pop(error.output)
    elif result.errors:
        result.conformance = NON_CONFORMANT


def _escape(name: str) -> str:
    """Escape a property name for a JSON Pointer in a URI fragment.

    Args:
        name: The name.

    Returns:
        The name as a reference token (``~0``, ``~1``), percent-encoded.
    """
    return quote(name.replace("~", "~0").replace("/", "~1"), safe="")
