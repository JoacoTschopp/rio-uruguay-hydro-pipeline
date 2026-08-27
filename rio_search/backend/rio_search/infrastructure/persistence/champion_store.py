"""`SqliteChampionStore` (Fase 6, docs/rio_search_plan.md §3.5: "Copia local en SQLite para
operar sin red"). Implementa `application.ports.champion_store.ChampionStorePort` con
`sqlite3` puro (mismo criterio que `infrastructure.persistence.sqlite_cache`, Fase 4: no
depende de nada nuevo en `pyproject.toml`).

Dos tablas: `champions` (el campeon vigente por target, una fila por target, `INSERT OR
REPLACE`) y `champion_history` (append-only, auditoria de todas las promociones -- §8: "revision
de nombres, aliases y politica de versiones" necesita poder ver que se promovio antes)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rio_search.domain.predictions.champion import Champion
from rio_search.domain.shared.target_variable import TargetVariable


class SqliteChampionStore:
    """Implementa `application.ports.champion_store.ChampionStorePort`."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS champions ("
            "target TEXT PRIMARY KEY, payload TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS champion_history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT NOT NULL, "
            "promoted_at TEXT NOT NULL, payload TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def set(self, champion: Champion) -> None:
        payload = json.dumps(_to_dict(champion), ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO champions (target, payload) VALUES (?, ?) "
            "ON CONFLICT(target) DO UPDATE SET payload=excluded.payload",
            (champion.target.value, payload),
        )
        self._conn.execute(
            "INSERT INTO champion_history (target, promoted_at, payload) VALUES (?, ?, ?)",
            (champion.target.value, champion.promoted_at, payload),
        )
        self._conn.commit()

    def get(self, target: TargetVariable) -> Champion | None:
        row = self._conn.execute(
            "SELECT payload FROM champions WHERE target = ?", (target.value,)
        ).fetchone()
        if row is None:
            return None
        return _from_dict(json.loads(row[0]))

    def history(self, target: TargetVariable, max_results: int = 50) -> list[Champion]:
        rows = self._conn.execute(
            "SELECT payload FROM champion_history WHERE target = ? ORDER BY id DESC LIMIT ?",
            (target.value, max_results),
        ).fetchall()
        return [_from_dict(json.loads(row[0])) for row in rows]

    def close(self) -> None:
        self._conn.close()


def _to_dict(champion: Champion) -> dict:
    return {
        "target": champion.target.value,
        "run_id": champion.run_id,
        "model_name": champion.model_name,
        "metric_name": champion.metric_name,
        "metric_value": champion.metric_value,
        "promoted_at": champion.promoted_at,
        "registered_model_name": champion.registered_model_name,
        "registered_model_version": champion.registered_model_version,
        "note": champion.note,
    }


def _from_dict(data: dict) -> Champion:
    return Champion(
        target=TargetVariable(data["target"]),
        run_id=data["run_id"],
        model_name=data["model_name"],
        metric_name=data["metric_name"],
        metric_value=float(data["metric_value"]),
        promoted_at=data["promoted_at"],
        registered_model_name=data.get("registered_model_name"),
        registered_model_version=data.get("registered_model_version"),
        note=data.get("note"),
    )
