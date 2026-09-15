"""Auditoría de fuga sobre la matriz de features construida.

    python -m rio_search.audit

Complementa la guarda que corre en `Validate_Training_Dataset_v0` (Decisión 043),
que protege el **dataset publicado**. Ésta protege lo que se construye encima:
las features derivadas de `rio_search.data`, el modulador τ y los splits.

El criterio es el mismo, y no es arbitrario: **nada debería predecir el caudal de
mañana mejor que el caudal de hoy**. Comparar valores sólo atrapa duplicación
literal; un proxy del futuro no es idéntico a ninguna columna y pasa esa prueba
sin problema. Superar la autocorrelación del río, en cambio, o es física
sorprendente o es un atajo — y sigue disparando aunque el proxy venga degradado.

Alcance medido, inyectando el target con ruido multiplicativo creciente contra una
línea base de |r| = 0,856, y midiendo qué le hace al RMSE de un modelo legítimo
(`caudal_actual + caudal_media_3d`, RMSE 1001 m³/s):

    ruido   |r| marginal   ¿pasa?      RMSE   mejora
     25 %        0,950        no      528     +473
     40 %        0,876        no      748     +253
     50 %        0,826        SÍ      820     +182
    100 %        0,572        SÍ      948      +53

**Un proxy con 50 % de ruido pasa la guarda y baja el RMSE un 18 %.** No es
inofensivo, y conviene decirlo sin adornos: la primera versión de este comentario
argumentaba que por debajo de la línea base el proxy no podía aportar nada porque
era "menos informativo que una feature que el modelo ya tiene". Eso confundía
correlación **marginal** con aporte **incremental**. Dos features de 0,7 cada una,
si son independientes entre sí, superan juntas a una de 0,85; el proxy aporta
justamente la innovación —la parte de mañana que hoy no predice— que es lo que el
modelo intenta aprender.

La correlación **parcial** (controlando por `caudal_actual`) sería el diagnóstico
teóricamente correcto, y tampoco alcanza como umbral: sobre las features reales el
máximo legítimo es 0,49 (`lluvia_media_est_mm` — la lluvia de hoy sí anticipa el
caudal de mañana más allá del caudal de hoy, es hidrología, no fuga) y un proxy con
100 % de ruido da 0,38. Los rangos se superponen. No hay umbral, marginal ni
parcial, que separe fuga de señal legítima en todo el rango.

Entonces, qué cubre esta guarda de verdad: **el régimen realista**. El accidente
que ocurre —una columna futura olvidada en el esquema, que es exactamente la fuga
de la Decisión 040— es una copia exacta o casi. Nadie le agrega 50 % de ruido a una
fuga por accidente. Ahí la guarda dispara siempre.

Contra un proxy fuertemente degradado la defensa no es estadística sino
**estructural**: saber cómo se construye cada columna. Eso es lo que hacen los
tests de ventanas de lluvia y de τ en `tests/test_leakage.py`, que no miden
correlación sino que inyectan un valor y verifican el mecanismo. Esa es la capa
que ninguna guarda de umbral puede reemplazar.
"""

from __future__ import annotations

import numpy as np

__all__ = ["FUTURO_LEGITIMO", "abs_corr", "audit_features", "audit_gate",
           "audit_splits", "main"]

#: Features que son **legítimamente** información sobre el futuro, emitida en t₀.
#: Hoy está vacío. Cuando entren las columnas de pronóstico (Fase 4 del roadmap)
#: van acá, con su justificación.
#:
#: La tentación al ver el primer falso positivo va a ser bajar el umbral. **No.**
#: Bajarlo pierde la protección entera para acomodar un caso previsto; declarar la
#: columna acá deja escrito cuál es la excepción y por qué. Una lista que crece de
#: a una entrada documentada es auditable; un umbral relajado no.
FUTURO_LEGITIMO: frozenset[str] = frozenset()

#: Por debajo de esto la línea base no es creíble y el resto del test no significa
#: nada: conviene fallar antes que dar un visto bueno vacío.
BASE_MINIMA = 0.80


