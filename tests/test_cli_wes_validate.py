# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the ``wes-validate`` subcommand."""

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.cli import main
from ga4gh_io_schema.cli.commands import wes_params as wes_params_command
from ga4gh_io_schema.validator import UnresolvableReferenceError

TESTS_DIR = Path(__file__).resolve().parent
VECTORS_DIR = TESTS_DIR / "vectors" / "wes-requests"
WDL = VECTORS_DIR / "WDL" / "qualified-names"
CWL = VECTORS_DIR / "CWL" / "file-objects"
EXAMPLE_WDL = TESTS_DIR / "data" / "example_wdl.schema.json"
TOOL_PAGE = TESTS_DIR.parent / "docs" / "tools" / "wes-validate.md"
PROFILE = (
    "https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/"
    "ga4gh-io-profile.schema.json"
)


def args(vector: Path, *extra: str) -> list[str]:
    """Build the arguments of ``wes-validate`` for a vector.

    Args:
        vector: Directory of the vector.
        *extra: Further arguments.

    Returns:
        The command-line arguments.
    """
    return [
        "wes-validate",
        "--schema",
        str(vector / "schema.json"),
        "--params",
        str(vector / "workflow_params.json"),
        *extra,
    ]


def read(path: Path) -> Any:
    """Read a JSON file.

    Args:
        path: The file.

    Returns:
        The parsed document.
    """
    return json.loads(path.read_text(encoding="utf-8"))


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


def json_blocks(page: Path) -> list[Any]:
    """Parse the JSON code blocks of a documentation page.

    Args:
        page: The page.

    Returns:
        The parsed blocks, in the order of the page.
    """
    blocks = page.read_text(encoding="utf-8").split("```json\n")[1:]
    return [json.loads(block.split("```")[0]) for block in blocks]


def test_documented_examples(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test the examples of the tool page, with the schema of Example 3.

    The page shows the ``workflow_params`` and the input values, then a
    request with a wrong value and the error that ``--json`` writes.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    params, values, bad, error = json_blocks(TOOL_PAGE)
    # The vector has the same parameters as the page
    assert params == read(WDL / "workflow_params.json")

    command = ["wes-validate", "--schema", str(EXAMPLE_WDL), "--params"]
    assert main([*command, str(WDL / "workflow_params.json")]) == 0
    assert json.loads(capsys.readouterr().out) == values
    bad_path = write(tmp_path / "bad.json", bad)
    assert main([*command, str(bad_path), "--json"]) == 1
    assert json.loads(capsys.readouterr().err) == error


def test_writes_input_values(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the command writes the input values as JSON.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(WDL)) == 0
    assert json.loads(capsys.readouterr().out) == read(WDL / "values.json")


def test_writes_json_on_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--json`` writes the result on one line.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(CWL, "--json")) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert json.loads(out) == read(CWL / "values.json")


def test_reports_errors_with_pointer(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that errors name their JSON Pointer into ``workflow_params``.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(VECTORS_DIR / "WDL" / "error-message")) == 1
    assert capsys.readouterr().err == (
        "Validation Error: Condition must be either control or treatment "
        "(at /variant_calling.condition)\n"
    )


def test_reports_error_response_with_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that ``--json`` adds the WES ``ErrorResponse`` to the error.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(VECTORS_DIR / "CWL" / "forbidden-scheme", "--json")) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["location"] == "/reads/location"
    assert error["exitCode"] == 1
    assert error["errorResponse"]["status_code"] == 400
    assert error["errorResponse"]["msg"].startswith("/reads/location: ")


def test_reports_errors_of_the_request_as_a_whole(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that an error without a location names ``workflow_params``.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(VECTORS_DIR / "WDL" / "unqualified-key", "--json")) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["location"] is None
    assert error["errorResponse"]["msg"].startswith("workflow_params: ")


