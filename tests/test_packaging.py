# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the packaging, schema identifiers and documentation of the project."""

import re
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from ga4gh_io_schema import validator
from ga4gh_io_schema.cli.app import render_reference
from ga4gh_io_schema.validator import get_schemas_dir, load_json

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
DATA_DIR = REPO_ROOT / "tests" / "data"
SUITE_DIR = REPO_ROOT / "tests" / "conformance"
VECTORS_DIR = REPO_ROOT / "tests" / "vectors"
EXAMPLES_DIR = REPO_ROOT / "examples"
PROFILE_PATH = SCHEMAS_DIR / "ga4gh-io-profile.schema.json"
# Base of the schema `$id`s until there are releases (see docs/development.md).
SCHEMA_BASE = (
    "https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/"
)
# A schema base in text; a version segment with a placeholder (e.g., `<sha>`,
# or `$1` in a rewrite rule) is no base.
SCHEMA_URL = re.compile(r"https?://[^\"\s<>`]*?/ga4gh-io-schema/[^/\"\s<>`$]+/schemas/")
# Text files of the repository that may link to it: those at its root and
# below these directories, by suffix, and the pages that explain its move
# from `uniqueg` (the changelog's old `$id`s, the transfer page).
REPO_TEXT_DIRS = (
    ".github",
    "docs",
    "docs_hooks",
    "examples",
    "prototype",
    "schemas",
    "src",
    "tests",
)
# Installed dependencies and caches below these directories
NOT_REPO_TEXT = {"node_modules", "__pycache__"}
REPO_TEXT_SUFFIXES = {
    ".cff",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}
MOVE_EXPLAINED = {REPO_ROOT / "CHANGELOG.md", REPO_ROOT / "docs" / "transfer.md"}
# The copyright notice of the repository's own files, as in the other
# elixir-cloud-aai repositories (#99)
NOTICE = "2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>"
# A copyright tag in a header (`tag: notice`) or in `REUSE.toml`
# (`tag = "notice"`); the tag is split so that REUSE doesn't read this line
# as a header.
COPYRIGHT_TAG = re.compile(
    r"SPDX-" r'FileCopyrightText\s*(?::|=\s*")\s*(?P<notice>.*?)"?\s*$', re.M
)
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


@pytest.mark.parametrize(
    ("text", "bases"),
    [
        (f"`{SCHEMA_BASE}ga4gh-io-profile.schema.json`", [SCHEMA_BASE]),
        (
            "https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/0123abc/schemas/",
            [
                "https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/0123abc/schemas/"
            ],
        ),
        ("https://example.org/<owner>/ga4gh-io-schema/<sha>/schemas/x", []),
        (
            "https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/$1/schemas/$2",
            [],
        ),
    ],
)
def test_schema_url_pattern(text: str, bases: list[str]) -> None:
    """Test which schema URLs are checked, and which are placeholders.

    Args:
        text: The text that names a URL.
        bases: The schema bases found in it.
    """
    assert SCHEMA_URL.findall(text) == bases


def _repo_text_files() -> list[Path]:
    """Return the text files of the repository.

    Returns:
        The files at the root of the repository and below ``REPO_TEXT_DIRS``
        with a suffix of ``REPO_TEXT_SUFFIXES``, without installed
        dependencies and caches (``NOT_REPO_TEXT``).
    """
    return [
        path
        for path in [
            *REPO_ROOT.glob("*"),
            *(
                path
                for directory in REPO_TEXT_DIRS
                for path in (REPO_ROOT / directory).rglob("*")
            ),
        ]
        if path.is_file()
        and path.suffix in REPO_TEXT_SUFFIXES
        and not NOT_REPO_TEXT & set(path.parts)
    ]


def test_no_links_to_the_former_repository() -> None:
    """Test that the repository names its home, ``elixir-cloud-aai``.

    The repository moved from ``uniqueg`` to ``elixir-cloud-aai`` (#25).
    GitHub redirects the old URLs, but links name the new home. Only the
    pages that explain the move (``MOVE_EXPLAINED``) name the old one, and
    not as a link to it on GitHub (they may name the old ``$id``s).
    """
    old_name = "uniqueg" + "/ga4gh-io-schema"
    old_link = "github.com/" + old_name
    paths = _repo_text_files()
    assert {REPO_ROOT / "CITATION.cff", REPO_ROOT / "docs" / "index.md"} <= set(paths)
    offending = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in paths
        if (old_link if path in MOVE_EXPLAINED else old_name)
        in path.read_text(encoding="utf-8")
    ]
    assert offending == []


