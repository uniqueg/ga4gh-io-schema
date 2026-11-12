"""Tests of the output normaliser (:mod:`ga4gh_io_schema.outputs`)."""

import copy
import json
import time
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from test_examples import WORKFLOW_OUTPUTS

from ga4gh_io_schema import outputs as outputs_module
from ga4gh_io_schema.outputs import (
    CONFORMANT,
    NON_CONFORMANT,
    PARTIAL,
    NormalisationError,
    NormalisedOutputs,
    normalise_outputs,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
#: Test vectors of the normaliser, one directory per case.
VECTORS_DIR = Path(__file__).resolve().parent / "vectors" / "wes-outputs"
CASES = sorted(path for path in VECTORS_DIR.iterdir() if path.is_dir())
#: The cases whose run conforms to the schema.
CONFORMANT_CASES = [
    case
    for case in CASES
    if (case / "expected.json").exists()
    and json.loads((case / "expected.json").read_text(encoding="utf-8"))["conformance"]
    == "conformant"
]
WORKFLOW = json.loads(
    (DATA_DIR / "example_workflow.schema.json").read_text(encoding="utf-8")
)
BASE = "s3://example-bucket/runs/7"


def read(path: Path) -> Any:
    """Read a JSON file.

    Args:
        path: The file.

    Returns:
        The parsed document.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(case: Path) -> NormalisedOutputs:
    """Run the normaliser on a test vector.

    Args:
        case: The directory of the case.

    Returns:
        The result.
    """
    options_file = case / "options.json"
    options = read(options_file) if options_file.exists() else {}
    return normalise_outputs(
        read(case / "schema.json"),
        read(case / "run_log.json"),
        output_dir=options.get("outputDir"),
        local_dir=options.get("localDir"),
        files=options.get("files"),
    )


def summary(result: NormalisedOutputs) -> dict[str, Any]:
    """Return the parts of a result that the test vectors fix.

    Error messages and reasons are not part of the vectors, only which
    outputs and entries are reported.

    Args:
        result: The result of the normaliser.

    Returns:
        The result in the format of ``expected.json``, without description.
    """
    return {
        "conformance": result.conformance,
        "outputs": result.outputs,
        "removed": sorted(result.removed),
        "ambiguous": result.ambiguous,
        "unconverted": sorted(u.output for u in result.unconverted),
        "undeclared": sorted(result.undeclared),
        "unmatchedFiles": result.unmatched_files,
        "skippedFiles": [s.entry for s in result.skipped_files],
    }


def test_vectors_exist() -> None:
    """Test that every case has a schema, a run log and one expectation."""
    assert len(CASES) >= 10
    for case in CASES:
        assert (case / "schema.json").is_file(), case
        assert (case / "run_log.json").is_file(), case
        assert (case / "expected.json").exists() != (case / "error.json").exists()


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_vector(case: Path) -> None:
    """Test that the normaliser produces the expected result of each case.

    Args:
        case: The directory of the case.
    """
    if (case / "error.json").exists():
        with pytest.raises(NormalisationError):
            run_case(case)
        return
    expected = {
        "removed": [],
        "ambiguous": {},
        "unconverted": [],
        "undeclared": [],
        "unmatchedFiles": [],
        "skippedFiles": [],
        **read(case / "expected.json"),
    }
    del expected["description"]

    assert summary(run_case(case)) == expected


@pytest.mark.parametrize(
    "case", CONFORMANT_CASES, ids=[case.name for case in CONFORMANT_CASES]
)
def test_vector_outputs_conform_unless_reported(case: Path) -> None:
    """Test that each vector's outputs are valid unless reported otherwise.

    The expected outputs of a conformant case are valid against ``outputs``
    by plain JSON Schema validation, as clients would check them.

    Args:
        case: The directory of the case.
    """
    expected_file = case / "expected.json"
    schema = read(case / "schema.json")
    outputs = schema["properties"].get("outputs", {"additionalProperties": False})
    resource = {**outputs, "$defs": schema.get("$defs", {})}
    jsonschema.validate(read(expected_file)["outputs"], resource)


def test_to_json_reports_everything() -> None:
    """Test that the JSON form of a result has every part of the report."""
    log = {
        "state": "COMPLETE",
        "outputs": [{"file_name": "../x", "file_url": "u"}, "multiqc/r.html"],
    }

    report = normalise_outputs(WORKFLOW, log, output_dir=BASE).to_json()

    assert report == {
        "state": "COMPLETE",
        "conformance": NON_CONFORMANT,
        "outputs": {},
        "errors": [
            {
                "output": None,
                "location": "$",
                "message": "'qc_report' is a required property",
            },
            {
                "output": None,
                "location": "$",
                "message": "'alignments' is a required property",
            },
        ],
        "removed": {},
        "ambiguous": {},
        "unconverted": [],
        "undeclared": {},
        "unmatchedFiles": [f"{BASE}/multiqc/r.html"],
        "skippedFiles": [{"entry": "../x", "reason": "a '..' segment"}],
    }


def test_by_name_gives_the_example_outputs() -> None:
    """Test that outputs reported by name give the outputs of the example."""
    log = {"state": "COMPLETE", "outputs": copy.deepcopy(WORKFLOW_OUTPUTS)}

    result = normalise_outputs(WORKFLOW, log)

    assert result.outputs == WORKFLOW_OUTPUTS
    assert result.conformance == CONFORMANT
    assert result.errors == []


def test_errors_of_partial_runs_name_their_outputs() -> None:
    """Test that the errors of a partial run say which output was removed."""
    log = {"state": "SYSTEM_ERROR", "outputs": {"samples_passed_qc": -1}}

    result = normalise_outputs(WORKFLOW, log)

    assert result.conformance == PARTIAL
    assert result.removed == {"samples_passed_qc": -1}
    assert [(e.output, e.location) for e in result.errors] == [
        ("samples_passed_qc", "$.samples_passed_qc")
    ]


def test_file_values_must_be_uris() -> None:
    """Test that a file reference that is left a path fails validation.

    Values of tuples, whose shape isn't converted, stay as they are.
    """
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["pair"] = {
        "type": "array",
        "prefixItems": [{"type": "string", "x-ga4gh-file": {"kind": "file"}}],
    }
    log = {
        "state": "COMPLETE",
        "outputs": {
            "qc_report": 3,
            "alignments": ["relative.bam"],
            "pair": ["relative.txt"],
        },
    }

    result = normalise_outputs(schema, log, output_dir=BASE)

    assert result.outputs == {
        "qc_report": 3,
        "alignments": [f"{BASE}/relative.bam"],
        "pair": ["relative.txt"],
    }
    assert result.conformance == NON_CONFORMANT
    assert [(e.location, e.message) for e in result.errors] == [
        ("$.pair[0]", "'relative.txt' is not an absolute URI"),
        ("$.qc_report", "3 is not of type 'string'"),
    ]


def test_annotation_checks_only_strings() -> None:
    """Test that only strings are checked as URIs (other types fail ``type``)."""
    log = {"state": "COMPLETE", "outputs": {"qc_report": 3, "alignments": []}}

    result = normalise_outputs(WORKFLOW, log)

    assert [e.message for e in result.errors] == ["3 is not of type 'string'"]


def test_paths_without_output_dir_are_unconverted() -> None:
    """Test that a relative path can't become a URI without an output directory."""
    log = {"state": "COMPLETE", "outputs": {"qc_report": "r.html", "alignments": []}}

    result = normalise_outputs(WORKFLOW, log)

    assert [(u.output, u.reason) for u in result.unconverted] == [
        ("qc_report", "a relative path, and no output directory given")
    ]


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("/data/r.html", "a local path outside the output directory"),
        ("file://host/data/out/r.html", "a file URI of another host, or with a query"),
        ("file:///data/out/r.html?x", "a file URI of another host, or with a query"),
        ("file:///data/out/r%zz.html", "invalid percent-encoding"),
        ("file:///data/out/r%FF.html", "percent-encoding that isn't UTF-8"),
        ("/data/out/../r.html", "a '..' segment"),
        ("/data/out/a:b/r.html", "a colon in the first segment"),
    ],
)
def test_local_paths_that_cant_be_converted(value: str, reason: str) -> None:
    """Test that unsafe or foreign local paths are reported, not converted.

    Args:
        value: The reported value.
        reason: The expected reason.
    """
    log = {"state": "COMPLETE", "outputs": {"qc_report": value}}

    result = normalise_outputs(WORKFLOW, log, output_dir=BASE, local_dir="/data/out")

    assert [(u.output, u.reason) for u in result.unconverted] == [("qc_report", reason)]
    assert "qc_report" not in result.outputs


