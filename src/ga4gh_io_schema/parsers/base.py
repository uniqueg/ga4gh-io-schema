# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud / GA4GH Contributors
# SPDX-License-Identifier: Apache-2.0

"""Base interface for ecosystem-specific schema parsers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AbstractParser(ABC):
    """Interface that converts an ecosystem-specific schema to a GA4GH IO Profile."""

    @abstractmethod
    def parse(self, path: Path | str) -> dict[str, Any]:
        """Read an ecosystem-specific schema from disk.

        Args:
            path: Path to the source schema file.

        Returns:
            The parsed source schema.
        """

    @abstractmethod
    def to_ga4gh(self, source: dict[str, Any]) -> dict[str, Any]:
        """Translate a parsed source schema into a GA4GH IO Profile schema.

        Args:
            source: The parsed source schema, as returned by `parse`.

        Returns:
            A new schema compliant with the GA4GH IO Profile meta-schema.
        """
