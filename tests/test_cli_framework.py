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
    ERROR_KINDS,
    EXIT_STATUS,
    ROOT,
    CliError,
    Command,
    CommandGroup,
    CommandResult,
    ErrorKind,
    ExitCode,
    read_json,
)
from ga4gh_io_schema.cli.commands import validate as validate_command

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "tests" / "data"
SUITE_DIR = REPO_ROOT / "tests" / "conformance" / "schema-documents"
CLI_PAGE = REPO_ROOT / "docs" / "tools" / "cli.md"
VALID = SUITE_DIR / "valid" / "annotated.schema.json"
INVALID = SUITE_DIR / "invalid" / "missing-inputs.schema.json"


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
        return CommandResult(text="done")


def _stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Replace standard input.

    Standard input is decoded as ASCII, to check that the CLI reads it as
    UTF-8 whatever the locale.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        text: Content of standard input.
    """
    stdin = io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="ascii")
    monkeypatch.setattr(sys, "stdin", stdin)


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


def test_old_command_name_is_gone() -> None:
    """Test that the old command is gone and a bare path is a usage error."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'ga4gh-io-schema = "ga4gh_io_schema.cli:main"' in pyproject
    assert "ga4gh-io-schema-validator" not in pyproject

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
    assert json.loads(capsys.readouterr().out) == {"output": "done"}


def test_cli_error_text_without_location() -> None:
    """Test that errors without a location don't name one."""
    error = CliError(ErrorKind.IO, "boom")

    assert error.to_text() == "Error: boom"
    assert error.exit_code == ExitCode.IO_ERROR


def test_read_json_reads_file() -> None:
    """Test that ``read_json`` reads a file."""
    assert read_json(str(VALID))["type"] == "object"


def test_reference_documents_every_command() -> None:
    """Test that the generated reference covers the root and ``validate``."""
    reference = app.render_reference()

    assert "## `ga4gh-io-schema`\n" in reference
    assert "## `ga4gh-io-schema validate`\n" in reference
    assert "--meta-schema" in reference
    assert reference.count("Exit status: 0 = success, 1 = ") == 1
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


def test_output_dash_means_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that ``--output -`` writes to standard output.

    Args:
        capsys: Pytest fixture capturing standard output and error.
    """
    assert main(["validate", str(VALID), "-o", "-"]) == 0
    assert "complies" in capsys.readouterr().out


def test_json_with_output_file(tmp_path: Path) -> None:
    """Test that ``--json`` and ``--output`` write the JSON result to the file.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
    """
    output = tmp_path / "result.json"

    assert main(["validate", str(VALID), "--json", "-o", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["valid"] is True


def test_json_internal_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--json`` reports unexpected errors with exit status 4.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """

    def fail(**_: object) -> None:
        """Raise an unexpected error.

        Args:
            **_: Ignored keyword arguments.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("boom")

    monkeypatch.setattr(validate_command, "validate_schema", fail)

    assert main(["validate", "--json", str(VALID)]) == ExitCode.INTERNAL
    assert json.loads(capsys.readouterr().err) == {
        "error": {"kind": "internal", "message": "boom", "location": None},
        "exitCode": 4,
    }


def test_non_utf8_input_is_an_io_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that an input that isn't UTF-8 exits with status 3.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    path = tmp_path / "latin1.schema.json"
    path.write_bytes(b'{"title": "\xe9"}')

    assert main(["validate", str(path)]) == ExitCode.IO_ERROR
    assert "Error: Not UTF-8 text - " in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["name", "help"])
def test_register_requires_name_and_help(missing: str) -> None:
    """Test that a command without ``name`` or ``help`` can't be registered.

    Args:
        missing: Class attribute that the command lacks.
    """
    partial = type("Partial", (BareCommand,), {missing: None})
    group = CommandGroup(name="root", help="Root.")

    with pytest.raises(
        TypeError, match=f"Partial must set the class attribute '{missing}'"
    ):
        group.register(partial())


def test_every_error_kind_has_a_label() -> None:
    """Test that every kind of error has a label and an exit status."""
    assert set(ERROR_KINDS) == set(ErrorKind)


def test_docs_list_every_error_kind_and_exit_status() -> None:
    """Test that the CLI page documents every error kind and exit status."""
    page = CLI_PAGE.read_text(encoding="utf-8")

    for kind in ErrorKind:
        assert f"`{kind}`" in page, kind
    assert set(EXIT_STATUS) == set(ExitCode)
    # Checks that each code has a row, not the wording of its meaning
    for code in ExitCode:
        assert f"\n| {int(code)} | " in page, code


def test_validate_reads_utf8_from_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that non-ASCII schemas on standard input are read as UTF-8.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    schema = json.loads(VALID.read_text(encoding="utf-8"))
    schema["title"] = "Séquences"
    _stdin(monkeypatch, json.dumps(schema, ensure_ascii=False))

    assert main(["validate", "-"]) == 0
    assert "complies" in capsys.readouterr().out


def test_meta_schema_dash_is_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that ``--meta-schema -`` names a file, not standard input.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    (tmp_path / "-").write_text("true", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _stdin(monkeypatch, "not read")

    assert main(["validate", str(VALID), "-m", "-"]) == 0
    assert "complies with the meta-schema '-'" in capsys.readouterr().out


def test_deeply_nested_json_is_an_io_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that JSON nested too deeply to parse exits with status 3.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    path = tmp_path / "deep.json"
    path.write_text('{"a":' * 1_000_000 + "1" + "}" * 1_000_000, encoding="utf-8")

    assert main(["validate", str(path)]) == ExitCode.IO_ERROR
    assert "Error: Invalid JSON - " in capsys.readouterr().err


def test_unresolvable_meta_schema_reference_is_a_meta_schema_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a meta-schema with a reference that can't be resolved exits 3.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    meta_schema = tmp_path / "meta.schema.json"
    meta_schema.write_text(
        json.dumps({"$ref": "https://nowhere.example.org/x.json"}), encoding="utf-8"
    )

    assert main(["validate", str(VALID), "-m", str(meta_schema)]) == ExitCode.IO_ERROR
    assert "Meta-schema Error: The meta-schema references" in capsys.readouterr().err


def test_closed_standard_input_is_an_io_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that reading a closed standard input exits with status 3.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        capsys: Pytest fixture capturing standard output and error.
    """
    monkeypatch.setattr(sys, "stdin", None)

    assert main(["validate", "-"]) == ExitCode.IO_ERROR
    assert "standard input is closed" in capsys.readouterr().err


def test_schema_too_deep_to_validate_is_an_io_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a schema that parses but is too deep to validate exits 3.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        capsys: Pytest fixture capturing standard output and error.
    """
    # 300 levels parse (below the parser's limit) but are too deep to validate;
    # json.dumps can't write them on every Python version, so build the text.
    levels = 300
    deep = '{"type": "object", "properties": {"x": ' * levels
    deep += '{"type": "object"}' + "}}" * levels
    schema = json.loads(VALID.read_text(encoding="utf-8"))
    schema["properties"]["inputs"]["properties"]["deep"] = "DEEP"
    text = json.dumps(schema).replace('"DEEP"', deep)
    path = tmp_path / "deep.schema.json"
    path.write_text(text, encoding="utf-8")

    assert main(["validate", str(path)]) == ExitCode.IO_ERROR
    assert "Too deeply nested to validate" in capsys.readouterr().err
