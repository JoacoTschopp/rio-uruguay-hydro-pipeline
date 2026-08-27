"""`flatten_params` (Fase 2, docs/rio_search_plan.md §3.5): aplana un dict anidado (la config
YAML de un experimento ya parseada, no el texto) a params de MLflow -- claves tipo
`model.hidden_size`, `sequence.lookback_days` (§3.5, ejemplo del plan). Funcion pura, testeable
offline sin tocar MLflow."""

from __future__ import annotations

from typing import Any


def flatten_params(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten_params(value, prefix=full_key))
        elif isinstance(value, (list, tuple)):
            out[full_key] = ",".join(str(v) for v in value)
        elif value is None:
            out[full_key] = ""
        else:
            out[full_key] = str(value)
    return out
