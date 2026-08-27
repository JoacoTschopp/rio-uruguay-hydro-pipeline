"""Puerto de procedencia del codigo (Decision #11, docs/rio_search_plan.md §3.13)."""

from __future__ import annotations

from typing import Protocol

from rio_search.domain.experiments.code_provenance import CodeProvenance


class GitProvenancePort(Protocol):
    def capture(self) -> CodeProvenance:
        """Commit, rama, remote, dirty (scoped a `rio_search/`) y el `git diff` no commiteado."""
        ...
