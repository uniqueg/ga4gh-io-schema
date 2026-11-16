# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

r"""ECMA-262 regular expressions for the validation of values.

JSON Schema patterns are ECMA-262 regular expressions. jsonschema matches
them with Python's ``re`` module, which differs from ECMA-262: it can't
parse some valid patterns (e.g., ``\p{L}``), and its ``$`` also matches
before a trailing newline, so ``^[a-z]+$`` accepts ``"abc\n"``, which a
JavaScript client rejects. :data:`ValuesValidator` matches ``pattern``,
``patternProperties`` and the keys that ``additionalProperties`` checks
with an ECMA-262 engine (regress, as check-jsonschema does), so that
servers and clients agree on what a value matches.
"""

import functools
from collections.abc import Iterator
from typing import Any

import jsonschema
import regress
from jsonschema.protocols import Validator

__all__ = ["PatternError", "ValuesValidator", "search"]


class PatternError(ValueError):
    """A schema has a pattern that isn't a valid ECMA-262 regular expression."""


@functools.lru_cache(maxsize=1024)
def _compile(pattern: str) -> regress.Regex:
    """Compile an ECMA-262 regular expression, with Unicode semantics.

    Args:
        pattern: The regular expression.

    Returns:
        The compiled regular expression.

    Raises:
        PatternError: If the pattern isn't a valid ECMA-262 regular expression.
    """
    try:
        return regress.Regex(pattern, flags="u")
    except regress.RegressError as exc:
        raise PatternError(
            f"The pattern {pattern!r} isn't a valid ECMA-262 regular expression."
        ) from exc


def search(pattern: str, string: str) -> bool:
    """Check whether an ECMA-262 regular expression matches part of a string.

    Args:
        pattern: The regular expression.
        string: The string.

    Returns:
        Whether the pattern matches anywhere in the string, as ``pattern``
        of JSON Schema requires.

    Raises:
        PatternError: If the pattern isn't a valid ECMA-262 regular expression.
    """
    return _compile(pattern).find(string) is not None


def _pattern(
    validator: Validator, pattern: str, instance: Any, schema: dict[str, Any]
) -> Iterator[jsonschema.ValidationError]:
    """Validate ``pattern`` with ECMA-262 semantics.

    Args:
        validator: The validator.
        pattern: The value of the keyword.
        instance: The instance.
        schema: The schema that holds the keyword.

    Yields:
        An error if the instance is a string that doesn't match.
    """
    if validator.is_type(instance, "string") and not search(pattern, instance):
        yield jsonschema.ValidationError(f"{instance!r} does not match {pattern!r}")


def _pattern_properties(
    validator: Validator,
    pattern_properties: dict[str, Any],
    instance: Any,
    schema: dict[str, Any],
) -> Iterator[jsonschema.ValidationError]:
    """Validate ``patternProperties`` with ECMA-262 semantics.

    Args:
        validator: The validator.
        pattern_properties: The value of the keyword.
        instance: The instance.
        schema: The schema that holds the keyword.

    Yields:
        The errors of the members whose names match a pattern.
    """
    if not validator.is_type(instance, "object"):
        return
    for pattern, subschema in pattern_properties.items():
        for key, value in instance.items():
            if search(pattern, key):
                yield from validator.descend(
                    value, subschema, path=key, schema_path=pattern
                )


def _additional_properties(
    validator: Validator,
    additional: Any,
    instance: Any,
    schema: dict[str, Any],
) -> Iterator[jsonschema.ValidationError]:
    """Validate ``additionalProperties`` with ECMA-262 semantics.

    Args:
        validator: The validator.
        additional: The value of the keyword.
        instance: The instance.
        schema: The schema that holds the keyword.

    Yields:
        The errors of the members that neither ``properties`` nor
        ``patternProperties`` cover.
    """
    if not validator.is_type(instance, "object"):
        return
    properties = schema.get("properties", {})
    patterns = schema.get("patternProperties", {})
    extras = sorted(
        key
        for key in instance
        if key not in properties
        and not any(search(pattern, key) for pattern in patterns)
    )
    if validator.is_type(additional, "object"):
        for extra in extras:
            yield from validator.descend(instance[extra], additional, path=extra)
    elif not additional and extras:
        joined = ", ".join(repr(extra) for extra in extras)
        if patterns:
            verb = "does" if len(extras) == 1 else "do"
            regexes = ", ".join(repr(pattern) for pattern in sorted(patterns))
            message = f"{joined} {verb} not match any of the regexes: {regexes}"
        else:
            verb = "was" if len(extras) == 1 else "were"
            message = (
                f"Additional properties are not allowed ({joined} {verb} unexpected)"
            )
        yield jsonschema.ValidationError(message)


#: Draft 2020-12 validator that matches patterns with ECMA-262 semantics.
#: ``unevaluatedProperties`` still matches ``patternProperties`` with Python's
#: ``re``; callers turn its ``re.error`` into an error of the schema.
ValuesValidator = jsonschema.validators.extend(
    jsonschema.Draft202012Validator,
    {
        "pattern": _pattern,
        "patternProperties": _pattern_properties,
        "additionalProperties": _additional_properties,
    },
)
