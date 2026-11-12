# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""MkDocs hook that inserts the CLI reference, generated from the parser."""

from typing import Any

from ga4gh_io_schema.cli.app import render_reference

#: Placeholder in a page that the reference replaces.
MARKER = "<!-- cli-reference -->"


def on_page_markdown(markdown: str, **_: Any) -> str:
    """Replace the placeholder with the help of every command.

    Args:
        markdown: Markdown of the page.
        **_: Other arguments of the event (page, config, files).

    Returns:
        The Markdown, with the reference in place of the placeholder.
    """
    if MARKER not in markdown:
        return markdown
    return markdown.replace(MARKER, render_reference(level=3))
