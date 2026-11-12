# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the packaging, schema identifiers and documentation of the project."""

import re
import tomllib
from pathlib import Path

import pytest

from ga4gh_io_schema import validator
from ga4gh_io_schema.validator import get_schemas_dir, load_json

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
DATA_DIR = REPO_ROOT / "tests" / "data"
PROFILE_PATH = SCHEMAS_DIR / "ga4gh-io-profile.schema.json"
DOCS = [REPO_ROOT / "README.md", REPO_ROOT / "docs" / "proposal_ga4gh_io_schema.md"]


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
    monkeypatch.setattr(validator, "PACKAGE_SCHEMAS_DIR", package_dir)
    monkeypatch.setattr(validator, "CHECKOUT_SCHEMAS_DIR", tmp_path / "checkout")

    assert get_schemas_dir() == package_dir


def test_get_schemas_dir_falls_back_to_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that a source checkout (e.g. an editable install) uses ``schemas/``.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
        monkeypatch: Pytest fixture for patching module attributes.
    """
    monkeypatch.setattr(validator, "PACKAGE_SCHEMAS_DIR", tmp_path / "missing")

    assert get_schemas_dir() == SCHEMAS_DIR


def test_pyproject_ships_schemas_in_wheel() -> None:
    """Test that the wheel maps the repository schemas into the package."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as file:
        pyproject = tomllib.load(file)

    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]
    assert force_include == {"schemas": "ga4gh_io_schema/schemas"}


def test_meta_schema_ids_are_versioned() -> None:
    """Test that no schema identifier points to a moving branch."""
    for path in SCHEMAS_DIR.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "/main/" not in text, path


def test_examples_reference_the_meta_schema() -> None:
    """Test that the examples name the meta-schema and use placeholder ``$id``s."""
    profile_id = load_json(PROFILE_PATH)["$id"]
    for path in DATA_DIR.glob("*.schema.json"):
        schema = load_json(path)
        assert schema["$schema"] == profile_id, path
        assert schema["$id"].startswith("https://example.org/"), path


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_relative_links_resolve(doc: Path) -> None:
    """Test that every relative Markdown link points to an existing file.

    Args:
        doc: Markdown file to check.
    """
    text = doc.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text)
    relative = [target for target in targets if "://" not in target]
    assert relative, doc
    for target in relative:
        assert (doc.parent / target).exists(), f"{doc.name}: {target}"


def test_readme_uses_existing_cli_options() -> None:
    """Test that the README only shows options the CLI defines."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    cli = (REPO_ROOT / "src" / "ga4gh_io_schema" / "cli.py").read_text(encoding="utf-8")
    usage = [
        line for line in readme.splitlines() if "ga4gh-io-schema-validator " in line
    ]
    assert usage
    for line in usage:
        for option in re.findall(r"(?<!\S)(--?[a-z][a-z-]*)", line):
            assert f'"{option}"' in cli, option


def test_readme_licence_matches_reuse_metadata() -> None:
    """Test that the README states the licence its own header declares."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # Split the tag so that REUSE doesn't read this line as a licence header.
    header = re.search(r"SPDX-" r"License-Identifier: (\S+)", readme)
    assert header is not None
    licence_section = readme.split("## License", 1)[1].split("\n## ", 1)[0]
    readme_lines = [line for line in licence_section.splitlines() if "README" in line]
    assert readme_lines
    for line in readme_lines:
        assert header.group(1) in line, line
