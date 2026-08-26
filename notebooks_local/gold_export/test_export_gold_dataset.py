"""Tests del exportador local de Gold (Fase 1 del roadmap). Corren offline: no tocan
Databricks ni la red, solo las funciones puras de export_gold_dataset.py (filtros,
regla R9, resumen, corte por version Delta).

Uso:
    python -m pytest notebooks_local/gold_export/test_export_gold_dataset.py -v
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import export_gold_dataset as m


def make_df(n_days: int = 20, start: str = "2020-01-01") -> pd.DataFrame:
    fechas = pd.date_range(start, periods=n_days, freq="D")
    df = pd.DataFrame(
        {
            "fecha": fechas,
            "caudal_actual_m3s": [100.0 + i for i in range(n_days)],
            "caudal_confiable": [i % 3 != 0 for i in range(n_days)],
            "caudal_metodo": ["curva" if i % 2 == 0 else "sin_curva" for i in range(n_days)],
            "caudal_t_mas_1d": [100.0 + i + 1 if i + 1 < n_days else None for i in range(n_days)],
            "caudal_t_mas_3d": [100.0 + i + 3 if i + 3 < n_days else None for i in range(n_days)],
            "caudal_t_mas_7d": [100.0 + i + 7 if i + 7 < n_days else None for i in range(n_days)],
            "caudal_t_mas_14d": [100.0 + i + 14 if i + 14 < n_days else None for i in range(n_days)],
        }
    )
    return df


def test_apply_filters_desde():
    df = make_df()
    out = m.apply_filters(df, desde=date(2020, 1, 10))
    assert out["fecha"].min() == pd.Timestamp("2020-01-10")
    assert len(out) == len(df) - 9


def test_apply_filters_confiable_excludes_false_and_null():
    df = make_df()
    out = m.apply_filters(df, confiable=True)
    assert (out["caudal_confiable"] == True).all()  # noqa: E712
    assert len(out) < len(df)


def test_apply_filters_confiable_missing_column_raises():
    df = make_df().drop(columns=["caudal_confiable"])
    with pytest.raises(ValueError, match="caudal_confiable"):
        m.apply_filters(df, confiable=True)


def test_trim_horizon_tail_r9_drops_only_recency_tail():
    # 20 dias, horizonte 7d: el target existe solo hasta fecha[-8]; la regla R9 debe
    # recortar exactamente esos ultimos 7 dias, no filas con NULL en el medio de la serie.
    df = make_df(n_days=20)
    out = m.trim_horizon_tail(df, 7)
    assert len(out) == 13
    assert out["fecha"].max() == df["fecha"].iloc[-8]
    assert out["caudal_t_mas_7d"].notna().all()


def test_trim_horizon_tail_does_not_touch_mid_series_nulls():
    df = make_df(n_days=20)
    # Introduce un NULL real a mitad de la serie (dato faltante, no cola de recencia).
    df.loc[5, "caudal_t_mas_7d"] = None
    out = m.trim_horizon_tail(df, 7)
    assert len(out) == 13
    assert out.loc[out["fecha"] == df["fecha"].iloc[5], "caudal_t_mas_7d"].isna().all()


def test_trim_horizon_tail_unknown_horizon_raises_with_available_list():
    df = make_df()
    with pytest.raises(ValueError, match="Horizontes disponibles hoy"):
        m.trim_horizon_tail(df, 2)


def test_apply_filters_combines_desde_confiable_horizonte():
    df = make_df(n_days=30)
    out = m.apply_filters(df, desde=date(2020, 1, 5), confiable=True, horizonte=1)
    assert out["fecha"].min() >= pd.Timestamp("2020-01-05")
    assert (out["caudal_confiable"] == True).all()  # noqa: E712
    assert out["caudal_t_mas_1d"].notna().all()


def test_apply_filters_empty_input_is_safe():
    df = make_df(n_days=0)
    out = m.apply_filters(df, desde=date(2020, 1, 1), confiable=True, horizonte=1)
    assert out.empty


def test_build_resumen_reports_rows_range_missing_and_metodo():
    df = make_df(n_days=10)
    df.loc[0, "caudal_actual_m3s"] = None
    resumen = m.build_resumen(df)
    assert "Filas: 10" in resumen
    assert "2020-01-01 a 2020-01-10" in resumen
    assert "caudal_actual_m3s: 1" in resumen
    assert "curva:" in resumen and "sin_curva:" in resumen


def test_build_resumen_empty_dataframe():
    df = make_df(n_days=0)
    resumen = m.build_resumen(df)
    assert "Filas: 0" in resumen
    assert "sin datos" in resumen


def test_needs_download_true_when_no_cache():
    remote = {"delta_version": 5}
    assert m.needs_download(None, remote, refresh=False, cache_exists=False) is True


def test_needs_download_true_when_version_changed():
    local = {"delta_version": 4}
    remote = {"delta_version": 5}
    assert m.needs_download(local, remote, refresh=False, cache_exists=True) is True


def test_needs_download_false_when_version_unchanged():
    local = {"delta_version": 5}
    remote = {"delta_version": 5}
    assert m.needs_download(local, remote, refresh=False, cache_exists=True) is False


def test_needs_download_true_when_refresh_forced():
    local = {"delta_version": 5}
    remote = {"delta_version": 5}
    assert m.needs_download(local, remote, refresh=True, cache_exists=True) is True


def test_sha256_of_matches_known_digest(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"hola mundo")
    import hashlib
    expected = hashlib.sha256(b"hola mundo").hexdigest()
    assert m.sha256_of(path) == expected


def test_export_file_parquet_and_csv_roundtrip(tmp_path):
    df = make_df(n_days=3)
    parquet_path = m.export_file(df, "parquet", tmp_path, suffix="_test")
    csv_path = m.export_file(df, "csv", tmp_path, suffix="_test")
    assert parquet_path.exists() and parquet_path.suffix == ".parquet"
    assert csv_path.exists() and csv_path.suffix == ".csv"
    assert len(pd.read_parquet(parquet_path)) == 3
    assert len(pd.read_csv(csv_path)) == 3


def test_filters_suffix_combines_active_filters():
    suffix = m.filters_suffix(date(2020, 1, 1), True, 7)
    assert suffix == "_desde-2020-01-01_confiable_h7d"


def test_filters_suffix_empty_when_no_filters():
    assert m.filters_suffix(None, False, None) == ""


@pytest.fixture
def clean_shared_lock():
    """El lock es literalmente el mismo archivo que usan las tareas de ANA
    (backfill.lock en ana_historic_backfill/). Si el entorno de test ya lo tiene
    tomado por un proceso real, no lo tocamos; si no, lo dejamos como lo encontramos."""
    pre_existing = m.shared_lock.is_locked()
    if pre_existing is not None:
        pytest.skip("El lock compartido ya esta tomado por otro proceso; no se puede probar contencion")
    yield
    m.shared_lock.release()


def test_shared_lock_blocks_concurrent_run(clean_shared_lock):
    assert m.shared_lock.acquire("test-holder") is True
    # Mismo proceso (PID vivo) intentando tomar el lock de nuevo: debe fallar, tal
    # como fallaria sync_to_databricks.py corriendo en paralelo a este exportador.
    assert m.shared_lock.acquire("gold_export") is False


def test_shared_lock_releases_cleanly(clean_shared_lock):
    assert m.shared_lock.acquire("test-holder") is True
    m.shared_lock.release()
    assert m.shared_lock.is_locked() is None
    assert m.shared_lock.acquire("gold_export") is True
