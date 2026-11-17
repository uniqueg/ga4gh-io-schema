# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the ``verify`` subcommand."""

import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.cli import main

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"
SCHEMA = DEMO / "ga4gh-io.schema.json"
DESCRIPTOR = DEMO / "demo.wdl"
TOOL_PAGE = ROOT / "docs" / "tools" / "verify.md"
IDS = [
    "--trs-tool-id",
    "ga4gh-io-schema-demo",
    "--trs-version-id",
    "1.0.0",
    "--descriptor-type",
    "WDL",
]


def check(*extra: str) -> list[str]:
    """Build the arguments of ``verify`` for the demo schema.

    Args:
        *extra: Further arguments.

    Returns:
        The command-line arguments.
    """
    return ["verify", "--schema", str(SCHEMA), *extra]


def write(path: Path, data: Any) -> Path:
    """Write a JSON file.

    Args:
        path: The file.
        data: The document.

    Returns:
        The path.
    """
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_documented_example(capsys: pytest.CaptureFixture[str]) -> None:
    """Test the example of the tool page, in text and as JSON.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    blocks = TOOL_PAGE.read_text(encoding="utf-8").split("```json\n")[1:]
    expected = json.loads(blocks[0].split("```")[0])

    assert main(check(*IDS, "--descriptor", str(DESCRIPTOR))) == 0
    assert capsys.readouterr().out == "The schema is verified (sha-256).\n"
    assert main(check(*IDS, "--descriptor", str(DESCRIPTOR), "--json")) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_mismatches_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a changed descriptor and another version fail with both values.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    changed = tmp_path / "demo.wdl"
    changed.write_bytes(DESCRIPTOR.read_bytes() + b"\n")

    status = main(
        check("--trs-version-id", "1.1.0", "--descriptor", str(changed), "--json")
    )

    assert status == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["message"].startswith(
        "The schema may not match the workflow: "
        "x-ga4gh-workflow.trs_version_id is '1.0.0', not '1.1.0'. "
        "x-ga4gh-workflow.checksum (sha-256) is '"
    )
    assert error["verified"] is False
    assert [m["field"] for m in error["mismatches"]] == ["trs_version_id", "checksum"]
    assert error["exitCode"] == 1


def test_file_wrapper(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the checksum of a TRS ``FileWrapper`` is compared.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    digest = hashlib.sha256(DESCRIPTOR.read_bytes()).hexdigest()
    wrapper = write(
        tmp_path / "wrapper.json",
        {"checksum": [{"type": "sha-256", "checksum": digest}]},
    )

    assert main(check("--file-wrapper", str(wrapper))) == 0
    assert "verified" in capsys.readouterr().out


def test_unverified_schema_passes_unless_required(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test a schema without a descriptor to compare with.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(check(*IDS)) == 0
    assert capsys.readouterr().out.startswith("The schema is unverified: ")

    assert main(check(*IDS, "--require-verified", "--json")) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["message"].startswith("The schema is unverified: ")
    assert error["compared"] == []


def test_descriptor_from_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the descriptor can come from standard input, as bytes.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    stdin = io.TextIOWrapper(io.BytesIO(DESCRIPTOR.read_bytes()))
    monkeypatch.setattr(sys, "stdin", stdin)

    assert main(check("--descriptor", "-")) == 0
    assert capsys.readouterr().out == "The schema is verified (sha-256).\n"


def test_closed_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a closed standard input is an I/O error.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    monkeypatch.setattr(sys, "stdin", None)

    assert main(check("--descriptor", "-")) == 3
    assert "standard input is closed" in capsys.readouterr().err


def test_missing_descriptor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a descriptor that can't be read is an I/O error.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(check("--descriptor", str(tmp_path / "missing.wdl"))) == 3
    assert "File not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--schema", "-", "--descriptor", "-"], "only one of"),
        (
            ["--schema", str(SCHEMA), "--descriptor", "a", "--file-wrapper", "b"],
            "can't be used together",
        ),
    ],
)
def test_usage_errors(
    capsys: pytest.CaptureFixture[str], arguments: list[str], message: str
) -> None:
    """Test inputs that can't be combined.

    Args:
        capsys: Pytest fixture capturing standard output and error.
        arguments: The arguments after the subcommand.
        message: Part of the error message.
    """
    with pytest.raises(SystemExit) as info:
        main(["verify", *arguments])

    assert info.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("option", "message"),
    [("--schema", "The schema isn't"), ("--file-wrapper", "The FileWrapper isn't")],
)
def test_inputs_must_be_objects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], option: str, message: str
) -> None:
    """Test that a schema or ``FileWrapper`` that isn't an object fails.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
        option: The option that gets a JSON array.
        message: The start of the error message.
    """
    array = write(tmp_path / "array.json", [])
    arguments = ["verify", "--schema", str(SCHEMA), option, str(array)]

    assert main(arguments) == 1
    assert message in capsys.readouterr().err
