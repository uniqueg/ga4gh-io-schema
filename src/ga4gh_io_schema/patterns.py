# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

r"""ECMA-262 regular expressions for the validation of values.

JSON Schema patterns are ECMA-262 regular expressions. jsonschema matches
them with Python's ``re`` module, which differs from ECMA-262: it can't
parse some valid patterns (e.g., ``\p{L}``), and its ``$`` also matches
before a trailing newline, so ``^[a-z]+$`` accepts ``"abc\n"``, which a
JavaScript client rejects. :data:`ValuesValidator` matches ``pattern``,
``patternProperties`` and the names that ``additionalProperties`` and
``unevaluatedProperties`` check with an ECMA-262 engine in Unicode mode
(regress, as check-jsonschema does), so that servers and clients agree on
what a value matches; :func:`is_pattern` checks the ``regex`` format.

The keywords that match names follow jsonschema (4.26) and keep its error
messages; ``tests/test_patterns.py`` compares them with jsonschema's.
"""

from __future__ import annotations

import functools
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import jsonschema
import regress

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    # The type of the validators that jsonschema creates, with `descend`,
    # which `Validator` of `jsonschema.protocols` lacks. The class exists in
    # the stubs (types-jsonschema) only: a new version of the stubs may
    # rename it.
    from jsonschema.validators import _Validator as _DescendingValidator

__all__ = ["PatternError", "ValuesValidator", "is_pattern", "search"]


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


def is_pattern(instance: object) -> bool:
    """Check the ``regex`` format: a valid ECMA-262 regular expression.

    Args:
        instance: The instance; only strings are checked.

    Returns:
        Whether the instance isn't a string, or is a valid ECMA-262 regular
        expression in Unicode mode.
    """
    if not isinstance(instance, str):
        return True
    try:
        _compile(instance)
    except PatternError:
        return False
    return True


def _is_valid(validator: _DescendingValidator, instance: Any, schema: Any) -> bool:
    """Check an instance against a subschema of the validator's schema.

    Args:
        validator: The validator.
        instance: The instance.
        schema: The subschema.

    Returns:
        Whether the instance is valid.
    """
    return next(iter(validator.descend(instance, schema)), None) is None


def _plural(names: list[str], verb: str) -> str:
    """List names as jsonschema does in its messages.

    Args:
        names: The names.
        verb: ``was`` or ``does``, for a single name.

    Returns:
        The quoted names and the verb in singular or plural.
    """
    plural = {"was": "were", "does": "do"}[verb]
    joined = ", ".join(repr(name) for name in names)
    return f"{joined} {verb if len(names) == 1 else plural}"


def _pattern(
    validator: _DescendingValidator, pattern: str, instance: Any, schema: dict[str, Any]
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
    validator: _DescendingValidator,
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
    validator: _DescendingValidator,
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
        if patterns:
            regexes = ", ".join(repr(pattern) for pattern in sorted(patterns))
            message = (
                f"{_plural(extras, 'does')} not match any of the regexes: {regexes}"
            )
        else:
            message = (
                f"Additional properties are not allowed ({_plural(extras, 'was')} "
                "unexpected)"
            )
        yield jsonschema.ValidationError(message)


def _evaluated_names(
    validator: _DescendingValidator, instance: dict[str, Any], schema: Any
) -> set[str]:
    """Collect the names of members that a schema evaluates in place.

    As ``unevaluatedProperties`` requires: the members that ``properties``,
    ``patternProperties``, ``additionalProperties`` and
    ``unevaluatedProperties`` evaluate, also through ``$ref``,
    ``$dynamicRef``, ``dependentSchemas``, the valid branches of ``allOf``,
    ``anyOf`` and ``oneOf``, and ``if``/``then``/``else``.

    Args:
        validator: The validator, whose resolver is in the scope of the schema.
        instance: The object.
        schema: The schema.

    Returns:
        The names.
    """
    if not isinstance(schema, dict):
        return set()
    names: set[str] = set()
    for keyword in ("$ref", "$dynamicRef"):
        if isinstance(reference := schema.get(keyword), str):
            # `_resolver` is the only way to follow a reference in scope
            resolved = validator._resolver.lookup(reference)  # type: ignore[attr-defined]
            target = validator.evolve(
                schema=resolved.contents, _resolver=resolved.resolver
            )
            names |= _evaluated_names(target, instance, resolved.contents)
    if isinstance(properties := schema.get("properties"), dict):
        names |= properties.keys() & instance.keys()
    if isinstance(patterns := schema.get("patternProperties"), dict):
        names |= {name for name in instance if any(search(p, name) for p in patterns)}
    for keyword in ("additionalProperties", "unevaluatedProperties"):
        if keyword in schema:
            names |= {
                name
                for name, value in instance.items()
                if _is_valid(validator, value, schema[keyword])
            }
    if isinstance(dependent := schema.get("dependentSchemas"), dict):
        for name, subschema in dependent.items():
            if name in instance:
                names |= _evaluated_names(validator, instance, subschema)
    for keyword in ("allOf", "anyOf", "oneOf"):
        for subschema in schema.get(keyword, []):
            if _is_valid(validator, instance, subschema):
                names |= _evaluated_names(validator, instance, subschema)
    if "if" in schema:
        if _is_valid(validator, instance, schema["if"]):
            names |= _evaluated_names(validator, instance, schema["if"])
            names |= _evaluated_names(validator, instance, schema.get("then"))
        else:
            names |= _evaluated_names(validator, instance, schema.get("else"))
    return names


def _unevaluated_properties(
    validator: _DescendingValidator,
    unevaluated: Any,
    instance: Any,
    schema: dict[str, Any],
) -> Iterator[jsonschema.ValidationError]:
    """Validate ``unevaluatedProperties`` with ECMA-262 semantics.

    Args:
        validator: The validator.
        unevaluated: The value of the keyword.
        instance: The instance.
        schema: The schema that holds the keyword.

    Yields:
        An error if members that the schema doesn't evaluate in place fail
        the keyword's schema.
    """
    if not validator.is_type(instance, "object"):
        return
    evaluated = _evaluated_names(validator, instance, schema)
    invalid = [
        name
        for name in instance
        if name not in evaluated
        and not _is_valid(validator, instance[name], unevaluated)
    ]
    if not invalid:
        return
    if unevaluated is False:
        names = _plural(sorted(invalid), "was")
        message = f"Unevaluated properties are not allowed ({names} unexpected)"
    else:
        message = (
            "Unevaluated properties are not valid under the given schema "
            f"({_plural(invalid, 'was')} unevaluated and invalid)"
        )
    yield jsonschema.ValidationError(message)


#: Draft 2020-12 validator that matches patterns with ECMA-262 semantics.
ValuesValidator = jsonschema.validators.extend(
    jsonschema.Draft202012Validator,
    {
        "pattern": _pattern,
        "patternProperties": _pattern_properties,
        "additionalProperties": _additional_properties,
        "unevaluatedProperties": _unevaluated_properties,
    },
)