def test_file_uri_of_localhost() -> None:
    """Test that a ``file:`` URI of ``localhost`` is a local path."""
    log = {"state": "COMPLETE", "outputs": {"qc_report": "file://localhost/d/r.html"}}

    result = normalise_outputs(WORKFLOW, log, output_dir=BASE, local_dir="/d")

    assert result.outputs["qc_report"] == f"{BASE}/r.html"


def test_unresolvable_references_raise() -> None:
    """Test that a schema with a reference that can't be resolved is rejected."""
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["missing"] = {"$ref": "#/$defs/nowhere"}
    log = {"state": "EXECUTOR_ERROR", "outputs": {"missing": [None, 1]}}

    with pytest.raises(NormalisationError, match="nowhere.*resolved"):
        normalise_outputs(schema, log)


@pytest.mark.parametrize(
    "defs",
    [
        {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}},
        {"a": {"$ref": "#/$defs/nowhere"}},
    ],
    ids=["cycle", "unresolvable"],
)
def test_follow_stops_at_cycles_and_unresolvable_references(
    defs: dict[str, Any],
) -> None:
    """Test that the shape of a value is unknown behind a broken reference.

    The value is then kept as it is (validation reports the reference).

    Args:
        defs: The definitions of the schema.
    """
    schema = {"$id": "https://example.org/s", "$defs": defs}
    resolver = outputs_module._resolver(schema)

    assert outputs_module._follow({"$ref": "#/$defs/a"}, resolver)[0] is True