def abs_corr(a, b) -> float:
    """|correlación de Pearson| ignorando NaN. NaN si no hay muestra suficiente."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 100 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return float("nan")
    return abs(float(np.corrcoef(a[m], b[m])[0, 1]))


def audit_features(ds, *, baseline: str = "caudal_actual_m3s",
                   horizon_index: int = 0) -> dict:
    """¿Alguna feature predice el target mejor que la línea base?

    Devuelve `{"baseline", "ranking", "sospechosas", "excluidas"}`.
    `sospechosas` es lo que hay que explicar; vacío es el resultado esperado.
    """
    y = ds.Y[:, horizon_index]
    if baseline not in ds.feature_names:
        raise KeyError(f"la línea base {baseline!r} no está entre las features")
    base = abs_corr(ds.X[:, ds.feature_names.index(baseline)], y)

    ranking, sospechosas, excluidas = [], [], []
    for i, nombre in enumerate(ds.feature_names):
        r = abs_corr(ds.X[:, i], y)
        ranking.append((nombre, r))
        if nombre == baseline or not np.isfinite(r) or r <= base:
            continue
        (excluidas if nombre in FUTURO_LEGITIMO else sospechosas).append((nombre, r))

    ranking.sort(key=lambda kv: (-kv[1] if np.isfinite(kv[1]) else 0))
    return {"baseline": base, "baseline_name": baseline, "ranking": ranking,
            "sospechosas": sospechosas, "excluidas": excluidas,
            "horizonte": ds.horizons[horizon_index]}


def partial_corr(x, y, z) -> float:
    """|correlación| entre x e y una vez removido de ambos el efecto lineal de z.

    Mide el aporte **incremental**, que es lo que la correlación marginal no ve.
    Se reporta como diagnóstico, **nunca como umbral**: sobre las features reales
    el máximo legítimo (0,49) queda por encima de lo que da un proxy con 100 % de
    ruido (0,38), así que un corte acá barrería hidrología real. Sirve para mirar,
    no para decidir.
    """
    x, y, z = (np.asarray(v, dtype=float) for v in (x, y, z))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if ok.sum() < 100:
        return float("nan")
    M = np.column_stack([z[ok], np.ones(int(ok.sum()))])

    def resid(v):
        b, *_ = np.linalg.lstsq(M, v[ok], rcond=None)
        return v[ok] - M @ b

    rx, ry = resid(x), resid(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return float("nan")
    return abs(float(np.corrcoef(rx, ry)[0, 1]))


def audit_incremental(ds, *, baseline: str = "caudal_actual_m3s",
                      horizon_index: int = 0, top: int = 5) -> list[tuple[str, float]]:
    """Ranking de correlación parcial. Diagnóstico para leer, no para asertar."""
    y = ds.Y[:, horizon_index]
    z = ds.X[:, ds.feature_names.index(baseline)]
    out = [(n, partial_corr(ds.X[:, i], y, z))
           for i, n in enumerate(ds.feature_names) if n != baseline]
    out = [(n, v) for n, v in out if np.isfinite(v)]
    out.sort(key=lambda kv: -kv[1])
    return out[:top]


def audit_gate(ds) -> dict:
    """El modulador puede mirar el futuro; la matriz de entrada no.

    En modo `oracle` τ mira lluvia futura a propósito. Eso es válido mientras τ
    llegue sólo a la función de pérdida. Hay dos formas de romperlo: meter τ como
    feature, o que alguna feature lo replique por otra vía — de ahí que se mida la
    correlación además de chequear el nombre.
    """
    replica = max((abs_corr(ds.X[:, i], ds.tau) for i in range(ds.X.shape[1])),
                  default=float("nan"))
    return {
        "tau_es_feature": "tau" in ds.feature_names,
        "features_de_target": [c for c in ds.feature_names if "t_mas" in c],
        "max_corr_con_tau": replica,
    }


def audit_splits(ds, splits) -> dict:
    """Solape entre splits y tamaño del embargo contra el horizonte máximo."""
    h_max = max(ds.horizons)
    huecos = {}
    for antes, despues, nombre in ((splits.train, splits.val, "train_val"),
                                   (splits.val, splits.test, "val_test")):
        huecos[nombre] = int((ds.fecha[despues].min() - ds.fecha[antes].max()).days)
    return {
        "solape_train_val": int((splits.train & splits.val).sum()),
        "solape_val_test": int((splits.val & splits.test).sum()),
        "solape_train_test": int((splits.train & splits.test).sum()),
        "huecos_dias": huecos,
        "horizonte_maximo": h_max,
    }


def main(argv=None) -> int:
    import argparse

    from . import data as data_mod
    from .train import _utf8_console

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gate-rain", default="auto")
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args(argv)
    _utf8_console()

    ds = data_mod.build_dataset(groups=tuple(data_mod.FEATURE_GROUPS),
                                gate_rain_col=args.gate_rain)
    splits = data_mod.make_splits(ds.fecha)

    feats = audit_features(ds)
    print(f"\n=== Features · {len(ds.feature_names)} columnas, target t+{feats['horizonte']} ===")
    print(f"  línea base  {feats['baseline_name']}  |r| = {feats['baseline']:.4f}\n")
    for nombre, r in feats["ranking"][:args.top]:
        marca = ""
        if nombre in dict(feats["sospechosas"]):
            marca = "   <-- SOSPECHOSA"
        elif nombre in dict(feats["excluidas"]):
            marca = "   (futuro legítimo, declarada)"
        print(f"  {r:.4f}  {nombre}{marca}")

    print(f"\n=== Aporte incremental (parcial, controlando por {feats['baseline_name']}) ===")
    print("  diagnóstico para leer, no umbral: el máximo legítimo se superpone")
    print("  con el rango de un proxy degradado, así que un corte acá barrería hidrología.")
    for nombre, v in audit_incremental(ds):
        print(f"  {v:.4f}  {nombre}")

    gate = audit_gate(ds)
    print(f"\n=== Modulador ===")
    print(f"  τ entre las features: {'SÍ (FUGA)' if gate['tau_es_feature'] else 'no'}")
    print(f"  columnas de target  : {gate['features_de_target'] or 'ninguna'}")
    print(f"  |r| máxima feature-τ: {gate['max_corr_con_tau']:.4f}")

    sp = audit_splits(ds, splits)
    print(f"\n=== Splits ===")
    print(f"  solapes: {sp['solape_train_val']} / {sp['solape_val_test']} / {sp['solape_train_test']}")
    print(f"  huecos : {sp['huecos_dias']} d  contra horizonte máximo {sp['horizonte_maximo']} d")

    ok = (not feats["sospechosas"] and not gate["tau_es_feature"]
          and not gate["features_de_target"]
          and sp["solape_train_val"] == sp["solape_val_test"] == sp["solape_train_test"] == 0)
    print("\n  " + ("AUDITORÍA LIMPIA" if ok else "REVISAR: hay hallazgos arriba"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
