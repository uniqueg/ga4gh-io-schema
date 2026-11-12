# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the subcommand framework and the shared conventions of the CLI."""

import argparse
import io
import json
import runpy
import sys
from pathlib import Path

import pytest

from ga4gh_io_schema.cli import app, main
from ga4gh_io_schema.cli.base import (
    ROOT,
    CliError,
    Command,
    CommandGroup,
    CommandResult,
    ExitCode,
    read_json,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
VALID = DATA_DIR / "valid.schema.json"
INVALID = DATA_DIR / "invalid" / "missing-inputs.schema.json"


class EchoCommand(Command):
    """Command that echoes its argument, for tests of the framework."""

    name = "echo"
    help = "Echo a word."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the word argument.

        Args:
            parser: Parser of the command.
        """
        parser.add_argument("word")

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Echo the word.

        Args:
            args: Parsed arguments.

        Returns:
            The word.
        """
        return CommandResult(text=args.word, data={"word": args.word})


class BareCommand(Command):
    """Command without arguments of its own."""

    name = "bare"
    help = "Do nothing."

    def run(self, args: argparse.Namespace) -> CommandResult:
        """Do nothing.

        Args:
            args: Parsed arguments.

        Returns:
            An empty result.
        """
        return CommandResult(text="", data={})


def _stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Replace standard input.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        text: Content of standard input.
    """
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_validate_reads_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``-`` reads the schema from standard input.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    _stdin(monkeypatch, VALID.read_text(encoding="utf-8"))

    assert main(["validate", "-"]) == ExitCode.SUCCESS
    assert "Success: '<stdin>' complies" in capsys.readouterr().out


def test_validate_names_standard_input_in_json_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that malformed JSON on standard input is named ``<stdin>``.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    _stdin(monkeypatch, "{not json")

    assert main(["validate", "-"]) == ExitCode.IO_ERROR
    assert "Error: Invalid JSON - <stdin>:" in capsys.readouterr().err


def test_validate_writes_output_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--output`` writes the result to a file instead of stdout.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    output = tmp_path / "result.txt"

    assert main(["validate", str(VALID), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == (
        f"Success: '{VALID}' complies with the GA4GH IO Profile.\n"
    )
    assert capsys.readouterr().out == ""


def test_validate_leaves_output_file_alone_on_error(tmp_path: Path) -> None:
    """Test that a failed command doesn't create the output file.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
    """
    output = tmp_path / "result.txt"

    assert main(["validate", str(INVALID), "-o", str(output)]) == 1
    assert not output.exists()


def test_unwritable_output_is_an_io_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an output file that can't be written exits with status 3.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    output = tmp_path / "missing-dir" / "result.txt"

    assert main(["validate", str(VALID), "-o", str(output)]) == ExitCode.IO_ERROR
    assert "Error: Can't write - " in capsys.readouterr().err


def test_unreadable_input_is_an_io_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an input that can't be read (a directory) exits with status 3.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(["validate", str(tmp_path)]) == ExitCode.IO_ERROR
    assert "Error: Can't read - " in capsys.readouterr().err


def test_json_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--json`` writes the result as a JSON object.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(["validate", "--json", str(VALID)]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "valid": True,
        "schema": str(VALID),
        "metaSchema": None,
    }


def test_json_validation_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--json`` writes errors as JSON objects to stderr.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(["validate", "--json", str(INVALID)]) == ExitCode.INVALID

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": {
            "kind": "validation",
            "message": "'inputs' is a required property",
            "location": "$.properties",
        },
        "exitCode": 1,
    }


def test_json_io_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--json`` also reports a missing file as a JSON object.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    missing = DATA_DIR / "does-not-exist.schema.json"

    assert main(["validate", "--json", str(missing)]) == ExitCode.IO_ERROR

    error = json.loads(capsys.readouterr().err)
    assert error["error"]["kind"] == "io"
    assert error["error"]["location"] is None
    assert error["exitCode"] == 3


def test_json_meta_schema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the JSON result names a custom meta-schema.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    meta_schema = tmp_path / "meta.schema.json"
    meta_schema.write_text("true", encoding="utf-8")

    assert main(["validate", str(VALID), "-m", str(meta_schema), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["metaSchema"] == str(meta_schema)


def test_missing_command_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that a call without a subcommand exits with status 2.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == ExitCode.USAGE
    assert "COMMAND" in capsys.readouterr().err


def test_old_command_name_is_gone(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a schema path without ``validate`` is a usage error.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    with pytest.raises(SystemExit) as exc_info:
        main([str(VALID)])

    assert exc_info.value.code == ExitCode.USAGE


def test_module_runs_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``python -m ga4gh_io_schema.cli`` runs the CLI.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    monkeypatch.setattr(sys, "argv", ["ga4gh-io-schema", "validate", str(VALID)])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("ga4gh_io_schema.cli", run_name="__main__")

    assert exc_info.value.code == 0
    assert "complies" in capsys.readouterr().out


def test_root_registers_validate() -> None:
    """Test that loading the commands registers ``validate``."""
    app.load_commands()

    assert "validate" in ROOT.commands


def test_group_rejects_duplicate_names() -> None:
    """Test that a name can't be registered twice in a group."""
    group = CommandGroup(name="root", help="Root.")
    group.register(EchoCommand())
    group.group("convert", help="Convert.")

    with pytest.raises(ValueError, match="'root echo' is already registered"):
        group.register(EchoCommand())
    with pytest.raises(ValueError, match="'root echo' is already registered"):
        group.group("echo", help="Clash.")


def test_group_is_shared_between_modules() -> None:
    """Test that asking for a group twice returns the same group."""
    group = CommandGroup(name="root", help="Root.")

    first = group.group("convert", help="Convert schemas.")
    second = group.group("convert", help="Ignored.")

    assert first is second
    assert first.help == "Convert schemas."


def test_nested_group_dispatch(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a command in a nested group runs without dispatcher changes.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    root = CommandGroup(name="root", help="Root.")
    root.group("convert", help="Convert.").register(EchoCommand())
    root.register(BareCommand())

    assert main(["convert", "echo", "hello"], root=root) == 0
    assert capsys.readouterr().out == "hello\n"
    assert main(["bare", "--json"], root=root) == 0
    assert capsys.readouterr().out == "{}\n"


def test_cli_error_text_without_location() -> None:
    """Test that errors without a location don't name one."""
    error = CliError(
        kind="io", label="Error", message="boom", exit_code=ExitCode.IO_ERROR
    )

    assert error.to_text() == "Error: boom"


def test_read_json_reads_file() -> None:
    """Test that ``read_json`` reads a file."""
    assert read_json(str(VALID))["type"] == "object"


def test_reference_documents_every_command() -> None:
    """Test that the generated reference covers the root and ``validate``."""
    reference = app.render_reference()

    assert "## `ga4gh-io-schema`\n" in reference
    assert "## `ga4gh-io-schema validate`\n" in reference
    assert "--meta-schema" in reference
    assert "Exit status: 0 on success" in reference
    assert "\x1b[" not in reference


def test_reference_of_nested_group() -> None:
    """Test that the reference covers nested groups and their commands."""
    root = CommandGroup(name="root", help="Root.")
    root.group("convert", help="Convert.").register(EchoCommand())

    reference = app.render_reference(root)

    assert "## `ga4gh-io-schema convert`\n" in reference
    assert "## `ga4gh-io-schema convert echo`\n" in reference


def test_help_wraps_at_given_width() -> None:
    """Test that the reference wraps the help text at the given width."""
    reference = app.render_reference(width=60)
    lines = [
        line
        for line in reference.splitlines()
        if not line.startswith(("#", "```", "usage:"))
    ]

    assert max(len(line) for line in lines) <= 60
