# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Register the demo workflow, with its I/O Schema, in a TRS-Filer instance.

The tool version has, for the descriptor type ``WDL``, the primary
descriptor ``demo.wdl`` (with its content, and a URL pinned to a commit of
the repository) and the I/O Schema as a file of type ``OTHER`` at the path
``ga4gh-io.schema.json``, as the TRS convention of the profile says. The
identifiers of the tool and the version are those that the schema names in
``x-ga4gh-workflow``, so the tool is created with ``PUT /tools/{id}``.

Usage::

    python examples/demo/register.py --trs-url URL --revision SHA [--dry-run]

The access token for writing, if the instance needs one, is read from the
environment variable ``TRS_TOKEN``.
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from demo_http import HTTPError, request_json

#: Directory of the demo.
DEMO_DIR = Path(__file__).resolve().parent
#: Path of the demo directory in the repository.
REPOSITORY_DIR = "examples/demo"
#: The repository that holds the demo workflow.
DEFAULT_REPOSITORY = "https://github.com/uniqueg/ga4gh-io-schema"
#: Name of the environment variable with the access token.
TOKEN_ENV = "TRS_TOKEN"
#: A full commit SHA of Git.
_SHA = re.compile(r"^[0-9a-f]{40}$")
#: A repository on GitHub, as its root URL.
_GITHUB_REPOSITORY = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)


def check_revision(revision: str) -> str:
    """Check that a revision is a full commit SHA.

    Args:
        revision: The revision.

    Returns:
        The revision.

    Raises:
        ValueError: If it isn't 40 lowercase hexadecimal digits.
    """
    if not _SHA.match(revision):
        raise ValueError(
            "The revision must be a full commit SHA (40 lowercase hex digits)"
        )
    return revision


def check_repository(repository: str) -> str:
    """Check that a repository URL is the root URL of a GitHub repository.

    Args:
        repository: The URL, e.g. ``https://github.com/owner/repo``.

    Returns:
        The URL.

    Raises:
        ValueError: If it isn't such a URL.
    """
    if not _GITHUB_REPOSITORY.match(repository):
        raise ValueError(
            "The repository must be a GitHub repository URL: "
            "https://github.com/<owner>/<repo>"
        )
    return repository


def _sha256(content: bytes) -> list[dict[str, str]]:
    """Return a TRS checksum list with the SHA-256 digest of bytes."""
    return [{"type": "sha-256", "checksum": hashlib.sha256(content).hexdigest()}]


def build_payload(
    revision: str, repository: str = DEFAULT_REPOSITORY
) -> dict[str, Any]:
    """Build the TRS-Filer registration of the demo tool (``ToolRegister``).

    Args:
        revision: Full commit SHA that the URL of the primary descriptor
            pins; the commit must contain the demo files as they are here.
        repository: Root URL of the GitHub repository with the demo.

    Returns:
        The body of ``PUT /tools/{id}``.

    Raises:
        ValueError: If the revision or the repository is malformed.
    """
    check_revision(revision)
    check_repository(repository)
    schema_bytes = (DEMO_DIR / "ga4gh-io.schema.json").read_bytes()
    schema = json.loads(schema_bytes)
    workflow = schema["x-ga4gh-workflow"]
    descriptor_path = workflow["primary_descriptor_path"]
    descriptor_bytes = (DEMO_DIR / descriptor_path).read_bytes()
    raw_base = repository.replace(
        "https://github.com/", "https://raw.githubusercontent.com/", 1
    )
    descriptor_type = workflow["descriptor_type"]
    return {
        "organization": "GA4GH I/O Schema",
        "name": schema["title"],
        "description": schema["description"],
        "toolclass": {
            "id": "workflow",
            "name": "Workflow",
            "description": "A workflow.",
        },
        "versions": [
            {
                "id": workflow["trs_version_id"],
                "name": schema["title"],
                "descriptor_type": [descriptor_type],
                "descriptor_type_version": {
                    descriptor_type: [workflow["descriptor_type_version"]]
                },
                "is_production": False,
                "files": [
                    {
                        "tool_file": {
                            "path": descriptor_path,
                            "file_type": "PRIMARY_DESCRIPTOR",
                        },
                        "type": descriptor_type,
                        "file_wrapper": {
                            "content": descriptor_bytes.decode("utf-8"),
                            "checksum": _sha256(descriptor_bytes),
                            "url": f"{raw_base}/{revision}/{REPOSITORY_DIR}/{descriptor_path}",
                        },
                    },
                    {
                        "tool_file": {
                            "path": "ga4gh-io.schema.json",
                            "file_type": "OTHER",
                        },
                        "type": descriptor_type,
                        "file_wrapper": {
                            "content": schema_bytes.decode("utf-8"),
                            "checksum": _sha256(schema_bytes),
                        },
                    },
                ],
            }
        ],
    }


def tool_id() -> str:
    """Return the TRS identifier of the demo tool, as the schema names it.

    Returns:
        ``trs_tool_id`` of the schema's ``x-ga4gh-workflow``.
    """
    schema = json.loads((DEMO_DIR / "ga4gh-io.schema.json").read_text(encoding="utf-8"))
    return schema["x-ga4gh-workflow"]["trs_tool_id"]


def schema_url(trs_url: str, payload: dict[str, Any]) -> str:
    """Return the TRS URL of the I/O Schema of the registered version.

    Args:
        trs_url: Base URL of the TRS API.
        payload: The registration, from :func:`build_payload`.

    Returns:
        The URL of the schema's ``FileWrapper``.
    """
    version = payload["versions"][0]
    quote = urllib.parse.quote
    return (
        f"{trs_url.rstrip('/')}/tools/{quote(tool_id(), safe='')}"
        f"/versions/{quote(version['id'], safe='')}"
        f"/{version['descriptor_type'][0]}/descriptor/ga4gh-io.schema.json"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Register the demo tool, or print the registration.

    Args:
        argv: Command-line arguments, without the program name.

    Returns:
        The exit status: 0 on success, 1 if the arguments are invalid or the
        registration fails.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--trs-url",
        help="base URL of the TRS API, e.g. https://trs.example.org/ga4gh/trs/v2",
    )
    parser.add_argument(
        "--revision",
        required=True,
        help="full commit SHA of the repository that contains the demo files",
    )
    parser.add_argument(
        "--repository",
        default=DEFAULT_REPOSITORY,
        help=f"GitHub repository with the demo (default: {DEFAULT_REPOSITORY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the registration instead of sending it",
    )
    args = parser.parse_args(argv)
    try:
        payload = build_payload(args.revision, args.repository)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    if not args.trs_url:
        print("Error: --trs-url is required unless --dry-run is given", file=sys.stderr)
        return 1
    url = f"{args.trs_url.rstrip('/')}/tools/{urllib.parse.quote(tool_id(), safe='')}"
    try:
        registered = request_json("PUT", url, payload, token_env=TOKEN_ENV)
    except HTTPError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Registered tool {registered}", file=sys.stderr)
    print(schema_url(args.trs_url, payload))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
