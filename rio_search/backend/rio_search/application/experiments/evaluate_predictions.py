"""`EvaluatePredictions` (Fase 2, docs/rio_search_plan.md §3.7): calcula un `MetricSet` por
horizonte a partir de arrays `(N, n_horizons)` de observado/predicho/referencia, usando las
funciones puras de `infrastructure.evaluation.metrics` (mismo criterio que
`application.datasets.build_feature_matrix` importando `infrastructure.preprocess.*`, Fase 1).
"""

from __future__ import annotations

import numpy as np

from rio_search.domain.experiments.metric_set import HorizonMetrics, MetricSet
from rio_search.infrastructure.evaluation import metrics


class EvaluatePredictions:
    def execute(
        self,
        split: str,
        horizons: tuple[int, ...],
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_pred_reference: np.ndarray,
    ) -> MetricSet:
        """`y_pred_reference` es la prediccion de `persistence` sobre el mismo split (misma
        alineacion de filas que `y_true`/`y_pred`): base del `skill_vs_persistence` (§3.7)."""
        horizon_metrics: list[HorizonMetrics] = []
        for j, h in enumerate(horizons):
            obs = y_true[:, j]
            sim = y_pred[:, j]
            ref = y_pred_reference[:, j]

            model_rmse = metrics.rmse(obs, sim)
            reference_rmse = metrics.rmse(obs, ref)
            peak = metrics.peak_error(obs, sim)

            values = {
                "rmse": model_rmse,
                "mae": metrics.mae(obs, sim),
                "mape": metrics.mape(obs, sim),
                "nse": metrics.nse(obs, sim),
                "kge": metrics.kge(obs, sim),
                "pbias": metrics.pbias(obs, sim),
                "r2": metrics.r_squared(obs, sim),
                "peak_mae": peak["mae"],
                "peak_bias": peak["bias"],
                "skill_vs_persistence": metrics.skill_score(model_rmse, reference_rmse),
            }
            coverage = float(np.isfinite(obs).mean()) if obs.size else 0.0
            horizon_metrics.append(HorizonMetrics(horizon=h, values=values, coverage=coverage))
        return MetricSet(split=split, horizons=tuple(horizon_metrics))
