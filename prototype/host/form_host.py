# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Host of the form proof of concept: serves a form for one IO schema.

A proof of concept, not a product (see ``docs/adoption/form.md``). The host
validates the IO schema once, at the start, and serves the form
(``index.html`` and the scripts next to this file) and the schema. The form
sends the values that the user enters; the host validates them against
``inputs`` with the Python validator, with the messages of
``x-ga4gh-error-message`` (see "Error messages" in
``docs/specification/keywords.md``), and turns valid values into a WES run
request with :func:`ga4gh_io_schema.wes.build_run_request`. It shows the
request; only if it is given the URL of a WES, it also submits it there on
request and shows the run id and state.

Run it with ``python prototype/host/form_host.py`` and open
http://127.0.0.1:8000/.
"""

import argparse
import json
import posixpath
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from collections.abc import Iterable, Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema.validators import Draft202012Validator
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from ga4gh_io_schema.patterns import PatternError, ValuesValidator, search
from ga4gh_io_schema.validator import validate_schema
from ga4gh_io_schema.wes import (
    DEFAULT_ALLOWED_SCHEMES,
    FORBIDDEN_SCHEMES,
    TranslationError,
    build_run_request,
    trs_descriptor_url,
)

HERE = Path(__file__).resolve().parent
#: The schema of the end-to-end demo, the default.
DEMO_SCHEMA = HERE.parents[1] / "examples" / "demo" / "ga4gh-io.schema.json"
#: Files of the form, by URL path: file name and media type.
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/form.css": ("form.css", "text/css; charset=utf-8"),
    "/form.js": ("form.js", "text/javascript; charset=utf-8"),
    "/io-schema-form.js": ("io-schema-form.js", "text/javascript; charset=utf-8"),
}
#: Largest request body that the host reads, in bytes.
MAX_BODY = 1024 * 1024
#: Seconds to wait for a schema from a URL.
TIMEOUT = 30
#: Base URI of an IO schema without an ``$id``, for its local references.
DOCUMENT_URI = "urn:ga4gh-io-schema:form"
#: Applicators whose subschemas apply to the same value.
IN_PLACE = ("not", "if", "then", "else")
IN_PLACE_LISTS = ("allOf", "anyOf", "oneOf")

#: Name of the IO schema file next to the primary descriptor in TRS.
SCHEMA_NAME = "ga4gh-io.schema.json"
#: Error of a request for the schema when no workflow is picked.
PICK_A_WORKFLOW = "Pick a workflow: the host serves no default schema."
#: Names of the host in requests that are accepted, besides its address.
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})
#: Error of valid values for which the host knows no workflow URL.
NO_WORKFLOW_URL = (
    "The host knows no workflow URL: the schema names neither its TRS tool "
    "version (x-ga4gh-workflow.trs_tool_id and trs_version_id, with --trs-url) "
    "nor its primary descriptor (x-ga4gh-workflow.primary_descriptor_path)."
)

#: A subschema with the resolver of its base URI.
Scope = tuple[Any, Any]


def load_schema(source: str) -> dict[str, Any]:
    """Load an IO schema and validate it against the profile.

    Args:
        source: Path of a schema file, or an ``http(s)`` URL of a schema,
            e.g., the TRS URL of the file ``ga4gh-io.schema.json`` of a tool
            version, which returns a ``FileWrapper`` with the schema in
            ``content``.

    Returns:
        The schema.

    Raises:
        OSError: If the schema can't be read (also ``urllib.error.URLError``).
        ValueError: If the schema isn't JSON, or a ``FileWrapper`` has no
            ``content``.
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the profile.
    """
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            document = json.loads(response.read())
        if isinstance(document, dict) and "$schema" not in document:
            content = document.get("content")
            if not isinstance(content, str):
                raise ValueError("The response is no IO schema and no FileWrapper.")
            document = json.loads(content)
    else:
        document = json.loads(Path(source).read_text(encoding="utf-8"))
    validate_schema(document)
    return document


def list_workflows(trs_url: str) -> list[dict[str, str]]:
    """List the workflows of a TRS: its tool versions, per descriptor type.

    Args:
        trs_url: Base URL of the TRS API.

    Returns:
        The workflows, each with ``tool_id``, ``version_id``,
        ``descriptor_type`` and the ``name`` of the tool.

    Raises:
        OSError: If the TRS can't be reached or fails (also
            ``urllib.error.HTTPError``).
        ValueError: If the answer isn't a list of tools.
    """
    tools = _fetch_json(urllib.request.Request(f"{trs_url.rstrip('/')}/tools"))
    if not isinstance(tools, list):
        raise ValueError("The TRS answer isn't a list of tools.")
    workflows = []
    try:
        for tool in tools:
            tool_id = tool["id"]
            for version in tool["versions"]:
                for descriptor_type in version.get("descriptor_type") or []:
                    workflows.append(
                        {
                            "tool_id": tool_id,
                            "version_id": version["id"],
                            "descriptor_type": descriptor_type,
                            "name": tool.get("name") or tool_id,
                        }
                    )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("The TRS answer isn't a list of tools.") from exc
    return workflows


def load_trs_schema(
    trs_url: str, tool_id: str, version_id: str, descriptor_type: str
) -> tuple[dict[str, Any], str]:
    """Load the IO schema of a tool version from TRS, as a client does.

    The schema is the file ``ga4gh-io.schema.json`` of type ``OTHER`` in the
    directory of the primary descriptor (see "Publishing convention" in
    ``docs/adoption/trs.md``). It must name the tool version and the
    descriptor type that it was fetched for, where it names them (step 2 of
    the guide for portals and clients, without the checksum).

    Args:
        trs_url: Base URL of the TRS API.
        tool_id: Id of the tool.
        version_id: Id of the tool version.
        descriptor_type: TRS descriptor type, e.g., ``WDL``.

    Returns:
        The schema, valid against the profile, and the ``workflow_url`` of
        run requests: the TRS URL of the plain primary descriptor, by the
        path that TRS lists for it, so that relative imports of multi-file
        workflows resolve to files of the tool version.

    Raises:
        OSError: If the TRS can't be reached or fails (also
            ``urllib.error.HTTPError``).
        ValueError: If an id is empty, ``.`` or ``..``, the tool version
            has no IO schema, the path of its primary descriptor has empty,
            ``.`` or ``..`` segments, or the schema isn't JSON or names
            another tool version or descriptor type.
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the profile.
    """
    if {tool_id, version_id, descriptor_type} & {"", ".", ".."}:
        raise ValueError("Empty ids and the ids . and .. aren't allowed.")
    version = (
        f"{trs_url.rstrip('/')}/tools/{urllib.parse.quote(tool_id, safe='')}"
        f"/versions/{urllib.parse.quote(version_id, safe='')}"
        f"/{urllib.parse.quote(descriptor_type, safe='')}"
    )
    files = _fetch_json(urllib.request.Request(f"{version}/files"))
    try:
        # path and file_type are optional in TRS: skip entries without them
        primary = next(
            f["path"] for f in files if f.get("file_type") == "PRIMARY_DESCRIPTOR"
        )
        path = posixpath.join(posixpath.dirname(primary), SCHEMA_NAME)
        # Entries may have more fields, e.g., checksum
        found = any(
            f.get("path") == path and f.get("file_type") == "OTHER" for f in files
        )
    except (KeyError, TypeError, AttributeError, StopIteration):
        found = False
    if not found:
        raise ValueError(
            f"The tool version has no IO schema ({SCHEMA_NAME} of type OTHER "
            "next to the primary descriptor)."
        )
    schema = load_schema(f"{version}/descriptor/{urllib.parse.quote(path, safe='')}")
    block = schema.get("x-ga4gh-workflow") or {}
    expected = {
        "trs_tool_id": tool_id,
        "trs_version_id": version_id,
        "descriptor_type": descriptor_type,
    }
    for key, value in expected.items():
        if key in block and block[key] != value:
            raise ValueError(
                f"The schema is for another workflow: x-ga4gh-workflow.{key} is "
                f"{block[key]!r}, not {value!r}."
            )
    url = trs_descriptor_url(trs_url, tool_id, version_id, descriptor_type, primary)
    return schema, url


def workflow_url(schema: dict[str, Any], trs_url: str | None = None) -> str | None:
    """Find the ``workflow_url`` of the run request for a schema.

    Args:
        schema: IO schema.
        trs_url: Base URL of the TRS API that serves the workflow, if any.

    Returns:
        The TRS URL of the plain primary descriptor (by its path, if the
        workflow block has ``primary_descriptor_path``), if a TRS URL is
        given and the workflow block names the tool version; else the path
        of the primary descriptor, which WES resolves against the files
        attached to the request; else ``None``.

    Raises:
        ValueError: If the TRS URL would have a primary descriptor path with
            empty, ``.`` or ``..`` segments.
    """
    block = schema.get("x-ga4gh-workflow") or {}
    ids = [block.get(key) for key in ("trs_tool_id", "trs_version_id")]
    path = block.get("primary_descriptor_path")
    path = path if isinstance(path, str) else None
    if trs_url and all(isinstance(value, str) for value in ids):
        return trs_descriptor_url(trs_url, *ids, block["descriptor_type"], path)
    return path


def check_values(
    schema: dict[str, Any],
    values: Any,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    url: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Validate input values and turn them into a WES run request.

    Args:
        schema: IO schema, valid against the profile.
        values: Input values from the form.
        allowed_schemes: URI schemes of the deployment's allow-list.
        url: The ``workflow_url`` of the request (see :func:`workflow_url`).

    Returns:
        The run request (``workflow_params``, ``workflow_type``,
        ``workflow_type_version`` and ``workflow_url``) and no errors; or
        ``None`` and the errors, each with the location of the value
        (``pointer``, a JSON Pointer into the values) and its ``message``.
    """
    try:
        errors = validation_errors(schema, values)
    except Unresolvable as exc:
        message = f"The schema references '{exc.ref}', which can't be resolved."
        return None, [{"pointer": "", "message": message}]
    except PatternError as exc:
        return None, [{"pointer": "", "message": str(exc)}]
    if errors:
        return None, errors
    if url is None:
        return None, [{"pointer": "", "message": NO_WORKFLOW_URL}]
    try:
        request = build_run_request(
            schema, values, url, allowed_schemes=allowed_schemes
        )
    except TranslationError as exc:
        return None, [{"pointer": exc.pointer, "message": exc.message}]
    return request, []


