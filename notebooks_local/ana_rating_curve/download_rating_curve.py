"""Descarga la curva de descarga (rating curve) y los aforos reales de una estacion
fluviometrica de la ANA, y arma un CSV cota(cm) -> vazao(m3/s) listo para calcular
el aforo a partir del nivel leido.

Fuente: ANA HidroWebService (misma API/autenticacion que notebooks/00_Landing/ANA_Hidrico/Daily_ANA.ipynb).
Endpoints confirmados leyendo el codigo fuente de pyHidroWeb (traduccion abierta de
hydroDataBR, MIT) porque no estan documentados de forma legible en el swagger publico:
  - GET /EstacoesTelemetricas/HidroSerieCurvaDescarga/v1     -> segmentos de curva-chave
  - GET /EstacoesTelemetricas/HidroSerieResumoDescarga/v1    -> aforos (medicoes reales)

La formula de la curva-chave segmentada (DNAEE/ANA, estandar de hidrometria brasileira)
es Q = A * (H - H0) ** N, con H y H0 en cm y Q en m3/s. Este script NO asume esa
convencion de unidades a ciegas: descarga tambien los aforos reales de la estacion y
elige entre "H0 en cm" vs "H0 en m" la que mejor reproduce los aforos medidos, dejando
el resultado de esa validacion en el reporte final.

Uso:
    Las credenciales se leen de USER_API_ANA / PASS_API_ANA, ya sea como variables de
    entorno o desde el archivo .env en la raiz del repo (mismas credenciales que
    Daily_ANA.ipynb en Databricks). El .env tiene prioridad mas baja: una variable de
    entorno ya seteada no se pisa.

    python download_rating_curve.py --station 74100000 --start 1950-01-01

Salidas (en ./output/):
    raw_json/curva_descarga_<station>_<start>_<end>.json   (uno por ventana de request)
    raw_json/aforos_<station>_<start>_<end>.json
    segmentos_curva_<station>.csv     Coeficientes de cada segmento de curva por vigencia
    aforos_<station>.csv              Aforos reales (cota, vazao medidos en campo)
    curva_aforo_<station>.csv         Tabla cota(cm)->vazao(m3/s) de la curva vigente
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://www.ana.gov.br/hidrowebservice"
LOGIN_ENDPOINT = "/EstacoesTelemetricas/OAUth/v1"
RATING_CURVE_ENDPOINT = "/EstacoesTelemetricas/HidroSerieCurvaDescarga/v1"
DISCHARGE_MEASUREMENTS_ENDPOINT = "/EstacoesTelemetricas/HidroSerieResumoDescarga/v1"
DEFAULT_TIMEOUT = 60
MAX_WINDOW_DAYS = 365  # la API rechaza ventanas > ~366 dias

OUTPUT_DIR = Path(__file__).parent / "output"
RAW_JSON_DIR = OUTPUT_DIR / "raw_json"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Carga variables desde un .env simple (KEY = "value"), sin pisar las que ya
    esten seteadas en el entorno. Parser manual porque python-dotenv no esta instalado
    en este entorno local y no vale la pena sumar la dependencia solo para esto."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()


class AnaApiError(RuntimeError):
    """Errores especificos del webservice de la ANA."""


def create_session() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def log_api_ana(session: requests.Session) -> str:
    usuario = os.environ.get("USER_API_ANA")
    password = os.environ.get("PASS_API_ANA")
    if not usuario or not password:
        raise AnaApiError(
            "Configura USER_API_ANA y PASS_API_ANA como variables de entorno "
            "(mismas credenciales que Daily_ANA.ipynb en Databricks)."
        )
    url = f"{BASE_URL}{LOGIN_ENDPOINT}"
    headers = {"Identificador": usuario, "Senha": password}
    response = session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    try:
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except (ValueError, requests.RequestException) as exc:
        raise AnaApiError(f"Error autenticando con ANA: {exc}") from exc
    try:
        token = payload["items"]["tokenautenticacao"]
    except (KeyError, TypeError) as exc:
        raise AnaApiError("La respuesta de login no contiene el token esperado") from exc
    if not isinstance(token, str) or not token:
        raise AnaApiError("Token de autenticacion vacio o invalido")
    return token


def date_windows(start: date, end: date, max_days: int = MAX_WINDOW_DAYS):
    """Parte [start, end] en ventanas de a lo sumo max_days dias (la API rechaza ventanas mayores)."""
    windows = []
    cur = start
    while cur <= end:
        window_end = min(end, date.fromordinal(cur.toordinal() + max_days))
        windows.append((cur, window_end))
        cur = date.fromordinal(window_end.toordinal() + 1)
    return windows


def _get_json(
    session: requests.Session,
    token: str,
    endpoint: str,
    params: dict[str, str],
) -> list[dict]:
    url = f"{BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    response = session.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
    try:
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except (ValueError, requests.RequestException) as exc:
        raise AnaApiError(f"Error consultando {endpoint}: {exc}") from exc
    items = payload.get("items")
    if items is None:
        return []
    if not isinstance(items, list):
        raise AnaApiError(f"Respuesta inesperada de {endpoint}: 'items' no es una lista")
    return items


def fetch_rating_curve_segments(
    session: requests.Session, token: str, station: str, start: date, end: date
) -> list[dict]:
    all_items: list[dict] = []
    for window_start, window_end in date_windows(start, end):
        params = {
            "Código da Estação": station,
            "Data Inicial (yyyy-MM-dd)": window_start.isoformat(),
            "Data Final (yyyy-MM-dd)": window_end.isoformat(),
        }
        items = _get_json(session, token, RATING_CURVE_ENDPOINT, params)
        RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)
        raw_path = RAW_JSON_DIR / f"curva_descarga_{station}_{window_start}_{window_end}.json"
        raw_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        if items:
            print(f"  curva-chave {window_start}..{window_end}: {len(items)} registros")
        all_items.extend(items)
        time.sleep(0.5)
    return all_items


def fetch_discharge_measurements(
    session: requests.Session, token: str, station: str, start: date, end: date
) -> list[dict]:
    all_items: list[dict] = []
    for window_start, window_end in date_windows(start, end):
        params = {
            "Código da Estação": station,
            "Tipo Filtro Data": "DATA_LEITURA",
            "Data Inicial (yyyy-MM-dd)": window_start.isoformat(),
            "Data Final (yyyy-MM-dd)": window_end.isoformat(),
        }
        items = _get_json(session, token, DISCHARGE_MEASUREMENTS_ENDPOINT, params)
        RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)
        raw_path = RAW_JSON_DIR / f"aforos_{station}_{window_start}_{window_end}.json"
        raw_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        if items:
            print(f"  aforos {window_start}..{window_end}: {len(items)} registros")
        all_items.extend(items)
        time.sleep(0.5)
    return all_items


# ---------------------------------------------------------------------------
# Normalizacion
# ---------------------------------------------------------------------------

def _num(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in ("", "NA", "NaN", "null", "None"):
        return None
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _first(record: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _parse_numero_curva(value) -> tuple[Optional[int], Optional[int]]:
    """'Numero_Curva' viene como "01/04" (segmento/total_segmentos)."""
    if value is None:
        return None, None
    text = str(value).strip()
    if "/" not in text:
        num = _num(text)
        return (int(num) if num is not None else None), None
    seg, _, total = text.partition("/")
    seg_num = _num(seg)
    total_num = _num(total)
    return (int(seg_num) if seg_num is not None else None), (int(total_num) if total_num is not None else None)


def normalize_rating_curve_segments(items: list[dict], station: str) -> pd.DataFrame:
    rows = []
    for item in items:
        # Nombres de campo confirmados contra la respuesta real de la API (no coinciden
        # con los candidatos de pyHidroWeb para este endpoint puntual; se dejan tambien
        # los candidatos originales por si la API cambia de convencion en el futuro).
        valid_from = _first(
            item, ("Periodo_Validade_Inicio", "DataInicio", "Data_Inicio", "InicioValidade", "DataValidadeInicial")
        )
        valid_to = _first(item, ("Periodo_Validade_Fim", "DataFim", "Data_Fim", "FimValidade", "DataValidadeFinal"))
        h0_raw = _num(_first(item, ("Coef_h0", "CoeficienteH0", "CoefH0", "H0")))
        segment_number, n_segments_reported = _parse_numero_curva(
            _first(item, ("Numero_Curva", "NumeroTrecho", "Numero_Trecho", "Trecho", "Segmento"))
        )
        rows.append(
            {
                "station_code": station,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "segment_number": segment_number,
                "n_segments_reported": n_segments_reported,
                "curve_type": _first(item, ("Tipo_Curva", "TipoCurva")),
                "equation_type": _first(item, ("Tipo_Equacao", "TipoEquacao", "Equacao")),
                "stage_min_cm": _num(_first(item, ("Cota_Minima", "CotaMinima", "CotaInicial"))),
                "stage_max_cm": _num(_first(item, ("Cota_Maxima", "CotaMaxima", "CotaFinal"))),
                "table_stage_step_cm": _num(_first(item, ("Tabela_Passo_Cota", "IntervaloCota", "PassoCota"))),
                "coefficient_a": _num(_first(item, ("Coef_a", "CoeficienteA", "CoefA", "A"))),
                "coefficient_h0_cm": h0_raw,
                "coefficient_n": _num(_first(item, ("Coef_n", "CoeficienteN", "CoefN", "N"))),
                "consistency_level": _first(item, ("Nivel_Consistencia", "NivelConsistencia")),
                "rating_curve_id": _first(item, ("CodigoCurva", "IdCurva", "IdentificadorCurva")),
                "raw": json.dumps(item, ensure_ascii=False),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["valid_from_dt"] = pd.to_datetime(df["valid_from"], errors="coerce", dayfirst=False)
    df["valid_to_dt"] = pd.to_datetime(df["valid_to"], errors="coerce", dayfirst=False)
    df["rating_curve_id"] = df["rating_curve_id"].fillna(
        df["station_code"].astype(str) + "_" + df["valid_from"].astype(str) + "_" + df["valid_to"].astype(str)
    )
    df = df.drop_duplicates(subset=["rating_curve_id", "segment_number", "stage_min_cm", "stage_max_cm"])
    return df.sort_values(["valid_from_dt", "segment_number"]).reset_index(drop=True)


def normalize_discharge_measurements(items: list[dict], station: str) -> pd.DataFrame:
    rows = []
    for item in items:
        rows.append(
            {
                "station_code": station,
                "measurement_datetime": _first(
                    item,
                    ("Data_Hora_Dado", "DataHoraDado", "Data_Hora_Medicao", "DataHoraMedicao", "DataMedicao", "Data"),
                ),
                "stage_cm": _num(_first(item, ("Cota", "Cota (cm)", "Cota_cm", "CotaMedida", "Nivel"))),
                "discharge_m3s": _num(
                    _first(item, ("Vazao", "Vazão", "Vazao (m3/s)", "Vazao_m3s", "VazaoMedida", "DescargaLiquida"))
                ),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["measurement_datetime"] = pd.to_datetime(df["measurement_datetime"], errors="coerce", dayfirst=False)
    df = df.dropna(subset=["stage_cm", "discharge_m3s"]).drop_duplicates()
    return df.sort_values("measurement_datetime").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Validacion de convencion de unidades + construccion de la tabla cota->vazao
# ---------------------------------------------------------------------------

def _predicted_discharge(stage_cm: float, a: float, h0_cm: float, n: float, h0_in_meters: bool) -> Optional[float]:
    if h0_in_meters:
        delta = (stage_cm / 100.0) - (h0_cm / 100.0)
    else:
        delta = stage_cm - h0_cm
    if delta <= 0 or a is None or n is None:
        return None
    try:
        return a * (delta**n)
    except (ValueError, OverflowError):
        return None


def _segment_for_stage(segments: pd.DataFrame, stage_cm: float, at: Optional[pd.Timestamp]):
    candidates = segments
    if at is not None:
        active = candidates[
            (candidates["valid_from_dt"].isna() | (candidates["valid_from_dt"] <= at))
            & (candidates["valid_to_dt"].isna() | (candidates["valid_to_dt"] >= at))
        ]
        if not active.empty:
            candidates = active
    in_range = candidates[
        (candidates["stage_min_cm"].isna() | (candidates["stage_min_cm"] <= stage_cm))
        & (candidates["stage_max_cm"].isna() | (candidates["stage_max_cm"] >= stage_cm))
    ]
    if in_range.empty:
        return None
    return in_range.iloc[0]


def evaluate_h0_convention(segments: pd.DataFrame, measurements: pd.DataFrame, h0_in_meters: bool) -> dict:
    errors = []
    matched = 0
    for _, row in measurements.iterrows():
        segment = _segment_for_stage(segments, row["stage_cm"], row["measurement_datetime"])
        if segment is None:
            continue
        predicted = _predicted_discharge(
            row["stage_cm"], segment["coefficient_a"], segment["coefficient_h0_cm"], segment["coefficient_n"], h0_in_meters
        )
        if predicted is None or predicted <= 0 or row["discharge_m3s"] in (None, 0):
            continue
        matched += 1
        errors.append(abs(predicted - row["discharge_m3s"]) / row["discharge_m3s"])
    if matched == 0:
        return {"h0_in_meters": h0_in_meters, "matched": 0, "mape": None}
    return {"h0_in_meters": h0_in_meters, "matched": matched, "mape": sum(errors) / len(errors)}


def choose_active_curve(segments: pd.DataFrame) -> pd.DataFrame:
    """Elige el grupo de segmentos (rating_curve_id) vigente hoy, o el mas reciente."""
    today = pd.Timestamp(date.today())
    open_ended = segments[segments["valid_to_dt"].isna()]
    if not open_ended.empty:
        latest_start = open_ended["valid_from_dt"].max()
        active_id = open_ended[open_ended["valid_from_dt"] == latest_start]["rating_curve_id"].iloc[0]
    else:
        containing = segments[(segments["valid_from_dt"] <= today) & (segments["valid_to_dt"] >= today)]
        pool = containing if not containing.empty else segments
        latest_start = pool["valid_from_dt"].max()
        active_id = pool[pool["valid_from_dt"] == latest_start]["rating_curve_id"].iloc[0]
    return segments[segments["rating_curve_id"] == active_id].sort_values("stage_min_cm").reset_index(drop=True)


def build_stage_discharge_table(active_segments: pd.DataFrame, h0_in_meters: bool, step_cm: float) -> pd.DataFrame:
    rows = []
    for _, seg in active_segments.iterrows():
        stage_min = seg["stage_min_cm"]
        stage_max = seg["stage_max_cm"]
        if pd.isna(stage_min) or pd.isna(stage_max):
            continue
        stage = stage_min
        while stage <= stage_max + 1e-9:
            q = _predicted_discharge(stage, seg["coefficient_a"], seg["coefficient_h0_cm"], seg["coefficient_n"], h0_in_meters)
            rows.append(
                {
                    "cota_cm": round(stage, 2),
                    "cota_m": round(stage / 100.0, 4),
                    "vazao_m3s": None if q is None else round(q, 3),
                    "rating_curve_id": seg["rating_curve_id"],
                    "segment_number": seg["segment_number"],
                    "vigencia_inicio": seg["valid_from"],
                    "vigencia_fin": seg["valid_to"],
                    "coeficiente_a": seg["coefficient_a"],
                    "coeficiente_h0_cm": seg["coefficient_h0_cm"],
                    "coeficiente_n": seg["coefficient_n"],
                }
            )
            stage += step_cm
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--station", default="74100000", help="Codigo de estacion ANA (default: 74100000, Irai)")
    parser.add_argument("--start", default="1950-01-01", help="Fecha inicial de busqueda (yyyy-mm-dd)")
    parser.add_argument("--end", default=None, help="Fecha final de busqueda (yyyy-mm-dd), default hoy")
    parser.add_argument("--step-cm", type=float, default=1.0, help="Paso de cota en cm para la tabla final")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = create_session()
    token = log_api_ana(session)

    print(f"Descargando curva de descarga de la estacion {args.station} ({start}..{end})...")
    curve_items = fetch_rating_curve_segments(session, token, args.station, start, end)
    print(f"Descargando aforos (medicoes reales) de la estacion {args.station} ({start}..{end})...")
    measurement_items = fetch_discharge_measurements(session, token, args.station, start, end)

    segments = normalize_rating_curve_segments(curve_items, args.station)
    measurements = normalize_discharge_measurements(measurement_items, args.station)

    if segments.empty:
        raise SystemExit(
            "No se encontraron segmentos de curva de descarga para esta estacion/rango. "
            "Revisa los JSON crudos en output/raw_json/ para ver la respuesta cruda de la API."
        )

    segments.drop(columns=["raw"]).to_csv(OUTPUT_DIR / f"segmentos_curva_{args.station}.csv", index=False)
    measurements.to_csv(OUTPUT_DIR / f"aforos_{args.station}.csv", index=False)
    print(f"\n{len(segments)} segmentos de curva y {len(measurements)} aforos guardados en {OUTPUT_DIR}")

    cm_eval = evaluate_h0_convention(segments, measurements, h0_in_meters=False)
    m_eval = evaluate_h0_convention(segments, measurements, h0_in_meters=True)
    print("\nValidacion de la formula Q = A * (H - H0) ** N contra aforos reales:")
    print(f"  H0 en cm: {cm_eval['matched']} aforos comparados, error medio absoluto = {cm_eval['mape']}")
    print(f"  H0 en m : {m_eval['matched']} aforos comparados, error medio absoluto = {m_eval['mape']}")

    candidates = [e for e in (cm_eval, m_eval) if e["mape"] is not None]
    if candidates:
        best = min(candidates, key=lambda e: e["mape"])
        print(f"  -> Convencion elegida: H0 en {'m' if best['h0_in_meters'] else 'cm'} (menor error vs aforos reales)")
        h0_in_meters = best["h0_in_meters"]
    else:
        print("  -> No hay aforos suficientes para validar; se asume H0 en cm (convencion estandar DNAEE/ANA).")
        h0_in_meters = False

    active_segments = choose_active_curve(segments)
    print(
        f"\nCurva vigente: rating_curve_id={active_segments['rating_curve_id'].iloc[0]!r}, "
        f"vigente desde {active_segments['valid_from'].iloc[0]} hasta {active_segments['valid_to'].iloc[0]}, "
        f"{len(active_segments)} segmento(s)."
    )

    table = build_stage_discharge_table(active_segments, h0_in_meters, args.step_cm)
    out_path = OUTPUT_DIR / f"curva_aforo_{args.station}.csv"
    table.to_csv(out_path, index=False)
    print(f"\nTabla cota->vazao escrita en: {out_path} ({len(table)} filas)")
    print(
        "\nIMPORTANTE: esta tabla usa solo la curva vigente al momento de la descarga. "
        "Cruzala contra el informe tecnico del SGB-CPRM / Portal HidroWeb para confirmar "
        "coeficientes y vigencia, especialmente porque Irai (74100000) esta bajo influencia "
        "directa de la UHE Foz do Chapeco (regimen no natural, la curva puede requerir "
        "recalibraciones mas frecuentes que una estacion en regimen natural)."
    )


if __name__ == "__main__":
    try:
        main()
    except AnaApiError as exc:
        raise SystemExit(f"✗ {exc}")
