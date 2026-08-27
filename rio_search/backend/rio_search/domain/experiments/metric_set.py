"""`HorizonMetrics` / `MetricSet` (Fase 2, docs/rio_search_plan.md §3.7): resultado de evaluar
un split (`val`/`test`) horizonte por horizonte. Quien calcula los valores con NumPy es
`infrastructure.evaluation.metrics` (via `application.experiments.evaluate_predictions`); este
modulo solo agrega esos numeros ya calculados en la forma jerarquica que loguea MLflow
(`test/rmse/h01` ... `test/rmse/mean`, §3.5). Sin dependencias del proyecto (regla de `domain`):
solo `math` para saltear NaN al promediar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    horizon: int
    values: dict[str, float]
    coverage: float  # fraccion de pares (obs, pred) finitos usados (§3.7: "cobertura por split")

    def get(self, metric: str) -> float:
        return self.values[metric]


@dataclass(frozen=True, slots=True)
class MetricSet:
    split: str  # "val" | "test"
    horizons: tuple[HorizonMetrics, ...]

    def horizon(self, h: int) -> HorizonMetrics:
        for hm in self.horizons:
            if hm.horizon == h:
                return hm
        raise KeyError(f"Sin metricas para horizonte {h} en split {self.split!r}")

    def metric_names(self) -> tuple[str, ...]:
        seen: list[str] = []
        for hm in self.horizons:
            for name in hm.values:
                if name not in seen:
                    seen.append(name)
        return tuple(seen)

    def mean(self, metric: str) -> float:
        """Promedio del metrico entre horizontes, salteando NaN (§3.5: `test/rmse/mean`)."""
        values = [
            hm.values[metric]
            for hm in self.horizons
            if metric in hm.values and not math.isnan(hm.values[metric])
        ]
        if not values:
            return float("nan")
        return sum(values) / len(values)

    def as_mlflow_metrics(self) -> dict[str, float]:
        """`{split}/{metrica}/h{NN}` por horizonte + `{split}/{metrica}/mean` agregada (§3.5).
        NaN se omite (MLflow no acepta NaN en `log_metrics` de forma confiable entre backends)."""
        out: dict[str, float] = {}
        for hm in self.horizons:
            for name, value in hm.values.items():
                if not math.isnan(value):
                    out[f"{self.split}/{name}/h{hm.horizon:02d}"] = value
            out[f"{self.split}/coverage/h{hm.horizon:02d}"] = hm.coverage
        for name in self.metric_names():
            mean_value = self.mean(name)
            if not math.isnan(mean_value):
                out[f"{self.split}/{name}/mean"] = mean_value
        return out
