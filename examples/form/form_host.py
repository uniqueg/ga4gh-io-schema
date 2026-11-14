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
``docs/specification/keywords.md``), and turns valid values into
``workflow_params`` with :func:`ga4gh_io_schema.wes.to_workflow_params`. It
submits nothing.

Run it with ``python examples/form/form_host.py`` and open
http://127.0.0.1:8000/.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
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

from ga4gh_io_schema.validator import validate_schema
from ga4gh_io_schema.wes import (
    DEFAULT_ALLOWED_SCHEMES,
    FORBIDDEN_SCHEMES,
    TranslationError,
    to_workflow_params,
)

HERE = Path(__file__).resolve().parent
#: The schema of the end-to-end demo, the default.
DEMO_SCHEMA = HERE.parent / "demo" / "ga4gh-io.schema.json"
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


def check_values(
    schema: dict[str, Any],
    values: Any,
    allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Validate input values and turn them into ``workflow_params``.

    Args:
        schema: IO schema, valid against the profile.
        values: Input values from the form.
        allowed_schemes: URI schemes of the deployment's allow-list.

    Returns:
        The ``workflow_params`` and no errors; or ``None`` and the errors,
        each with the location of the value (``pointer``, a JSON Pointer
        into the values) and its ``message``.
    """
    try:
        errors = validation_errors(schema, values)
    except Unresolvable as exc:
        message = f"The schema references '{exc.ref}', which can't be resolved."
        return None, [{"pointer": "", "message": message}]
    if errors:
        return None, errors
    try:
        params = to_workflow_params(schema, values, allowed_schemes=allowed_schemes)
    except TranslationError as exc:
        return None, [{"pointer": exc.pointer, "message": exc.message}]
    return params, []


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
    validator = Draft202012Validator(
        {"$ref": f"{uri}#/properties/inputs"},
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    inputs = _descend(registry.resolver(base_uri=uri), schema["properties"]["inputs"])
    errors: list[dict[str, str]] = []
    for error in sorted(validator.iter_errors(values), key=lambda e: list(e.path)):
        path = list(error.absolute_path)
        message = error_message(inputs, path) or error.message
        entry = {"pointer": pointer(path), "message": message}
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


def pointer(path: Iterable[str | int]) -> str:
    """Turn a location into a JSON Pointer (RFC 6901).

    Args:
        path: Keys of objects and indexes of arrays.

    Returns:
        The JSON Pointer; the empty string for the values as a whole.
    """
    return "".join(
        "/" + str(part).replace("~", "~0").replace("/", "~1") for part in path
    )


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
            if re.search(pattern, key)
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
    """HTTP server of the form, for one IO schema.

    Attributes:
        schema: The IO schema.
        allowed_schemes: URI schemes of the deployment's allow-list.
    """

    def __init__(
        self,
        address: tuple[str, int],
        schema: dict[str, Any],
        allowed_schemes: Iterable[str] = DEFAULT_ALLOWED_SCHEMES,
    ) -> None:
        """Bind the server.

        Args:
            address: Host and port; port 0 picks a free one.
            schema: The IO schema, valid against the profile.
            allowed_schemes: URI schemes of the deployment's allow-list.
        """
        super().__init__(address, FormHandler)
        self.schema = schema
        self.allowed_schemes = tuple(allowed_schemes)


class FormHandler(BaseHTTPRequestHandler):
    """Requests to the host: the form, the schema and the values."""

    server: FormHost

    def do_GET(self) -> None:  # noqa: N802 - name defined by http.server
        """Serve a file of the form, or the schema (``/api/schema``)."""
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/schema":
            self._send_json(HTTPStatus.OK, self.server.schema)
        elif path in STATIC:
            name, media_type = STATIC[path]
            self._send(HTTPStatus.OK, media_type, (HERE / name).read_bytes())
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"msg": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - name defined by http.server
        """Turn the values of the form into ``workflow_params`` (``/api/params``).

        Responds with ``{"workflow_params": …}``, or with status 400 and
        ``{"errors": [{"pointer": …, "message": …}]}``.
        """
        if urllib.parse.urlsplit(self.path).path != "/api/params":
            self._send_json(HTTPStatus.NOT_FOUND, {"msg": "Not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"msg": "Too large"})
            return
        try:
            values = json.loads(self.rfile.read(length))
        except ValueError:
            errors = [{"pointer": "", "message": "The values aren't JSON."}]
            self._send_json(HTTPStatus.BAD_REQUEST, {"errors": errors})
            return
        params, errors = check_values(
            self.server.schema, values, self.server.allowed_schemes
        )
        if errors:
            self._send_json(HTTPStatus.BAD_REQUEST, {"errors": errors})
        else:
            self._send_json(HTTPStatus.OK, {"workflow_params": params})

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
        default=str(DEMO_SCHEMA),
        help="path or http(s) URL of the IO schema, e.g., its TRS URL "
        "(default: the schema of the end-to-end demo)",
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
    return parser


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
    try:
        schema = load_schema(args.schema)
    except (OSError, ValueError, jsonschema.exceptions.ValidationError) as exc:
        print(f"Can't use the schema {args.schema}: {exc}", file=sys.stderr)
        return 1
    server = FormHost((args.host, args.port), schema, schemes)
    host, port = server.server_address[:2]
    print(f"Serving the form on http://{host}:{port}/ (Ctrl+C stops)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - run as a script
    sys.exit(main())
