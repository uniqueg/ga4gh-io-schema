# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the ``wes-params`` subcommand."""

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.cli import main
from ga4gh_io_schema.cli.commands import wes_params as wes_params_command
from ga4gh_io_schema.validator import UnresolvableReferenceError

VECTORS_DIR = Path(__file__).resolve().parent / "vectors" / "wes-params"
WDL = VECTORS_DIR / "WDL" / "qualified-names"
CWL = VECTORS_DIR / "CWL" / "file-objects"
NFL_S3 = VECTORS_DIR / "NFL" / "deployment-scheme"
PROFILE = (
    "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/"
    "ga4gh-io-profile.schema.json"
)


def args(vector: Path, *extra: str) -> list[str]:
    """Build the arguments of ``wes-params`` for a vector.

    Args:
        vector: Directory of the vector.
        *extra: Further arguments.

    Returns:
        The command-line arguments.
    """
    return [
        "wes-params",
        "--schema",
        str(vector / "schema.json"),
        "--values",
        str(vector / "values.json"),
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


def test_writes_workflow_params(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the command writes the ``workflow_params`` as JSON.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(WDL)) == 0
    assert json.loads(capsys.readouterr().out) == read(WDL / "workflow_params.json")


def test_writes_json_on_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--json`` writes the result on one line.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(CWL, "--json")) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert json.loads(out) == read(CWL / "workflow_params.json")


def test_allow_scheme(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--allow-scheme`` replaces the default allow-list.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(NFL_S3)) == 1
    assert "isn't on the allow-list" in capsys.readouterr().err
    assert main(args(NFL_S3, "--allow-scheme", "S3")) == 0
    assert json.loads(capsys.readouterr().out) == read(NFL_S3 / "workflow_params.json")


def test_allow_absolute_paths(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--allow-absolute-paths`` allows absolute paths.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    vector = VECTORS_DIR / "NFL" / "absolute-path-allowed"

    assert main(args(vector)) == 1
    assert main(args(vector, "--allow-absolute-paths")) == 0
    assert json.loads(capsys.readouterr().out) == read(vector / "workflow_params.json")


def test_forbidden_scheme_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that a forbidden scheme can't be allowed.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as info:
        main(args(WDL, "--allow-scheme", "javascript"))
    assert info.value.code == 2
    assert "the scheme 'javascript' can't be allowed" in capsys.readouterr().err


def test_reports_value_errors_with_location(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that errors in the values name their JSON path.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(VECTORS_DIR / "NFL" / "file-in-array", "--json")) == 1
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["kind"] == "validation"
    assert error["location"] == "$.fastqs[1]"


def test_reports_binding_errors_without_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that errors of the binding have no location.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(WDL, "--descriptor-type", "CWL")) == 1
    err = capsys.readouterr().err
    assert err.startswith("Validation Error: The descriptor_type 'CWL' differs")
    assert "(at " not in err


def test_reports_invalid_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a schema that doesn't comply is reported as such.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = write(tmp_path / "s.json", {"$schema": PROFILE, "type": "object"})
    values = write(tmp_path / "v.json", {})

    status = main(["wes-params", "--schema", str(schema), "--values", str(values)])

    assert status == 1
    assert capsys.readouterr().err.startswith(
        "Validation Error: The schema doesn't comply with the GA4GH IO Profile: "
        "'properties' is a required property"
    )


def test_reports_top_level_schema_error_without_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an error of the schema as a whole has no location.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = write(tmp_path / "s.json", ["not", "an", "object"])

    assert main(["wes-params", "--schema", str(schema), "--values", str(schema)]) == 1
    err = capsys.readouterr().err
    assert "must be a JSON object" in err
    assert "(at " not in err


def test_reads_values_from_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--values -`` reads the values from standard input.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    stdin = io.TextIOWrapper(
        io.BytesIO((WDL / "values.json").read_bytes()), encoding="ascii"
    )
    monkeypatch.setattr(sys, "stdin", stdin)

    status = main(["wes-params", "--schema", str(WDL / "schema.json"), "--values", "-"])

    assert status == 0
    assert json.loads(capsys.readouterr().out) == read(WDL / "workflow_params.json")


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--request"], "--request needs --workflow-url or --trs-url"),
        (["--workflow-url", "https://e.org/w"], "need --request"),
        (["--trs-url", "https://e.org/trs"], "need --request"),
        (
            ["--request", "--workflow-url", "https://e.org/w", "--trs-url", "x"],
            "exclude each other",
        ),
    ],
)
def test_usage_errors_of_the_request(
    extra: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the options of the run request must fit together.

    Args:
        extra: Further arguments.
        message: Expected part of the error.
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as info:
        main(args(WDL, *extra))
    assert info.value.code == 2
    assert message in capsys.readouterr().err


def test_schema_and_values_not_both_from_standard_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that only one input can come from standard input.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as info:
        main(["wes-params", "--schema", "-", "--values", "-"])
    assert info.value.code == 2
    assert "only one of --schema and --values" in capsys.readouterr().err


def test_request_with_workflow_url(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--request`` writes a run request.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    url = "https://e.org/variant_calling.wdl"

    assert main(args(WDL, "--request", "--workflow-url", url)) == 0
    assert json.loads(capsys.readouterr().out) == {
        "workflow_params": read(WDL / "workflow_params.json"),
        "workflow_type": "WDL",
        "workflow_type_version": "1.1",
        "workflow_url": url,
    }


def test_request_with_trs_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--trs-url`` builds the workflow URL from the TRS ids.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = read(CWL / "schema.json")
    schema["x-ga4gh-workflow"].update(
        trs_tool_id="#workflow/e.org/align", trs_version_id="1.0", entry_point="#main"
    )
    path = write(tmp_path / "schema.json", schema)

    status = main(
        [
            "wes-params",
            "--schema",
            str(path),
            "--values",
            str(CWL / "values.json"),
            "--request",
            "--trs-url",
            "https://trs.e.org/ga4gh/trs/v2",
        ]
    )

    assert status == 0
    assert json.loads(capsys.readouterr().out)["workflow_url"] == (
        "https://trs.e.org/ga4gh/trs/v2/tools/%23workflow%2Fe.org%2Falign/"
        "versions/1.0/PLAIN_CWL/descriptor#main"
    )


def test_request_with_trs_url_needs_trs_ids(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that ``--trs-url`` needs the TRS ids in the schema.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(args(CWL, "--request", "--trs-url", "https://trs.e.org")) == 1
    assert "needs x-ga4gh-workflow.trs_tool_id" in capsys.readouterr().err


def test_options_fill_in_the_binding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the binding options fill in a schema without workflow block.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = read(WDL / "schema.json")
    del schema["x-ga4gh-workflow"]
    path = write(tmp_path / "schema.json", schema)

    status = main(
        [
            "wes-params",
            "--schema",
            str(path),
            "--values",
            str(WDL / "values.json"),
            "--descriptor-type",
            "WDL",
            "--type-version",
            "1.1",
            "--entry-point",
            "variant_calling",
            "--request",
            "--workflow-url",
            "https://e.org/w.wdl",
        ]
    )

    assert status == 0
    request = json.loads(capsys.readouterr().out)
    assert request["workflow_params"] == read(WDL / "workflow_params.json")
    assert request["workflow_type_version"] == "1.1"


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