def test_tuples_and_boolean_schemas_keep_values() -> None:
    """Test that tuples and values of boolean schemas are kept as they are."""
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["pair"] = {"type": "array", "prefixItems": [{"type": "string"}]}
    outputs["anything"] = True
    log = {
        "state": "EXECUTOR_ERROR",
        "outputs": {"pair": ["a", None], "anything": {"x": None}},
    }

    result = normalise_outputs(schema, log)

    assert result.outputs == {"pair": ["a", None], "anything": {"x": None}}


def test_applicators_with_one_branch_besides_null_are_converted() -> None:
    """Test values of ``anyOf`` and ``oneOf``: converted by a single branch.

    Values of an ``anyOf`` or ``oneOf`` with one branch besides
    ``{"type": "null"}`` are converted by that branch; others are kept.
    """
    reference = {"type": "string", "x-ga4gh-file": {"kind": "file"}}
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["maybe"] = {"oneOf": [{"type": "null"}, reference]}
    outputs["either"] = {"anyOf": [reference, {"type": "integer"}]}
    log = {
        "state": "EXECUTOR_ERROR",
        "outputs": {"maybe": "out/a.txt", "either": "out/b.txt"},
    }

    result = normalise_outputs(schema, log, output_dir=BASE)

    assert result.outputs == {"maybe": f"{BASE}/out/a.txt"}
    assert result.removed == {"either": "out/b.txt"}


def test_names_with_special_characters() -> None:
    """Test that outputs with characters of JSON Pointers and URIs work."""
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["a/b ~%c"] = {"type": "integer"}
    log = {"state": "CANCELED", "outputs": {"a/b ~%c": 1, "samples_passed_qc": 2}}

    result = normalise_outputs(schema, log)

    assert result.outputs == {"a/b ~%c": 1, "samples_passed_qc": 2}
    assert result.errors == []


def test_schema_without_id_resolves_local_references() -> None:
    """Test that the references of a schema without ``$id`` resolve."""
    schema = copy.deepcopy(WORKFLOW)
    del schema["$id"]
    schema["$defs"] = {"count": {"type": "integer", "minimum": 0}}
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["samples_passed_qc"] = {"$ref": "#/$defs/count"}
    log = {"state": "CANCELED", "outputs": {"samples_passed_qc": -1}}

    result = normalise_outputs(schema, log)

    assert result.removed == {"samples_passed_qc": -1}


def test_weskit_shape_needs_no_declared_filesystem_output() -> None:
    """Test that ``filesystem`` and ``S3`` are outputs if the schema declares them."""
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["filesystem"] = {"type": "array", "items": {"type": "string"}}
    outputs["S3"] = {"type": "integer"}
    log = {"state": "CANCELED", "outputs": {"filesystem": ["a", "b"], "S3": 1}}

    result = normalise_outputs(schema, log)

    assert result.outputs == {"filesystem": ["a", "b"], "S3": 1}