def test_schema_urls_use_the_schema_base() -> None:
    """Test that all schema URLs use the same base, ``SCHEMA_BASE``.

    There are no releases before the repository moves to GA4GH, so the
    ``$id``s name ``main``, the latest reviewed state (see "Schema
    identifiers" in ``docs/development.md``). URLs with placeholders (e.g.,
    ``<owner>``, ``<sha>``, or ``$1`` in a rewrite rule) in the
    documentation are left out.
    """
    found = set()
    for path in [
        *SCHEMAS_DIR.rglob("*.json"),
        *DATA_DIR.rglob("*.json"),
        *SUITE_DIR.rglob("*.json"),
        *VECTORS_DIR.rglob("*.json"),
        *EXAMPLES_DIR.rglob("*.json"),
        *(REPO_ROOT / "docs").rglob("*.md"),
        REPO_ROOT / "README.md",
    ]:
        text = path.read_text(encoding="utf-8")
        bases = set(SCHEMA_URL.findall(text))
        assert bases <= {SCHEMA_BASE}, (path, bases)
        found |= bases
    assert found == {SCHEMA_BASE}
    for path in SCHEMAS_DIR.rglob("*.json"):
        assert load_json(path)["$id"].startswith(SCHEMA_BASE), path


#: A row of the document history in ``docs/roadmap.md``: its version.
HISTORY_ROW = re.compile(r"\| \*\*([0-9]+\.[0-9]+\.[0-9]+)\*\* \|.*")


def latest_document_version(roadmap: str) -> str:
    """Return the latest version of the document history of the roadmap.

    Only the table of the section "Document history" counts, and each of its
    rows must name a version, so that a malformed row can't hide.

    Args:
        roadmap: The text of ``docs/roadmap.md``.

    Returns:
        The version of the last row of the table "Document history".
    """
    section = roadmap.split("\n## Document history\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    assert rows, "no rows in the document history"
    versions = []
    for row in rows:
        match = HISTORY_ROW.fullmatch(row)
        assert match, f"row without a version: {row}"
        versions.append(match[1])
    return versions[-1]


HISTORY = """# Roadmap

## Document history

| Version | Date | Author | Notes |
| ----- | ----- | ----- | ----- |
| **0.1.0** | 2026-10-10 | A | First. |
{last}

## Later

| **9.9.9** | never | A | Not in the history. |
"""


def test_latest_document_version() -> None:
    """Test that the last row of the history table names the latest version."""
    roadmap = HISTORY.format(last="| **0.2.0** | 2026-10-13 | A | Second. |")

    assert latest_document_version(roadmap) == "0.2.0"


@pytest.mark.parametrize(
    "last",
    ["| **v0.2** | 2026-10-13 | A | Second. |", "| **0.2** | x | A | Second. |"],
)
def test_latest_document_version_rejects_malformed_rows(last: str) -> None:
    """Test that a row without a version fails instead of being skipped.

    Args:
        last: The last row of the history table.
    """
    with pytest.raises(AssertionError, match="row without a version"):
        latest_document_version(HISTORY.format(last=last))


def version_matches_history(version: str, latest: str) -> bool:
    """Tell whether a package version fits the document history.

    The package version is the version of the proposal: the latest version
    of the document history, or a development version (``.devN``) of a
    higher version, for work after it.

    Args:
        version: The ``version`` of ``pyproject.toml``.
        latest: The latest version of the document history.

    Returns:
        Whether the package version is ``latest``, or a ``.devN`` of a
        version higher than ``latest``.
    """
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)(\.dev[0-9]+)?", version)
    if match is None:
        return False
    if match[4] is None:
        return version == latest
    release = tuple(int(part) for part in match.group(1, 2, 3))
    return release > tuple(int(part) for part in latest.split("."))


@pytest.mark.parametrize(
    ("version", "latest", "expected"),
    [
        ("0.3.0", "0.3.0", True),
        ("0.3.1.dev0", "0.3.0", True),
        ("0.4.0.dev2", "0.3.0", True),
        ("1.0.0.dev0", "0.3.0", True),
        ("0.2.0", "0.3.0", False),
        ("0.4.0", "0.3.0", False),
        ("0.3.0.dev0", "0.3.0", False),
        ("0.2.9.dev0", "0.3.0", False),
        ("0.3", "0.3.0", False),
        ("0.3.0rc1", "0.3.0", False),
        ("\u0660.4.0.dev0", "0.3.0", False),
    ],
)
def test_version_matches_history(version: str, latest: str, expected: bool) -> None:
    """Test which package versions fit the latest version of the history.

    Args:
        version: A package version.
        latest: The latest version of the document history.
        expected: Whether ``version`` fits ``latest``.
    """
    assert version_matches_history(version, latest) is expected


