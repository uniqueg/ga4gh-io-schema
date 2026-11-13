# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the packaging, schema identifiers and documentation of the project."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ga4gh_io_schema import validator
from ga4gh_io_schema.cli.app import render_reference
from ga4gh_io_schema.validator import get_schemas_dir, load_json

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
DATA_DIR = REPO_ROOT / "tests" / "data"
SUITE_DIR = REPO_ROOT / "tests" / "conformance"
VECTORS_DIR = REPO_ROOT / "tests" / "vectors"
PROFILE_PATH = SCHEMAS_DIR / "ga4gh-io-profile.schema.json"
# Docs that show CLI usage; mkdocs build --strict checks the links of docs/.
USAGE_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "tools" / "validator.md",
    REPO_ROOT / "docs" / "tools" / "cwl.md",
]


def test_get_schemas_dir_prefers_package_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the schemas shipped inside the package take precedence.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        monkeypatch: Pytest fixture for patching module attributes.
    """
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    monkeypatch.setattr(validator, "_PACKAGE_SCHEMAS_DIR", package_dir)
    monkeypatch.setattr(validator, "_CHECKOUT_SCHEMAS_DIR", tmp_path / "checkout")

    assert get_schemas_dir() == package_dir


def test_get_schemas_dir_falls_back_to_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a source checkout (e.g. an editable install) uses ``schemas/``.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        monkeypatch: Pytest fixture for patching module attributes.
    """
    monkeypatch.setattr(validator, "_PACKAGE_SCHEMAS_DIR", tmp_path / "missing")

    assert get_schemas_dir() == SCHEMAS_DIR


def test_schema_ids_share_one_release_tag() -> None:
    """Test that all schema URLs name the same release tag, not a branch.

    The tag must be bumped in every file at once for a new profile release
    (see the release notes in ``docs/development.md``).
    """
    tags = set()
    meta_schema_doc = REPO_ROOT / "docs" / "specification" / "meta-schema.md"
    for path in [
        *SCHEMAS_DIR.rglob("*.json"),
        *DATA_DIR.rglob("*.json"),
        *SUITE_DIR.rglob("*.json"),
        *VECTORS_DIR.rglob("*.json"),
    ]:
        text = path.read_text(encoding="utf-8")
        assert "/main/" not in text, path
        tags.update(re.findall(r"/ga4gh-io-schema/([^/]+)/schemas/", text))
    doc_text = meta_schema_doc.read_text(encoding="utf-8")
    tags.update(
        re.findall(r'"\$schema": ".*?/ga4gh-io-schema/([^/]+)/schemas/', doc_text)
    )
    assert len(tags) == 1, tags
    assert re.fullmatch(r"v\d+\.\d+\.\d+", tags.pop())


def test_examples_reference_the_meta_schema() -> None:
    """Test that the examples name the meta-schema and use placeholder ``$id``s."""
    profile_id = load_json(PROFILE_PATH)["$id"]
    valid = SUITE_DIR / "schema-documents" / "valid"
    for path in [*DATA_DIR.glob("*.schema.json"), *valid.glob("*.schema.json")]:
        schema = load_json(path)
        assert schema["$schema"] == profile_id, path
        assert schema["$id"].startswith("https://example.org/"), path


def test_readme_relative_links_resolve() -> None:
    """Test that every relative Markdown link of the README exists."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text)
    relative = [target for target in targets if "://" not in target]
    assert relative
    for target in relative:
        assert (REPO_ROOT / target).exists(), target


def _documented_calls() -> list[str]:
    """Collect the documented calls of the CLI.

    Returns:
        Every line of the usage docs that starts with the command name.
    """
    return [
        line
        for doc in USAGE_DOCS
        for line in doc.read_text(encoding="utf-8").splitlines()
        if line.startswith("ga4gh-io-schema ")
    ]


def test_docs_use_existing_cli_commands_and_options() -> None:
    """Test that the documented CLI calls use only commands and options it has."""
    reference = render_reference()
    commands = set(re.findall(r"^## `ga4gh-io-schema ([a-z -]+)`$", reference, re.M))
    defined = set(re.findall(r"(?<![\w-])(--?[a-z][a-z-]*)", reference))
    calls = _documented_calls()
    assert calls
    for line in calls:
        words = line.split()
        assert any(
            " ".join(words[1 : n + 1]) in commands for n in range(1, len(words))
        ), line
        for option in re.findall(r"(?<!\S)(--?[a-z][a-z-]*)", line):
            assert option in defined, option


def test_docs_drop_old_command() -> None:
    """Test that the usage docs no longer show ``ga4gh-io-schema-validator``."""
    for doc in USAGE_DOCS:
        assert "ga4gh-io-schema-validator" not in doc.read_text(encoding="utf-8")


def test_readme_licence_matches_reuse_metadata() -> None:
    """Test that the README states the licence its own header declares.

    ``reuse lint`` checks the headers but not the prose that describes them.
    """
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # Split the tag so that REUSE doesn't read this line as a licence header.
    header = re.search(r"SPDX-" r"License-Identifier: (\S+)", readme)
    assert header is not None
    licence_section = readme.split("## License", 1)[1].split("\n## ", 1)[0]
    readme_lines = [line for line in licence_section.splitlines() if "README" in line]
    assert readme_lines
    for line in readme_lines:
        assert header.group(1) in line, line


def test_every_vocabulary_is_registered() -> None:
    """Test that each keyword vocabulary is referenced from exactly one place.

    Keywords of every schema go into ``$defs/node/$defs/keywords``; top-level
    keywords (``workflow.schema.json``) into the branch of the top level's
    ``allOf`` that checks the ``x-ga4gh-*`` keywords.
    ``ui-widgets.schema.json`` is a value vocabulary, referenced from a keyword.
    """
    profile = load_json(PROFILE_PATH)
    keywords = profile["$defs"]["node"]["$defs"]["keywords"]["allOf"]
    every_schema = {entry["$ref"] for entry in keywords}
    check = _keyword_check(profile)
    top_level = {entry.get("$ref") for entry in check["allOf"]} - {None}
    for path in (SCHEMAS_DIR / "vocabularies").glob("*.schema.json"):
        vocabulary_id = load_json(path)["$id"]
        if path.name == "ui-widgets.schema.json":
            continue
        if path.name == "workflow.schema.json":
            assert vocabulary_id in top_level, path
            assert vocabulary_id not in every_schema, path
        else:
            assert vocabulary_id in every_schema, path
            assert vocabulary_id not in top_level, path


def _keyword_check(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the branch of a schema's ``allOf`` that checks x-ga4gh-* keywords.

    Args:
        schema: The top level of the profile, or ``$defs/node``.

    Returns:
        The only branch with ``unevaluatedProperties``.
    """
    checks = [branch for branch in schema["allOf"] if "unevaluatedProperties" in branch]
    assert len(checks) == 1, checks
    return checks[0]


