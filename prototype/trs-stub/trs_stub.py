# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""TRS stub of the prototype: serves workflows and their IO schemas.

A proof of concept, not a TRS implementation (see ``prototype/README.md``).
It answers only the read-only TRS v2 requests that a client needs to find
a workflow and its IO schema: the tools, their versions, the primary
descriptor, the list of files and a file by its relative path, each
descriptor as ``FileWrapper`` or plain text (``PLAIN_<type>``). Everything
comes from files in the repository: each workflow is a directory with an
IO schema, ``ga4gh-io.schema.json``, and the primary descriptor that its
``x-ga4gh-workflow`` block names. The block also gives the ids of the tool
and the version, the descriptor type and its version. No database, no
writes, no authentication.

Run it with ``python prototype/trs-stub/trs_stub.py`` and open
http://127.0.0.1:8080/ga4gh/trs/v2/tools.
"""

import argparse
import hashlib
import json
import sys
import urllib.parse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

#: Base path of the TRS API.
API = "/ga4gh/trs/v2"
#: Name of the IO schema file, next to the primary descriptor (TRS convention
#: of the profile).
SCHEMA_NAME = "ga4gh-io.schema.json"
#: The workflow of the end-to-end demo, the default.
DEMO_DIR = Path(__file__).resolve().parents[2] / "examples" / "demo"
#: The tool class of every tool.
TOOLCLASS = {
    "id": "workflow",
    "name": "Workflow",
    "description": "A workflow (served by the TRS stub of the prototype)",
}


@dataclass(frozen=True)
class Workflow:
    """A tool version with its files, for one descriptor type.

    Attributes:
        tool_id: Id of the tool.
        version_id: Id of the tool version.
        name: Name of the tool: the title of the schema, or the tool id.
        description: Description of the tool, from the schema.
        descriptor_type: TRS descriptor type, e.g., ``WDL``.
        descriptor_type_version: Version of the workflow language.
        primary: Relative path of the primary descriptor, a file name.
        files: The files by relative path: file type and content.
    """

    tool_id: str
    version_id: str
    name: str
    description: str
    descriptor_type: str
    descriptor_type_version: str
    primary: str
    files: dict[str, tuple[str, str]]


def load_workflow(directory: Path) -> Workflow:
    """Read a workflow from a directory.

    The directory holds the IO schema (``ga4gh-io.schema.json``) and the
    primary descriptor, at the ``primary_descriptor_path`` of the schema's
    ``x-ga4gh-workflow`` block, which must be a file name: the stub serves
    both files at the top level of the tool version (the publishing
    convention of the profile puts the schema in the directory of the
    primary descriptor). The files are served as they are, byte for byte,
    so that their checksums match.

    Args:
        directory: The directory.

    Returns:
        The workflow.

    Raises:
        OSError: If a file can't be read.
        ValueError: If a file isn't UTF-8, the schema isn't JSON, or its
            workflow block lacks the TRS ids, the descriptor type and its
            version, or the path of the primary descriptor, or that path
            isn't a file name.
    """
    text = (directory / SCHEMA_NAME).read_bytes().decode("utf-8")
    schema = json.loads(text)
    block = schema.get("x-ga4gh-workflow") if isinstance(schema, dict) else None
    if not isinstance(block, dict):
        raise ValueError(f"The schema has no x-ga4gh-workflow block: {directory}")
    keys = (
        "trs_tool_id",
        "trs_version_id",
        "descriptor_type",
        "descriptor_type_version",
        "primary_descriptor_path",
    )
    for key in keys:
        if not isinstance(block.get(key), str):
            raise ValueError(f"x-ga4gh-workflow has no {key}: {directory}")
    primary = block["primary_descriptor_path"]
    if "/" in primary or primary in ("", ".", "..", SCHEMA_NAME):
        raise ValueError(
            f"primary_descriptor_path must be a file name, not {primary!r}: {directory}"
        )
    descriptor = (directory / primary).read_bytes().decode("utf-8")
    return Workflow(
        tool_id=block["trs_tool_id"],
        version_id=block["trs_version_id"],
        name=schema.get("title") or block["trs_tool_id"],
        description=schema.get("description") or "",
        descriptor_type=block["descriptor_type"],
        descriptor_type_version=block["descriptor_type_version"],
        primary=primary,
        files={
            primary: ("PRIMARY_DESCRIPTOR", descriptor),
            SCHEMA_NAME: ("OTHER", text),
        },
    )


class TrsStub(ThreadingHTTPServer):
    """HTTP server of the TRS stub.

    Attributes:
        workflows: The tool versions by tool id and version id.
    """

    def __init__(self, address: tuple[str, int], workflows: Iterable[Workflow]) -> None:
        """Bind the server.

        Args:
            address: Host and port; port 0 picks a free one.
            workflows: The tool versions to serve.

        Raises:
            ValueError: If two workflows have the same tool and version id.
            OSError: If the address can't be bound.
        """
        self.workflows: dict[str, dict[str, Workflow]] = {}
        for workflow in workflows:
            versions = self.workflows.setdefault(workflow.tool_id, {})
            if workflow.version_id in versions:
                raise ValueError(
                    f"Two workflows are version {workflow.version_id} of "
                    f"{workflow.tool_id}."
                )
            versions[workflow.version_id] = workflow
        super().__init__(address, TrsHandler)


class TrsHandler(BaseHTTPRequestHandler):
    """Requests to the stub: read-only TRS v2 endpoints."""

    server: TrsStub

    def do_GET(self) -> None:  # noqa: N802 - name defined by http.server
        """Serve a tool, a tool version, a file list or a descriptor."""
        path = urllib.parse.urlsplit(self.path).path
        if not path.startswith(f"{API}/"):
            self._not_found()
            return
        parts = [urllib.parse.unquote(part) for part in path[len(API) + 1 :].split("/")]
        base = f"http://{self.headers.get('Host', 'localhost')}{API}"
        match parts:
            case ["tools"]:
                tools = [
                    self._tool(base, versions)
                    for versions in self.server.workflows.values()
                ]
                self._send_json(HTTPStatus.OK, tools)
            case ["tools", tool_id] if tool_id in self.server.workflows:
                tool = self._tool(base, self.server.workflows[tool_id])
                self._send_json(HTTPStatus.OK, tool)
            case ["tools", tool_id, "versions"] if tool_id in self.server.workflows:
                versions = self.server.workflows[tool_id].values()
                self._send_json(
                    HTTPStatus.OK, [self._version(base, w) for w in versions]
                )
            case ["tools", tool_id, "versions", version_id, *rest]:
                workflow = self.server.workflows.get(tool_id, {}).get(version_id)
                if workflow is None:
                    self._not_found()
                elif not rest:
                    self._send_json(HTTPStatus.OK, self._version(base, workflow))
                else:
                    self._files(base, workflow, rest)
            case _:
                self._not_found()

    def _files(self, base: str, workflow: Workflow, parts: list[str]) -> None:
        """Serve the file list or a descriptor of a tool version.

        Args:
            base: Base URL of the TRS API.
            workflow: The tool version.
            parts: The path after ``.../versions/{version_id}/``.
        """
        kind, *rest = parts
        plain = kind.startswith("PLAIN_")
        if kind.removeprefix("PLAIN_") != workflow.descriptor_type:
            self._not_found()
        elif rest == ["files"] and not plain:
            files = [
                {"path": p, "file_type": t} for p, (t, _) in workflow.files.items()
            ]
            self._send_json(HTTPStatus.OK, files)
        elif rest[:1] == ["descriptor"]:
            relative = "/".join(rest[1:]) or workflow.primary
            if relative not in workflow.files:
                self._not_found()
                return
            content = workflow.files[relative][1]
            if plain:
                data = content.encode("utf-8")
                self._send(HTTPStatus.OK, "text/plain; charset=utf-8", data)
                return
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            # The primary descriptor too, by its path: relative imports of
            # the plain URL then resolve under .../descriptor/
            url = (
                f"{self._version(base, workflow)['url']}/PLAIN_{kind}/descriptor"
                f"/{urllib.parse.quote(relative, safe='')}"
            )
            wrapper = {
                "content": content,
                "checksum": [{"type": "sha-256", "checksum": digest}],
                "url": url,
            }
            self._send_json(HTTPStatus.OK, wrapper)
        else:
            self._not_found()

    @staticmethod
    def _tool(base: str, versions: dict[str, Workflow]) -> dict[str, Any]:
        """Build a TRS ``Tool``.

        Args:
            base: Base URL of the TRS API.
            versions: The tool versions of the tool, by id.

        Returns:
            The tool, with the name and description of its first version.
        """
        first = next(iter(versions.values()))
        return {
            "id": first.tool_id,
            "url": f"{base}/tools/{urllib.parse.quote(first.tool_id, safe='')}",
            "name": first.name,
            "description": first.description,
            "organization": "I/O Schema prototype",
            "toolclass": TOOLCLASS,
            "versions": [TrsHandler._version(base, w) for w in versions.values()],
        }

    @staticmethod
    def _version(base: str, workflow: Workflow) -> dict[str, Any]:
        """Build a TRS ``ToolVersion``.

        Args:
            base: Base URL of the TRS API.
            workflow: The tool version.

        Returns:
            The tool version.
        """
        tool = urllib.parse.quote(workflow.tool_id, safe="")
        version = urllib.parse.quote(workflow.version_id, safe="")
        return {
            "id": workflow.version_id,
            "url": f"{base}/tools/{tool}/versions/{version}",
            "name": workflow.version_id,
            "descriptor_type": [workflow.descriptor_type],
            "descriptor_type_version": {
                workflow.descriptor_type: [workflow.descriptor_type_version]
            },
        }

    def _not_found(self) -> None:
        """Send a TRS ``Error`` with status 404."""
        self._send_json(HTTPStatus.NOT_FOUND, {"code": 404, "message": "Not found"})

    def _send_json(self, status: HTTPStatus, body: Any) -> None:
        """Send a JSON response.

        Args:
            status: HTTP status.
            body: The JSON body.
        """
        data = json.dumps(body, indent=2).encode("utf-8")
        self._send(status, "application/json", data)

    def _send(self, status: HTTPStatus, media_type: str, data: bytes) -> None:
        """Send a response.

        Args:
            status: HTTP status.
            media_type: Value of ``Content-Type``.
            data: The body.
        """
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)


def _parser() -> argparse.ArgumentParser:
    """Build the parser of the command-line arguments.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        description="Serve workflows and their IO schemas over TRS v2: a stub "
        "for the prototype, a proof of concept, not a TRS implementation."
    )
    parser.add_argument(
        "--workflow",
        action="append",
        dest="workflows",
        metavar="DIR",
        help="directory with ga4gh-io.schema.json and the primary descriptor "
        "(repeatable; default: the end-to-end demo)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="address to bind (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="port to bind (default: 8080)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Start the stub and serve until interrupted.

    Args:
        argv: Command-line arguments; by default, those of the process.

    Returns:
        Exit status: 0 when interrupted, 1 if a workflow can't be read or
        the stub can't start.
    """
    args = _parser().parse_args(argv)
    workflows = []
    for directory in args.workflows or [str(DEMO_DIR)]:
        try:
            workflows.append(load_workflow(Path(directory)))
        except (OSError, ValueError) as exc:
            print(f"Can't serve the workflow {directory}: {exc}", file=sys.stderr)
            return 1
    try:
        server = TrsStub((args.host, args.port), workflows)
    except (OSError, ValueError) as exc:
        print(f"Can't start the stub: {exc}", file=sys.stderr)
        return 1
    host, port = server.server_address[:2]
    print("TRS stub of the prototype (a proof of concept, not a TRS)")
    print(f"Serving TRS on http://{host}:{port}{API}/tools (Ctrl+C stops)")
    for workflow in workflows:
        print(f"  {API}/tools/{workflow.tool_id}/versions/{workflow.version_id}")
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
