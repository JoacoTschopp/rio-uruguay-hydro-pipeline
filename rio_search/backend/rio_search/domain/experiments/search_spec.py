"""`SearchSpec`: bloque `search:` del YAML de experimento (Fase 3, docs/rio_search_plan.md
§4.1, §5 "Busqueda de hiperparametros"). Sin bloque `search:` una busqueda tiene un unico
trial (`ExperimentConfig.trials()`, Fase 2); con el bloque, `RunSearch` (Fase 3) expande varios
trials segun `strategy` (`grid` | `random` | `tpe`) explorando `space` -- un mapa de "path
punteado en el YAML" (p. ej. `"model.params.hidden_size"`, mismo formato que
`infrastructure.tracking.params.flatten_params`) a un dominio de valores.

Sin dependencias del proyecto (regla de `domain`): la expansion real de trials (grid
cartesiano, muestreo aleatorio, Optuna TPE) vive en
`infrastructure.experiments.search_strategies` -- este modulo solo declara la forma de datos y
la direccion de optimizacion del objetivo (metrica conocida -> mayor/menor es mejor), que es
una regla de dominio pura (no depende de Optuna ni de MLflow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_STRATEGIES = ("grid", "random", "tpe")

# Metricas de §3.7 donde un valor mas alto es mejor (kge/nse/r2 -> 1 es perfecto;
# skill_vs_persistence/coverage -> mas alto es mejor). El resto (rmse, mae, mape, pbias,
# peak_mae, peak_bias) es "mas bajo es mejor" -- el caso comun de un error.
_HIGHER_IS_BETTER = {"kge", "nse", "r2", "skill_vs_persistence", "coverage"}


@dataclass(frozen=True, slots=True)
class ChoiceParam:
    """Lista de valores discretos (`sequence.lookback_days: [30, 60, 90, 120]`, §4.1)."""

    values: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class LogUniformParam:
    """Rango continuo muestreado log-uniforme (`training.optimizer.lr:
    {log_uniform: [0.0001, 0.01]}`, §4.1) -- solo lo soportan `random`/`tpe`, no `grid`
    (un grid necesita un conjunto discreto)."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if self.low <= 0 or self.high <= 0:
            raise ValueError(f"log_uniform requiere limites positivos, recibido [{self.low}, {self.high}]")
        if self.low >= self.high:
            raise ValueError(f"log_uniform requiere low < high, recibido [{self.low}, {self.high}]")


ParamDomain = ChoiceParam | LogUniformParam


def _parse_param_domain(raw: Any) -> ParamDomain:
    if isinstance(raw, dict):
        if "log_uniform" in raw:
            low, high = raw["log_uniform"]
            return LogUniformParam(low=float(low), high=float(high))
        raise ValueError(f"Dominio de parametro desconocido: {raw!r} (esperaba 'log_uniform')")
    if isinstance(raw, (list, tuple)):
        if not raw:
            raise ValueError("Un parametro de 'search.space' con lista de valores no puede estar vacio")
        return ChoiceParam(values=tuple(raw))
    raise ValueError(f"Dominio de parametro desconocido: {raw!r} (esperaba lista o {{log_uniform: [...]}})")


@dataclass(frozen=True, slots=True)
class SearchSpec:
    strategy: str  # grid | random | tpe
    n_trials: int
    objective: str  # "{val|test}/{metrica}/mean", p. ej. "val/kge/mean" (§3.7, §4.1)
    space: dict[str, ParamDomain] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.strategy not in _STRATEGIES:
            raise ValueError(f"search.strategy desconocida: {self.strategy!r}. Disponibles: {_STRATEGIES}")
        if self.n_trials <= 0:
            raise ValueError(f"search.n_trials debe ser positivo, recibido {self.n_trials}")
        if not self.space:
            raise ValueError("search.space requiere al menos un parametro")
        parts = self.objective.split("/")
        if len(parts) != 3 or parts[0] not in ("val", "test") or parts[2] != "mean":
            raise ValueError(
                "search.objective debe tener forma '{val|test}/{metrica}/mean', recibido "
                f"{self.objective!r}"
            )
        if self.strategy == "grid":
            non_choice = [name for name, domain in self.space.items() if not isinstance(domain, ChoiceParam)]
            if non_choice:
                raise ValueError(
                    f"search.strategy=grid requiere valores discretos (listas) en 'space': "
                    f"{non_choice} no lo son (usar 'random'/'tpe' para 'log_uniform')"
                )

    @property
    def objective_split(self) -> str:
        return self.objective.split("/")[0]

    @property
    def objective_metric(self) -> str:
        return self.objective.split("/")[1]

    @property
    def maximize(self) -> bool:
        """`True` si un valor mas alto de `objective_metric` es mejor (kge/nse/r2/skill/
        coverage); `False` (minimizar) para el resto (rmse/mae/mape/pbias/peak_*)."""
        return self.objective_metric in _HIGHER_IS_BETTER

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SearchSpec | None":
        """`None` si el YAML no trae bloque `search:` (§4.1: "opcional: sin este bloque la
        busqueda tiene un unico trial")."""
        if not data:
            return None
        space = {str(k): _parse_param_domain(v) for k, v in (data.get("space") or {}).items()}
        return cls(
            strategy=str(data.get("strategy", "random")),
            n_trials=int(data.get("n_trials", 1)),
            objective=str(data.get("objective", "val/kge/mean")),
            space=space,
        )
