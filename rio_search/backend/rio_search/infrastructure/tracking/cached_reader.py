"""`CachedTrackingReader` (Fase 4, docs/rio_search_plan.md §5): decora cualquier
`application.ports.tracking_read.TrackingReadPort` (real o falso, en tests) con
`infrastructure.persistence.sqlite_cache.SqliteReadCache` -- la UI (Fase 5) puede refrescar cada
pocos segundos sin que cada render dispare una llamada a Databricks/MLflow.

**Criterio de TTL** (documentado como pide el plan, no un numero arbitrario):

* `list_runs` (usado por las paginas Búsquedas/Run/Comparar para poblar listas): TTL corto,
  `LIST_TTL_SECONDS = 20`. Es la consulta que mas rapido "envejece" -- un job recien lanzado
  (Fase 4, `POST /api/jobs`) crea runs nuevos y la UI quiere verlos aparecer sin esperar minutos,
  pero tampoco hace falta que cada polling de 1s le pegue a Databricks: 20s es el mismo orden de
  magnitud que un poll de UI razonable (TanStack Query, Fase 5, `refetchInterval` tipico).
* `get_run` de un run **terminal** (`FINISHED`/`FAILED`/`KILLED`): ese run ya no cambia --
  MLflow no permite reabrirlo. TTL largo, `TERMINAL_TTL_SECONDS = 21600` (6h): equivale a "cache
  hasta que alguien reinicie el proceso", pero con vencimiento real por si el archivo SQLite
  sobrevive dias (no queremos servir datos de hace una semana como si fueran frescos sin razon).
  Se decide *despues* de la llamada real (se mira `status` en la respuesta), no antes.
* `get_run` de un run **activo** (`RUNNING`/`SCHEDULED`): TTL corto, `RUNNING_TTL_SECONDS = 10`
  -- la pagina Run (Fase 5) puede estar mirando un job que esta corriendo ahora mismo (lanzado
  por `POST /api/jobs`) y sus metricas/tags cambian epoch a epoch.
* `get_metric_history` (curvas de loss, panel de tiempos): TTL corto fijo,
  `METRIC_HISTORY_TTL_SECONDS = 15` -- no se sabe el estado del run sin otra llamada, y una
  curva de un run terminado tampoco cambia, asi que 15s es barato de mas (peor caso: una
  llamada extra cada 15s a un run que ya termino) contra el riesgo de mostrar una curva
  desactualizada de un run que sigue entrenando.

Ningun TTL es "para siempre" a proposito: aunque un run terminal es logicamente inmutable, un
TTL finito (por largo que sea) es la unica forma de que un bug de escritura en MLflow (o un
`run_id` reusado por error) se autocorrija sin reiniciar el backend.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from rio_search.application.ports.tracking_read import MetricPoint, RunRecord, TrackingReadPort
from rio_search.infrastructure.persistence.sqlite_cache import SqliteReadCache

LIST_TTL_SECONDS = 20.0
TERMINAL_TTL_SECONDS = 6 * 3600.0
RUNNING_TTL_SECONDS = 10.0
METRIC_HISTORY_TTL_SECONDS = 15.0

_TERMINAL_STATUSES = {"FINISHED", "FAILED", "KILLED"}


class CachedTrackingReader:
    """Implementa `TrackingReadPort`; envuelve otro `TrackingReadPort` (real o falso)."""

    def __init__(self, inner: TrackingReadPort, cache: SqliteReadCache) -> None:
        self._inner = inner
        self._cache = cache

    def list_runs(self, experiment_names: Sequence[str], max_results: int = 500) -> list[RunRecord]:
        key = f"list_runs:{','.join(sorted(experiment_names))}:{max_results}"
        cached = self._cache.get(key)
        if cached is not None:
            return [_record_from_dict(d) for d in cached]
        records = self._inner.list_runs(experiment_names, max_results=max_results)
        self._cache.set(key, [asdict(r) for r in records], ttl_seconds=LIST_TTL_SECONDS)
        return records

    def get_run(self, run_id: str) -> RunRecord | None:
        key = f"get_run:{run_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return _record_from_dict(cached) if cached != {} else None
        record = self._inner.get_run(run_id)
        if record is None:
            # No cacheamos "no existe" por mas de un instante: podria ser un run recien creado
            # que todavia no replico en el backend de tracking (race con `POST /api/jobs`).
            return None
        ttl = TERMINAL_TTL_SECONDS if record.status in _TERMINAL_STATUSES else RUNNING_TTL_SECONDS
        self._cache.set(key, asdict(record), ttl_seconds=ttl)
        return record

    def list_children(
        self, parent_run_id: str, experiment_id: str, max_results: int = 200
    ) -> list[RunRecord]:
        # Mismo TTL que `list_runs`: mismo tipo de consulta (lista de runs), misma razon.
        key = f"list_children:{parent_run_id}:{experiment_id}:{max_results}"
        cached = self._cache.get(key)
        if cached is not None:
            return [_record_from_dict(d) for d in cached]
        records = self._inner.list_children(parent_run_id, experiment_id, max_results=max_results)
        self._cache.set(key, [asdict(r) for r in records], ttl_seconds=LIST_TTL_SECONDS)
        return records

    def get_metric_history(self, run_id: str, metric_key: str) -> list[MetricPoint]:
        key = f"metric_history:{run_id}:{metric_key}"
        cached = self._cache.get(key)
        if cached is not None:
            return [MetricPoint(**d) for d in cached]
        points = self._inner.get_metric_history(run_id, metric_key)
        self._cache.set(key, [asdict(p) for p in points], ttl_seconds=METRIC_HISTORY_TTL_SECONDS)
        return points


def _record_from_dict(d: dict) -> RunRecord:
    return RunRecord(**d)