def test_package_version_is_the_proposal_version() -> None:
    """Test that the package version is the version of the proposal.

    The package version follows the document history of the roadmap (see
    ``version_matches_history``), so that the two can't drift apart. Neither
    is a release: versions 0.1.0 to 0.3.0 have no tags.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    roadmap = (REPO_ROOT / "docs" / "roadmap.md").read_text("utf-8")
    version = pyproject["project"]["version"]

    latest = latest_document_version(roadmap)

    assert version_matches_history(version, latest), (version, latest)


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


def _repo_files() -> list[Path]:
    """Return the files of the repository, whatever their directory or suffix.

    The files that git tracks (or has staged), so that installed
    dependencies, caches and local files are left out; CI checks every
    committed file.

    Returns:
        The files of the working tree.
    """
    git = shutil.which("git")
    assert git is not None, "git is needed to list the files of the repository"
    listed = subprocess.run(
        [git, "ls-files", "--cached", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return [
        path
        for path in (REPO_ROOT / name for name in listed.split("\0") if name)
        if path.is_file()
    ]


def foreign_copyright_notices(paths: list[Path]) -> list[tuple[Path, str]]:
    """Find the copyright notices that aren't the repository's ``NOTICE``.

    The ``*.license`` files next to third-party files keep the notices of
    their authors and are left out.

    Args:
        paths: The files to check.

    Returns:
        Each file and notice that differs from ``NOTICE``, in order.
    """
    return [
        (path, match.group("notice"))
        for path in paths
        if path.suffix != ".license"
        for match in COPYRIGHT_TAG.finditer(
            path.read_bytes().decode("utf-8", errors="replace")
        )
        if match.group("notice") != NOTICE
    ]


def test_copyright_notices_are_the_notice() -> None:
    """Test that the repository's own files, of any kind, name one holder.

    The file headers and the annotations of ``REUSE.toml`` all give
    ``NOTICE``, the notice of the elixir-cloud-aai repositories (#99).
    ``reuse lint`` accepts any notice, so this test catches a new file
    with another one.
    """
    paths = _repo_files()
    assert {
        REPO_ROOT / "REUSE.toml",
        REPO_ROOT / "Makefile",
        REPO_ROOT / "prototype" / "Dockerfile",
        REPO_ROOT / ".github" / "CODEOWNERS",
    } <= set(paths)
    assert foreign_copyright_notices(paths) == []
    reuse = tomllib.loads((REPO_ROOT / "REUSE.toml").read_text(encoding="utf-8"))
    annotations = {
        annotation["SPDX-FileCopyrightText"] for annotation in reuse["annotations"]
    }
    assert annotations == {NOTICE}


def test_foreign_copyright_notices(tmp_path: Path) -> None:
    """Test that other notices are found, except in ``*.license`` files.

    Files that aren't UTF-8 (e.g., images) are read too.

    Args:
        tmp_path: Pytest fixture providing a temporary directory.
    """
    tag = "SPDX-" + "FileCopyrightText"
    own = tmp_path / "own.py"
    own.write_text(f"# {tag}: {NOTICE}\n", encoding="utf-8")
    other = tmp_path / "other.js"
    other.write_text(f"// {tag}: 2026 Someone Else\n", encoding="utf-8")
    toml = tmp_path / "REUSE.toml"
    toml.write_text(f'{tag} = "2026 Someone Else"\n', encoding="utf-8")
    binary = tmp_path / "image.png"
    binary.write_bytes(b"\x89PNG\xff\xfe")
    third_party = tmp_path / "data.cwl.license"
    third_party.write_text(f"{tag}: The CWL project\n", encoding="utf-8")
    assert foreign_copyright_notices([own, other, toml, binary, third_party]) == [
        (other, "2026 Someone Else"),
        (toml, "2026 Someone Else"),
    ]


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

    Deliberately minimal: it resolves absolute and fragment-only (``#...``)
    references with JSON pointers that need no unescaping, which is all
    that the profile uses.

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
        profile["$id"] + "#",
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


#: An image reference pinned to a digest: ``name[:tag]@sha256:<64 hex digits>``.
PINNED_IMAGE = re.compile(r"\S+@sha256:[0-9a-f]{64}")


def test_prototype_image_installs_pinned_versions() -> None:
    """Test that the image of the prototype installs only pinned versions.

    Its images are pinned to digests (Dependabot updates them), and the
    package and its dependencies come from ``uv.lock``, as in CI, which
    ``.dockerignore`` lets into the build context.
    """
    dockerfile = (REPO_ROOT / "prototype" / "Dockerfile").read_text("utf-8")
    images = re.findall(r"^FROM\s+(\S+)", dockerfile, re.M)
    dockerignore = (REPO_ROOT / ".dockerignore").read_text("utf-8").splitlines()

    assert len(images) == 2
    for image in images:
        assert PINNED_IMAGE.fullmatch(image), image
    assert "uv sync --locked" in dockerfile
    assert "pip install" not in dockerfile
    assert "!uv.lock" in dockerignore


def test_prototype_image_sets_the_modes_it_copies() -> None:
    """Test that the prototype's image sets the modes of what it copies.

    A clone made with a strict umask (e.g., 077) has files that only their
    owner can read; copied as they are, the image's unprivileged user
    couldn't open them (#146). A ``chmod`` after the last ``COPY`` makes
    them readable for all and writable only by root (not ``COPY --chmod``,
    whose symbolic modes older Dockerfile frontends reject or ignore). The
    CI job "End-to-end test" runs the demo from such a checkout.
    """
    dockerfile = (REPO_ROOT / "prototype" / "Dockerfile").read_text("utf-8")
    # Instructions are case-insensitive; ADD copies files too
    instructions = [
        (name.upper(), args)
        for name, args in re.findall(r"^([A-Za-z]+)\s+(.*)$", dockerfile, re.M)
    ]
    last_copy = max(
        i for i, (name, _) in enumerate(instructions) if name in {"COPY", "ADD"}
    )
    chmod = instructions.index(("RUN", "chmod -R u=rwX,go=rX /app"))

    assert last_copy < chmod < instructions.index(("USER", "65534:65534"))
    assert not [args for name, args in instructions if "--chmod" in args]


def test_prototype_stub_runs_as_the_user_of_make() -> None:
    """Test that ``make demo`` runs the TRS stub as the user running it.

    The stub reads ``examples/`` of the checkout from a bind mount, which
    the image's unprivileged user can't read if only the owner of the
    checkout can (#146). Without ``make``, the stub stays that user.
    """
    compose = yaml.safe_load(
        (REPO_ROOT / "prototype" / "compose.yaml").read_text("utf-8")
    )
    makefile = (REPO_ROOT / "Makefile").read_text("utf-8")

    assert compose["services"]["trs-stub"]["user"] == (
        "${DEMO_UID:-65534}:${DEMO_GID:-65534}"
    )
    assert "$(or $(SUDO_UID),0)" in makefile
    assert "$(or $(SUDO_GID),0)" in makefile
    assert re.search(r"^export .*\bDEMO_UID DEMO_GID\b", makefile, re.M)


def test_read_the_docs_installs_the_lock() -> None:
    """Test that Read the Docs builds with the versions of ``uv.lock``.

    The ``docs`` job of CI installs them too, so that the previews and the
    published site are built as CI checks them.
    """
    config = yaml.safe_load((REPO_ROOT / ".readthedocs.yaml").read_text("utf-8"))
    jobs = config["build"]["jobs"]

    assert "python" not in config
    pins = {
        match
        for step in jobs["pre_install"]
        for match in re.findall(r"\buv==([0-9]+\.[0-9]+\.[0-9]+)", step)
    }
    assert any("uv sync --locked --extra docs" in step for step in jobs["install"])
    # The uv of the image (whose tag Dependabot updates) and of the lock (a
    # dev dependency, also updated by Dependabot): an older uv may not read
    # a lock written by a newer one. Not where the lock was resolved again for
    # the lowest versions (the CI job "Test (lowest dependencies)")
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text("utf-8"))
    if "resolution-mode" not in lock.get("options", {}):
        locked = {item["version"] for item in lock["package"] if item["name"] == "uv"}
        assert pins == locked, "set uv in .readthedocs.yaml to the version of uv.lock"
    dockerfile = (REPO_ROOT / "prototype" / "Dockerfile").read_text("utf-8")
    assert pins == set(
        re.findall(r"^FROM ghcr\.io/astral-sh/uv:(\S+)@", dockerfile, re.M)
    )


def test_markdown_lint_is_pinned() -> None:
    """Test that the Markdown lint runs at a pinned version.

    It runs as a pre-commit hook, pinned to the commit of a release that
    Dependabot updates. The workflows run no npm package through ``npx``
    without a version (``package@1.2.3``), which would take the newest
    release on every run and could fail unrelated pull requests.
    """
    for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        text = path.read_text("utf-8")
        for package in re.findall(r"\bnpx\s+(?:-\S+\s+)*(\S+)", text):
            # A version after the name (a scope's "@" comes first)
            assert re.search(r"[^@]@[0-9]", package), (path.name, package)
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text("utf-8")
    revisions = [
        repo["rev"]
        for repo in yaml.safe_load(config)["repos"]
        if any(hook["id"] == "markdownlint" for hook in repo["hooks"])
    ]
    assert len(revisions) == 1
    assert re.fullmatch(r"[0-9a-f]{40}", revisions[0]), revisions
