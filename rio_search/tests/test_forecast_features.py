"""Tests de las features de pronóstico ECMWF (B2.19).

`_derive_forecast` sólo agrega lo que Gold no trae: la cola 8-14 días del
control y el desacuerdo cf/pf a 7 días. Es causal por construcción (nada de
`.rolling`, cada fila usa sólo sus propias columnas), así que la prueba de
causalidad es sobre independencia entre filas, no sobre una ventana temporal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import audit as A
from rio_search import data as D


def _df_forecast(n=5, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    cols = {}
    for k in range(1, 16):
        cols[f"ecmwf_cf_tp_mm_d{k}"] = rng.uniform(0, 20, n)
        cols[f"ecmwf_pf_tp_mm_d{k}"] = rng.uniform(0, 20, n)
    df = pd.DataFrame(cols, index=idx)
    df["ecmwf_cf_tp_acum_3d_mm"] = df[[f"ecmwf_cf_tp_mm_d{k}" for k in (1, 2, 3)]].sum(axis=1)
    df["ecmwf_cf_tp_acum_7d_mm"] = df[[f"ecmwf_cf_tp_mm_d{k}" for k in range(1, 8)]].sum(axis=1)
    df["ecmwf_pf_tp_acum_7d_mm"] = df[[f"ecmwf_pf_tp_mm_d{k}" for k in range(1, 8)]].sum(axis=1)
    return df


def test_cola_8_14_es_la_suma_de_esos_leads():
    df = _df_forecast()
    out = D._derive_forecast(df)
    esperado = df[[f"ecmwf_cf_tp_mm_d{k}" for k in range(8, 15)]].sum(axis=1)
    assert np.allclose(out["ecmwf_cf_tp_8_14d_mm"], esperado)


def test_cola_8_14_no_incluye_d15():
    """d15 queda fuera: la cola es 8-14, no 8-15."""
    df = _df_forecast()
    out = D._derive_forecast(df)
    con_d15 = df[[f"ecmwf_cf_tp_mm_d{k}" for k in range(8, 16)]].sum(axis=1)
    assert not np.allclose(out["ecmwf_cf_tp_8_14d_mm"], con_d15)


def test_desacuerdo_es_valor_absoluto_de_la_diferencia():
    df = _df_forecast()
    out = D._derive_forecast(df)
    esperado = (df["ecmwf_cf_tp_acum_7d_mm"] - df["ecmwf_pf_tp_acum_7d_mm"]).abs()
    assert np.allclose(out["ecmwf_fc_desacuerdo_7d_mm"], esperado)
    assert (out["ecmwf_fc_desacuerdo_7d_mm"] >= 0).all()


def test_cada_fila_es_independiente_de_las_demas():
    """Perturbar el pronóstico de un día no puede cambiar el derivado de otro:
    no hay rolling, cada fila se calcula sola."""
    df = _df_forecast(n=10, seed=1)
    df2 = df.copy()
    df2.loc[df2.index[5], [f"ecmwf_cf_tp_mm_d{k}" for k in range(1, 16)]] += 500.0
    a = D._derive_forecast(df)
    b = D._derive_forecast(df2)
    otras = [i for i in range(10) if i != 5]
    for col in ("ecmwf_cf_tp_8_14d_mm", "ecmwf_fc_desacuerdo_7d_mm"):
        assert np.allclose(a[col].iloc[otras], b[col].iloc[otras]), col
    # y la fila perturbada sí cambia: confirma que la función no es un no-op.
    assert a["ecmwf_cf_tp_8_14d_mm"].iloc[5] != b["ecmwf_cf_tp_8_14d_mm"].iloc[5]


def test_snapshot_sin_columnas_ecmwf_no_rompe():
    """Un snapshot legacy (pre Fase 4) simplemente no gana las columnas derivadas."""
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    df = pd.DataFrame({"caudal_actual_m3s": [100.0, 110.0, 90.0]}, index=idx)
    out = D._derive_forecast(df)
    assert "ecmwf_cf_tp_8_14d_mm" not in out.columns
    assert "ecmwf_fc_desacuerdo_7d_mm" not in out.columns


def test_grupo_pronostico_ecmwf_declarado():
    assert D.FEATURE_GROUPS["pronostico_ecmwf"] == (
        "ecmwf_cf_tp_acum_3d_mm", "ecmwf_cf_tp_acum_7d_mm", "ecmwf_cf_tp_8_14d_mm",
        "ecmwf_pf_tp_acum_7d_mm", "ecmwf_fc_desacuerdo_7d_mm",
    )


def test_las_cinco_columnas_estan_declaradas_como_futuro_legitimo():
    for col in D.FEATURE_GROUPS["pronostico_ecmwf"]:
        assert col in A.FUTURO_LEGITIMO, (
            f"{col} entra como feature de pronóstico pero no está en "
            "FUTURO_LEGITIMO: la auditoría de fuga la va a marcar sospechosa")


def test_pedir_el_grupo_en_snapshot_legacy_da_keyerror_claro():
    """Sin las columnas de Gold, build_dataset debe fallar con el KeyError
    habitual (columnas faltantes), no con un error oscuro de `_derive_forecast`."""
    import pytest
    idx = pd.date_range("2020-01-01", periods=40, freq="D")
    df = pd.DataFrame({
        "caudal_actual_m3s": np.linspace(100, 140, 40),
        "caudal_lag_1d": np.linspace(99, 139, 40),
        "caudal_lag_3d": np.linspace(97, 137, 40),
        "caudal_lag_7d": np.linspace(93, 133, 40),
        "caudal_media_3d": np.linspace(99, 139, 40),
        "caudal_media_7d": np.linspace(96, 136, 40),
        "caudal_delta_1d": np.ones(40),
        "lluvia_acumulada_mm": np.zeros(40),
        "lluvia_agregado_alta_frontera_station_count": np.ones(40),
        "lluvia_media_est_mm": np.zeros(40),
        "caudal_t_mas_1d": np.linspace(100, 140, 40),
    }, index=idx)
    with pytest.raises(KeyError):
        D.build_dataset(df=df, groups=("caudal_estado", "pronostico_ecmwf"),
                        horizons=(1,), permitir_legacy=True)


# --------------------------------------------------------------------------
# Integración con la auditoría, sobre el snapshot real (se saltea si no está)
# --------------------------------------------------------------------------

def test_pronostico_ecmwf_no_dispara_la_auditoria_de_fuga():
    if not D.DEFAULT_SNAPSHOT.exists():
        print("    (salteado: no hay snapshot)")
        return
    ds = D.build_dataset(groups=("caudal_estado", "pronostico_ecmwf"),
                         gate_rain_col="lluvia_merge_alta_frontera_mm")
    out = A.audit_features(ds)
    assert not out["sospechosas"], out["sospechosas"]
    presentes = {c for c, _ in out["excluidas"]}
    for col in D.FEATURE_GROUPS["pronostico_ecmwf"]:
        assert col in ds.feature_names


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests de pronostico_ecmwf OK")
