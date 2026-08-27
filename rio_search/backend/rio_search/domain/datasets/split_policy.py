"""`SplitPolicy`: `rolling_365` y `calendar_year` con `embargo_days` (Decision #4,
docs/rio_search_plan.md §3.6). Calculo puro de fechas (`datetime.date`, sin Polars ni pandas
-- regla de `domain`); quien filtra el `pl.DataFrame` real con estos rangos es
`application.datasets.build_split.BuildSplit`.

`anchor` = ultimo dia en el que el target es observable (`caudal_t_mas_{h}d` no nulo); en
`multi_output` se toma el minimo entre los horizontes (= `fecha_max - max(horizons)`), regla
estructural de R9 (la cola de nulos es por LEAD sin computar, no por huecos de datos reales
en medio de la serie -- ver `notebooks_local/gold_export/export_gold_dataset.trim_horizon_tail`).

Tabla de rangos (§3.6):

| Politica      | TEST                    | VAL                            | TRAIN                         |
| rolling_365   | (anchor-365, anchor]    | (anchor-730-e, anchor-365-e]   | [train_start, anchor-730-2e]  |
| calendar_year | año Y (ultimo completo) | año Y-1 menos embargo al final | [train_start, 31-dic-(Y-2)-e] |
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Sequence

from rio_search.domain.shared.date_range import DateRange

SplitPolicyName = Literal["rolling_365", "calendar_year"]


def compute_anchor(fecha_max: date, horizons: Sequence[int]) -> date:
    """`anchor` = `fecha_max - max(horizons)` (§3.6): el ultimo dia en el que el horizonte
    mas largo todavia tiene target observable, regla estructural (no depende de escanear
    nulidad fila por fila, ver docstring del modulo)."""
    if not horizons:
        raise ValueError("compute_anchor requiere al menos un horizonte")
    return fecha_max - timedelta(days=max(horizons))


@dataclass(frozen=True, slots=True)
class TrainWindow:
    """`start: 2008-01-01` **o** `years: 10` (§3.6) -- exactamente uno de los dos."""

    start: date | None = None
    years: int | None = None

    def __post_init__(self) -> None:
        if (self.start is None) == (self.years is None):
            raise ValueError("TrainWindow requiere exactamente uno de 'start' o 'years'")
        if self.years is not None and self.years <= 0:
            raise ValueError(f"TrainWindow.years debe ser positivo, recibido {self.years}")

    def resolve_start(self, val_start: date) -> date:
        """`years: N` = los N años previos al inicio de VAL (§3.6, 'ventana de entrenamiento')."""
        if self.start is not None:
            return self.start
        assert self.years is not None
        try:
            return val_start.replace(year=val_start.year - self.years)
        except ValueError:
            # 29-feb sin año bisiesto equivalente -> retrocede al 28-feb (caso borde de calendario).
            return val_start.replace(year=val_start.year - self.years, day=28)


@dataclass(frozen=True, slots=True)
class Split:
    """Resultado de aplicar una `SplitPolicy`: tres `DateRange` que no se solapan y respetan
    el embargo (invariante del contexto Datasets, §3.2)."""

    policy: SplitPolicyName
    anchor: date
    train: DateRange
    val: DateRange
    test: DateRange

    def __post_init__(self) -> None:
        if self.train.overlaps(self.val):
            raise ValueError(f"Split invalido: train {self.train} solapa con val {self.val}")
        if self.val.overlaps(self.test):
            raise ValueError(f"Split invalido: val {self.val} solapa con test {self.test}")
        if self.train.overlaps(self.test):
            raise ValueError(f"Split invalido: train {self.train} solapa con test {self.test}")
        if not (self.train.end < self.val.start < self.val.end < self.test.start <= self.test.end):
            raise ValueError(
                f"Split invalido: el orden temporal train < val < test no se respeta "
                f"(train={self.train}, val={self.val}, test={self.test})"
            )
        if self.test.end > self.anchor:
            raise ValueError(
                f"Split invalido: test termina ({self.test.end}) despues del anchor ({self.anchor})"
            )


@dataclass(frozen=True, slots=True)
class SplitPolicy:
    policy: SplitPolicyName
    embargo_days: int
    train_window: TrainWindow

    def __post_init__(self) -> None:
        if self.embargo_days < 0:
            raise ValueError(f"embargo_days debe ser >= 0, recibido {self.embargo_days}")
        if self.policy not in ("rolling_365", "calendar_year"):
            raise ValueError(f"Politica de split desconocida: {self.policy!r}")

    def build(self, fecha_max: date, horizons: Sequence[int]) -> Split:
        anchor = compute_anchor(fecha_max, horizons)
        if self.policy == "rolling_365":
            return self._build_rolling_365(anchor)
        return self._build_calendar_year(anchor)

    def _build_rolling_365(self, anchor: date) -> Split:
        e = self.embargo_days
        test = DateRange(anchor - timedelta(days=364), anchor)
        val_end = anchor - timedelta(days=365 + e)
        val_start = anchor - timedelta(days=730 + e) + timedelta(days=1)
        val = DateRange(val_start, val_end)
        train_end = anchor - timedelta(days=730 + 2 * e)
        train_start = self.train_window.resolve_start(val_start)
        train = DateRange(train_start, train_end)
        return Split(policy="rolling_365", anchor=anchor, train=train, val=val, test=test)

    def _build_calendar_year(self, anchor: date) -> Split:
        e = self.embargo_days
        # ultimo año calendario completo con target: si el anchor no llega al 31-dic de su
        # propio año, ese año esta incompleto y el "ultimo completo" es el anterior.
        last_complete_year = anchor.year if anchor >= date(anchor.year, 12, 31) else anchor.year - 1

        test = DateRange(date(last_complete_year, 1, 1), date(last_complete_year, 12, 31))

        val_start = date(last_complete_year - 1, 1, 1)
        val_end = date(last_complete_year - 1, 12, 31) - timedelta(days=e)
        val = DateRange(val_start, val_end)

        train_end = date(last_complete_year - 2, 12, 31) - timedelta(days=e)
        train_start = self.train_window.resolve_start(val_start)
        train = DateRange(train_start, train_end)

        return Split(policy="calendar_year", anchor=anchor, train=train, val=val, test=test)
