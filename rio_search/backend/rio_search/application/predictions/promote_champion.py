"""`PromoteChampion` (Fase 6, docs/rio_search_plan.md §3.5, §4.2, §5): "fija el alias de campeon
para un target (alias UC + registro local, Decision #12)". Lee el run real via `TrackingReadPort`
(Fase 4, nunca inventa metricas), fija el alias `champion_<target>` en Unity Catalog si el run
registro un modelo, y persiste el `Champion` en el store local (SQLite) para que
`IssueDailyForecast` pueda resolverlo sin red.

Nota importante (ver el reporte de cierre de esta fase, `docs/decisions.md`): el usuario todavia
no reviso `weather.ml` (§8 del plan: "revisar `weather.ml` con el usuario tras la primera
corrida registrada", Decision #12). Esta clase no asume ninguna politica de nombres/aliases mas
alla de la que ya existe (`weather.ml.rio_search_<model>`, `champion_<target>`) -- el campeon
fijado con `note=...` explicito queda documentado como provisorio, no como decision cerrada.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rio_search.application.ports.champion_store import ChampionStorePort
from rio_search.application.ports.model_alias import ModelAliasPort
from rio_search.application.ports.tracking_read import TrackingReadPort
from rio_search.domain.predictions.champion import Champion
from rio_search.domain.shared.target_variable import TargetVariable

DEFAULT_METRIC_NAME = "val/kge/mean"


class PromoteChampion:
    def __init__(
        self,
        reader: TrackingReadPort,
        store: ChampionStorePort,
        model_alias: ModelAliasPort | None = None,
    ) -> None:
        self._reader = reader
        self._store = store
        self._model_alias = model_alias

    def execute(
        self,
        run_id: str,
        target: TargetVariable,
        metric_name: str = DEFAULT_METRIC_NAME,
        note: str | None = None,
        set_alias: bool = True,
    ) -> Champion:
        run = self._reader.get_run(run_id)
        if run is None:
            raise ValueError(f"run {run_id!r} no existe en MLflow (Databricks)")

        model_name = run.rio_search_tag("model")
        if model_name is None:
            raise ValueError(
                f"run {run_id!r} no tiene el tag rio_search.model -- no parece un trial de "
                "Rio_Search (¿es un run de busqueda/padre en vez de un trial?)"
            )

        run_target = run.rio_search_tag("target")
        if run_target is not None and run_target != target.value:
            raise ValueError(
                f"run {run_id!r} tiene rio_search.target={run_target!r}, no coincide con el "
                f"target pedido {target.value!r}"
            )

        metric_value = run.metrics.get(metric_name)
        if metric_value is None:
            raise ValueError(f"run {run_id!r} no tiene la metrica {metric_name!r} en MLflow")

        registered_model_name = run.rio_search_tag("registered_model_name")
        registered_model_version = run.rio_search_tag("registered_model_version")

        champion = Champion(
            target=target,
            run_id=run_id,
            model_name=model_name,
            metric_name=metric_name,
            metric_value=float(metric_value),
            promoted_at=datetime.now(timezone.utc).isoformat(),
            registered_model_name=registered_model_name,
            registered_model_version=registered_model_version,
            note=note,
        )

        if set_alias and self._model_alias is not None and registered_model_name and registered_model_version:
            self._model_alias.set_alias(
                name=registered_model_name,
                alias=f"champion_{target.value}",
                version=registered_model_version,
            )

        self._store.set(champion)
        return champion
