"""``ExportThesisArtifacts`` (Fase 8, docs/rio_search_plan.md §3.11, §4.2): puente entre MLflow
y la tesis LaTeX -- ``rio-search thesis export --run <id> [--compare <id> ...]`` genera
``thesis/figures/*.pdf`` y ``thesis/tables/*.tex`` a partir de las metricas ya logueadas en
MLflow (``RunRecord.metrics``, ``TrackingReadPort`` de la Fase 4) -- sin descargar artefactos
binarios ni tocar pandas (Decision #9): la data que pasa por aca es ``dict[str, float]`` (los
mismos numeros que ya se ven en la UI de la Fase 5), nunca un DataFrame.

Cada archivo generado lleva el/los ``run_id`` de origen en un comentario LaTeX (§3.11), asi
cualquier numero o figura de la tesis se puede rastrear a la corrida exacta que lo produjo --
misma idea que el header de ``thesis/common/references.bib`` (Fase 7)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rio_search.application.ports.tracking_read import RunRecord, TrackingReadPort
from rio_search.infrastructure.thesis.latex_export import (
    ExportedFigure,
    ExportedTable,
    SeriesData,
    write_comparison_table,
    write_metric_figure,
    write_metrics_table,
)

# `{split}/{metrica}/h{NN}` (Decision de la Fase 2, `domain.experiments.metric_set.as_mlflow_metrics`).
_METRIC_KEY_RE = re.compile(r"^(?P<split>val|test)/(?P<metric>[a-z0-9_]+)/h(?P<h>\d{2})$")

# NSE y KGE son las metricas que la tesis defiende (§3.7); RMSE/MAE son las que se leen en m3/s;
# skill_vs_persistence es la vara contra la que se mide todo (§1, §3.7).
DEFAULT_TABLE_METRICS: tuple[str, ...] = ("rmse", "mae", "kge", "nse", "skill_vs_persistence")
DEFAULT_COMPARE_METRICS: tuple[str, ...] = ("kge", "rmse")
DEFAULT_FIGURE_METRIC = "kge"
DEFAULT_SPLIT = "test"  # §3.7: "TEST se reporta una vez" -- nunca se selecciona/grafica por VAL.


class ThesisExportError(ValueError):
    """``run_id`` inexistente en MLflow o sin metricas por horizonte para exportar."""


def _label_for(run: RunRecord) -> str:
    model = run.rio_search_tag("model") or run.run_name
    strategy = run.rio_search_tag("horizon_strategy")
    return f"{model} ({strategy})" if strategy else str(model)


def _to_series(run: RunRecord, split: str = DEFAULT_SPLIT) -> SeriesData:
    values: dict[tuple[str, int], float] = {}
    horizons: set[int] = set()
    for key, value in run.metrics.items():
        match = _METRIC_KEY_RE.match(key)
        if match is None or match.group("split") != split:
            continue
        h = int(match.group("h"))
        values[(match.group("metric"), h)] = value
        horizons.add(h)
    return SeriesData(
        run_id=run.run_id, label=_label_for(run), horizons=tuple(sorted(horizons)), values=values
    )


@dataclass(frozen=True, slots=True)
class ThesisExportResult:
    table: ExportedTable
    figure: ExportedFigure
    compare_table: ExportedTable | None


@dataclass(frozen=True, slots=True)
class ExportThesisArtifacts:
    reader: TrackingReadPort
    figures_dir: Path
    tables_dir: Path

    def execute(self, run_id: str, compare_run_ids: Sequence[str] = ()) -> ThesisExportResult:
        run = self.reader.get_run(run_id)
        if run is None:
            raise ThesisExportError(f"run_id {run_id!r} no existe en MLflow")

        compare_runs: list[RunRecord] = []
        for compare_id in compare_run_ids:
            record = self.reader.get_run(compare_id)
            if record is None:
                raise ThesisExportError(f"run_id {compare_id!r} (--compare) no existe en MLflow")
            compare_runs.append(record)

        primary = _to_series(run)
        if not primary.horizons:
            raise ThesisExportError(
                f"run_id {run_id!r} no tiene metricas '{DEFAULT_SPLIT}/<metrica>/hNN' logueadas "
                "(es un run padre de busqueda/trial per_horizon sin metricas propias? pasar el "
                "run_id de un trial u horizonte, no el de la busqueda)."
            )

        table = write_metrics_table(
            output_path=self.tables_dir / f"metrics_{run_id[:12]}.tex",
            series=primary,
            metrics=DEFAULT_TABLE_METRICS,
        )

        all_series = [primary] + [_to_series(r) for r in compare_runs]
        figure = write_metric_figure(
            output_stem=self.figures_dir / f"metric_vs_horizon_{run_id[:12]}",
            metric=DEFAULT_FIGURE_METRIC,
            series=all_series,
        )

        compare_table = None
        if compare_runs:
            compare_table = write_comparison_table(
                output_path=self.tables_dir / f"compare_{run_id[:12]}.tex",
                series=all_series,
                metrics=DEFAULT_COMPARE_METRICS,
            )

        return ThesisExportResult(table=table, figure=figure, compare_table=compare_table)
