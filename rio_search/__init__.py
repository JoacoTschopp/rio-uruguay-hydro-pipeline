"""Rio_Search — núcleo de métricas y arnés de entrenamiento.

Alcance de este paquete hoy: las **funciones puras de evaluación** (incluida la
métrica asimétrica por régimen G-RAL) y un arnés de entrenamiento en NumPy que
permite entrenar con cualquiera de las pérdidas y comparar. No es todavía la
aplicación completa descrita en `docs/rio_search_plan.md` (Onion + DDD, PyTorch,
MLflow, UI React): eso es la Fase 0 en adelante del plan.

Lo que sí está pensado para sobrevivir a esa fase sin cambios: `metrics.py` y
`gate.py` son NumPy puro, sin estado y sin dependencias del arnés, así que se
importan tal cual desde la app cuando exista.
"""

from . import gate, metrics  # noqa: F401

__all__ = ["metrics", "gate"]
