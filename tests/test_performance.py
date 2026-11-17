# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Regression tests of the time that validation against the profile takes.

Validation once took time exponential in the nesting depth of a schema
(issue #47): every level validated its subschemas several times. These
tests validate deeply nested schemas within a time budget that is generous
for linear time and far too short for exponential time. They need SIGALRM
to stop a slow run early, and are skipped where it is missing (e.g., on
Windows); ``test_packaging.py`` checks the structure that keeps validation
fast on every platform, without timing it. The translation of large values
between input values and WES ``workflow_params`` is timed the same way.
"""

import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import jsonschema
import pytest

from ga4gh_io_schema import validator
from ga4gh_io_schema.converters.snakemake import load_schema, to_ga4gh
from ga4gh_io_schema.validator import load_profile, validate_schema
from ga4gh_io_schema.wes import from_workflow_params, to_workflow_params

#: Seconds that validating one of the schemas below may take. They take
#: about 0.2 s or less each on a laptop; before the fix of issue #47, each
#: took several seconds to more than a minute.
BUDGET = 2.0

VARLOCIRAPTOR_CONFIG = (
    Path(__file__).resolve().parent
    / "data"
    / "snakemake"
    / "dna-seq-varlociraptor"
    / "config.schema.yaml"
)

pytestmark = pytest.mark.skipif(
    not hasattr(signal, "setitimer"), reason="needs SIGALRM to stop slow runs"
)


class BudgetExceededError(Exception):
    """Validation took longer than its time budget."""


@contextmanager
def time_budget(seconds: float) -> Iterator[None]:
    """Fail if the block takes longer than the budget, without waiting for it.

    Args:
        seconds: The time budget.

    Yields:
        Nothing; the block runs within the budget.

    Raises:
        BudgetExceededError: If the block took longer than the budget.
    """

    def stop(signum: int, frame: Any) -> None:
        """Stop the block when the timer fires.

        Args:
            signum: The number of the signal.
            frame: The current stack frame.

        Raises:
            BudgetExceededError: Always.
        """
        raise BudgetExceededError(f"took longer than {seconds} s")

    previous = signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    start = time.perf_counter()
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    elapsed = time.perf_counter() - start
    if elapsed > seconds:
        raise BudgetExceededError(f"took {elapsed:.2f} s, more than {seconds} s")


def io_schema(parameter: dict[str, Any]) -> dict[str, Any]:
    """Build an IO schema with one input.

    Args:
        parameter: The schema of the input.

    Returns:
        The IO schema.
    """
    return {
        "$schema": load_profile()["$id"],
        "type": "object",
        "properties": {
            "inputs": {"type": "object", "properties": {"parameter": parameter}},
        },
    }


def nested_arrays(depth: int) -> dict[str, Any]:
    """Build the schema of an array of arrays (e.g., of a CWL ``File[][]``).

    Args:
        depth: The number of nested arrays.

    Returns:
        The schema, with a file reference as the innermost items.
    """
    schema: dict[str, Any] = {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
        "x-ga4gh-parameter": {"type": "File"},
    }
    for _ in range(depth):
        schema = {
            "type": "array",
            "items": schema,
            "x-ga4gh-parameter": {"type": "File[]"},
        }
    return schema


def nested_records(depth: int, width: int) -> dict[str, Any]:
    """Build the schema of nested records (e.g., of nested CWL records).

    Args:
        depth: The number of nested records.
        width: The number of fields of each record.

    Returns:
        The schema.
    """
    schema: dict[str, Any] = {"type": "string", "x-ga4gh-hidden": False}
    for _ in range(depth):
        schema = {
            "type": "object",
            "properties": {f"field_{index}": schema for index in range(width)},
            "required": [f"field_{index}" for index in range(width)],
            "x-ga4gh-parameter": {"type": "record"},
        }
    return schema


def test_nested_arrays_validate_in_time() -> None:
    """Test that arrays nested 10 levels deep validate within the budget."""
    schema = io_schema(nested_arrays(10))

    with time_budget(BUDGET):
        validate_schema(schema)


@pytest.mark.parametrize(("depth", "width"), [(4, 3), (6, 1), (6, 2)])
def test_nested_records_validate_in_time(depth: int, width: int) -> None:
    """Test that a schema of nested records validates within the budget.

    Args:
        depth: The number of nested records.
        width: The number of fields of each record.
    """
    schema = io_schema(nested_records(depth, width))

    with time_budget(BUDGET):
        validate_schema(schema)


@pytest.mark.parametrize(("size", "budget"), [(10, BUDGET), (30, 4 * BUDGET)])
def test_groups_of_inputs_validate_in_time(size: int, budget: float) -> None:
    """Test that groups of inputs (records of scalars) validate in time.

    The shape of IO schemas that group the inputs of a large workflow,
    e.g., 30 groups of 30 inputs each (about 0.3 s on a laptop, 35 s before
    the fix of issue #47).

    Args:
        size: The number of groups, and of inputs in each group.
        budget: The time budget, larger for the larger schema.
    """
    groups = {
        f"group_{group}": nested_records(1, size) | {"title": f"Group {group}"}
        for group in range(size)
    }
    schema = io_schema({"type": "object", "properties": groups})

    with time_budget(budget):
        validate_schema(schema)


def test_nested_schemas_in_tabular_schemas_validate_in_time() -> None:
    """Test that nested schemas in tabular schemas validate within the budget.

    Each tabular schema starts a tree of its own for the Draft 2020-12 rules,
    so time stays linear within and across nested tabular schemas.
    """
    schema: dict[str, Any] = nested_records(4, 3)
    for _ in range(4):
        schema = {
            "type": "string",
            "x-ga4gh-file": {"kind": "file"},
            "x-ga4gh-tabular-schema": {
                "type": "object",
                "properties": {"column": schema, "values": nested_arrays(10)},
            },
        }

    with time_budget(BUDGET):
        validate_schema(io_schema(schema))


def test_varlociraptor_conversion_validates_in_time() -> None:
    """Test that a converted public workflow config validates in under 1 s.

    The acceptance criterion of issue #47.
    """
    schema = to_ga4gh(
        load_schema(VARLOCIRAPTOR_CONFIG.read_text(encoding="utf-8"), "config")
    ).schema
    validate_schema(schema)  # Warm-up: load the meta-schema once

    with time_budget(1.0):
        validate_schema(schema)


@pytest.mark.parametrize("with_schema_dir", [False, True])
def test_repeated_calls_reuse_the_validator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, with_schema_dir: bool
) -> None:
    """Test that repeated calls don't set up meta-schema validation again.

    Loading the profile, building the registry, checking the profile against
    Draft 2020-12 and building the validator are done once per meta-schema
    and schema directory (issue #66); before, they took about half the time
    of validating a small schema, on every call. The test counts the setup
    steps instead of timing them, so that it catches a regression of the
    cache on any machine.

    Args:
        monkeypatch: Pytest fixture for patching module attributes.
        tmp_path: Pytest fixture providing a temporary directory.
        with_schema_dir: Whether to pass a schema directory.
    """
    schema_dir = tmp_path if with_schema_dir else None
    (tmp_path / "other.json").write_text(
        '{"$id": "https://example.org/schemas/other"}', encoding="utf-8"
    )
    schema = io_schema(nested_records(2, 2))
    validate_schema(schema, schema_dir=schema_dir)  # Warm-up: set up validation
    steps = {
        name: Mock(wraps=getattr(validator, name))
        for name in [
            "build_registry",
            "load_json",
            "validator_for",
            "_build_validator",
        ]
    }
    for name, step in steps.items():
        monkeypatch.setattr(validator, name, step)

    for _ in range(3):
        validate_schema(schema, schema_dir=schema_dir)
        with pytest.raises(jsonschema.ValidationError, match="x-ga4gh-unknown"):
            validate_schema(schema | {"x-ga4gh-unknown": True}, schema_dir=schema_dir)

    assert {name: step.call_count for name, step in steps.items()} == dict.fromkeys(
        steps, 0
    )

    validate_schema(
        schema,
        {"title": "test_repeated_calls_reuse_the_validator"},
        schema_dir=schema_dir,
    )

    assert steps["_build_validator"].call_count == 1


def test_nested_schema_errors_are_found_in_time() -> None:
    """Test that an error deep in a nested schema is reported within budget."""
    inner = nested_arrays(10)
    leaf = inner
    while "items" in leaf:
        leaf = leaf["items"]
    leaf["x-ga4gh-unknown"] = True

    with (
        time_budget(BUDGET),
        pytest.raises(jsonschema.ValidationError, match="x-ga4gh-unknown"),
    ):
        validate_schema(io_schema(inner))


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        (
            {
                "type": "array",
                "if": {"items": {"type": "string"}},
                "unevaluatedItems": {"type": "string"},
            },
            ["v"] * 4000,
        ),
        (
            {
                "type": "object",
                "anyOf": [{"propertyNames": {"maxLength": 64}}],
                "unevaluatedProperties": {"type": "string"},
            },
            {f"k{index}": "v" for index in range(4000)},
        ),
    ],
)
def test_translation_of_large_containers(parameter: dict[str, Any], value: Any) -> None:
    """Test that ``unevaluated*`` next to conditions cost linear time.

    Whether ``unevaluated*`` applies to a member depends on the subschemas
    applied to the whole container; computing them once per member took
    time quadratic in the number of members (over a minute for these).

    Args:
        parameter: The schema of the input.
        value: A large value of the input.
    """
    schema = io_schema(parameter)
    schema["x-ga4gh-workflow"] = {"descriptor_type": "NFL"}

    with time_budget(BUDGET * 5):
        params = to_workflow_params(schema, {"parameter": value})
        assert from_workflow_params(schema, params) == {"parameter": value}


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
@pytest.mark.parametrize("depth", [1, 10, 40])
def test_translation_of_recursive_values(keyword: str, depth: int) -> None:
    """Test that values of recursive schemas translate in linear time.

    An input that is a string or a list of such inputs, with 10,000 strings
    (about 50 KB of ``workflow_params``) at several depths: under 1 s on a
    busy laptop at each depth, there and back; before the fix of issue #86,
    4 s at depth 1, 13 s at depth 10 and 37 s at depth 40.

    Args:
        keyword: ``anyOf`` or ``oneOf``.
        depth: The number of nested lists.
    """
    schema = io_schema({"$ref": "#/$defs/n"})
    schema["$defs"] = {
        "n": {
            keyword: [
                {"type": "string"},
                {"type": "array", "items": {"$ref": "#/$defs/n"}},
            ]
        }
    }
    schema["x-ga4gh-workflow"] = {"descriptor_type": "NFL"}
    value: list[Any] = ["x"] * 10_000
    for _ in range(depth - 1):
        value = [value]

    with time_budget(BUDGET * 2):
        params = to_workflow_params(schema, {"parameter": value})
        assert from_workflow_params(schema, params) == {"parameter": value}


def test_time_budget_stops_slow_blocks() -> None:
    """Test that the budget stops a block that runs too long, then disarms."""
    previous = signal.getsignal(signal.SIGALRM)

    with pytest.raises(BudgetExceededError, match="longer than"):
        with time_budget(0.05):
            while True:
                pass

    assert signal.getsignal(signal.SIGALRM) is previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_time_budget_fails_blocks_that_ran_too_long() -> None:
    """Test that the budget fails a block that the timer didn't interrupt."""
    with pytest.raises(BudgetExceededError, match="more than"):
        with time_budget(0.05):
            signal.setitimer(signal.ITIMER_REAL, 0)
            time.sleep(0.1)
