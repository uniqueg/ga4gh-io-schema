# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Set the checksums of the seeded workflows of the demo.

Each directory in ``examples/workflows/`` is a workflow that the TRS stub
of the demo serves: an IO schema, ``ga4gh-io.schema.json``, and the primary
descriptor that its ``x-ga4gh-workflow`` block names. The block also names
the SHA-256 checksum of the descriptor, which the form host compares with
the descriptor that the stub serves: after an edit of a descriptor, the
host refuses the schema (drift), until this script has set the checksum
again.

Usage::

    python examples/demo/checksums.py          # set the checksums
    python examples/demo/checksums.py --check  # fail if one is outdated
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: Directory of the seeded workflows.
WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "workflows"
#: Name of the IO schema in each directory.
SCHEMA_NAME = "ga4gh-io.schema.json"


def workflow_dirs(root: Path = WORKFLOWS_DIR) -> list[Path]:
    """List the directories of the seeded workflows.

    The same rule as ``find_workflows()`` of the TRS stub, which this
    script doesn't import, to run without the prototype (a test checks that
    both agree).

    Args:
        root: The directory that holds them.

    Returns:
        The subdirectories with an IO schema, sorted by name.
    """
    return sorted(path.parent for path in root.glob(f"*/{SCHEMA_NAME}"))


def with_checksum(schema: dict[str, Any], descriptor: bytes) -> dict[str, Any]:
    """Set the checksum of the primary descriptor in a schema.

    Args:
        schema: The IO schema; it isn't changed.
        descriptor: The primary descriptor, as the stub serves it.

    Returns:
        The schema, with ``x-ga4gh-workflow.checksum`` set to the SHA-256
        checksum of the descriptor.
    """
    digest = hashlib.sha256(descriptor).hexdigest()
    block = {**schema["x-ga4gh-workflow"]}
    block["checksum"] = [{"type": "sha-256", "checksum": digest}]
    return {**schema, "x-ga4gh-workflow": block}


def render(schema: dict[str, Any]) -> str:
    """Render a schema as it is checked in.

    Args:
        schema: The schema.

    Returns:
        The schema as JSON, indented by two spaces, with a final newline.
    """
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def update(directory: Path, check: bool) -> bool:
    """Set the checksum of one workflow, or check it.

    Args:
        directory: The directory of the workflow.
        check: Don't write; only compare.

    Returns:
        Whether the checked-in schema was up to date.

    Raises:
        OSError: If a file can't be read or written.
        ValueError: If the schema isn't JSON.
        KeyError: If it has no workflow block with ``primary_descriptor_path``.
    """
    path = directory / SCHEMA_NAME
    current = path.read_text(encoding="utf-8")
    schema = json.loads(current)
    primary = schema["x-ga4gh-workflow"]["primary_descriptor_path"]
    text = render(with_checksum(schema, (directory / primary).read_bytes()))
    if text == current:
        return True
    if not check:
        path.write_text(text, encoding="utf-8")
    return False


def main(argv: Sequence[str] | None = None) -> int:
    """Set the checksums, or check that they are current.

    Args:
        argv: Command-line arguments, without the program name.

    Returns:
        The exit status: 0 on success, 1 if ``--check`` finds a checksum
        outdated or a workflow can't be read.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="don't write the schemas; fail if a checksum is outdated",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=WORKFLOWS_DIR,
        help="directory of the workflows (default: examples/workflows)",
    )
    args = parser.parse_args(argv)
    status = 0
    for directory in workflow_dirs(args.dir):
        try:
            current = update(directory, args.check)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Can't read the workflow {directory.name}: {exc}", file=sys.stderr)
            status = 1
            continue
        if current:
            continue
        if args.check:
            print(
                f"{directory.name}: the checksum is outdated; run "
                f"{Path(__file__).name}",
                file=sys.stderr,
            )
            status = 1
        else:
            print(f"{directory.name}: checksum set", file=sys.stderr)
    return status


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
