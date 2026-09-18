"""Auditoría de fuga sobre la matriz de features, como test permanente.

La guarda de `Validate_Training_Dataset_v0` (Decisión 043) protege el dataset
publicado. Estos tests cubren la capa de arriba: las features **derivadas** que
arma `rio_search.data`, el modulador τ y los splits.

Cada guarda va con su **prueba negativa**: se inyecta la fuga y se verifica que
dispare. Una guarda que nunca se vio fallar no es evidencia de nada — y el caso
que importa no es la fuga exacta sino el proxy degradado, que es lo que hace
falta para atrapar algo como la fuga de la Decisión 040 (nivel futuro, que no era
idéntico a ninguna columna: era la misma señal transformada por la curva de aforo).

Son tests de integración: necesitan el snapshot Gold real. Si no está, se saltean
en vez de fallar, para que el resto de la suite siga siendo hermética.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import audit as A
from rio_search import data as D
from rio_search.train import Preprocessor


def _dataset():
    """Dataset con TODOS los grupos de features, o None si no hay snapshot."""
    if not D.DEFAULT_SNAPSHOT.exists():
        return None
    return D.build_dataset(groups=tuple(D.FEATURE_GROUPS),
                           gate_rain_col="lluvia_merge_alta_frontera_mm")


def _con_feature_extra(ds, nombre: str, columna: np.ndarray):
    """Copia del Dataset con una columna más. Para inyectar fugas."""
    return D.Dataset(
        fecha=ds.fecha, X=np.column_stack([ds.X, columna]), Y=ds.Y,
        q_actual=ds.q_actual, tau=ds.tau,
        feature_names=list(ds.feature_names) + [nombre],
        horizons=ds.horizons, tau_mode=ds.tau_mode,
    )


# --------------------------------------------------------------------------
# Caso limpio
# --------------------------------------------------------------------------

def test_ninguna_feature_predice_el_futuro_mejor_que_el_presente():
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    out = A.audit_features(ds)
    assert out["baseline"] > A.BASE_MINIMA, (
        f"la línea base cayó a {out['baseline']:.4f}: el resto del test no significa nada")
    assert not out["sospechosas"], (
        f"features que superan la autocorrelación del río: {out['sospechosas']}. "
        "Si son features de pronóstico (Fase 4), declararlas en "
        "`audit.FUTURO_LEGITIMO` con su justificación — NO bajar el umbral.")


# --------------------------------------------------------------------------
# Pruebas negativas: la guarda tiene que disparar
# --------------------------------------------------------------------------

def test_la_guarda_dispara_ante_el_futuro_exacto():
    """El caso trivial: el target metido como feature."""
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    sucio = _con_feature_extra(ds, "fuga_exacta", ds.Y[:, 0].copy())
    out = A.audit_features(sucio)
    assert "fuga_exacta" in dict(out["sospechosas"])
    assert abs(dict(out["sospechosas"])["fuga_exacta"] - 1.0) < 1e-9


def test_la_guarda_dispara_ante_un_proxy_degradado():
    """El caso que importa, y el que separa esta prueba de comparar valores.

    La fuga de la Decisión 040 era el nivel futuro: no idéntico al caudal futuro,
    sino la misma señal pasada por la curva de aforo. Una comparación de valores
    no la habría visto. Acá se reproduce esa forma — futuro más ruido — y la
    guarda tiene que seguir disparando.

    El rango llega hasta 40 % **a propósito**: más allá de ~50 % la guarda deja
    pasar el proxy, y eso está medido y documentado en `audit.py`. Afirmar acá que
    dispara siempre sería falso. El régimen que este test cubre es el realista —
    una columna futura olvidada en el esquema es exacta o casi, nadie le agrega
    50 % de ruido a una fuga por accidente. Lo degradado lo cubren los tests
    estructurales (ventanas de lluvia, τ), que verifican mecanismo y no correlación.
    """
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    rng = np.random.default_rng(20260830)
    futuro = ds.Y[:, 0]
    for ruido in (0.10, 0.25, 0.40):
        proxy = futuro * rng.normal(1.0, ruido, size=futuro.shape)
        sucio = _con_feature_extra(ds, f"proxy_{int(ruido*100)}", proxy)
        out = A.audit_features(sucio)
        hallado = dict(out["sospechosas"])
        assert f"proxy_{int(ruido*100)}" in hallado, (
            f"un proxy con {ruido:.0%} de ruido pasó la guarda: no protege "
            "contra fugas transformadas, que son las que importan")


def test_una_feature_legitima_no_dispara():
    """El otro lado: la guarda no puede ser tan sensible que marque física normal.

    `caudal_media_3d` está fuertemente correlacionada con el futuro por razones
    hidrológicas y tiene que pasar.
    """
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    out = A.audit_features(ds)
    r = dict(out["ranking"])["caudal_media_3d"]
    assert 0.5 < r < out["baseline"], (
        f"caudal_media_3d dio |r| = {r:.4f} contra base {out['baseline']:.4f}")


def test_una_feature_declarada_como_futuro_legitimo_se_excluye():
    """El mecanismo previsto para la Fase 4: declarar, no bajar el umbral.

    Las features de pronóstico son legítimamente información sobre el futuro
    emitida en t₀. Van a superar el umbral y va a ser un verdadero positivo del
    test, no una fuga. La salida correcta es declararlas.
    """
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    sucio = _con_feature_extra(ds, "precip_fc_d1", ds.Y[:, 0].copy())

    assert "precip_fc_d1" in dict(A.audit_features(sucio)["sospechosas"])

    original = A.FUTURO_LEGITIMO
    try:
        A.FUTURO_LEGITIMO = frozenset({"precip_fc_d1"})
        out = A.audit_features(sucio)
        assert not out["sospechosas"]
        assert "precip_fc_d1" in dict(out["excluidas"])
    finally:
        A.FUTURO_LEGITIMO = original


# --------------------------------------------------------------------------
# Modulador, splits, preprocesamiento, ventanas
# --------------------------------------------------------------------------

def test_el_modulador_no_entra_como_feature():
    """τ puede mirar lluvia futura (modo oráculo) sin que eso sea fuga —
    siempre que llegue sólo a la pérdida y nunca a la matriz de entrada."""
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    out = A.audit_gate(ds)
    assert not out["tau_es_feature"]
    assert not out["features_de_target"]
    assert out["max_corr_con_tau"] < 0.7, (
        f"alguna feature replica τ (|r| = {out['max_corr_con_tau']:.3f})")


def test_la_guarda_del_modulador_dispara_si_tau_entra_como_feature():
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    sucio = _con_feature_extra(ds, "tau", ds.tau.copy())
    out = A.audit_gate(sucio)
    assert out["tau_es_feature"]
    assert out["max_corr_con_tau"] > 0.99


def test_los_splits_no_se_solapan_y_respetan_el_embargo():
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    sp = D.make_splits(ds.fecha)
    out = A.audit_splits(ds, sp)
    assert out["solape_train_val"] == 0
    assert out["solape_val_test"] == 0
    assert out["solape_train_test"] == 0
    for nombre, hueco in out["huecos_dias"].items():
        assert hueco > out["horizonte_maximo"], (
            f"{nombre}: hueco de {hueco} d, no alcanza para h={out['horizonte_maximo']}")


def test_el_preprocesamiento_solo_mira_train():
    """Los estadísticos de imputación y escalado tienen que salir de TRAIN.

    Se verifica alterando VAL y TEST: si el ajuste mirara esas filas, las
    medianas y medias cambiarían.
    """
    ds = _dataset()
    if ds is None:
        print("    (salteado: no hay snapshot)")
        return
    sp = D.make_splits(ds.fecha)
    limpio = Preprocessor(target_transform="log").fit(ds.X[sp.train], ds.Y[sp.train])

    X = ds.X.copy()
    X[sp.val | sp.test] = 1e9          # basura fuera de TRAIN
    Y = ds.Y.copy()
    Y[sp.val | sp.test] = 1e9
    sucio = Preprocessor(target_transform="log").fit(X[sp.train], Y[sp.train])

    assert np.allclose(limpio.x_median, sucio.x_median, equal_nan=True)
    assert np.allclose(limpio.x_mean, sucio.x_mean, equal_nan=True)
    assert np.allclose(limpio.x_std, sucio.x_std, equal_nan=True)
    assert limpio.y_mean == sucio.y_mean and limpio.y_std == sucio.y_std


def test_los_acumulados_de_lluvia_miran_hacia_atras():
    """Una ventana centrada o adelantada se ve normal en el código y contiene
    lluvia que todavía no cayó. No hay forma de verlo leyendo: hay que inyectar
    un día y mirar dónde aparece."""
    import pandas as pd
    idx = pd.date_range("2020-01-01", periods=60, freq="D")
    df = pd.DataFrame({
        "lluvia_acumulada_mm": np.zeros(60),
        "lluvia_agregado_alta_frontera_station_count": np.full(60, 10.0),
    }, index=idx)
    df.iloc[40, df.columns.get_loc("lluvia_acumulada_mm")] = 100.0   # un solo día de lluvia

    out = D._derive_rain(df)
    for w in (3, 7, 10, 30):
        col = out[f"lluvia_media_est_acum_{w}d"].to_numpy()
        assert np.nanmax(col[:40]) == 0.0, (
            f"acum_{w}d tiene lluvia antes de que ocurriera: mira al futuro")
        assert col[40] > 0.0, f"acum_{w}d no registra la lluvia del propio día"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests de fuga OK")
