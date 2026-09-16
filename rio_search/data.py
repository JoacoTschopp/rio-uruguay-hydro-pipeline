"""Carga del snapshot Gold, features, targets y splits temporales.

Lee el parquet exportado por `notebooks_local/gold_export/export_gold_dataset.py`
(`weather.gold.training_dataset_v0`). No habla con Databricks: trabaja sobre el
snapshot local ya verificado por sha256 contra su manifest.

La política de split es `rolling_365` con embargo, tal como la define
`docs/rio_search_plan.md` §3.6:

    anchor = último día con target observable  (= fecha_max − max(horizontes))
    TEST   = (anchor − 365, anchor]
    VAL    = (anchor − 730 − e, anchor − 365 − e]
    TRAIN  = [train_start, anchor − 730 − 2e]

con `e = embargo_days` (14 por defecto, = horizonte máximo) para que ningún
target de un split caiga dentro del período de inputs del siguiente.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = ["HORIZONS", "FEATURE_GROUPS", "Dataset", "Splits",
           "load_snapshot", "build_dataset", "make_splits", "REPO_ROOT",
           "DEFAULT_SNAPSHOT", "LEGACY_SNAPSHOT", "DEFAULT_GROUPS",
           "MIN_DELTA_VERSION", "read_manifest", "Fold", "make_walkforward_folds",
           "make_sequences", "with_lookback"]

REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE = REPO_ROOT / "notebooks_local" / "gold_export" / "cache"

#: Snapshot por defecto: el parquet que baja `export_gold_dataset.py` del Volume.
#: Verificado el 2026-08-30 contra un pull directo por SQL de Gold v278 — las 53
#: columnas numéricas coinciden exactamente, así que el camino normal sirve.
DEFAULT_SNAPSHOT = _CACHE / "training_dataset_v0.parquet"

#: Snapshot anterior a las Decisiones 039/040, conservado para poder medir cuánto
#: se movieron los resultados con la corrección del target.
LEGACY_SNAPSHOT = _CACHE / "training_dataset_v0_PRE039.parquet"

#: Piso de versión Delta aceptada. 278 es la primera que incorpora la corrección
#: de telemetría (Decisión 039) y la salida del nivel (Decisión 040). Sólo se
#: sube cuando otra corrección cambie los valores del target: es un piso de
#: validez del dato, no un "última versión conocida".
MIN_DELTA_VERSION = 278

#: Horizontes de pronóstico, en días.
HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)

#: Grupos de features. El estado del punto de predicción y el agregado de la
#: sub-cuenca `alta_frontera` van por defecto (Decisión 018 restringe el alcance
#: a la cuenca alta). Las derivadas de lluvia se construyen acá porque Gold sólo
#: tiene la suma cruda sobre un número variable de estaciones.
FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "caudal_estado": (
        "caudal_actual_m3s", "caudal_lag_1d", "caudal_lag_3d", "caudal_lag_7d",
        "caudal_media_3d", "caudal_media_7d", "caudal_delta_1d",
    ),
    # El grupo `nivel_estado` se eliminó: la Decisión 040 sacó las 17 columnas de
    # nivel de Gold. El caudal es función determinista del nivel vía curva de
    # aforo, así que no aportaban información — y las 8 columnas futuras eran fuga
    # directa del target por la monotonía de la curva. El nivel sigue completo en
    # `weather.silver.river_levels_daily` si alguna vez hace falta por JOIN.
    "caudal_agregado_alta_frontera": (
        "caudal_agregado_alta_frontera_m3s",
        "caudal_agregado_alta_frontera_lag_1d",
        "caudal_agregado_alta_frontera_lag_2d",
        "caudal_agregado_alta_frontera_lag_3d",
        "caudal_agregado_alta_frontera_confiable_pct",
    ),
    "lluvia_ratio": (
        "lluvia_media_est_mm", "lluvia_media_est_acum_3d",
        "lluvia_media_est_acum_7d", "lluvia_media_est_acum_10d",
        "lluvia_media_est_acum_30d",
    ),
    # Grilla CPTEC (Decisión 033). Es media areal real, no una suma sobre un
    # número variable de estaciones: es la fuente estacionaria que el informe de
    # la función de ganancia recomendaba para el modulador.
    "cptec_grid": (
        "lluvia_merge_alta_frontera_mm", "lluvia_merge_alta_frontera_max_mm",
        "lluvia_merge_alta_frontera_acum_3d_mm", "lluvia_merge_alta_frontera_acum_7d_mm",
        "temp_samet_alta_frontera_media_c", "temp_samet_alta_frontera_max_c",
        "temp_samet_alta_frontera_min_c",
    ),
    # Índice de precipitación antecedente (B2.12): memoria exponencial de la
    # lluvia con tres constantes de decaimiento. Se construye en `_derive_rain`.
    "lluvia_api": ("api_k085", "api_k090", "api_k095"),
    "estacionalidad": ("doy_sin", "doy_cos"),
}

#: Grupos por defecto. `cptec_grid` queda fuera para que el default reproduzca
#: exactamente el experimento del informe; se activa con --groups.
DEFAULT_GROUPS = ("caudal_estado", "caudal_agregado_alta_frontera",
                  "lluvia_ratio", "estacionalidad")


@dataclass
class Dataset:
    """Matriz de features, targets por horizonte y la serie τ, ya alineados."""

    fecha: pd.DatetimeIndex
    X: np.ndarray                 # (n, n_features)
    Y: np.ndarray                 # (n, n_horizons)
    q_actual: np.ndarray          # (n,) caudal en t, para los baselines
    tau: np.ndarray               # (n,)
    feature_names: list[str]
    horizons: tuple[int, ...]
    tau_mode: str

    def __len__(self) -> int:
        return len(self.fecha)

    def subset(self, mask) -> "Dataset":
        """Nuevo Dataset con las filas de `mask`. Para alinear dos moduladores."""
        mask = np.asarray(mask, bool)
        return Dataset(
            fecha=self.fecha[mask], X=self.X[mask], Y=self.Y[mask],
            q_actual=self.q_actual[mask], tau=self.tau[mask],
            feature_names=list(self.feature_names), horizons=self.horizons,
            tau_mode=self.tau_mode,
        )

    def align_to(self, other: "Dataset") -> tuple["Dataset", "Dataset"]:
        """Recorta ambos Dataset a las fechas que tienen en común.

        Hace falta porque cada modo de modulador filtra distinto: `oracle` pierde la
        cola de la serie (no hay lluvia futura que mirar) y `antecedent` pierde
        el arranque. Sin alinear, comparar τ entre modos desalinearía las filas
        en silencio, que es la peor clase de error en una evaluación.
        """
        common = self.fecha.intersection(other.fecha)
        return self.subset(self.fecha.isin(common)), other.subset(other.fecha.isin(common))


@dataclass
class Splits:
    train: np.ndarray
    val: np.ndarray
    test: np.ndarray

    def describe(self, fecha: pd.DatetimeIndex) -> dict:
        out = {}
        for name in ("train", "val", "test"):
            idx = getattr(self, name)
            out[name] = {
                "n": int(idx.sum()),
                "desde": str(fecha[idx].min().date()) if idx.any() else None,
                "hasta": str(fecha[idx].max().date()) if idx.any() else None,
            }
        return out


def load_snapshot(path: Path | str | None = None,
                  punto: str = "ana_74100000",
                  permitir_legacy: bool = False) -> pd.DataFrame:
    """Lee el parquet del snapshot y lo devuelve en calendario diario continuo.

    `permitir_legacy=True` desactiva la guarda de esquema. Sólo para comparar a
    propósito contra el snapshot previo a las Decisiones 039/040.
    """
    path = Path(path) if path is not None else DEFAULT_SNAPSHOT
    if not path.exists():
        raise FileNotFoundError(
            f"no está el snapshot Gold en {path}. Correr "
            "notebooks_local/gold_export/export_gold_dataset.py primero."
        )
    df = pd.read_parquet(path)
    if not permitir_legacy:
        _assert_schema_vigente(df, path)
        _assert_manifest_vigente(path)
    if "punto_prediccion" in df.columns and punto:
        df = df[df["punto_prediccion"] == punto]
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha").set_index("fecha").asfreq("D")
    return df


def _assert_schema_vigente(df: pd.DataFrame, path: Path) -> None:
    """Falla si el snapshot es anterior a las Decisiones 039/040.

    Existe porque el modo de fallar de un snapshot viejo es silencioso y caro: el
    parquet carga, el entrenamiento corre y los números salen — calculados contra
    valores de caudal que Gold ya corrigió. Un `KeyError` tardío sería mejor que
    eso, y un error explícito acá es mejor todavía.
    """
    nivel = [c for c in df.columns if "nivel" in c]
    if nivel:
        raise ValueError(
            f"{path.name} tiene {len(nivel)} columnas de nivel: es anterior a la "
            "Decisión 040 y sus valores de caudal 2019-2026 son previos a la "
            "corrección de telemetría de la Decisión 039 (85,5 % de esos días "
            "cambiaron). Regenerar con Export_Gold_Snapshot y volver a bajar, o "
            "correr `export_gold_dataset.py --refresh`. "
            "Para comparar a propósito contra el snapshot viejo, "
            "usar `load_snapshot(LEGACY_SNAPSHOT, permitir_legacy=True)`."
        )


def read_manifest(path: Path) -> dict | None:
    """Manifest que acompaña al parquet, o None si no es el que lo describe.

    El manifest sólo aplica al archivo que él mismo nombra en `file_name`; para
    cualquier otro parquet del mismo directorio (el legacy, un export puntual)
    devuelve None en vez de comparar cosas que no se corresponden.
    """
    m_path = path.parent / "manifest.json"
    if not m_path.exists():
        return None
    try:
        manifest = json.loads(m_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return manifest if manifest.get("file_name") == path.name else None


def _assert_manifest_vigente(path: Path) -> None:
    """Falla si los **valores** del snapshot son viejos, aunque el esquema esté bien.

    `_assert_schema_vigente` sólo ve columnas que no deberían estar. Queda un
    hueco: un snapshot con el esquema correcto pero con los valores de caudal
    previos a la corrección de telemetría de la Decisión 039 pasa esa guarda sin
    ruido. Es exactamente lo que pasó entre el 28 y el 30 de agosto de 2026, y lo
    insidioso es que el manifest guarda la `delta_version` **del momento del
    export**: un snapshot viejo se ve internamente consistente y nada delata el
    desfasaje salvo compararlo contra algo externo.

    Acá ese algo externo es `MIN_DELTA_VERSION`, un piso fijo en el repo, para no
    tener que hablar con Databricks desde la capa de datos. Cubre el caso de
    quedarse atrás; no cubre el de Gold avanzando por delante — de eso avisa
    `export_gold_dataset.py` (Decisión 042), que sí consulta la historia de la tabla.
    """
    manifest = read_manifest(path)
    if manifest is None:
        return

    version = manifest.get("delta_version")
    if isinstance(version, int) and version < MIN_DELTA_VERSION:
        raise ValueError(
            f"{path.name} es delta {version} y el piso es {MIN_DELTA_VERSION}: sus "
            "valores de caudal 2019-2026 son previos a la corrección de telemetría "
            "de la Decisión 039 (cambió el 85,5 % de esos días). El esquema puede "
            "verse bien igual — por eso este chequeo existe aparte del de columnas. "
            "Correr `export_gold_dataset.py --refresh`."
        )

    esperado = manifest.get("file_sha256")
    if esperado:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for bloque in iter(lambda: fh.read(1 << 20), b""):
                h.update(bloque)
        if h.hexdigest() != esperado:
            raise ValueError(
                f"{path.name} no coincide con el sha256 de su manifest: el parquet "
                "y el manifest describen datos distintos, así que la delta_version "
                "que informa no es confiable. Correr `export_gold_dataset.py --refresh`."
            )


def _derive_rain(df: pd.DataFrame) -> pd.DataFrame:
    """Lluvia media por estación y sus acumulados.

    `lluvia_acumulada_mm` es la SUMA sobre las estaciones que reportaron ese día
    y `station_count` va de 0 a 177 según la época, así que la serie cruda no es
    estacionaria y no sirve ni como feature ni para el modulador. La media por
    estación sí lo es. Es la transform `ratio` prevista en el plan §3.6.
    """
    out = df.copy()
    count = out["lluvia_agregado_alta_frontera_station_count"].replace(0, np.nan)
    out["lluvia_media_est_mm"] = out["lluvia_acumulada_mm"] / count
    base = out["lluvia_media_est_mm"]
    for w in (3, 7, 10, 30):
        out[f"lluvia_media_est_acum_{w}d"] = base.rolling(w, min_periods=max(1, int(0.8 * w))).sum()
    # Índice de precipitación antecedente (Kohler & Linsley 1951), B2.12:
    # API(t) = k·API(t−1) + P(t) = Σ k^i·P(t−i). Es la memoria exponencial de la
    # lluvia — la misma señal de humedad que el modulador resume en A(t), ofrecida
    # al modelo como feature. Se calcula con la definición literal de la
    # recursión (el ewm de pandas arranca distinto, así que se escribe literal).
    # Un hueco de P cuenta como 0 dentro de la recursión (mismo criterio que un
    # acumulado con cobertura parcial) y el arranque en frío queda NaN los
    # primeros 30 días — la ventana más larga de los acumulados — para no
    # inventar sequía donde sólo falta historia.
    p_api = base.fillna(0.0).to_numpy(dtype=float)
    for k in (0.85, 0.90, 0.95):
        api = np.empty_like(p_api)
        acc = 0.0
        for i, v in enumerate(p_api):
            acc = k * acc + v
            api[i] = acc
        api[:30] = np.nan
        out[f"api_k{int(round(k * 100)):03d}"] = api
    doy = out.index.dayofyear.to_numpy(dtype=float)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return out


def build_dataset(
    df: pd.DataFrame | None = None,
    *,
    groups: tuple[str, ...] = DEFAULT_GROUPS,
    horizons: tuple[int, ...] = HORIZONS,
    target: str = "caudal",
    tau_mode: str = "oracle",
    gate_params=None,
    gate_rain_col: str = "auto",
    snapshot_path: Path | str | None = None,
    permitir_legacy: bool = False,
) -> Dataset:
    """Arma features, targets y τ desde el snapshot.

    Se descartan las filas sin caudal actual o sin ninguna feature; los NaN
    restantes se imputan más tarde, con estadísticos de TRAIN únicamente
    (ver `rio_search.train`).
    """
    from . import gate as gate_mod

    # Validar el argumento antes de hacer trabajo: la Decisión 040 dejó a Gold
    # con un solo target.
    if target != "caudal":
        raise ValueError(
            "Gold tiene un solo target desde la Decisión 040: el caudal. "
            "El nivel sigue en weather.silver.river_levels_daily (es un JOIN)."
        )

    if df is None:
        df = load_snapshot(snapshot_path, permitir_legacy=permitir_legacy)
    df = _derive_rain(df)

    feature_names: list[str] = []
    for g in groups:
        if g not in FEATURE_GROUPS:
            raise KeyError(f"grupo de features desconocido: {g}")
        feature_names.extend(FEATURE_GROUPS[g])
    missing = [c for c in feature_names if c not in df.columns]
    if missing:
        raise KeyError(f"faltan columnas en el snapshot: {missing}")

    # Invariante del modulador: nada que mire al futuro del target.
    gate_mod.assert_causal(feature_names)

    target_cols = [f"caudal_t_mas_{h}d" for h in horizons]
    missing_t = [c for c in target_cols if c not in df.columns]
    if missing_t:
        raise KeyError(f"faltan targets en el snapshot: {missing_t}")

    params = gate_params if gate_params is not None else gate_mod.DEFAULT_PARAMS
    # Fuente de lluvia del modulador. MERGE de CPTEC es media areal de grilla y por
    # eso es preferible: la media por estación sigue dependiendo de qué
    # pluviómetros reportaron ese día. `auto` usa MERGE si la columna existe.
    if gate_rain_col == "auto":
        gate_rain_col = ("lluvia_merge_alta_frontera_mm"
                         if "lluvia_merge_alta_frontera_mm" in df.columns
                         else "lluvia_media_est_mm")
    if gate_rain_col not in df.columns:
        raise KeyError(f"la fuente de lluvia del modulador no está en el snapshot: {gate_rain_col}")
    gate_mod.assert_causal([gate_rain_col])
    # Modo forecast (B8.05): el único operable que usa futuro. La fila t trae el
    # pronóstico ECMWF emitido en t para t+1..t+15; el modulador consume los
    # primeros fc_days leads. Donde el pronóstico no existe (antes de 2006-11 y
    # el hueco de 2017), τ queda NaN y la fila se filtra como cualquier otra.
    forecast_rain = None
    if tau_mode == "forecast":
        fc_cols = [f"ecmwf_cf_tp_mm_d{k}" for k in range(1, params.fc_days + 1)]
        faltan_fc = [c for c in fc_cols if c not in df.columns]
        if faltan_fc:
            raise KeyError(
                "tau_mode='forecast' necesita las columnas de pronóstico de Gold "
                f"(Fase 4 del roadmap): faltan {faltan_fc}")
        gate_mod.assert_causal(fc_cols)
        forecast_rain = df[fc_cols].to_numpy(dtype=float)
    gate_out = gate_mod.build_tau(df[gate_rain_col].to_numpy(),
                                  forecast_rain=forecast_rain,
                                  mode=tau_mode, params=params)

    q_col = "caudal_actual_m3s"
    X = df[feature_names].to_numpy(dtype=float)
    Y = df[target_cols].to_numpy(dtype=float)
    q_actual = df[q_col].to_numpy(dtype=float)
    tau = gate_out["tau"]

    # Una fila sirve si tiene el estado actual y al menos un target observable.
    usable = np.isfinite(q_actual) & np.isfinite(Y).any(axis=1) & np.isfinite(tau)
    return Dataset(
        fecha=df.index[usable],
        X=X[usable],
        Y=Y[usable],
        q_actual=q_actual[usable],
        tau=tau[usable],
        feature_names=feature_names,
        horizons=tuple(horizons),
        tau_mode=f"{tau_mode}:{gate_rain_col.replace('_alta_frontera','').replace('lluvia_','')}",
    )


def make_sequences(ds: Dataset, lookback: int) -> tuple[Dataset, np.ndarray]:
    """Tensores causales (N, L, F): la ventana de la fila i cubre [t_i-L+1, t_i].

    B2.17, y prerrequisito de todo B4 secuencial. La ventana se arma sobre el
    calendario diario continuo entre la primera y la última fecha del Dataset:
    los días que `build_dataset` filtró (sin caudal actual, sin target, sin τ)
    entran como NaN y los imputa después el `Preprocessor` con estadísticos de
    TRAIN, igual que cualquier otro NaN. Sólo se descartan las filas cuya
    ventana se saldría del calendario por el arranque.

    Devuelve el Dataset recortado a las filas con ventana completa y el tensor
    alineado fila a fila. El eje L va de lo más viejo a lo más nuevo:
    `seq[i, -1] == X[i]` — la ventana termina en t, nunca lo cruza.
    """
    if lookback < 1:
        raise ValueError(f"lookback debe ser >= 1, vino {lookback}")
    cal = pd.date_range(ds.fecha.min(), ds.fecha.max(), freq="D")
    pos = cal.get_indexer(ds.fecha)
    X_cal = np.full((len(cal), ds.X.shape[1]), np.nan)
    X_cal[pos] = ds.X
    keep = pos >= lookback - 1
    ventanas = pos[keep][:, None] + np.arange(-(lookback - 1), 1)[None, :]
    return ds.subset(keep), X_cal[ventanas]


def with_lookback(ds: Dataset, lookback: int) -> Dataset:
    """El mismo Dataset con la ventana aplanada en X: (N, L·F), para el MLP.

    Los modelos secuenciales de B4 consumen `make_sequences` tal cual; el MLP
    la consume aplanada. El orden de las columnas va de lo más viejo a lo más
    nuevo: las últimas F columnas son las features originales del día t
    (sufijo `_tm0`, "t menos 0").
    """
    rec, seq = make_sequences(ds, lookback)
    nombres = [f"{n}_tm{lookback - 1 - j}"
               for j in range(lookback) for n in ds.feature_names]
    return Dataset(
        fecha=rec.fecha, X=seq.reshape(len(rec), -1), Y=rec.Y,
        q_actual=rec.q_actual, tau=rec.tau, feature_names=nombres,
        horizons=rec.horizons, tau_mode=rec.tau_mode,
    )


@dataclass
class Fold:
    """Un corte del walk-forward: un año de TEST con su VAL y TRAIN previos."""

    nombre: str                   # el año que se prueba, p. ej. "2024"
    ventana: str                  # "expandible" | "deslizante"
    splits: Splits
    anio_test: int
    parcial: bool                 # True si el año de TEST está incompleto

    def describe(self, fecha: pd.DatetimeIndex) -> dict:
        out = {"fold": self.nombre, "ventana": self.ventana,
               "anio_test": self.anio_test, "parcial": self.parcial}
        out.update(self.splits.describe(fecha))
        return out


def make_walkforward_folds(
    fecha: pd.DatetimeIndex, *,
    n_folds: int = 5,
    ventana: str = "expandible",
    train_years: int = 10,
    embargo_days: int = 14,
    train_start: str | None = None,
) -> list[Fold]:
    """Cortes temporales año a año, caminando hacia adelante.

    Cada fold prueba **un año calendario** y usa el año anterior como VAL (que es
    lo que consume la búsqueda de hiperparámetros y el early stopping). Lo que
    cambia entre modos es de dónde sale TRAIN:

    - ``expandible``: desde `train_start` hasta el borde de VAL. El train crece
      fold a fold y usa toda la historia disponible.
    - ``deslizante``: los últimos `train_years` años antes de VAL. El train
      mantiene largo fijo y va olvidando el pasado lejano.

    Comparar los dos modos es lo que responde si la historia vieja aporta o
    estorba: si gana expandible, aporta; si gana deslizante, el río cambió lo
    suficiente como para que el pasado lejano confunda.

    Entre TRAIN y VAL, y entre VAL y TEST, va un embargo de `embargo_days` para
    que ningún target de un split caiga dentro del período de inputs del
    siguiente.

    El último año suele estar incompleto (la serie corta a mitad de año); queda
    marcado con `parcial=True` porque su TEST es más corto y más ruidoso.
    """
    if ventana not in ("expandible", "deslizante"):
        raise ValueError(f"ventana desconocida: {ventana!r}")

    fecha = pd.DatetimeIndex(fecha)
    e = pd.Timedelta(days=embargo_days)
    anio_max = int(fecha.max().year)
    anios_test = list(range(anio_max - n_folds + 1, anio_max + 1))
    piso = pd.Timestamp(train_start) if train_start else fecha.min()

    folds: list[Fold] = []
    for anio in anios_test:
        test_lo = pd.Timestamp(year=anio, month=1, day=1)
        test_hi = pd.Timestamp(year=anio, month=12, day=31)
        val_lo = pd.Timestamp(year=anio - 1, month=1, day=1)
        val_hi = test_lo - e
        train_hi = val_lo - e
        train_lo = (piso if ventana == "expandible"
                    else max(piso, train_hi - pd.DateOffset(years=train_years)))

        splits = Splits(
            train=(fecha >= train_lo) & (fecha <= train_hi),
            val=(fecha >= val_lo) & (fecha <= val_hi),
            test=(fecha >= test_lo) & (fecha <= test_hi),
        )
        if splits.train.sum() == 0 or splits.val.sum() == 0 or splits.test.sum() == 0:
            continue
        folds.append(Fold(
            nombre=str(anio), ventana=ventana, splits=splits, anio_test=anio,
            parcial=bool(fecha[splits.test].max() < test_hi - pd.Timedelta(days=30)),
        ))
    return folds


def make_splits(fecha: pd.DatetimeIndex, *, embargo_days: int = 14,
                test_days: int = 365, val_days: int = 365,
                train_start: str | None = None) -> Splits:
    """Split `rolling_365` con embargo. Devuelve máscaras booleanas."""
    fecha = pd.DatetimeIndex(fecha)
    anchor = fecha.max()
    e = pd.Timedelta(days=embargo_days)
    td_test = pd.Timedelta(days=test_days)
    td_val = pd.Timedelta(days=val_days)

    test_lo, test_hi = anchor - td_test, anchor
    val_hi = test_lo - e
    val_lo = val_hi - td_val
    train_hi = val_lo - e
    train_lo = pd.Timestamp(train_start) if train_start else fecha.min()

    return Splits(
        train=(fecha >= train_lo) & (fecha <= train_hi),
        val=(fecha > val_lo) & (fecha <= val_hi),
        test=(fecha > test_lo) & (fecha <= test_hi),
    )
