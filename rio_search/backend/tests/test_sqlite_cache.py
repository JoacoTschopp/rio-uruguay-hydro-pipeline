"""Tests offline de `infrastructure.persistence.sqlite_cache.SqliteReadCache` (Fase 4,
docs/rio_search_plan.md §5): TTL, sobreescritura y `invalidate` -- solo `tempfile`, sin tocar
Databricks/MLflow."""

from __future__ import annotations

import time
from pathlib import Path

from rio_search.infrastructure.persistence.sqlite_cache import SqliteReadCache


def test_set_then_get_returns_same_value(tmp_path: Path) -> None:
    cache = SqliteReadCache(tmp_path / "cache.sqlite3")
    cache.set("k", {"a": 1, "b": [1, 2, 3]}, ttl_seconds=60)
    assert cache.get("k") == {"a": 1, "b": [1, 2, 3]}


def test_missing_key_returns_none(tmp_path: Path) -> None:
    cache = SqliteReadCache(tmp_path / "cache.sqlite3")
    assert cache.get("nope") is None


def test_expired_entry_returns_none(tmp_path: Path) -> None:
    cache = SqliteReadCache(tmp_path / "cache.sqlite3")
    cache.set("k", "v", ttl_seconds=0.05)
    time.sleep(0.15)
    assert cache.get("k") is None


def test_set_overwrites_previous_value_and_ttl(tmp_path: Path) -> None:
    cache = SqliteReadCache(tmp_path / "cache.sqlite3")
    cache.set("k", "v1", ttl_seconds=60)
    cache.set("k", "v2", ttl_seconds=60)
    assert cache.get("k") == "v2"


def test_invalidate_removes_entry(tmp_path: Path) -> None:
    cache = SqliteReadCache(tmp_path / "cache.sqlite3")
    cache.set("k", "v", ttl_seconds=60)
    cache.invalidate("k")
    assert cache.get("k") is None


def test_persists_across_new_connection_to_same_file(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    SqliteReadCache(path).set("k", "v", ttl_seconds=60)
    reopened = SqliteReadCache(path)
    assert reopened.get("k") == "v"
