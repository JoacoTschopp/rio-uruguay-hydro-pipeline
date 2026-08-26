"""Backfill historico local de GEFS Reforecast v12 (NOAA) -- precipitacion (`apcp_sfc`) recortada
al bounding box de la cuenca, para las Decisiones 021/026/028 (ver docs/decisions.md).

Descarga GRIB2 (~26,5 MiB/dia/miembro, grilla global, sin recortar) a un directorio temporal,
recorta al bounding box de la cuenca inmediatamente, acumula (`cumsum`) y aplana a records
comparables a `tp_mm` de TIGGE, escribe UN JSON por dia (todos los miembros de esa corrida) en
output_json/, y borra los .grib2 temporales -- nunca se guardan en disco de forma permanente
(mismo principio que notebooks_local/inmet_backfill/download_inmet_zips.py con los ZIP anuales).
Ningun archivo pesado se sube a Databricks: sync_to_databricks.py sube solo estos JSON ya
recortados y aplanados.

Resumible via gefs_backfill_state.json (fecha -> status/miembros/registros). Usa el lock
compartido de ana_historic_backfill para no correr en paralelo con otro backfill local.

Uso:
    python download_gefs_backfill.py --from-date 2000-01-01 --to-date 2006-09-30 --max-days-per-run 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_gefs import (  # noqa: E402
    EARLIEST_GEFS_DATE,
    LATEST_GEFS_DATE,
    compute_download_area,
    flatten_member_day,
    list_members,
    write_json,
)

LOCAL_DIR = Path(__file__).parent
REPO_ROOT = LOCAL_DIR.parents[1]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

STATE_FILE = LOCAL_DIR / "gefs_backfill_state.json"
OUTPUT_JSON_DIR = LOCAL_DIR / "output_json"
TMP_DIR = LOCAL_DIR / "tmp_grib"

ANA_BACKFILL_DIR = REPO_ROOT / "notebooks_local" / "ana_historic_backfill"
sys.path.insert(0, str(ANA_BACKFILL_DIR))
import lock  # noqa: E402  (notebooks_local/ana_historic_backfill/lock.py, reusado)

DEFAULT_TO_DATE = date(2006, 9, 30)  # hueco unico de GEFS (Decision 021); extender a 2019-12-31 para calibracion
PAUSE_BETWEEN_REQUESTS_SECONDS = 1.0


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"days": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def process_day(session, run_date: date, area: dict) -> dict:
    members = list_members(session, run_date)
    if not members:
        return {"status": "not_found", "members": [], "records": 0}

    all_records: list[dict] = []
    for member in members:
        records = flatten_member_day(session, run_date, member, area, TMP_DIR)
        if records is None:
            continue
        all_records.extend(records)

    if not all_records:
        return {"status": "empty", "members": members, "records": 0}

    out_file = OUTPUT_JSON_DIR / f"GEFS_{run_date:%Y_%m_%d}_t00.json"
    write_json(all_records, out_file)
    return {"status": "done", "members": members, "records": len(all_records)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-date", type=date.fromisoformat, default=EARLIEST_GEFS_DATE)
    parser.add_argument("--to-date", type=date.fromisoformat, default=DEFAULT_TO_DATE)
    parser.add_argument("--max-days-per-run", type=int, default=10, help="Tope de dias a procesar en esta corrida")
    parser.add_argument("--force", action="store_true", help="Reprocesa dias ya marcados como done")
    parser.add_argument("--dry-run", action="store_true", help="Solo lista dias pendientes, sin descargar")
    args = parser.parse_args()

    if args.from_date < EARLIEST_GEFS_DATE or args.to_date > LATEST_GEFS_DATE:
        print(f"Rango fuera de la cobertura real de GEFS v12 ({EARLIEST_GEFS_DATE} .. {LATEST_GEFS_DATE})")
        return

    if not lock.acquire("gefs_backfill"):
        info = lock.read_lock()
        print(f"Ya hay un backfill corriendo (pid={info.get('pid') if info else '?'}); salgo.")
        return

    try:
        OUTPUT_JSON_DIR.mkdir(exist_ok=True)
        area = compute_download_area(GEOJSON_PATH)
        print(f"Area de descarga: {area}")

        state = load_state()
        n_days_total = (args.to_date - args.from_date).days + 1
        print(f"Rango objetivo: {args.from_date} .. {args.to_date} ({n_days_total} dias)")

        if args.dry_run:
            d = args.from_date
            while d <= args.to_date:
                done = state["days"].get(d.isoformat(), {}).get("status") == "done"
                print(f"  {d}  {'completo' if done else 'PENDIENTE'}")
                d += timedelta(days=1)
            return

        session = requests.Session()
        processed = 0
        d = args.from_date
        while d <= args.to_date:
            if processed >= args.max_days_per_run:
                print(f"Limite de {args.max_days_per_run} dias por corrida alcanzado. Volver a correr para continuar.")
                break

            day_key = d.isoformat()
            if not args.force and state["days"].get(day_key, {}).get("status") == "done":
                d += timedelta(days=1)
                continue

            try:
                result = process_day(session, d, area)
            except Exception as exc:
                print(f"[{d}] FALLO: {exc}")
                result = {"status": "failed", "error": str(exc)}
            state["days"][day_key] = result
            save_state(state)
            print(f"[{d}] {result.get('status')}: {len(result.get('members', []))} miembros, {result.get('records', 0)} registros")

            if result.get("status") == "failed":
                print("Se corta la ejecucion por el fallo anterior (no se reintenta en bucle).")
                break

            processed += 1
            time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)
            d += timedelta(days=1)

        done = sum(1 for v in state["days"].values() if v.get("status") == "done")
        print(f"\n{done} dias completos en el estado acumulado (de {n_days_total} en el rango objetivo de esta corrida).")
    finally:
        lock.release()
        try:
            if TMP_DIR.exists() and not any(TMP_DIR.iterdir()):
                TMP_DIR.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    main()
