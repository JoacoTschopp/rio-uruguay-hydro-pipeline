"""Backfill historico de temperatura INMET para las estaciones automaticas de la cuenca.

Descarga un ZIP anual (portal.inmet.gov.br/uploads/dadoshistoricos/{AAAA}.zip, 2000-2026
confirmados, ~100 MB c/u, requiere User-Agent de navegador -- ver docs/data_sources.md #9.3),
extrae en memoria solo los CSV de las estaciones de estaciones_inmet_catalogo.json (generado
por fetch_station_catalog.py) y escribe un JSON por estacion/anio en output_json/, listo para
que ETL_Bronze_INMET.ipynb lo lea con schema forzado (mismo patron que
notebooks_local/ana_historic_backfill/run_backfill_local.py).

El ZIP se borra despues de procesarlo (no se guardan ~2.6 GB en disco de forma permanente).
Solo se conservan filas con temperatura no nula: esta tabla Bronze es especifica de
temperatura, no un passthrough crudo generico.

Resumible via inmet_backfill_state.json (anio -> done/failed). Usa el lock compartido de
ana_historic_backfill para no correr en paralelo con otro backfill local.

Uso:
    python download_inmet_zips.py [--from-year 2000] [--to-year 2026] [--pause-seconds 3]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

import requests

LOCAL_DIR = Path(__file__).parent
STATIONS_FILE = LOCAL_DIR / "estaciones_inmet_catalogo.json"
STATE_FILE = LOCAL_DIR / "inmet_backfill_state.json"
OUTPUT_DIR = LOCAL_DIR / "output_json"

ANA_BACKFILL_DIR = LOCAL_DIR.parent / "ana_historic_backfill"
sys.path.insert(0, str(ANA_BACKFILL_DIR))
import lock  # noqa: E402  (notebooks_local/ana_historic_backfill/lock.py, reusado)

ZIP_URL_TEMPLATE = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{year}.zip"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 120
METADATA_LINES = 8  # REGIAO/UF/ESTACAO/CODIGO/LATITUDE/LONGITUDE/ALTITUDE/DATA_FUNDACAO


def load_stations() -> list[dict]:
    if not STATIONS_FILE.exists():
        raise RuntimeError(f"No existe {STATIONS_FILE}; corre fetch_station_catalog.py primero")
    return json.loads(STATIONS_FILE.read_text(encoding="utf-8"))


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"years": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_decimal(raw: str) -> float | None:
    raw = raw.strip()
    if not raw or raw == "-9999":
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def parse_station_csv(raw_bytes: bytes, codigo_estacao: str, source_file: str) -> list[dict]:
    text = raw_bytes.decode("latin-1")
    lines = text.splitlines()
    if len(lines) <= METADATA_LINES + 1:
        return []

    header = lines[METADATA_LINES].split(";")
    temp_idx = next((i for i, h in enumerate(header) if "BULBO SECO" in h.upper()), None)
    if temp_idx is None:
        return []

    records = []
    for line in lines[METADATA_LINES + 1:]:
        if not line.strip():
            continue
        fields = line.split(";")
        if len(fields) <= temp_idx:
            continue
        data_str = fields[0].strip().replace('/', '-')  # INMET cambia el separador a partir de 2019
        hora_str = fields[1].strip()
        temp_c = parse_decimal(fields[temp_idx])
        if temp_c is None or not data_str or not hora_str:
            continue
        hora_norm = hora_str.replace(" UTC", "").strip()
        if len(hora_norm) == 4:  # algunos anios usan "0000" en vez de "00:00"
            hora_norm = f"{hora_norm[:2]}:{hora_norm[2:]}"
        records.append({
            "codigo_estacao": codigo_estacao,
            "data_hora_medicao": f"{data_str}T{hora_norm}:00",
            "temp_c": temp_c,
            "source_file": source_file,
        })
    return records


def process_year(year: int, station_codes: set[str], session: requests.Session) -> dict:
    url = ZIP_URL_TEMPLATE.format(year=year)
    print(f"[{year}] GET {url}")
    response = session.get(url, headers={"User-Agent": BROWSER_USER_AGENT}, timeout=DEFAULT_TIMEOUT)
    if response.status_code == 404:
        print(f"[{year}] 404 -- no existe ZIP para este anio")
        return {"status": "not_found", "stations_matched": 0, "records": 0}
    response.raise_for_status()

    zip_bytes = io.BytesIO(response.content)
    stations_matched = 0
    total_records = 0
    with zipfile.ZipFile(zip_bytes) as zf:
        names = zf.namelist()
        for codigo in sorted(station_codes):
            pattern = re.compile(rf"_{re.escape(codigo)}_")
            matches = [n for n in names if pattern.search(n)]
            if not matches:
                continue
            entry_name = matches[0]
            records = parse_station_csv(zf.read(entry_name), codigo, entry_name)
            if not records:
                continue
            out_file = OUTPUT_DIR / f"INMET_{codigo}_{year}.json"
            out_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            stations_matched += 1
            total_records += len(records)

    print(f"[{year}] {stations_matched}/{len(station_codes)} estaciones con datos, {total_records} registros")
    return {"status": "done", "stations_matched": stations_matched, "records": total_records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-year", type=int, default=2000)
    parser.add_argument("--to-year", type=int, default=date.today().year)
    parser.add_argument("--pause-seconds", type=float, default=3.0, help="Pausa entre anios, no golpear el portal")
    parser.add_argument("--force", action="store_true", help="Reprocesa anios ya marcados como done")
    args = parser.parse_args()

    if not lock.acquire("inmet_backfill"):
        info = lock.read_lock()
        print(f"Ya hay un backfill corriendo (pid={info.get('pid') if info else '?'}); salgo.")
        return

    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        stations = load_stations()
        station_codes = {s["codigo_estacao"] for s in stations}
        print(f"{len(station_codes)} estaciones de la cuenca a buscar en cada ZIP anual")

        state = load_state()
        session = requests.Session()

        for year in range(args.from_year, args.to_year + 1):
            year_key = str(year)
            if not args.force and state["years"].get(year_key, {}).get("status") == "done":
                print(f"[{year}] ya procesado, salteo")
                continue
            try:
                result = process_year(year, station_codes, session)
            except Exception as exc:
                print(f"[{year}] FALLO: {exc}")
                result = {"status": "failed", "error": str(exc)}
            state["years"][year_key] = result
            save_state(state)
            time.sleep(args.pause_seconds)

        print("Backfill INMET terminado.")
        done = sum(1 for v in state["years"].values() if v.get("status") == "done")
        failed = sum(1 for v in state["years"].values() if v.get("status") == "failed")
        print(f"{done} anios OK, {failed} fallidos, de {args.to_year - args.from_year + 1} intentados")
    finally:
        lock.release()


if __name__ == "__main__":
    main()
