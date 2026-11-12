# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests of the MkDocs hook that inserts the CLI reference."""

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "docs_hooks" / "cli_reference.py"
CLI_PAGE = REPO_ROOT / "docs" / "tools" / "cli.md"


def _load_hook() -> ModuleType:
    """Import the hook module from its file, as MkDocs does.

    Returns:
        The hook module.
    """
    spec = importlib.util.spec_from_file_location("cli_reference", HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_inserts_reference_into_cli_page() -> None:
    """Test that the CLI page gets the reference in place of its marker."""
    hook = _load_hook()
    markdown = CLI_PAGE.read_text(encoding="utf-8")
    assert hook.MARKER in markdown

    rendered = hook.on_page_markdown(markdown, page=None, config=None, files=None)

    assert hook.MARKER not in rendered
    assert "### `ga4gh-io-schema validate`" in rendered


def test_hook_leaves_other_pages_alone() -> None:
    """Test that pages without the marker stay as they are."""
    hook = _load_hook()

    assert hook.on_page_markdown("# Title\n", page=None) == "# Title\n"
