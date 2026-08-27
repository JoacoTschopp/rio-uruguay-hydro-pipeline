"""Carga `configs/feature_groups.yaml` a un `FeatureCatalog` (Fase 1, docs/rio_search_plan.md
§3.6). El parseo del YAML vive en `infrastructure` (el dominio no toca el filesystem);
`FeatureCatalog.from_dict` (dominio, puro) hace el resto."""

from __future__ import annotations

from pathlib import Path

import yaml

from rio_search.domain.datasets.feature_catalog import FeatureCatalog


def load_feature_catalog(path: Path) -> FeatureCatalog:
    if not path.exists():
        raise FileNotFoundError(
            f"No existe el catalogo de features: {path}. Se esperaba configs/feature_groups.yaml (§3.6)."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return FeatureCatalog.from_dict(data)
