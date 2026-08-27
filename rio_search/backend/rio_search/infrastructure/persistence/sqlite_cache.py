"""Cache de lectura generico en SQLite (Fase 4, docs/rio_search_plan.md §5: "cliente MLflow con
cache de lectura en SQLite -- la UI no debe pegarle a Databricks en cada render").

`stdlib sqlite3` unicamente (nada nuevo en `pyproject.toml`): una tabla `(key, value, cached_at,
ttl_seconds)`, valor serializado a JSON por quien llama (este modulo no sabe que es un `RunRecord`
ni un `MetricPoint`, solo guarda texto -- lo mismo que ya hace `infrastructure.persistence` para
el resto de la app segun §3.2). `get()` devuelve `None` si la clave no esta o si vencio el TTL
(no borra la fila vieja: `set()` la pisa la proxima vez que haga falta, evita un `DELETE` extra en
el camino caliente de lectura).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SqliteReadCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, cached_at REAL NOT NULL, ttl_seconds REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    def get(self, key: str) -> Any | None:
        row = self._conn.execute(
            "SELECT value, cached_at, ttl_seconds FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, cached_at, ttl_seconds = row
        if time.time() - cached_at > ttl_seconds:
            return None
        return json.loads(value)

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._conn.execute(
            "INSERT INTO cache (key, value, cached_at, ttl_seconds) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, cached_at=excluded.cached_at, "
            "ttl_seconds=excluded.ttl_seconds",
            (key, json.dumps(value), time.time(), ttl_seconds),
        )
        self._conn.commit()

    def invalidate(self, key: str) -> None:
        self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
