"""`DateRange`: rango de fechas inclusivo en ambos extremos (docs/rio_search_plan.md §3.2,
domain/shared). Sin dependencias del proyecto (regla de `domain`): solo `datetime.date`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"DateRange invalido: end ({self.end}) < start ({self.start})")

    @property
    def days(self) -> int:
        """Cantidad de dias cubiertos, extremos incluidos."""
        return (self.end - self.start).days + 1

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end

    def overlaps(self, other: DateRange) -> bool:
        return self.start <= other.end and other.start <= self.end

    def __str__(self) -> str:
        return f"{self.start.isoformat()} -> {self.end.isoformat()}"
