# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Find the IO schema of a workflow in TRS, as a client, and build a run request.

The steps of "Discovery by clients" (``docs/adoption/trs.md``) with the
package: list the files of the tool version for the descriptor type, find
the IO schema among them (:func:`ga4gh_io_schema.trs.find_schema_file`:
the file of type ``IO_SCHEMA``, or else ``ga4gh-io.schema.json`` of type
``OTHER`` next to the primary descriptor), fetch it, validate it against the
profile, check its ``x-ga4gh-workflow`` against the tool version and the
checksum of the primary descriptor, and turn input values into a WES run
request whose ``workflow_url`` is the TRS URL of the primary descriptor.

Usage::

    python examples/demo/trs_client.py --trs-url URL [--tool-id ID]
        [--version-id ID] [--descriptor-type TYPE] [--values FILE]

The identifiers default to those of the demo; the steps are reported on
standard error, the run request is written to standard output. Nothing is
submitted.
"""

import argparse
import json
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from demo_http import HTTPError, request_json
from jsonschema.exceptions import ValidationError

from ga4gh_io_schema.trs import find_schema_file
from ga4gh_io_schema.validator import validate_schema
from ga4gh_io_schema.wes import build_run_request, trs_descriptor_url

#: Directory of the demo.
DEMO_DIR = Path(__file__).resolve().parent
#: The ``x-ga4gh-workflow`` block of the demo's IO schema, for the defaults.
DEMO_WORKFLOW = json.loads(
    (DEMO_DIR / "ga4gh-io.schema.json").read_text(encoding="utf-8")
)["x-ga4gh-workflow"]


class ClientError(RuntimeError):
    """The tool version has no usable IO schema."""


def _report(message: str) -> None:
    """Report a step on standard error.

    Args:
        message: What happened.
    """
    print(message, file=sys.stderr)


def version_url(
    trs_url: str, tool_id: str, version_id: str, descriptor_type: str
) -> str:
    """Build the TRS URL of a tool version for a descriptor type.

    Args:
        trs_url: Base URL of the TRS API.
        tool_id: Id of the tool.
        version_id: Id of the tool version.
        descriptor_type: TRS descriptor type, e.g., ``WDL``.

    Returns:
        ``{trs_url}/tools/{id}/versions/{version_id}/{type}``, with the ids
        percent-encoded.
    """
    quoted = [urllib.parse.quote(part, safe="") for part in (tool_id, version_id)]
    return (
        f"{trs_url.rstrip('/')}/tools/{quoted[0]}/versions/{quoted[1]}"
        f"/{urllib.parse.quote(descriptor_type, safe='')}"
    )


def _sha256(wrapper: Any) -> set[str]:
    """Return the SHA-256 checksums of a ``FileWrapper`` or a checksum list.

    Algorithm names are compared case-insensitively (see "Drift" in the
    specification); ``sha256`` is taken as ``sha-256``.

    Args:
        wrapper: A ``FileWrapper`` (with ``checksum``), or a list of
            checksums; anything else has none.

    Returns:
        The hex digests of type ``sha-256``, in lowercase.
    """
    checksums = wrapper.get("checksum") if isinstance(wrapper, dict) else wrapper
    if not isinstance(checksums, list):
        return set()
    return {
        c["checksum"].lower()
        for c in checksums
        if isinstance(c, dict)
        and isinstance(c.get("type"), str)
        and c["type"].lower() in ("sha-256", "sha256")
        and isinstance(c.get("checksum"), str)
    }


def discover(
    trs_url: str, tool_id: str, version_id: str, descriptor_type: str
) -> dict[str, Any]:
    """Find, fetch and check the IO schema of a tool version in TRS.

    Args:
        trs_url: Base URL of the TRS API.
        tool_id: Id of the tool.
        version_id: Id of the tool version.
        descriptor_type: TRS descriptor type, e.g., ``WDL``.

    Returns:
        The IO schema, valid against the profile and bound to the tool
        version.

    Raises:
        HTTPError: If a request to TRS fails.
        ClientError: If the tool version has no IO schema, or its schema
            isn't JSON, names another tool version or descriptor type, or
            names a checksum that the primary descriptor doesn't have.
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the profile.
    """
    base = version_url(trs_url, tool_id, version_id, descriptor_type)
    files = request_json("GET", f"{base}/files")
    _report(f"1. Files of the tool version: {json.dumps(files)}")
    found = find_schema_file(files)
    if found is None:
        raise ClientError("The tool version has no IO schema.")
    _report(f"2. IO schema: {found.path} (file type {found.file_type})")
    path = urllib.parse.quote(found.path, safe="")
    wrapper = request_json("GET", f"{base}/descriptor/{path}")
    try:
        schema = json.loads(wrapper["content"])
    except (TypeError, KeyError, ValueError) as exc:
        raise ClientError("The IO schema isn't JSON in a FileWrapper.") from exc
    validate_schema(schema)
    _report(f"3. Valid against the profile: {schema.get('$schema')}")
    block = schema.get("x-ga4gh-workflow") or {}
    expected = {
        "trs_tool_id": tool_id,
        "trs_version_id": version_id,
        "descriptor_type": descriptor_type,
    }
    for key, value in expected.items():
        if key in block and block[key] != value:
            raise ClientError(
                f"The IO schema is for another workflow: x-ga4gh-workflow.{key} "
                f"is {block[key]!r}, not {value!r}."
            )
    named = _sha256(block.get("checksum"))
    if named:
        primary = _sha256(request_json("GET", f"{base}/descriptor"))
        if not primary:
            _report("4. Bound to the tool version; checksum unverified")
        elif named & primary:
            _report("4. Bound to the tool version; checksum matches")
        else:
            raise ClientError(
                "The IO schema names another checksum of the primary descriptor "
                "than TRS (drift)."
            )
    else:
        _report("4. Bound to the tool version; no checksum to compare")
    return schema


def main(argv: Sequence[str] | None = None) -> int:
    """Find the IO schema of a tool version and print a run request.

    Args:
        argv: Command-line arguments, without the program name.

    Returns:
        The exit status: 0 on success, 1 if the schema can't be found,
        fetched or used, or the values can't be translated.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--trs-url",
        required=True,
        help="base URL of the TRS API, e.g. http://127.0.0.1:8080/ga4gh/trs/v2",
    )
    parser.add_argument("--tool-id", default=DEMO_WORKFLOW["trs_tool_id"])
    parser.add_argument("--version-id", default=DEMO_WORKFLOW["trs_version_id"])
    parser.add_argument("--descriptor-type", default=DEMO_WORKFLOW["descriptor_type"])
    parser.add_argument(
        "--values",
        type=Path,
        default=DEMO_DIR / "values.json",
        help="input values, a JSON object (default: the demo's values.json)",
    )
    args = parser.parse_args(argv)
    try:
        values = json.loads(args.values.read_text(encoding="utf-8"))
        schema = discover(
            args.trs_url, args.tool_id, args.version_id, args.descriptor_type
        )
        url = trs_descriptor_url(
            args.trs_url, args.tool_id, args.version_id, args.descriptor_type
        )
        request = build_run_request(schema, values, workflow_url=url)
    except ValidationError as exc:
        print(f"Error: the IO schema is invalid: {exc.message}", file=sys.stderr)
        return 1
    # TranslationError (invalid values) is a ValueError, as is invalid JSON
    except (OSError, ValueError, HTTPError, ClientError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _report("5. Run request (not submitted):")
    print(json.dumps(request, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
