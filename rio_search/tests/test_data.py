"""Tests del cargador de datos, con foco en la guarda de esquema.

La guarda existe porque un snapshot viejo falla en silencio: carga, entrena y
devuelve números — calculados contra valores de caudal que Gold ya corrigió
(Decisión 039: cambió el 85,5 % de los días de 2019-2026).
"""

from __future__ import annotations

import sys
from pathlib import Path

import hashlib
import json
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as D


def _df_minimo(con_nivel: bool):
    cols = {"fecha": pd.date_range("2020-01-01", periods=5),
            "caudal_actual_m3s": np.arange(5.0)}
    if con_nivel:
        cols["nivel_rio_t_mas_1d"] = np.arange(5.0)
    return pd.DataFrame(cols)


def test_guarda_rechaza_snapshot_con_nivel():
    """Un snapshot con columnas de nivel es anterior a la Decisión 040."""
    try:
        D._assert_schema_vigente(_df_minimo(True), Path("viejo.parquet"))
    except ValueError as exc:
        assert "Decisión 040" in str(exc) and "039" in str(exc)
        return
    raise AssertionError("debería haber rechazado el snapshot viejo")


def test_guarda_acepta_snapshot_vigente():
    D._assert_schema_vigente(_df_minimo(False), Path("nuevo.parquet"))


def test_target_nivel_ya_no_existe():
    """Gold tiene un solo target desde la Decisión 040."""
    try:
        D.build_dataset(df=_df_minimo(False), target="nivel")
    except ValueError as exc:
        assert "un solo target" in str(exc)
        return
    raise AssertionError("target='nivel' debería fallar con un mensaje claro")


def test_grupos_por_defecto_no_piden_nivel():
    pedidas = [c for g in D.DEFAULT_GROUPS for c in D.FEATURE_GROUPS[g]]
    assert not [c for c in pedidas if "nivel" in c]


def test_splits_respetan_el_embargo():
    fecha = pd.date_range("2020-01-01", "2026-08-23", freq="D")
    sp = D.make_splits(fecha, embargo_days=14)
    assert fecha[sp.train].max() < fecha[sp.val].min()
    assert fecha[sp.val].max() < fecha[sp.test].min()
    assert (fecha[sp.val].min() - fecha[sp.train].max()).days > 14
    assert not (sp.train & sp.val).any() and not (sp.val & sp.test).any()


def _snapshot_temporal(delta_version, romper_hash=False):
    """Escribe un parquet + su manifest en un directorio temporal."""
    tmp = tempfile.mkdtemp()
    p = Path(tmp) / "training_dataset_v0.parquet"
    _df_minimo(False).to_parquet(p, index=False)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {"delta_version": delta_version, "file_name": p.name,
                "file_sha256": "0" * 64 if romper_hash else sha,
                "exported_at": "2026-08-30T00:00:00+00:00"}
    (Path(tmp) / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return p


def test_manifest_viejo_falla_aunque_el_esquema_este_bien():
    """El hueco que la guarda de columnas no cubre: esquema correcto, valores viejos."""
    p = _snapshot_temporal(D.MIN_DELTA_VERSION - 1)
    D._assert_schema_vigente(pd.read_parquet(p), p)     # el esquema pasa...
    try:
        D._assert_manifest_vigente(p)                    # ...y la version no
    except ValueError as exc:
        assert str(D.MIN_DELTA_VERSION) in str(exc)
        return
    raise AssertionError("un snapshot por debajo del piso deberia fallar")


def test_manifest_vigente_pasa():
    D._assert_manifest_vigente(_snapshot_temporal(D.MIN_DELTA_VERSION))


def test_sha256_que_no_coincide_falla():
    """Si el parquet y su manifest describen datos distintos, la version que
    informa el manifest no es confiable."""
    p = _snapshot_temporal(D.MIN_DELTA_VERSION, romper_hash=True)
    try:
        D._assert_manifest_vigente(p)
    except ValueError as exc:
        assert "sha256" in str(exc)
        return
    raise AssertionError("un sha256 distinto deberia fallar")


def test_manifest_de_otro_archivo_se_ignora():
    """El manifest sólo describe al archivo que él nombra: para el snapshot
    legacy, que vive en el mismo directorio, no aplica."""
    p = _snapshot_temporal(D.MIN_DELTA_VERSION)
    otro = p.parent / "training_dataset_v0_PRE039.parquet"
    otro.write_bytes(p.read_bytes())
    assert D.read_manifest(otro) is None
    D._assert_manifest_vigente(otro)          # no compara, no falla


def test_sin_manifest_no_falla():
    """Un parquet suelto sigue cubierto por la guarda de esquema, nada mas."""
    tmp = tempfile.mkdtemp()
    p = Path(tmp) / "suelto.parquet"
    _df_minimo(False).to_parquet(p, index=False)
    assert D.read_manifest(p) is None
    D._assert_manifest_vigente(p)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests de datos OK")
