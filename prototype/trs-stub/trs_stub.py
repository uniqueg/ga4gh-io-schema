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
writes, no authentication. With ``--reload``, the files are read again on
every request, so that edits show without a restart.

Run it with ``python prototype/trs-stub/trs_stub.py`` and open
http://127.0.0.1:8080/ga4gh/trs/v2/tools.
"""

import argparse
import functools
import hashlib
import json
import sys
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
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


def find_workflows(root: Path) -> list[Path]:
    """List the workflows in a directory.

    Args:
        root: The directory.

    Returns:
        Its subdirectories that hold an IO schema, sorted by name.
    """
    return sorted(path.parent for path in root.glob(f"*/{SCHEMA_NAME}"))


def load_workflows(
    directories: Iterable[Path], roots: Iterable[Path] = (), *, strict: bool = True
) -> list[Workflow]:
    """Read workflows from their directories.

    Args:
        directories: Directories of workflows (see :func:`load_workflow`).
        roots: Directories whose subdirectories with an IO schema are
            workflows (see :func:`find_workflows`), after ``directories``.
        strict: Whether a workflow that can't be read is an error; if not,
            it is reported on standard error and left out, and so is a
            workflow with the tool and version id of an earlier one.

    Returns:
        The workflows.

    Raises:
        OSError: If ``strict`` and a file can't be read.
        ValueError: If ``strict`` and a workflow is invalid (see
            :func:`load_workflow`).
    """
    paths = [*directories, *(p for root in roots for p in find_workflows(root))]
    workflows: list[Workflow] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        try:
            workflow = load_workflow(path)
            key = (workflow.tool_id, workflow.version_id)
            if key in seen and not strict:
                raise ValueError(_duplicate(workflow))
        except (OSError, ValueError) as exc:
            if strict:
                raise
            print(f"Can't serve the workflow {path}: {exc}", file=sys.stderr)
            continue
        seen.add(key)
        workflows.append(workflow)
    return workflows


def _duplicate(workflow: Workflow) -> str:
    """Describe a workflow whose tool version is served already.

    Args:
        workflow: The workflow.

    Returns:
        The message.
    """
    return f"Two workflows are version {workflow.version_id} of {workflow.tool_id}."


def _index(workflows: Iterable[Workflow]) -> dict[str, dict[str, Workflow]]:
    """Index workflows by tool id and version id.

    Args:
        workflows: The workflows.

    Returns:
        The workflows by tool id and version id.

    Raises:
        ValueError: If two workflows have the same tool and version id.
    """
    index: dict[str, dict[str, Workflow]] = {}
    for workflow in workflows:
        versions = index.setdefault(workflow.tool_id, {})
        if workflow.version_id in versions:
            raise ValueError(_duplicate(workflow))
        versions[workflow.version_id] = workflow
    return index


class TrsStub(ThreadingHTTPServer):
    """HTTP server of the TRS stub.

    Attributes:
        workflows: The tool versions by tool id and version id, as read at
            the start.
        reload: Reads the workflows again, for each request; ``None`` serves
            ``workflows``.
    """

    def __init__(
        self,
        address: tuple[str, int],
        workflows: Iterable[Workflow],
        reload: Callable[[], Iterable[Workflow]] | None = None,
    ) -> None:
        """Bind the server.

        Args:
            address: Host and port; port 0 picks a free one.
            workflows: The tool versions to serve.
            reload: Reads the tool versions to serve, on each request; it
                must leave out duplicates (see :func:`load_workflows`).

        Raises:
            ValueError: If two workflows have the same tool and version id.
            OSError: If the address can't be bound.
        """
        self.workflows = _index(workflows)
        self.reload = reload
        super().__init__(address, TrsHandler)

    def current(self) -> dict[str, dict[str, Workflow]]:
        """Get the workflows to serve now.

        Returns:
            The tool versions by tool id and version id: read again with
            ``reload``, if given.
        """
        if self.reload is None:
            return self.workflows
        return _index(self.reload())


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
        workflows = self.server.current()
        match parts:
            case ["tools"]:
                tools = [self._tool(base, versions) for versions in workflows.values()]
                self._send_json(HTTPStatus.OK, tools)
            case ["tools", tool_id] if tool_id in workflows:
                self._send_json(HTTPStatus.OK, self._tool(base, workflows[tool_id]))
            case ["tools", tool_id, "versions"] if tool_id in workflows:
                versions = workflows[tool_id].values()
                self._send_json(
                    HTTPStatus.OK, [self._version(base, w) for w in versions]
                )
            case ["tools", tool_id, "versions", version_id, *rest]:
                workflow = workflows.get(tool_id, {}).get(version_id)
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
            path = "/".join(urllib.parse.quote(s, safe="") for s in relative.split("/"))
            url = (
                f"{self._version(base, workflow)['url']}/PLAIN_{kind}/descriptor/{path}"
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
        "(repeatable; default, without --workflows-dir: the end-to-end demo)",
    )
    parser.add_argument(
        "--workflows-dir",
        action="append",
        dest="roots",
        default=[],
        metavar="DIR",
        help="directory whose subdirectories with ga4gh-io.schema.json are "
        "workflows (repeatable), e.g., examples/workflows",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="read the workflows again on every request, so that edits and "
        "new workflows show without a restart (broken ones are left out and "
        "reported)",
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
    default = [] if args.roots else [str(DEMO_DIR)]
    directories = [Path(directory) for directory in args.workflows or default]
    roots = [Path(root) for root in args.roots]
    workflows = []
    for directory in [*directories, *(p for r in roots for p in find_workflows(r))]:
        try:
            workflows.append(load_workflow(directory))
        except (OSError, ValueError) as exc:
            print(f"Can't serve the workflow {directory}: {exc}", file=sys.stderr)
            return 1
    reload: Callable[[], list[Workflow]] | None = None
    if args.reload:
        # Broken workflows are left out on reload, not fatal: users edit them
        reload = functools.partial(load_workflows, directories, roots, strict=False)
    try:
        server = TrsStub((args.host, args.port), workflows, reload)
    except (OSError, ValueError) as exc:
        print(f"Can't start the stub: {exc}", file=sys.stderr)
        return 1
    # The bound address, which `server_address` is set to as well; typeshed
    # types `server_address` with bytes, which f-strings would print as b'...'
    host, port = server.socket.getsockname()[:2]
    print("TRS stub of the prototype (a proof of concept, not a TRS)")
    print(f"Serving TRS on http://{host}:{port}{API}/tools (Ctrl+C stops)")
    for workflow in workflows:
        print(f"  {API}/tools/{workflow.tool_id}/versions/{workflow.version_id}")
    if args.reload:
        print("Files are re-read on every request (--reload)")
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