def test_listing_strings_and_unknown_entries() -> None:
    """Test that a listing can hold strings, and other entries are skipped."""
    log = {"state": "COMPLETE", "outputs": ["multiqc/multiqc_report.html", {"x": 1}]}

    result = normalise_outputs(WORKFLOW, log, output_dir=BASE)

    assert result.outputs == {"qc_report": f"{BASE}/multiqc/multiqc_report.html"}
    assert [(s.entry, s.reason) for s in result.skipped_files] == [
        ({"x": 1}, "not a path or URI")
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"run_log": []}, "The run log must be a JSON object."),
        ({"run_log": {}}, "not in a final state"),
        ({"run_log": {"state": "QUEUED"}}, "'QUEUED'"),
        ({"output_dir": "relative/dir"}, "must be an absolute URI"),
        ({"output_dir": "s3://b/r?x=1"}, "without query or fragment"),
        ({"output_dir": "s3://b/r#f"}, "without query or fragment"),
        ({"local_dir": "relative"}, "must be absolute"),
        ({"local_dir": "/data"}, "needs the URI of the output directory"),
        ({"files": "a.txt"}, "must be an array"),
        ({"files": {"a": 1}}, "must be an array"),
        ({"files": ["a.txt"]}, "give the URI of its output directory"),
        (
            {"run_log": {"state": "COMPLETE", "outputs": "x"}},
            "must be an object, an array or null, not str",
        ),
    ],
)
def test_normalisation_errors(kwargs: dict[str, Any], message: str) -> None:
    """Test that faults of the input as a whole raise an error.

    Args:
        kwargs: Arguments that replace the defaults.
        message: Part of the expected message.
    """
    arguments: dict[str, Any] = {"schema": WORKFLOW, "run_log": {"state": "COMPLETE"}}
    arguments.update(kwargs)

    with pytest.raises(NormalisationError, match=message.replace("?", r"\?")):
        normalise_outputs(**arguments)


def test_colliding_engine_names_raise() -> None:
    """Test that two outputs with the same name in the engine are an error."""
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["samples_passed_qc"]["x-ga4gh-parameter"] = {"name": "qc_report"}

    with pytest.raises(NormalisationError, match="'qc_report' in the engine"):
        normalise_outputs(schema, {"state": "COMPLETE"})


def test_invalid_schema_raises() -> None:
    """Test that a schema that doesn't conform is rejected."""
    with pytest.raises(jsonschema.exceptions.ValidationError):
        normalise_outputs({"type": "object"}, {"state": "COMPLETE"})


def test_listed_uri_with_trailing_slash_of_output_dir() -> None:
    """Test that a trailing slash of the output directory is removed once."""
    log = {"state": "COMPLETE", "outputs": [f"{BASE}/multiqc/multiqc_report.html"]}

    result = normalise_outputs(WORKFLOW, log, output_dir=f"{BASE}/")

    assert result.outputs == {"qc_report": f"{BASE}/multiqc/multiqc_report.html"}


@pytest.mark.parametrize(
    ("name", "pattern", "secondary"),
    [
        ("sample.bam", ".bai", "sample.bam.bai"),
        ("sample.bam", "^.bai", "sample.bai"),
        ("calls.vcf.gz", ".tbi", "calls.vcf.gz.tbi"),
        ("calls.vcf.gz", "^^.idx", "calls.idx"),
        ("sample.bam", "^^.bai", "sample.bai"),
    ],
)
def test_secondary_file_names(name: str, pattern: str, secondary: str) -> None:
    """Test the names of secondary files, as in the table of File references.

    A glob that matches a file and its secondary file finds only the file.

    Args:
        name: The name of the file.
        pattern: The suffix pattern.
        secondary: The expected name of the secondary file.
    """
    schema = copy.deepcopy(WORKFLOW)
    alignments = schema["properties"]["outputs"]["properties"]["alignments"]
    alignments["x-ga4gh-output-glob"] = "*"
    alignments["items"]["x-ga4gh-file"]["secondaryFiles"] = [pattern]
    log = {"state": "CANCELED", "outputs": [name, secondary]}

    result = normalise_outputs(schema, log, output_dir=BASE)

    assert result.outputs == {"alignments": [f"{BASE}/{name}"]}
    assert result.unmatched_files == []


def test_partial_output_with_several_errors_is_removed_once() -> None:
    """Test that an output with several errors is removed, with all errors."""
    log = {"state": "CANCELED", "outputs": {"alignments": [1, 2]}}

    result = normalise_outputs(WORKFLOW, log)

    assert result.removed == {"alignments": [1, 2]}
    assert [e.location for e in result.errors] == [
        "$.alignments[0]",
        "$.alignments[1]",
    ]


