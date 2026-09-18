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


# --------------------------------------------------------------------------
# Modo forecast del modulador (B8.05)
# --------------------------------------------------------------------------

def _df_completo(n=200, con_forecast=False, fc_alto_desde=None, fc_nan_hasta=0):
    """Un snapshot sintético con todo lo que `build_dataset` exige."""
    rng = np.random.default_rng(5)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame(index=idx)
    q = 2000.0 + rng.normal(0, 100, n).cumsum()
    df["caudal_actual_m3s"] = q
    for c in ("caudal_lag_1d", "caudal_lag_3d", "caudal_lag_7d",
              "caudal_media_3d", "caudal_media_7d", "caudal_delta_1d"):
        df[c] = q + rng.normal(0, 10, n)
    for c in ("caudal_agregado_alta_frontera_m3s", "caudal_agregado_alta_frontera_lag_1d",
              "caudal_agregado_alta_frontera_lag_2d", "caudal_agregado_alta_frontera_lag_3d"):
        df[c] = q * 0.5
    df["caudal_agregado_alta_frontera_confiable_pct"] = 100.0
    df["lluvia_acumulada_mm"] = rng.gamma(2.0, 4.0, n) * 20
    df["lluvia_agregado_alta_frontera_station_count"] = 20
    for h in D.HORIZONS:
        df[f"caudal_t_mas_{h}d"] = q
    if con_forecast:
        for k in range(1, 15):
            col = rng.gamma(2.0, 4.0, n)
            if fc_alto_desde is not None:
                col[fc_alto_desde:] = 300.0
            col[:fc_nan_hasta] = np.nan
            df[f"ecmwf_cf_tp_mm_d{k}"] = col
    return df


def test_forecast_sin_columnas_falla_claro():
    try:
        D.build_dataset(df=_df_completo(con_forecast=False), tau_mode="forecast")
    except KeyError as exc:
        assert "forecast" in str(exc)
    else:
        raise AssertionError("sin columnas ECMWF el modo forecast tiene que fallar")


def test_forecast_usa_el_pronostico_real():
    """Meter lluvia pronosticada enorme en la segunda mitad tiene que subir τ ahí."""
    ds_a = D.build_dataset(df=_df_completo(con_forecast=True), tau_mode="forecast")
    ds_b = D.build_dataset(df=_df_completo(con_forecast=True, fc_alto_desde=100),
                           tau_mode="forecast")
    m_a = ds_a.fecha >= "2020-05-01"
    m_b = ds_b.fecha >= "2020-05-01"
    assert np.nanmean(ds_b.tau[m_b]) > np.nanmean(ds_a.tau[m_a]) + 0.05


def test_forecast_filtra_las_filas_sin_pronostico():
    """Sin pronóstico no hay τ, y sin τ la fila no entra — igual que cualquier NaN."""
    ds_con = D.build_dataset(df=_df_completo(con_forecast=True), tau_mode="forecast")
    ds_hueco = D.build_dataset(df=_df_completo(con_forecast=True, fc_nan_hasta=60),
                               tau_mode="forecast")
    assert len(ds_hueco) < len(ds_con)
    assert ds_hueco.fecha.min() > ds_con.fecha.min()


def test_forecast_no_altera_los_otros_modos():
    """El cableado nuevo no puede tocar el τ del oráculo."""
    df = _df_completo(con_forecast=True)
    tau_con = D.build_dataset(df=df, tau_mode="oracle").tau
    tau_sin = D.build_dataset(df=_df_completo(con_forecast=False), tau_mode="oracle").tau
    assert np.allclose(tau_con, tau_sin, equal_nan=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests de datos OK")