@pytest.mark.parametrize(
    ("vector", "option"),
    [
        ("path-allowed", "--allow-paths"),
        ("scheme-not-allowed-in-array", "--allow-scheme=s3"),
    ],
)
def test_options_of_file_values(
    vector: str, option: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test the options that accept more file values.

    Args:
        vector: Name of a CWL vector that fails without the option.
        option: The option.
        capsys: Pytest fixture capturing standard output and error.
    """
    path = VECTORS_DIR / "CWL" / vector
    # The default allow-list, which --allow-scheme replaces
    schemes = ("--allow-scheme=drs", "--allow-scheme=https")

    assert main(args(path)) == 1
    assert main(args(path, option, *schemes, "--json")) == 0
    assert "class" not in capsys.readouterr().out


def test_allow_absolute_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--allow-absolute-paths`` allows absolute paths.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    params = read(WDL / "workflow_params.json")
    params["variant_calling.input_bam"] = "/data/sample.bam"
    path = write(tmp_path / "p.json", params)
    command = ["wes-validate", "--schema", str(WDL / "schema.json")]

    assert main([*command, "--params", str(path)]) == 1
    assert main([*command, "--params", str(path), "--allow-absolute-paths"]) == 0
    assert json.loads(capsys.readouterr().out)["input_bam"] == "/data/sample.bam"


def test_reports_binding_errors_with_error_response(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that a request for another workflow type is rejected.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(WDL, "--descriptor-type", "CWL", "--json")) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["message"].startswith("The descriptor_type 'CWL' differs")
    assert error["errorResponse"]["status_code"] == 400


def test_reports_invalid_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a schema that doesn't comply is reported as such.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = write(tmp_path / "s.json", {"$schema": PROFILE, "type": "object"})
    params = write(tmp_path / "p.json", {})

    status = main(["wes-validate", "--schema", str(schema), "--params", str(params)])

    assert status == 1
    err = capsys.readouterr().err
    assert err.startswith(
        "Validation Error: The schema doesn't comply with the GA4GH IO Profile: "
        "'properties' is a required property"
    )
    assert "(at $)" not in err


def test_reports_top_level_schema_error_without_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an error of the schema as a whole has no location.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = write(tmp_path / "s.json", ["not", "an", "object"])

    status = main(["wes-validate", "--schema", str(schema), "--params", str(schema)])

    assert status == 1
    assert "(at " not in capsys.readouterr().err


def test_reads_params_from_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--params -`` reads the parameters from standard input.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    stdin = io.TextIOWrapper(
        io.BytesIO((WDL / "workflow_params.json").read_bytes()), encoding="ascii"
    )
    monkeypatch.setattr(sys, "stdin", stdin)

    status = main(
        ["wes-validate", "--schema", str(WDL / "schema.json"), "--params", "-"]
    )

    assert status == 0
    assert json.loads(capsys.readouterr().out) == read(WDL / "values.json")


def test_reports_deep_nesting_as_a_rejected_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that parameters too deep to validate are a rejected request.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = read(WDL / "schema.json")
    schema["properties"]["inputs"]["properties"]["deep"] = {"$ref": "#/$defs/n"}
    schema["$defs"] = {"n": {"type": "array", "items": {"$ref": "#/$defs/n"}}}
    nested: list[Any] = []
    for _ in range(sys.getrecursionlimit() // 2):
        nested = [nested]
    params = {**read(WDL / "workflow_params.json"), "variant_calling.deep": nested}
    command = ["wes-validate", "--schema", str(write(tmp_path / "s.json", schema))]

    status = main([*command, "--params", str(write(tmp_path / "p.json", params))])

    assert status == 1
    assert capsys.readouterr().err.startswith(
        "Validation Error: workflow_params are too deeply nested to validate."
    )


def test_schema_and_params_not_both_from_standard_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that only one input can come from standard input.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as info:
        main(["wes-validate", "--schema", "-", "--params", "-"])
    assert info.value.code == 2
    assert "only one of --schema and --params" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "kind", "message"),
    [
        (
            UnresolvableReferenceError("unresolvable"),
            "Meta-schema Error",
            "unresolvable",
        ),
        (RecursionError(), "Error", "Too deeply nested to translate"),
    ],
)
def test_reports_other_failures(
    error: Exception,
    kind: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test how failures of the meta-schema and deep nesting are reported.

    Args:
        error: Error that the validation raises.
        kind: Expected label of the error.
        message: Expected part of the message.
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """

    def fail(*_: object) -> None:
        """Raise the error.

        Args:
            *_: Ignored arguments.

        Raises:
            Exception: Always.
        """
        raise error

    monkeypatch.setattr(wes_params_command, "validate_schema", fail)

    assert main(args(WDL)) == 3
    assert capsys.readouterr().err.startswith(f"{kind}: {message}")
