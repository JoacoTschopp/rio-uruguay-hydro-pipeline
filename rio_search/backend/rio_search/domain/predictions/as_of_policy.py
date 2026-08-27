"""`AsOfPolicy` (Decision #7, docs/rio_search_plan.md §3.8, paso 3): "`as_of` = ultimo dia en el
que el target es observable... loguea `data_lag_days = hoy - as_of`".

Adaptado a inferencia: acá "observable" es "todos los inputs del modelo estan disponibles tras
la imputacion permitida" (ffill acotado a `max_ffill_days`, la misma regla de entrenamiento --
`infrastructure.preprocess.imputers.apply_imputer` -- pero **sin** el relleno por mediana de
TRAIN: usar la mediana para tapar el dia mas reciente seria fabricar un pronostico a partir de
un dato que en realidad no llego, no imputar un hueco historico). Quien escanea el `pl.DataFrame`
real para encontrar esa fecha es `application.predictions.issue_daily_forecast` (domain no puede
importar Polars); esta clase es la regla pura: dada la fecha ya resuelta, computa cuan atrasada
esta respecto de "hoy". Sin dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class AsOfPolicy:
    max_ffill_days: int = 3

    def __post_init__(self) -> None:
        if self.max_ffill_days < 0:
            raise ValueError(f"max_ffill_days debe ser >= 0, recibido {self.max_ffill_days}")

    def data_lag_days(self, as_of: date, today: date) -> int:
        """`hoy - as_of` (§3.8): la cola de Gold puede tener dias con `nivel` sin `caudal`
        (§2.1), asi que `as_of` casi nunca es literalmente "hoy"."""
        lag = (today - as_of).days
        if lag < 0:
            raise ValueError(f"as_of ({as_of}) no puede ser posterior a hoy ({today})")
        return lag