def _references(
    schema: Any, base: str, documents: dict[str, Any], seen: set[str]
) -> Iterator[str]:
    """Yield every reference that a schema reaches, following references.

    Args:
        schema: The schema (or any JSON value in it).
        base: The URI of the document that holds the schema.
        documents: The documents of the profile, by URI.
        seen: The absolute references followed so far.

    Yields:
        Each absolute reference, once.
    """
    if isinstance(schema, list):
        for item in schema:
            yield from _references(item, base, documents, seen)
        return
    if not isinstance(schema, dict):
        return
    for key, value in schema.items():
        if key in ("$ref", "$dynamicRef") and isinstance(value, str):
            target = base + value if value.startswith("#") else value
            if target in seen:
                continue
            seen.add(target)
            yield target
            uri, _, pointer = target.partition("#")
            if uri in documents:
                resolved = documents[uri]
                for segment in filter(None, pointer.split("/")):
                    resolved = resolved[segment]
                yield from _references(resolved, uri, documents, seen)
        elif key != "$defs":
            yield from _references(value, base, documents, seen)


def test_checks_of_unevaluated_keywords_reach_no_nested_schema() -> None:
    """Test that no check of unevaluated keywords reaches nested schemas.

    The checks may see only the vocabularies, not ``$defs/node`` itself,
    ``$defs/subschemas``, ``$defs/schema`` or the Draft 2020-12 meta-schema:
    they would validate the nested schemas again at each level (see
    "Structure of the meta-schema" in ``docs/specification/meta-schema.md``,
    issue #47).
    """
    profile = load_json(PROFILE_PATH)
    node = profile["$defs"]["node"]
    documents = {profile["$id"]: profile, node["$id"]: node}
    for path in (SCHEMAS_DIR / "vocabularies").glob("*.schema.json"):
        vocabulary = load_json(path)
        documents[vocabulary["$id"]] = vocabulary
    forbidden = {
        "https://json-schema.org/draft/2020-12/schema",
        node["$id"] + "#",
        node["$id"] + "#/$defs/subschemas",
        node["$id"] + "#/$defs/schema",
    }
    for schema, base in [(profile, profile["$id"]), (node, node["$id"])]:
        assert "unevaluatedProperties" not in schema
        check = _keyword_check(schema)
        assert check["unevaluatedProperties"] is False
        reached = set(_references(check, base, documents, set()))
        assert node["$id"] + "#/$defs/keywords" in reached
        assert not reached & forbidden, reached & forbidden


def test_every_widget_has_one_fit_rule_and_one_group() -> None:
    """Test that the widget lists of ``ui-widgets.schema.json`` agree.

    Every widget of the vocabulary has exactly one rule in ``$defs/fit``, and
    is either an output viewer (rejected on inputs) or an input widget
    (rejected on outputs), so that a new widget can't go unchecked.
    """
    vocabulary = load_json(SCHEMAS_DIR / "vocabularies" / "ui-widgets.schema.json")
    widgets = vocabulary["anyOf"][0]["enum"]
    defs = vocabulary["$defs"]
    ruled = [
        widget
        for rule in defs["fit"]["allOf"]
        for widget in rule["if"]["properties"]["x-ga4gh-ui-widget"]["enum"]
    ]
    viewers = defs["inputParameters"]["additionalProperties"]["properties"][
        "x-ga4gh-ui-widget"
    ]["not"]["enum"]
    inputs = defs["outputParameters"]["additionalProperties"]["properties"][
        "x-ga4gh-ui-widget"
    ]["not"]["enum"]

    assert sorted(ruled) == sorted(widgets)
    assert sorted(viewers + inputs) == sorted(widgets)
    assert not set(viewers) & set(inputs)
