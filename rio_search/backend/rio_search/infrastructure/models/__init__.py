"""Importar este paquete registra todos los adaptadores de modelo via `@register_model`
(Fase 2, docs/rio_search_plan.md §3.3): "el `ModelRegistry` descubre adaptadores por decorador
al importar `infrastructure.models`". Agregar un modelo nuevo = un archivo nuevo bajo
`naive/`/`sklearn/`/`torch/` + importarlo aca."""

from __future__ import annotations

from rio_search.infrastructure.models.naive import climatology as _climatology  # noqa: F401
from rio_search.infrastructure.models.naive import persistence as _persistence  # noqa: F401
from rio_search.infrastructure.models.naive import seasonal_naive as _seasonal_naive  # noqa: F401
from rio_search.infrastructure.models.sklearn import ridge as _ridge  # noqa: F401
from rio_search.infrastructure.models.torch import bilstm as _bilstm  # noqa: F401