def test_globs_match_in_polynomial_time() -> None:
    """Test that globs with many wildcards don't backtrack exponentially.

    Schemas are untrusted; a normaliser in a gateway must not hang on them.
    """
    schema = copy.deepcopy(WORKFLOW)
    outputs = schema["properties"]["outputs"]["properties"]
    outputs["alignments"]["x-ga4gh-output-glob"] = "/".join(
        ["**"] * 8 + ["*a" * 12 + "*b"]
    )
    deep = "/".join(["d"] * 26 + ["a" * 60])
    log = {"state": "CANCELED", "outputs": [deep]}

    started = time.monotonic()
    result = normalise_outputs(schema, log, output_dir=BASE)

    assert time.monotonic() - started < 10
    assert result.outputs == {}


@pytest.mark.parametrize(
    ("glob", "path", "matches"),
    [
        ("*", "", True),
        ("a*b*c", "aXbYc", True),
        ("a*b*c", "aXbY", False),
        ("?b", "ab", True),
        ("?b", "b", False),
        ("*.txt", ".x.txt", True),
        ("a*", "a", True),
        ("a*a", "a", False),
    ],
)
def test_segment_wildcards(glob: str, path: str, matches: bool) -> None:
    """Test ``*`` and ``?`` within a segment.

    Args:
        glob: A segment of a glob.
        path: A segment of a path.
        matches: Whether they match.
    """
    assert outputs_module._match_segment(glob, path) is matches


@pytest.mark.parametrize(
    "outputs",
    [
        {"filesystem": None, "S3": ["https://s3.example.org/x?X-Amz-Signature=S"]},
        {"S3": ["https://s3.example.org/x?X-Amz-Signature=S"]},
        {"filesystem": [], "S3": ["https://s3.example.org/x?sig=S"], "other": 1},
    ],
)
def test_presigned_urls_never_reach_the_report(outputs: dict[str, Any]) -> None:
    """Test that WESkit's ``S3`` presigned URLs are dropped in any shape.

    Args:
        outputs: ``RunLog.outputs``.
    """
    log = {"state": "COMPLETE", "outputs": outputs}

    report = normalise_outputs(WORKFLOW, log, output_dir=BASE).to_json()

    assert "Signature" not in json.dumps(report)
    assert "sig=" not in json.dumps(report)


def test_skipped_entries_hide_queries_and_sapporo_urls() -> None:
    """Test that skipped entries don't repeat queries, fragments or file URLs."""
    log = {
        "state": "COMPLETE",
        "outputs": [
            f"{BASE}/a.bam?X-Amz-Signature=S#frag",
            {"file_name": 3, "file_url": "https://x/?token=S"},
        ],
    }

    result = normalise_outputs(WORKFLOW, log, output_dir=BASE)

    assert [s.entry for s in result.skipped_files] == [
        f"{BASE}/a.bam",
        {"file_name": 3},
    ]


def test_encoded_slashes_in_listed_uris_are_skipped() -> None:
    """Test that a ``%2F`` in a listed URI doesn't hide segments in one."""
    log = {
        "state": "COMPLETE",
        "outputs": [f"{BASE}/alignments/sub%2Fdeep.bam", f"{BASE}/x%2F..%2Fy"],
    }

    result = normalise_outputs(WORKFLOW, log, output_dir=BASE)

    assert "alignments" not in result.outputs
    assert [s.reason for s in result.skipped_files] == ["an encoded '/'"] * 2


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ({"class": "File", "location": None}, "a File or Directory object"),
        ({"class": "Directory"}, "a File or Directory object"),
        ("C:\\data\\r.html", "a Windows path"),
        ("c:/data/r.html", "a Windows path"),
    ],
)
def test_values_that_arent_uris_are_unconverted(value: Any, reason: str) -> None:
    """Test that objects without location and Windows paths are reported.

    Args:
        value: The reported value.
        reason: The start of the expected reason.
    """
    log = {"state": "COMPLETE", "outputs": {"qc_report": value}}

    result = normalise_outputs(WORKFLOW, log, output_dir=BASE)

    assert "qc_report" not in result.outputs
    assert result.unconverted[0].reason.startswith(reason)


@pytest.mark.parametrize("state", [["COMPLETE"], {"s": 1}, 3])
def test_states_that_arent_strings(state: Any) -> None:
    """Test that a state that isn't a string is a normalisation error.

    Args:
        state: The state.
    """
    with pytest.raises(NormalisationError, match="not in a final state"):
        normalise_outputs(WORKFLOW, {"state": state})