def submit_run(wes_url: str, request: dict[str, Any]) -> tuple[str, str | None]:
    """Submit a run request to a WES and read the state of the run.

    The request is posted as ``multipart/form-data``, as WES defines it,
    with ``workflow_params`` as JSON text; no files are attached.

    Args:
        wes_url: Base URL of the WES API, e.g.,
            ``https://wes.example.org/ga4gh/wes/v1``.
        request: The run request.

    Returns:
        The run id, and the state of the run, or ``None`` if it can't be
        read.

    Raises:
        OSError: If the WES can't be reached or rejects the request (also
            ``urllib.error.HTTPError``).
        ValueError: If the answer isn't JSON or has no ``run_id``.
    """
    base = wes_url.rstrip("/")
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in request.items():
        text = value if isinstance(value, str) else json.dumps(value)
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="{name}"\r\n\r\n{text}\r\n'
        )
    body = "".join(parts) + f"--{boundary}--\r\n"
    answer = _fetch_json(
        urllib.request.Request(
            f"{base}/runs",
            data=body.encode("utf-8"),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
    )
    run_id = answer.get("run_id") if isinstance(answer, dict) else None
    if not isinstance(run_id, str):
        raise ValueError("The answer has no run_id.")
    try:
        status = _fetch_json(
            urllib.request.Request(
                f"{base}/runs/{urllib.parse.quote(run_id, safe='')}/status"
            )
        )
    except (OSError, ValueError):
        return run_id, None
    state = status.get("state") if isinstance(status, dict) else None
    return run_id, state if isinstance(state, str) else None


def _fetch_json(request: urllib.request.Request) -> Any:
    """Send a request and parse the JSON answer.

    Args:
        request: The request.

    Returns:
        The parsed answer.

    Raises:
        OSError: If the request fails (also ``urllib.error.HTTPError``).
        ValueError: If the answer isn't JSON.
    """
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def validation_errors(schema: dict[str, Any], values: Any) -> list[dict[str, str]]:
    """Validate input values against ``inputs`` of an IO schema.

    Every failure gets the ``x-ga4gh-error-message`` that covers it, given
    once per location, or else the validator's message.

    Args:
        schema: IO schema.
        values: Input values.

    Returns:
        The errors, each with ``pointer`` and ``message``, in the order of
        their locations.

    Raises:
        referencing.exceptions.Unresolvable: If a reference of the schema
            can't be resolved from the schema itself.
    """
    uri = schema["$id"] if isinstance(schema.get("$id"), str) else DOCUMENT_URI
    registry: Registry = Registry().with_resource(
        uri, DRAFT202012.create_resource(schema)
    )
    validator = ValuesValidator(
        {"$ref": f"{uri}#/properties/inputs"},
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    inputs = _descend(registry.resolver(base_uri=uri), schema["properties"]["inputs"])
    errors: list[dict[str, str]] = []
    for error in sorted(validator.iter_errors(values), key=lambda e: list(e.path)):
        path = list(error.absolute_path)
        message = error_message(inputs, path) or error.message
        location = TranslationError(message, path).pointer
        entry = {"pointer": location, "message": message}
        if entry not in errors:
            errors.append(entry)
    return errors


def error_message(inputs: Scope, path: Sequence[str | int]) -> str | None:
    """Find the ``x-ga4gh-error-message`` for a location in the values.

    The message is that of the outermost schema that applies to the value at
    the location: the schemas are searched breadth-first, from the schemas
    of the location through ``$ref`` and the in-place applicators. This
    proof of concept follows every branch of the applicators, not only
    those on the evaluation path of the failure.

    Args:
        inputs: The schema of ``inputs``, with its resolver.
        path: Location of the value: keys of objects, indexes of arrays.

    Returns:
        The message, or ``None`` if no schema at the location has one.
    """
    scopes = _in_place([inputs])
    for key in path:
        scopes = _in_place(_children(scopes, key))
    for subschema, _ in scopes:
        message = subschema.get("x-ga4gh-error-message")
        if isinstance(message, str):
            return message
    return None


def _descend(resolver: Any, subschema: Any) -> Scope:
    """Enter a subschema, which may set its own base URI with ``$id``.

    Args:
        resolver: Resolver of the enclosing schema.
        subschema: The subschema.

    Returns:
        The subschema with its resolver.
    """
    if isinstance(subschema, dict) and isinstance(subschema.get("$id"), str):
        resource = DRAFT202012.create_resource(subschema)
        return subschema, resolver.in_subresource(resource)
    return subschema, resolver


def _in_place(scopes: Iterable[Scope]) -> list[Scope]:
    """Collect the schemas that apply to the value at one location.

    Args:
        scopes: The schemas of the location.

    Returns:
        These schemas and those that they apply to the same value, outermost
        first.
    """
    found: list[Scope] = []
    seen: set[int] = set()
    queue = deque(scopes)
    while queue:
        subschema, resolver = queue.popleft()
        if not isinstance(subschema, dict) or id(subschema) in seen:
            continue
        seen.add(id(subschema))
        found.append((subschema, resolver))
        if isinstance(subschema.get("$ref"), str):
            resolved = resolver.lookup(subschema["$ref"])
            queue.append((resolved.contents, resolved.resolver))
        for keyword in IN_PLACE:
            if keyword in subschema:
                queue.append(_descend(resolver, subschema[keyword]))
        for keyword in IN_PLACE_LISTS:
            for item in subschema.get(keyword) or ():
                queue.append(_descend(resolver, item))
        for item in (subschema.get("dependentSchemas") or {}).values():
            queue.append(_descend(resolver, item))
    return found


def _children(scopes: Iterable[Scope], key: str | int) -> list[Scope]:
    """Collect the schemas of a member of an object or an item of an array.

    Args:
        scopes: The schemas of the object or array.
        key: Key of the member, or index of the item.

    Returns:
        The schemas of the member or item.
    """
    children: list[Scope] = []
    for subschema, resolver in scopes:
        if isinstance(key, int):
            prefix = subschema.get("prefixItems") or []
            if key < len(prefix):
                children.append(_descend(resolver, prefix[key]))
            elif "items" in subschema:
                children.append(_descend(resolver, subschema["items"]))
            continue
        properties = subschema.get("properties") or {}
        patterns = [
            item
            for pattern, item in (subschema.get("patternProperties") or {}).items()
            if search(pattern, key)
        ]
        if key in properties:
            children.append(_descend(resolver, properties[key]))
        children.extend(_descend(resolver, item) for item in patterns)
        if (
            key not in properties
            and not patterns
            and "additionalProperties" in subschema
        ):
            children.append(_descend(resolver, subschema["additionalProperties"]))
    return children


class FormHost(ThreadingHTTPServer):
    """HTTP server of the form, for a default IO schema or those of a TRS.

    Attributes:
        schema: The default IO schema, if any.
        allowed_schemes: URI schemes of the deployment's allow-list.
        workflow_url: The ``workflow_url`` of run requests for the default
            schema.
        wes_url: Base URL of the WES API to submit runs to, if any.
        trs_url: Base URL of the TRS API to pick workflows from, if any;
            their schemas are loaded again for each request, so changes in
            the TRS show at once.
    """

    def __init__(
        self,
        address: tuple[str, int],
        schema: dict[str, Any] | None,
        allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
        workflow_url: str | None = None,
        wes_url: str | None = None,
        trs_url: str | None = None,
    ) -> None:
        """Bind the server.

        Args:
            address: Host and port; port 0 picks a free one.
            schema: The default IO schema, valid against the profile; with
                ``trs_url``, it may be ``None``.
            allowed_schemes: URI schemes of the deployment's allow-list.
            workflow_url: The ``workflow_url`` of run requests for the
                default schema.
            wes_url: Base URL of the WES API to submit runs to; without it,
                nothing is sent.
            trs_url: Base URL of a TRS API whose workflows users can pick.
        """
        super().__init__(address, FormHandler)
        self.schema = schema
        self.allowed_schemes = tuple(allowed_schemes)
        self.workflow_url = workflow_url
        self.wes_url = wes_url
        self.trs_url = trs_url


class FormHandler(BaseHTTPRequestHandler):
    """Requests to the host: the form, the schema, the values and runs."""

    server: FormHost

    def do_GET(self) -> None:  # noqa: N802 - name defined by http.server
        """Serve a file of the form, the schema or the configuration.

        ``/api/schema`` is the schema: of the workflow picked in the TRS
        with the query ``tool``, ``version`` and ``type``, or else the
        default one. ``/api/config`` says whether runs can be submitted to a
        WES (``{"wes": true}``) and, with a TRS, lists its ``workflows`` (see
        :func:`list_workflows`), or gives ``trs_error``.
        """
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/api/") and not self._same_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {"msg": "Foreign host or origin"})
        elif path == "/api/schema":
            selected = self._selected()
            if selected is not None:
                self._send_json(HTTPStatus.OK, selected[0])
        elif path == "/api/config":
            self._send_json(HTTPStatus.OK, self._config())
        elif path in STATIC:
            name, media_type = STATIC[path]
            self._send(HTTPStatus.OK, media_type, (HERE / name).read_bytes())
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"msg": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - name defined by http.server
        """Turn the values of the form into a run request, or submit it.

        ``/api/params`` responds with ``{"run_request": …}``; ``/api/runs``
        also submits the request to the WES and responds with
        ``{"run_request": …, "run_id": …, "state": …}``. Invalid values get
        status 400 and ``{"errors": [{"pointer": …, "message": …}]}``;
        ``/api/runs`` without a WES gets 404, and a failure of the WES 502,
        each with a request-level error. Only JSON bodies (``Content-Type:
        application/json``) are taken, from a page served by the host under a
        loopback name or its own address (``Host``, ``Origin``): other web
        pages that the user opens can't make the host submit runs (no CSRF,
        no DNS rebinding).
        """
        path = urllib.parse.urlsplit(self.path).path
        if path not in ("/api/params", "/api/runs"):
            self._send_json(HTTPStatus.NOT_FOUND, {"msg": "Not found"})
            return
        header = self.headers.get("Content-Length") or "0"
        if not (header.isascii() and header.isdigit()):
            self._send_json(HTTPStatus.BAD_REQUEST, {"msg": "Bad Content-Length"})
            self.close_connection = True
            return
        length = int(header)
        if length > MAX_BODY:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"msg": "Too large"})
            self.close_connection = True
            return
        media_type = (self.headers.get("Content-Type") or "").split(";")[0]
        if media_type.strip().lower() != "application/json":
            self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"msg": "Not JSON"})
            self.close_connection = True
            return
        if not self._same_origin():
            self._send_json(HTTPStatus.FORBIDDEN, {"msg": "Foreign host or origin"})
            self.close_connection = True
            return
        try:
            values = json.loads(self.rfile.read(length))
        except (ValueError, RecursionError):
            errors = [{"pointer": "", "message": "The values aren't JSON."}]
            self._send_json(HTTPStatus.BAD_REQUEST, {"errors": errors})
            return
        selected = self._selected()
        if selected is None:
            return
        try:
            request, errors = check_values(
                selected[0], values, self.server.allowed_schemes, selected[1]
            )
        except RecursionError:
            errors = [{"pointer": "", "message": "The values are nested too deeply."}]
        if errors:
            self._send_json(HTTPStatus.BAD_REQUEST, {"errors": errors})
        elif path == "/api/params":
            self._send_json(HTTPStatus.OK, {"run_request": request})
        else:
            self._submit(request)

    def _config(self) -> dict[str, Any]:
        """Build the configuration for the page.

        Returns:
            Whether a WES is configured and, with a TRS, its workflows.
        """
        config: dict[str, Any] = {"wes": self.server.wes_url is not None}
        trs_url = self.server.trs_url
        if trs_url is not None:
            try:
                config["workflows"] = list_workflows(trs_url)
            except (OSError, ValueError) as exc:
                config["workflows"] = []
                config["trs_error"] = f"Can't list the workflows of {trs_url}: {exc}"
        return config

    def _selected(self) -> tuple[dict[str, Any], str | None] | None:
        """Find the schema of a request, or send an error.

        Returns:
            The schema and the ``workflow_url`` of the workflow picked in
            the TRS (query ``tool``, ``version`` and ``type``), or else of
            the default schema; ``None`` if there is none, after sending
            404, or if the workflow can't be loaded, after sending 502.
        """
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        keys = ("tool", "version", "type")
        trs_url = self.server.trs_url
        if trs_url is not None and all(key in query for key in keys):
            key = (query["tool"][0], query["version"][0], query["type"][0])
            try:
                return load_trs_schema(trs_url, *key)
            except (OSError, ValueError, jsonschema.exceptions.ValidationError) as exc:
                message = f"Can't load the workflow from {trs_url}: {exc}"
                error = {"pointer": "", "message": message}
                self._send_json(HTTPStatus.BAD_GATEWAY, {"errors": [error]})
                return None
        if self.server.schema is None:
            error = {"pointer": "", "message": PICK_A_WORKFLOW}
            self._send_json(HTTPStatus.NOT_FOUND, {"errors": [error]})
            return None
        return self.server.schema, self.server.workflow_url

    def _same_origin(self) -> bool:
        """Check that a request comes from a page of the host itself.

        Returns:
            Whether the ``Host`` header names the host by a loopback name or
            its own address, and the ``Origin`` header, if any, is the same.
        """
        host = self.headers.get("Host") or ""
        name = urllib.parse.urlsplit(f"//{host}").hostname or ""
        bound = str(self.server.server_address[0])
        if name not in LOOPBACK_NAMES and name != bound:
            return False
        origin = self.headers.get("Origin")
        return origin is None or urllib.parse.urlsplit(origin).netloc == host

    def _submit(self, request: Any) -> None:
        """Submit a run request to the WES, if there is one, and respond.

        Args:
            request: The run request.
        """
        wes_url = self.server.wes_url
        if wes_url is None:
            error = {"pointer": "", "message": "No WES is configured."}
            self._send_json(HTTPStatus.NOT_FOUND, {"errors": [error]})
            return
        try:
            run_id, state = submit_run(wes_url, request)
        except (OSError, ValueError) as exc:
            error = {"pointer": "", "message": f"The WES at {wes_url} failed: {exc}"}
            self._send_json(HTTPStatus.BAD_GATEWAY, {"errors": [error]})
            return
        body = {"run_request": request, "run_id": run_id, "state": state}
        self._send_json(HTTPStatus.OK, body)

    def _send_json(self, status: HTTPStatus, body: Any) -> None:
        """Send a JSON response.

        Args:
            status: HTTP status.
            body: The JSON body.
        """
        data = json.dumps(body, indent=2).encode("utf-8")
        self._send(status, "application/json", data)

    def _send(self, status: HTTPStatus, media_type: str, data: bytes) -> None:
        """Send a response, with headers that keep the page to its own files.

        Args:
            status: HTTP status.
            media_type: Value of ``Content-Type``.
            data: The body.
        """
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Security-Policy", "default-src 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)


