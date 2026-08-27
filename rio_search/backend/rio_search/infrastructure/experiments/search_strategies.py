"""Expansion real del bloque `search:` (Fase 3, docs/rio_search_plan.md §4.1, §5): `grid`,
`random` y `tpe` (Optuna). Vive en `infrastructure` (no en `domain`, que solo declara
`SearchSpec`/`ChoiceParam`/`LogUniformParam`) porque necesita Optuna, `random.Random` y manejo
del `raw_dict` del YAML -- ninguno de los tres es una regla de dominio pura.

`apply_overrides` aplica un `dict[path_punteado, valor]` (mismo formato de path que
`infrastructure.tracking.params.flatten_params`, p. ej. `"model.params.hidden_size"`) sobre una
copia profunda del `raw_dict` original del experimento, y `ExperimentConfig.from_dict(...)`
reparsea el resultado a una config de trial completa -- evita reimplementar `dataclasses.replace`
anidado por cada campo posible del YAML (§4.1: el espacio de busqueda puede tocar `sequence`,
`model.params`, `training.optimizer`, `split.train_window`, cualquier bloque).

Los tres `TrialSampler` comparten la misma interfaz (`suggest()` -> overrides o `None` cuando se
agota; `report(objective_value)` -> feedback, no-op salvo en `tpe`) para que `RunSearch` no tenga
que conocer la estrategia concreta.
"""

from __future__ import annotations

import copy
import itertools
import random
from typing import Any, Protocol

from rio_search.domain.experiments.search_spec import ChoiceParam, LogUniformParam, ParamDomain, SearchSpec


