"""`ModelRegistry` + `@register_model` (Fase 2, docs/rio_search_plan.md §3.3): "agregar un
modelo nuevo = un archivo nuevo + un YAML de experimento". El registro es un dict de modulo
(global, deliberado: son *plugins* descubiertos por efecto secundario al importar
`infrastructure.models`, no un estado que el dominio deba inyectar) que mapea nombre -> clase
adaptadora. El dominio no importa `application.ports.model_adapter.ModelAdapterPort` (evitaria
depender "hacia afuera"): la conformidad es estructural (duck typing), no se verifica aca.

Sin dependencias del proyecto (regla de `domain`): solo `typing`.
"""

from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")

_REGISTRY: dict[str, type] = {}


def register_model(name: str) -> Callable[[type[T]], type[T]]:
    """`@register_model("persistence")` sobre una clase adaptadora (§3.3). Registrar el mismo
    nombre dos veces con clases distintas es un error de programacion (colision de plugins),
    no un caso valido a silenciar."""

    def decorator(cls: type[T]) -> type[T]:
        existing = _REGISTRY.get(name)
        if existing is not None and existing is not cls:
            raise ValueError(f"Modelo {name!r} ya registrado por {existing!r}, no se puede registrar {cls!r}")
        _REGISTRY[name] = cls
        return cls

    return decorator


class ModelRegistry:
    """Implementa estructuralmente `application.ports.model_registry.ModelRegistryPort`."""

    def get(self, name: str) -> type:
        cls = _REGISTRY.get(name)
        if cls is None:
            raise KeyError(f"Modelo desconocido: {name!r}. Disponibles: {sorted(_REGISTRY)}")
        return cls

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(_REGISTRY))
