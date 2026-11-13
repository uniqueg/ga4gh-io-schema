# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Regression tests of the time that validation against the profile takes.

Validation once took time exponential in the nesting depth of a schema
(issue #47): every level validated its subschemas several times. These
tests validate deeply nested schemas within a time budget that is generous
for linear time and far too short for exponential time.
"""

import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from ga4gh_io_schema.converters.snakemake import load_schema, to_ga4gh
from ga4gh_io_schema.validator import load_profile, validate_schema

#: Seconds that validating one of the schemas below may take. They take
#: less than 0.1 s each on a laptop; before the fix of issue #47, each took
#: more than a minute.
BUDGET = 2.0

VARLOCIRAPTOR = (
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


@pytest.mark.parametrize("depth", [10])
def test_nested_arrays_validate_in_time(depth: int) -> None:
    """Test that a deeply nested array schema validates within the budget.

    Args:
        depth: The number of nested arrays.
    """
    schema = io_schema(nested_arrays(depth))

    with time_budget(BUDGET):
        validate_schema(schema)


@pytest.mark.parametrize(("depth", "width"), [(4, 3), (6, 2)])
def test_nested_records_validate_in_time(depth: int, width: int) -> None:
    """Test that a schema of nested records validates within the budget.

    Args:
        depth: The number of nested records.
        width: The number of fields of each record.
    """
    schema = io_schema(nested_records(depth, width))

    with time_budget(BUDGET):
        validate_schema(schema)


def test_nested_schemas_in_tabular_schemas_validate_in_time() -> None:
    """Test that nested schemas in tabular schemas validate within the budget.

    Each level of ``x-ga4gh-tabular-schema`` in another one still doubles the
    time (see "Structure of the meta-schema" in
    ``docs/specification/meta-schema.md``); nesting
    within a tabular schema doesn't.
    """
    schema: dict[str, Any] = nested_records(4, 3)
    for _ in range(2):
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
        load_schema(VARLOCIRAPTOR.read_text(encoding="utf-8"), "config")
    ).schema
    validate_schema(schema)  # Warm-up: load the meta-schema once

    with time_budget(1.0):
        validate_schema(schema)


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
