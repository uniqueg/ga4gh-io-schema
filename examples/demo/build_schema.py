# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Build the I/O Schema of the demo workflow from its WDL document.

The schema, ``ga4gh-io.schema.json``, is what ``ga4gh-io-schema convert wdl
demo.wdl`` writes, with ``schema.overlay.json`` applied to it as a JSON
Merge Patch (RFC 7396). The overlay adds what WDL can't express and the
converter therefore leaves to the author: the identifiers of the tool
version in TRS and the path of the primary descriptor, bounds of numbers,
error messages, widgets, format terms and media types of files, and
examples.

Usage::

    python examples/demo/build_schema.py          # write the schema
    python examples/demo/build_schema.py --check  # fail if it is outdated
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ga4gh_io_schema.converters import wdl
from ga4gh_io_schema.validator import validate_schema

#: Directory of the demo.
DEMO_DIR = Path(__file__).resolve().parent
#: The primary descriptor of the demo workflow.
WDL_PATH = DEMO_DIR / "demo.wdl"
#: Additions to the converted schema, as a JSON Merge Patch.
OVERLAY_PATH = DEMO_DIR / "schema.overlay.json"
#: The I/O Schema of the demo workflow.
SCHEMA_PATH = DEMO_DIR / "ga4gh-io.schema.json"


def merge_patch(target: Any, patch: Any) -> Any:
    """Apply a JSON Merge Patch (RFC 7396) to a JSON value.

    Args:
        target: The value to patch; it isn't changed.
        patch: The patch: objects are merged member by member, ``null``
            removes a member, and any other value replaces the target.

    Returns:
        The patched value.
    """
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def build() -> tuple[dict[str, Any], list[str]]:
    """Convert the demo workflow and apply the overlay.

    Returns:
        The I/O Schema, and the notes of the conversion, as lines of text.

    Raises:
        jsonschema.exceptions.ValidationError: If the schema doesn't comply
            with the GA4GH IO Profile.
    """
    content = WDL_PATH.read_bytes()
    conversion = wdl.convert(
        WDL_PATH,
        content.decode("utf-8"),
        checksum=wdl.descriptor_checksum(content),
    )
    overlay = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    schema = merge_patch(conversion.schema, overlay)
    validate_schema(schema)
    return schema, [note.to_text() for note in conversion.notes]


def render(schema: dict[str, Any]) -> str:
    """Render a schema as it is checked in.

    Args:
        schema: The schema.

    Returns:
        The schema as JSON, indented by two spaces, with a final newline.
    """
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write the schema, or check that the checked-in schema is current.

    Args:
        argv: Command-line arguments, without the program name.

    Returns:
        The exit status: 0 on success, 1 if ``--check`` finds the
        checked-in schema outdated.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="don't write the schema; fail if the checked-in one differs",
    )
    args = parser.parse_args(argv)
    schema, notes = build()
    for note in notes:
        print(note, file=sys.stderr)
    text = render(schema)
    if args.check:
        current = (
            SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        )
        if current != text:
            print(
                f"{SCHEMA_PATH.name} is outdated; run {Path(__file__).name}",
                file=sys.stderr,
            )
            return 1
        return 0
    SCHEMA_PATH.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
