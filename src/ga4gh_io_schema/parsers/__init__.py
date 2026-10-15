# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Pluggable parsers translating ecosystem schemas to the GA4GH IO Profile.

To add a new ecosystem, implement `AbstractParser` and register it in `PARSERS`.
"""

from ga4gh_io_schema.parsers.base import AbstractParser
from ga4gh_io_schema.parsers.nextflow import NfSchemaParser

PARSERS: dict[str, type[AbstractParser]] = {
    "nextflow": NfSchemaParser,
}

__all__ = ["PARSERS", "AbstractParser", "NfSchemaParser", "get_parser"]


def get_parser(fmt: str) -> AbstractParser:
    """Return a parser instance for the given source format.

    Args:
        fmt: Name of the source format (e.g., 'nextflow').

    Returns:
        An instance of the parser registered for `fmt`.

    Raises:
        NotImplementedError: If no parser is registered for `fmt`.
    """
    try:
        return PARSERS[fmt]()
    except KeyError:
        supported = ", ".join(sorted(PARSERS))
        raise NotImplementedError(
            f"Unsupported format '{fmt}'. Supported formats: {supported}."
        ) from None
