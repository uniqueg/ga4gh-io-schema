# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the packaging, schema identifiers and documentation of the project."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from ga4gh_io_schema import validator
from ga4gh_io_schema.validator import get_schemas_dir, load_json

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
DATA_DIR = REPO_ROOT / "tests" / "data"
PROFILE_PATH = SCHEMAS_DIR / "ga4gh-io-profile.schema.json"
# Docs that show CLI usage; mkdocs build --strict checks the links of docs/.
USAGE_DOCS = [REPO_ROOT / "README.md", REPO_ROOT / "docs" / "tools" / "validator.md"]


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
    for path in [*SCHEMAS_DIR.rglob("*.json"), *DATA_DIR.glob("*.json")]:
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
    for path in DATA_DIR.glob("*.schema.json"):
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


def test_docs_use_existing_cli_options() -> None:
    """Test that the documented CLI calls only use options the CLI defines."""
    cli_help = subprocess.run(
        [sys.executable, "-m", "ga4gh_io_schema.cli", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    defined = set(re.findall(r"(?<![\w-])(--?[a-z][a-z-]*)", cli_help))
    usage = [
        line
        for doc in USAGE_DOCS
        for line in doc.read_text(encoding="utf-8").splitlines()
        if line.startswith("ga4gh-io-schema-validator ")
    ]
    assert usage
    for line in usage:
        for option in re.findall(r"(?<!\S)(--?[a-z][a-z-]*)", line):
            assert option in defined, option


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
