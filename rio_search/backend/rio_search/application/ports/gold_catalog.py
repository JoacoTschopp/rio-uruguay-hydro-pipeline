"""Puerto de metadatos de Gold via Statement API (docs/rio_search_plan.md §3.6, paso 1)."""

from __future__ import annotations

from typing import Protocol


class GoldCatalogPort(Protocol):
    def current_delta_version(self, table: str) -> int:
        """`DESCRIBE HISTORY <table> LIMIT 1` -> version Delta actual."""
        ...