def _parser() -> argparse.ArgumentParser:
    """Build the parser of the command-line arguments.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        description="Serve a form for an IO schema (a proof of concept)."
    )
    parser.add_argument(
        "--schema",
        help="path or http(s) URL of the default IO schema, e.g., its TRS URL "
        "(default: none with --trs-url, where users pick workflows in the TRS; "
        "else the schema of the end-to-end demo)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="address to bind (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="port to bind (default: 8000)"
    )
    parser.add_argument(
        "--allow-scheme",
        action="append",
        dest="allowed_schemes",
        metavar="SCHEME",
        help="URI scheme that file references may use (repeatable; "
        f"default: {', '.join(DEFAULT_ALLOWED_SCHEMES)})",
    )
    parser.add_argument(
        "--trs-url",
        type=_http_url,
        help="base URL of a TRS API, e.g., http://127.0.0.1:8080/ga4gh/trs/v2: "
        "users pick its workflows, and run requests name the workflow by its "
        "TRS URL (default: no TRS; the workflow_url of the default schema is "
        "the path of its primary descriptor)",
    )
    parser.add_argument(
        "--wes-url",
        type=_optional_http_url,
        help="base URL of a WES API to submit runs to, e.g., "
        "http://127.0.0.1:8081/ga4gh/wes/v1 (default, or if empty: none; run "
        "requests are shown, not sent)",
    )
    return parser


def _http_url(value: str) -> str:
    """Check that an argument is an ``http(s)`` URL.

    Args:
        value: The argument.

    Returns:
        The URL.

    Raises:
        argparse.ArgumentTypeError: If it isn't an ``http(s)`` URL.
    """
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise argparse.ArgumentTypeError(f"not an http(s) URL: {value}")
    return value


def _optional_http_url(value: str) -> str | None:
    """Check that an argument is empty or an ``http(s)`` URL.

    Args:
        value: The argument.

    Returns:
        The URL, or ``None`` if the argument is empty.
    """
    return _http_url(value) if value else None


def main(argv: Sequence[str] | None = None) -> int:
    """Start the host and serve until interrupted.

    Args:
        argv: Command-line arguments; by default, those of the process.

    Returns:
        Exit status: 0 when interrupted, 1 if the schema can't be used.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    schemes = args.allowed_schemes or list(DEFAULT_ALLOWED_SCHEMES)
    forbidden = sorted({scheme.lower() for scheme in schemes} & FORBIDDEN_SCHEMES)
    if forbidden:
        parser.error(f"these schemes can't be allowed: {', '.join(forbidden)}")
    schema = url = None
    if args.schema is not None or args.trs_url is None:
        source = args.schema or str(DEMO_SCHEMA)
        try:
            schema = load_schema(source)
            url = workflow_url(schema, args.trs_url)
        except (OSError, ValueError, jsonschema.exceptions.ValidationError) as exc:
            print(f"Can't use the schema {source}: {exc}", file=sys.stderr)
            return 1
        if args.wes_url and not (url or "").startswith(("http://", "https://")):
            parser.error(
                "--wes-url needs a workflow URL that a WES can fetch: give "
                "--trs-url and a schema that names its TRS tool version"
            )
    server = FormHost(
        (args.host, args.port), schema, schemes, url, args.wes_url, args.trs_url
    )
    host, port = server.server_address[:2]
    print(f"Serving the form on http://{host}:{port}/ (Ctrl+C stops)")
    if args.trs_url:
        print(f"  Workflows are picked from {args.trs_url}")
    if schema is not None:
        print(f"  Default schema: {schema.get('title', '(no title)')}")
        print(f"  workflow URL: {url}")
    if args.wes_url:
        print(f"  Run requests are sent to {args.wes_url} on request.")
    else:
        print("  No WES configured: run requests are shown, not sent.")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - run as a script
    sys.exit(main())