def apply_overrides(raw_dict: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Copia profunda de `raw_dict` con cada `path.punteado -> valor` de `overrides` aplicado
    (crea los `dict` intermedios que falten)."""
    result = copy.deepcopy(raw_dict)
    for dotted_path, value in overrides.items():
        _set_nested(result, dotted_path.split("."), value)
    return result


def _set_nested(node: dict[str, Any], keys: list[str], value: Any) -> None:
    key = keys[0]
    if len(keys) == 1:
        node[key] = value
        return
    child = node.setdefault(key, {})
    if not isinstance(child, dict):
        raise ValueError(f"No se puede aplicar override en {'.'.join(keys)!r}: {key!r} no es un mapping")
    _set_nested(child, keys[1:], value)


class TrialSampler(Protocol):
    def suggest(self) -> dict[str, Any] | None:
        """Proximo `overrides` a probar, o `None` si la busqueda ya se agoto (grid con menos
        combinaciones que `n_trials`, o el propio `n_trials` alcanzado)."""
        ...

    def report(self, objective_value: float) -> None:
        """Feedback del `objective_value` (§4.1: `search.objective`) del ultimo `suggest()`.
        No-op en `grid`/`random` (no usan el resultado para elegir el siguiente); en `tpe`
        alimenta el `optuna.Study` (`ask`/`tell`)."""
        ...


class GridSampler:
    """Producto cartesiano de `space` (solo `ChoiceParam`, validado por
    `SearchSpec.__post_init__`), en el orden de declaracion del YAML. Si hay mas combinaciones
    que `n_trials`, se cortan las primeras `n_trials` (orden determinista); si hay menos, se
    agotan todas sin llegar a `n_trials` -- ninguno de los dos casos es un error, `RunSearch`
    simplemente corre los trials que `suggest()` va devolviendo hasta el primer `None`."""

    def __init__(self, space: dict[str, ParamDomain], n_trials: int) -> None:
        names = list(space)
        value_lists = [list(_choice_values(space[name])) for name in names]
        combos = itertools.islice(itertools.product(*value_lists), n_trials)
        self._queue: list[dict[str, Any]] = [dict(zip(names, combo, strict=True)) for combo in combos]
        self._index = 0

    def suggest(self) -> dict[str, Any] | None:
        if self._index >= len(self._queue):
            return None
        overrides = self._queue[self._index]
        self._index += 1
        return overrides

    def report(self, objective_value: float) -> None:
        pass


class RandomSampler:
    """Muestreo aleatorio independiente por trial, con `random.Random(seed)` propio (no
    comparte estado con el seed de `training.seed`: son ejes distintos -- uno reproduce el
    *muestreo de hiperparametros*, el otro la *inicializacion/entrenamiento* de cada trial)."""

    def __init__(self, space: dict[str, ParamDomain], n_trials: int, seed: int = 42) -> None:
        self._space = space
        self._n_trials = n_trials
        self._rng = random.Random(seed)
        self._count = 0

    def suggest(self) -> dict[str, Any] | None:
        if self._count >= self._n_trials:
            return None
        self._count += 1
        overrides: dict[str, Any] = {}
        for name, domain in self._space.items():
            if isinstance(domain, ChoiceParam):
                overrides[name] = self._rng.choice(domain.values)
            else:
                overrides[name] = _log_uniform(self._rng, domain)
        return overrides

    def report(self, objective_value: float) -> None:
        pass


class TpeSampler:
    """`optuna.samplers.TPESampler` via `ask`/`tell` (Fase 3, §5: "tpe (Optuna)"): cada
    `suggest()` pide un `optuna.Trial` nuevo al `Study` y traduce `space` a
    `suggest_categorical`/`suggest_float(log=True)`; `report()` cierra el ciclo con
    `study.tell(...)`, lo que hace que el *siguiente* `suggest()` ya use lo aprendido (a
    diferencia de grid/random, que no dependen del objetivo)."""

    def __init__(self, space: dict[str, ParamDomain], n_trials: int, maximize: bool, seed: int = 42) -> None:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        self._space = space
        self._n_trials = n_trials
        self._count = 0
        self._current: Any = None
        self._study = optuna.create_study(
            direction="maximize" if maximize else "minimize",
            sampler=optuna.samplers.TPESampler(seed=seed),
        )

    def suggest(self) -> dict[str, Any] | None:
        if self._count >= self._n_trials:
            return None
        self._count += 1
        self._current = self._study.ask()
        overrides: dict[str, Any] = {}
        for name, domain in self._space.items():
            if isinstance(domain, ChoiceParam):
                overrides[name] = self._current.suggest_categorical(name, list(domain.values))
            else:
                overrides[name] = self._current.suggest_float(name, domain.low, domain.high, log=True)
        return overrides

    def report(self, objective_value: float) -> None:
        if self._current is None:
            raise RuntimeError("TpeSampler.report() llamado antes de suggest()")
        # Optuna no acepta NaN/inf en `tell`: un trial cuyo objetivo no se pudo calcular
        # (split sin cobertura finita, §2.1) se reporta como "lo peor posible" para que el TPE
        # lo descarte sin abortar la busqueda completa.
        value = objective_value
        if value != value or value in (float("inf"), float("-inf")):  # NaN check sin importar math
            value = float("-1e9") if self._study.direction.name == "MAXIMIZE" else float("1e9")
        self._study.tell(self._current, value)
        self._current = None


def build_sampler(search: SearchSpec, seed: int = 42) -> TrialSampler:
    if search.strategy == "grid":
        return GridSampler(search.space, search.n_trials)
    if search.strategy == "random":
        return RandomSampler(search.space, search.n_trials, seed=seed)
    if search.strategy == "tpe":
        return TpeSampler(search.space, search.n_trials, maximize=search.maximize, seed=seed)
    # pragma: no cover -- SearchSpec.__post_init__ ya valida `strategy`, esto es defensivo.
    raise ValueError(f"search.strategy desconocida: {search.strategy!r}")


def _choice_values(domain: ParamDomain) -> tuple[Any, ...]:
    assert isinstance(domain, ChoiceParam)  # SearchSpec.__post_init__ ya lo valido para 'grid'
    return domain.values


def _log_uniform(rng: random.Random, domain: LogUniformParam) -> float:
    import math

    log_low, log_high = math.log(domain.low), math.log(domain.high)
    return math.exp(rng.uniform(log_low, log_high))
