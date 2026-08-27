"""Tests de `FeatureCatalog` (Fase 1, docs/rio_search_plan.md §3.6): parseo de dict, seleccion
de columnas por grupo, validacion explicita contra las columnas reales del dataset (falla
clara si Gold cambia de esquema), y que el YAML real (`configs/feature_groups.yaml`) cubra
exactamente las 83 columnas del manifest real sin duplicados ni huecos."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.infrastructure.datasets.feature_catalog_loader import load_feature_catalog

BACKEND_DIR = Path(__file__).resolve().parents[1]
FEATURE_GROUPS_PATH = BACKEND_DIR / "configs" / "feature_groups.yaml"
MANIFEST_PATH = BACKEND_DIR / "data" / "gold_snapshot" / "manifest.json"


def _sample_dict() -> dict:
    return {
        "groups": {
            "caudal_estado": {
                "default_on": True,
                "columns": ["caudal_actual_m3s", "caudal_lag_1d"],
            },
            "cptec_grid": {
                "default_on": True,
                "columns": ["lluvia_merge_alta_frontera_mm"],
            },
            "calidad": {
                "default_on": False,
                "columns": ["caudal_confiable"],
            },
        }
    }


def test_from_dict_builds_groups() -> None:
    catalog = FeatureCatalog.from_dict(_sample_dict())
    assert {g.name for g in catalog.groups} == {"caudal_estado", "cptec_grid", "calidad"}
    assert catalog.group("caudal_estado").default_on is True
    assert catalog.group("calidad").default_on is False


def test_default_on_groups() -> None:
    catalog = FeatureCatalog.from_dict(_sample_dict())
    assert set(catalog.default_on_groups()) == {"caudal_estado", "cptec_grid"}


def test_columns_for_dedupes_and_preserves_order() -> None:
    catalog = FeatureCatalog.from_dict(_sample_dict())
    cols = catalog.columns_for(["caudal_estado", "cptec_grid", "caudal_estado"])
    assert cols == ("caudal_actual_m3s", "caudal_lag_1d", "lluvia_merge_alta_frontera_mm")


def test_group_unknown_raises_with_available_list() -> None:
    catalog = FeatureCatalog.from_dict(_sample_dict())
    with pytest.raises(KeyError, match="caudal_estado"):
        catalog.group("no_existe")


def test_validate_against_passes_when_all_columns_present() -> None:
    catalog = FeatureCatalog.from_dict(_sample_dict())
    catalog.validate_against(
        ["caudal_actual_m3s", "caudal_lag_1d", "lluvia_merge_alta_frontera_mm", "caudal_confiable", "otra"]
    )


def test_validate_against_fails_explicitly_when_column_missing() -> None:
    catalog = FeatureCatalog.from_dict(_sample_dict())
    with pytest.raises(ValueError, match="caudal_lag_1d"):
        catalog.validate_against(["caudal_actual_m3s"])  # falta caudal_lag_1d y el resto


def test_unassigned_columns_reports_columns_outside_catalog() -> None:
    catalog = FeatureCatalog.from_dict(_sample_dict())
    unassigned = catalog.unassigned_columns(["caudal_actual_m3s", "columna_nueva_de_gold"])
    assert unassigned == ("columna_nueva_de_gold",)


def test_real_feature_groups_yaml_loads() -> None:
    catalog = load_feature_catalog(FEATURE_GROUPS_PATH)
    assert len(catalog.groups) > 0
    assert "caudal_estado" in {g.name for g in catalog.groups}


def test_real_feature_groups_yaml_validates_against_real_manifest() -> None:
    """El catalogo real no debe fallar contra el manifest real -- si Gold cambia de esquema,
    este test es la primera señal (junto con `RefreshDataset` en produccion)."""
    catalog = load_feature_catalog(FEATURE_GROUPS_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    catalog.validate_against(manifest["columns"])


def test_real_feature_groups_yaml_covers_every_real_column_exactly_once() -> None:
    """Cada una de las 83 columnas reales cae en exactamente un grupo (sin huecos, sin
    duplicados) -- documentado como invariante de diseño en el propio YAML."""
    catalog = load_feature_catalog(FEATURE_GROUPS_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    real_columns = set(manifest["columns"])

    all_catalogued: list[str] = []
    for group in catalog.groups:
        all_catalogued.extend(group.columns)

    assert len(all_catalogued) == len(set(all_catalogued)), "hay columnas duplicadas entre grupos"
    assert set(all_catalogued) == real_columns, (
        f"faltan: {real_columns - set(all_catalogued)}; sobran: {set(all_catalogued) - real_columns}"
    )
