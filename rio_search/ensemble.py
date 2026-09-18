"""Ensembles por promedio de PREDICCIONES (B10), sobre la infraestructura G-05.

    python -m rio_search.ensemble --modo semillas                       # B10.01
    python -m rio_search.ensemble --modo configs                        # B10.02

Promediar métricas —lo que hace `run_experiment_seeds`— responde "cuánto rinde
una corrida típica". Promediar predicciones responde otra pregunta: "cuánto
rinde EL sistema que un operador desplegaría", porque el operador puede correr
las 5 semillas y quedarse con la media. Son números distintos y el segundo casi
siempre es mejor (la parte no correlacionada del error de inicialización se
cancela).

Reglas fijas:
- Se promedia en el **espacio de evaluación (m³/s)**, después de invertir la
  transformación del target de cada miembro. Así pueden convivir miembros con
  espacios internos distintos (log del ancla, log de huber, etc.) y el promedio
  es el del pronóstico que se publica, no el de un espacio interno.
- Sólo VAL. TEST no se calcula acá (R3: una sola mirada, en B11).
- Los miembros son configuraciones YA definidas por celdas del catálogo, con los
  HP del ancla; este módulo no inventa configuraciones nuevas.

La dispersión que acompaña al ensemble:
- `--modo configs`: el ensemble se arma POR SEMILLA (media entre miembros con la
  misma semilla) y se reporta media ± desvío entre las 5 semillas — la misma
  aritmética que cualquier celda, comparable con el ancla sin más.
- `--modo semillas`: el ensemble colapsa el eje de semillas, así que no tiene
  desvío propio. Se reporta el desvío **jackknife**: las 5 medias dejando una
  semilla afuera. Mide cuánto depende el ensemble de una semilla puntual y es lo
  que se declara como `_sd` (queda dicho acá y en el JSON: es jackknife, no
  desvío entre corridas independientes).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import data as data_mod
from . import gate as gate_mod
from .train import _evaluate_split, run_baselines, run_experiment, _utf8_console

__all__ = ["MIEMBROS", "ANCLA_HP", "predicciones_miembro", "ensemble_semillas",
           "ensemble_configs", "main"]

#: Los HP del ancla (B0.06). Todos los miembros los comparten: el eje que se
#: mide acá es el ensemble, no los hiperparámetros.
ANCLA_HP = dict(model="mlp", hidden=38, lr=0.0492, l2=0.000217, epochs=378)

_GRUPOS_B213 = ("caudal_estado", "caudal_agregado_alta_frontera", "lluvia_ratio",
                "dinamica_caudal", "estacionalidad")

#: Configuraciones elegibles como miembro. Cada una es una celda del catálogo.
MIEMBROS: dict[str, dict] = {
    "gral":            {"celda": "B0.06", "kw": {"loss": "gral"}},
    "huber_log":       {"celda": "B1.07", "kw": {"loss": "huber_log"}},
    "per_horizon":     {"celda": "B5.02", "kw": {"loss": "gral", "per_horizon": True}},
    "dinamica_caudal": {"celda": "B2.13", "kw": {"loss": "gral"},
                        "groups": _GRUPOS_B213},
}


# --------------------------------------------------------------------------
# Aritmética pura (testeable sin datos reales)
# --------------------------------------------------------------------------

def promedio_predicciones(preds: np.ndarray) -> np.ndarray:
    """Media sobre el primer eje de un stack (k, n, H) de predicciones en m³/s."""
    preds = np.asarray(preds, dtype=float)
    if preds.ndim != 3 or preds.shape[0] < 2:
        raise ValueError(f"se esperaba un stack (k>=2, n, H); llegó {preds.shape}")
    return preds.mean(axis=0)


def jackknife(preds: np.ndarray) -> list[np.ndarray]:
    """Las k medias dejando un miembro afuera, en el mismo orden del stack."""
    k = preds.shape[0]
    return [promedio_predicciones(preds[[j for j in range(k) if j != i]])
            for i in range(k)]


def _con_sd(media: dict, muestras: list[dict]) -> dict:
    """`media` + `<k>_sd` con el desvío (ddof=1) de cada métrica en `muestras`."""
    out = dict(media)
    for k in list(media):
        vals = np.array([m.get(k) for m in muestras], dtype=float)
        vals = vals[np.isfinite(vals)]
        out[f"{k}_sd"] = float(vals.std(ddof=1)) if vals.size > 1 else 0.0
    return out


# --------------------------------------------------------------------------
# Miembros: reproducir las predicciones (G-05 por recomputo)
# --------------------------------------------------------------------------

def predicciones_miembro(nombre: str, seeds, *, snapshot=None, _cache={}, _runs={}):
    """(ds, splits, preds (S, n_val, H), métricas por semilla) del miembro.

    Las predicciones se reproducen entrenando (las corridas tardan segundos);
    el dataset se cachea por grupos y las corridas por (miembro, semillas), así
    el CLI puede volver a pedirlas sin reentrenar. Antes de promediar entre
    miembros hay que verificar la alineación de fechas — lo hace
    `ensemble_configs`.
    """
    clave_run = (nombre, tuple(seeds), str(snapshot))
    if clave_run in _runs:
        return _runs[clave_run]
    conf = MIEMBROS[nombre]
    groups = tuple(conf.get("groups") or data_mod.DEFAULT_GROUPS)
    clave_ds = (groups, str(snapshot))
    if clave_ds not in _cache:
        params = gate_mod.GateParams(tau_max=0.85)
        ds = data_mod.build_dataset(target="caudal", tau_mode="oracle",
                                    gate_params=params, snapshot_path=snapshot,
                                    groups=groups,
                                    gate_rain_col="lluvia_media_est_mm")
        _cache[clave_ds] = (ds, data_mod.make_splits(ds.fecha))
    ds, splits = _cache[clave_ds]

    preds, metricas = [], []
    for s in seeds:
        r = run_experiment(ds, splits, seed=s, evaluar_test=False,
                           return_predictions=True, **ANCLA_HP, **conf["kw"])
        preds.append(r["predicciones"]["val"])
        metricas.append(r["val"]["mean"])
    _runs[clave_run] = (ds, splits, np.stack(preds), metricas)
    return _runs[clave_run]


# --------------------------------------------------------------------------
# Los dos ensembles
# --------------------------------------------------------------------------

def ensemble_semillas(miembro: str, seeds, *, snapshot=None) -> dict:
    """B10.01: media de las predicciones de las S semillas de UNA configuración."""
    ds, splits, preds, met_ind = predicciones_miembro(miembro, seeds, snapshot=snapshot)
    va = splits.val
    evaluar = lambda p: _evaluate_split(ds.Y[va], p, ds.tau[va], ds.horizons)

    pleno = evaluar(promedio_predicciones(preds))
    loo = [evaluar(p)["mean"] for p in jackknife(preds)]
    media_ind = {k: float(np.nanmean([m[k] for m in met_ind])) for k in met_ind[0]}

    return {
        "val": {"mean": _con_sd(pleno["mean"], loo),
                "per_horizon": pleno["per_horizon"],
                "jackknife": loo, "per_seed": met_ind},
        "miembro": miembro, "n_miembros": len(seeds),
        "sd_es": "jackknife entre semillas (no desvío entre corridas independientes)",
        "media_de_metricas_individuales": media_ind,
        "ganancia_vs_media_de_metricas": {
            k: round(pleno["mean"][k] - media_ind[k], 5)
            for k in ("gral", "rmse", "nse", "kge") if np.isfinite(media_ind.get(k, np.nan))},
    }


def ensemble_configs(miembros: list[str], seeds, *, snapshot=None) -> dict:
    """B10.02: media entre configuraciones, apareada por semilla.

    ens_i = media entre miembros de la predicción con la semilla i; el resultado
    es media ± desvío de las S ens_i — la misma aritmética que una celda normal.
    """
    corridas = {m: predicciones_miembro(m, seeds, snapshot=snapshot) for m in miembros}
    ds0, splits0, _, _ = corridas[miembros[0]]
    va = splits0.val
    fechas0 = ds0.fecha[va]
    for m, (ds, splits, _, _) in corridas.items():
        if not np.array_equal(ds.fecha[splits.val].values, fechas0.values):
            raise ValueError(f"el VAL de {m!r} no está alineado con el de "
                             f"{miembros[0]!r}: no se puede promediar")

    evaluar = lambda p: _evaluate_split(ds0.Y[va], p, ds0.tau[va], ds0.horizons)
    por_semilla = []
    for i in range(len(seeds)):
        stack = np.stack([corridas[m][2][i] for m in miembros])
        por_semilla.append(evaluar(promedio_predicciones(stack)))

    media = {k: float(np.nanmean([r["mean"][k] for r in por_semilla]))
             for k in por_semilla[0]["mean"]}
    return {
        "val": {"mean": _con_sd(media, [r["mean"] for r in por_semilla]),
                "per_horizon": por_semilla[0]["per_horizon"],
                "per_seed": [r["mean"] for r in por_semilla]},
        "miembros": list(miembros), "n_miembros": len(miembros),
        "sd_es": "desvío entre semillas del ensemble apareado por semilla",
        "individuales": {m: {k: float(np.nanmean([mm[k] for mm in corridas[m][3]]))
                             for k in ("gral", "rmse", "nse", "kge", "v_plus", "v_minus")}
                         for m in miembros},
    }


# --------------------------------------------------------------------------
# CLI — la salida imita el esquema de train para que el runner la lea igual
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modo", choices=["semillas", "configs"], required=True)
    p.add_argument("--miembros", default=None,
                   help="semillas: UN miembro (default gral). configs: lista "
                        "separada por coma (default huber_log,per_horizon,"
                        "dinamica_caudal — los 3 mejores del ledger)")
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--seed", type=int, default=20260828)
    p.add_argument("--snapshot", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--no-test", action="store_true",
                   help="aceptado por compatibilidad con el runner: este módulo "
                        "nunca calcula TEST")
    args = p.parse_args(argv)
    _utf8_console()

    seeds = [args.seed + i for i in range(max(1, args.seeds))]
    t0 = time.perf_counter()
    if args.modo == "semillas":
        miembro = (args.miembros or "gral").strip()
        if "," in miembro:
            p.error("--modo semillas toma UN miembro")
        clave, cuerpo = "ens_semillas", ensemble_semillas(
            miembro, seeds, snapshot=args.snapshot)
        ds, splits, _, _ = predicciones_miembro(miembro, seeds, snapshot=args.snapshot)
    else:
        miembros = [m.strip() for m in
                    (args.miembros or "huber_log,per_horizon,dinamica_caudal").split(",")]
        desconocidos = [m for m in miembros if m not in MIEMBROS]
        if desconocidos:
            p.error(f"miembros desconocidos: {desconocidos}. Opciones: {list(MIEMBROS)}")
        clave, cuerpo = "ens_top3", ensemble_configs(
            miembros, seeds, snapshot=args.snapshot)
        ds, splits, _, _ = predicciones_miembro(miembros[0], seeds,
                                                snapshot=args.snapshot)

    resultados = {
        "modo": args.modo, "seeds": seeds, "espacio_promedio": "m3/s (evaluación)",
        "baselines": run_baselines(ds, splits, evaluar_test=False),
        "models": {clave: cuerpo},
        "splits": splits.describe(ds.fecha),
        "tiempo_s": round(time.perf_counter() - t0, 1),
    }
    manifest = data_mod.read_manifest(
        Path(args.snapshot) if args.snapshot else data_mod.DEFAULT_SNAPSHOT)
    resultados["snapshot"] = {
        "path": str(args.snapshot or data_mod.DEFAULT_SNAPSHOT),
        "delta_version": (manifest or {}).get("delta_version"),
        "sha256": ((manifest or {}).get("file_sha256") or "")[:12] or None,
    }

    m = cuerpo["val"]["mean"]
    print(f"\n  {clave} ({args.modo}) → gral {m['gral']:.4f} ± {m.get('gral_sd', 0):.4f}"
          f"   rmse {m['rmse']:.0f}   ({resultados['tiempo_s']} s)")
    if "ganancia_vs_media_de_metricas" in cuerpo:
        print(f"  vs media de métricas: {cuerpo['ganancia_vs_media_de_metricas']}")

    out_path = Path(args.out) if args.out else (
        data_mod.REPO_ROOT / "rio_search" / "results" / f"ensemble_{args.modo}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(resultados, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    print(f"  resultados → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
