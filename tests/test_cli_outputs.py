"""Tests of the ``outputs`` subcommand of the command-line interface."""

import io
import json
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema.cli import main

TESTS_DIR = Path(__file__).resolve().parent
SCHEMA = TESTS_DIR / "data" / "example_workflow.schema.json"
VECTORS_DIR = TESTS_DIR / "vectors" / "wes-outputs"
SAPPORO = VECTORS_DIR / "sapporo-listing"
OUTPUT_DIR = "https://wes.example.org/runs/run-5/outputs"


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


def test_outputs_writes_the_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the command writes the report, indented, in text mode.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    status = main(
        [
            "outputs",
            "--schema",
            str(SAPPORO / "schema.json"),
            "--run-log",
            str(SAPPORO / "run_log.json"),
            "--output-dir",
            OUTPUT_DIR,
        ]
    )

    captured = capsys.readouterr()
    assert status == 0, captured.err
    report = json.loads(captured.out)
    assert report["conformance"] == "conformant"
    assert report["outputs"]["qc_report"] == f"{OUTPUT_DIR}/multiqc/multiqc_report.html"
    assert captured.out.startswith('{\n  "state": "COMPLETE"')


def test_outputs_json_and_files_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test ``--json`` and a listing given with ``--files``.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    run_log = write(tmp_path / "log.json", {"state": "COMPLETE", "outputs": {}})
    files = write(tmp_path / "files.json", ["multiqc/multiqc_report.html", "../x"])

    status = main(
        [
            "outputs",
            "--json",
            "--schema",
            str(SCHEMA),
            "--run-log",
            str(run_log),
            "--output-dir",
            "s3://b/r",
            "--files",
            str(files),
        ]
    )

    captured = capsys.readouterr()
    assert status == 0, captured.err
    assert captured.out.count("\n") == 1
    report = json.loads(captured.out)
    assert report["outputs"] == {"qc_report": "s3://b/r/multiqc/multiqc_report.html"}
    assert report["conformance"] == "non-conformant"
    assert report["skippedFiles"] == [{"entry": "../x", "reason": "a '..' segment"}]


def test_outputs_reads_the_run_log_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--run-log -`` reads the run log from standard input.

    Args:
        monkeypatch: Pytest fixture for patching standard input.
        capsys: Pytest fixture capturing standard output and error.
    """
    log = json.dumps({"state": "CANCELED", "outputs": {"samples_passed_qc": 1}})
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(log.encode())))

    status = main(["outputs", "--schema", str(SCHEMA), "--run-log", "-"])

    captured = capsys.readouterr()
    assert status == 0, captured.err
    assert json.loads(captured.out)["outputs"] == {"samples_passed_qc": 1}


@pytest.mark.parametrize(
    ("schema", "run_log", "extra", "status", "message"),
    [
        (
            SCHEMA,
            {"state": "RUNNING"},
            [],
            1,
            "Validation Error: The run is in the state 'RUNNING'",
        ),
        (
            {"type": "object"},
            {"state": "COMPLETE"},
            [],
            1,
            "Validation Error: The IO schema doesn't comply: The schema lacks a "
            "'$schema' property",
        ),
        (
            SCHEMA,
            {"state": "COMPLETE"},
            ["--output-dir", "relative"],
            1,
            "Validation Error: The output directory 'relative' must be an absolute URI",
        ),
    ],
    ids=["not-final", "invalid-schema", "bad-output-dir"],
)
def test_outputs_errors(
    schema: Path | dict[str, Any],
    run_log: dict[str, Any],
    extra: list[str],
    status: int,
    message: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test the errors of the command and their exit status.

    Args:
        schema: The IO schema, as a file or a document.
        run_log: The run log.
        extra: Further arguments.
        status: The expected exit status.
        message: The start of the expected error.
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    if isinstance(schema, dict):
        schema = write(tmp_path / "schema.json", schema)
    log = write(tmp_path / "log.json", run_log)

    args = ["outputs", "--schema", str(schema), "--run-log", str(log), *extra]
    assert main(args) == status

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(message)


def test_outputs_schema_errors_have_a_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an error of the schema names its location.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema["properties"]["outputs"]["properties"]["qc_report"][
        "x-ga4gh-output-glob"
    ] = "../x"
    path = write(tmp_path / "schema.json", schema)
    log = write(tmp_path / "log.json", {"state": "COMPLETE"})

    assert main(["outputs", "--schema", str(path), "--run-log", str(log)]) == 1
    assert "(at $.properties.outputs.properties.qc_report" in capsys.readouterr().err


def test_outputs_unresolvable_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a reference that can't be resolved is a validation error.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema["properties"]["outputs"]["properties"]["x"] = {"$ref": "#/$defs/none"}
    path = write(tmp_path / "schema.json", schema)
    log = write(tmp_path / "log.json", {"state": "COMPLETE", "outputs": {"x": 1}})

    assert main(["outputs", "--schema", str(path), "--run-log", str(log)]) == 1
    assert "can't be resolved locally" in capsys.readouterr().err


def test_outputs_too_deeply_nested(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a reference cycle is reported as too deeply nested.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema["properties"]["outputs"]["properties"]["x"] = {"$ref": "#/$defs/a"}
    schema["$defs"] = {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}
    path = write(tmp_path / "schema.json", schema)
    log = write(tmp_path / "log.json", {"state": "COMPLETE", "outputs": {"x": 1}})

    assert main(["outputs", "--schema", str(path), "--run-log", str(log)]) == 3
    assert capsys.readouterr().err.startswith("Error: Too deeply nested to normalise")


def test_outputs_one_stdin_only(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the schema and the run log can't both come from standard input.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(["outputs", "--schema", "-", "--run-log", "-"]) == 3
    assert "Only one of --schema and --run-log" in capsys.readouterr().err


def test_outputs_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a missing run log is an error of input.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    args = ["outputs", "--schema", str(SCHEMA), "--run-log", "missing.json"]
    assert main(args) == 3
    assert capsys.readouterr().err.startswith("Error: File not found")
