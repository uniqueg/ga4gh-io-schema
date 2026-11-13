# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the parts that the converters share."""

import argparse
import json

import jsonschema
import pytest

from ga4gh_io_schema import cwl
from ga4gh_io_schema.cli.app import load_commands
from ga4gh_io_schema.cli.base import ROOT
from ga4gh_io_schema.cli.convert import CONVERT, CONVERT_HELP, conversion_result
from ga4gh_io_schema.converters import common, snakemake, wdl


@pytest.mark.parametrize(
    "pointer",
    [
        (),
        ("properties", "inputs", 0, "items"),
        ("_a", "a_1", "1a", "a.b", "x-ga4gh-file", "it's", "a\\b", "ä"),
    ],
)
def test_json_path_matches_validator(pointer: tuple[str | int, ...]) -> None:
    """Test that JSON paths are rendered as the validator renders them.

    Args:
        pointer: The location.
    """
    error = jsonschema.ValidationError("x", path=pointer)

    assert common.json_path(pointer) == error.json_path


def test_child_path_extends_paths() -> None:
    """Test that a JSON path is extended by keys and indexes."""
    assert common.child_path("$.a", 0, "b", "c.d") == "$.a[0].b['c.d']"


def test_converters_share_parts() -> None:
    """Test that every converter offers the shared parts under its name."""
    for module in (snakemake, wdl):
        assert module.Note is common.Note
        assert module.Conversion is common.Conversion
        assert module.SourceError is common.SourceError
        assert module.ConversionError is common.ConversionError
        assert module.json_path is common.json_path
    assert issubclass(cwl.CwlConversionError, common.ConversionError)
    assert snakemake.MAX_VALUES == cwl.MAX_DOCUMENT_NODES == common.MAX_SOURCE_VALUES


def test_cwl_note_is_a_note() -> None:
    """Test that the notes of the CWL converter take the location first."""
    note = cwl.ConversionNote("$.a", "Left out.")

    assert isinstance(note, common.Note)
    assert note.to_dict() == {"message": "Left out.", "location": "$.a"}
    assert note.to_text("Warning") == "Warning: Left out. (at $.a)"
    assert note == cwl.ConversionNote(location="$.a", message="Left out.")
    assert note != common.Note("Left out.", "$.a")


def test_notes_as_dicts() -> None:
    """Test that notes are rendered as JSON objects, in order."""
    notes = [common.Note("A.", "$.a"), common.Note("B.", "$.b")]

    assert common.notes_as_dicts(notes) == [
        {"message": "A.", "location": "$.a"},
        {"message": "B.", "location": "$.b"},
    ]


def test_convert_group_is_declared_once() -> None:
    """Test that the converters register in one ``convert`` group."""
    load_commands()

    assert ROOT.groups["convert"] is CONVERT
    assert CONVERT.help == CONVERT_HELP
    assert {"cwl", "snakemake", "wdl"} <= set(CONVERT.commands)


@pytest.mark.parametrize("as_json", [False, True])
def test_conversion_result(as_json: bool, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the notes go to standard error, or into the JSON result.

    Args:
        as_json: Whether ``--json`` is given.
        capsys: Captured output.
    """
    conversion = common.Conversion(
        schema={"type": "object"}, notes=[common.Note("Guessed.", "$.a")]
    )

    result = conversion_result(conversion, argparse.Namespace(json=as_json))

    assert result.text == json.dumps({"type": "object"}, indent=2)
    assert result.data == {
        "schema": {"type": "object"},
        "notes": [{"message": "Guessed.", "location": "$.a"}],
    }
    expected = "" if as_json else "Note: Guessed. (at $.a)\n"
    assert capsys.readouterr().err == expected
