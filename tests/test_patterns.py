# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ECMA-262 patterns of :mod:`ga4gh_io_schema.patterns`."""

from typing import Any

import pytest

from ga4gh_io_schema.patterns import PatternError, ValuesValidator, search


def errors(schema: dict[str, Any], instance: Any) -> list[str]:
    """Validate an instance against a schema.

    Args:
        schema: The schema.
        instance: The instance.

    Returns:
        The messages of the errors.
    """
    return [error.message for error in ValuesValidator(schema).iter_errors(instance)]


def test_dollar_doesnt_match_before_a_trailing_newline() -> None:
    """Test that ``$`` matches only at the end, as in ECMA-262."""
    assert not search("^[a-z]+$", "abc\n")
    assert search("^[a-z]+$", "abc")


def test_unicode_property_escapes() -> None:
    r"""Test that ``\p{...}``, which Python's ``re`` can't parse, works."""
    assert search(r"^\p{L}+$", "äbc")
    assert not search(r"^\p{L}+$", "a1")


def test_invalid_patterns_raise() -> None:
    """Test that an invalid pattern raises :class:`PatternError`."""
    with pytest.raises(PatternError, match="isn't a valid ECMA-262"):
        search("(", "a")


def test_pattern_keyword() -> None:
    """Test ``pattern``: strings are matched, other types ignored."""
    schema = {"pattern": "^[a-z]+$"}

    assert errors(schema, "abc") == []
    assert errors(schema, 1) == []
    assert errors(schema, "abc\n") == ["'abc\\n' does not match '^[a-z]+$'"]


def test_pattern_properties_keyword() -> None:
    """Test ``patternProperties``: members whose names match are validated."""
    schema = {"patternProperties": {r"^\p{L}+$": {"type": "integer"}}}

    assert errors(schema, {"ä": 1, "1": "x"}) == []
    assert errors(schema, {"ä": "x"}) == ["'x' is not of type 'integer'"]
    assert errors(schema, ["ä"]) == []


@pytest.mark.parametrize(
    ("schema", "instance", "expected"),
    [
        ({"additionalProperties": False}, {"a": 1}, ["was unexpected"]),
        ({"additionalProperties": False}, {"a": 1, "b": 2}, ["were unexpected"]),
        (
            {"patternProperties": {"^x$": {}}, "additionalProperties": False},
            {"x\n": 1},
            ["'x\\n' does not match any of the regexes: '^x$'"],
        ),
        (
            {"patternProperties": {"^x$": {}}, "additionalProperties": False},
            {"x\n": 1, "y": 2},
            ["'x\\n', 'y' do not match any of the regexes: '^x$'"],
        ),
        (
            {"properties": {"a": {}}, "additionalProperties": {"type": "integer"}},
            {"a": "x", "b": "y"},
            ["'y' is not of type 'integer'"],
        ),
        ({"additionalProperties": False}, ["a"], []),
        ({"additionalProperties": True}, {"a": 1}, []),
    ],
)
def test_additional_properties_keyword(
    schema: dict[str, Any], instance: Any, expected: list[str]
) -> None:
    """Test ``additionalProperties`` with ECMA-262 matching of names.

    Args:
        schema: The schema.
        instance: The instance.
        expected: Substrings of the expected messages, in order.
    """
    messages = errors(schema, instance)

    assert len(messages) == len(expected)
    for message, part in zip(messages, expected, strict=True):
        assert part in message
