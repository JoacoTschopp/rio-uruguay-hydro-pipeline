"""Orquestador local del backfill historico de TIGGE `cf`+`pf` (reemplaza al job de Databricks
`ECMWF_Forecast_Historic_Backfill` como via de ejecucion -- mismo criterio que ya se aplico a
ANA/INMET/GEFS: bajar en local, donde hay control y visibilidad real, y subir solo los JSON ya
aplanados al Volume que Bronze ya sabe leer. Reusa `historic_cf_tigge.py`/`historic_pf_tigge.py`
tal cual, sin duplicar su logica -- solo agrega el lock compartido y el loop de corrida larga
que a ellos, corridos sueltos, les falta.

Regla de seguridad no negociable (Decision 012, sigue vigente corra donde corra): un solo
request a la vez contra TIGGE/ECDS, nunca `cf` y `pf` en paralelo entre si -- por eso este
orquestador corre `cf` hasta agotar lo pendiente y recien despues arranca `pf`, en un solo
proceso, nunca los dos a la vez. Tambien evitar correr esto a la misma hora que
`ECMWF_Forecast_Daily_Incremental` en Databricks (08:00 UTC) -- comparten cuenta/token.

Uso:
    python run_tigge_backfill.py --max-batches-per-call 25 --profile joaquintschopp@gmail.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import historic_cf_tigge  # noqa: E402
import historic_pf_tigge  # noqa: E402
import sync_to_databricks  # noqa: E402
import tigge_lock as lock  # noqa: E402  (lock dedicado, no el compartido de ana_historic_backfill -- ver tigge_lock.py)
from common_ecmwf import batch_fully_landed, iter_batches_backward  # noqa: E402


def _pending_batches(module) -> int:
    from datetime import date, timedelta

    latest = date.today() - timedelta(days=module.TIGGE_LAG_DAYS)
    batches = iter_batches_backward(module.EARLIEST_TIGGE_DATE, latest, module.BATCH_MONTHS)
    tipo = "cf" if module is historic_cf_tigge else "pf"
    # Un lote marcado como permanentemente no disponible en el modulo (ver
    # KNOWN_UNAVAILABLE_RANGES en historic_cf_tigge.py, Decision 031) nunca va a aterrizar --
    # sin excluirlo aca, este conteo nunca llega a 0 y el while True de run_source() de mas
    # arriba queda en loop infinito llamando a module.run() sin ningun progreso posible.
    known_unavailable = getattr(module, "_known_unavailable_reason", lambda s, e: None)
    return sum(
        1 for start, end in batches
        if not batch_fully_landed(tipo, start, end, module.RUN_TIME, module.JSON_DIR)
        and not known_unavailable(start, end)
    )


def run_source(module, label: str, max_batches_per_call: int, sync_every_calls: int, profile: str) -> bool:
    """Devuelve True si esta fuente quedo completa, False si se corto por un fallo (rate
    limit, request rechazado, etc). El caller NO debe volver a llamar esta funcion de
    inmediato si devuelve False -- ver Decision 030, incidente de rate-limit: llamar de
    nuevo sin pausa es exactamente el "reintento en bucle" que rechazo la cola de ECDS."""
    calls_since_sync = 0
    call_n = 0
    while True:
        pending = _pending_batches(module)
        if pending == 0:
            print(f"[{label}] Nada pendiente, backfill completo para esta fuente.")
            break
        call_n += 1
        print(f"[{label}] Llamada {call_n}: {pending} lotes pendientes, pidiendo hasta {max_batches_per_call} en esta corrida...")
        result = module.run(max_batches_per_run=max_batches_per_call, dry_run=False, force_reload=False)
        calls_since_sync += 1
        if calls_since_sync >= sync_every_calls:
            print(f"[{label}] Sincronizando con Databricks...")
            sync_to_databricks.sync(profile)
            calls_since_sync = 0

        if result.get("failed"):
            print(f"[{label}] Lote fallido -- se corta ESTA fuente, no se reintenta en el momento "
                  f"(evita bombardear la cola si esta rate-limited). Volver a correr mas tarde.")
            if calls_since_sync > 0:
                sync_to_databricks.sync(profile)
            return False

    if calls_since_sync > 0:
        print(f"[{label}] Sync final...")
        sync_to_databricks.sync(profile)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-batches-per-call", type=int, default=25, help="Lotes por llamada a cdsapi.retrieve antes de re-chequear")
    parser.add_argument("--sync-every-calls", type=int, default=3, help="Sincroniza con Databricks cada N llamadas exitosas")
    parser.add_argument("--profile", required=True, help="Perfil de databricks CLI")
    parser.add_argument("--skip-cf", action="store_true", help="Saltea cf (por si ya esta completo)")
    parser.add_argument("--skip-pf", action="store_true", help="Saltea pf")
    args = parser.parse_args()

    if not lock.acquire("ecmwf_tigge_backfill"):
        info = lock.read_lock()
        print(f"Ya hay un backfill corriendo (pid={info.get('pid') if info else '?'}); salgo.")
        return

    try:
        cf_ok = True
        if not args.skip_cf:
            cf_ok = run_source(historic_cf_tigge, "cf", args.max_batches_per_call, args.sync_every_calls, args.profile)
        else:
            print("[cf] Salteado por --skip-cf")

        if not cf_ok:
            print("cf se corto por un fallo -- no se arranca pf en la misma corrida (mismo motivo: "
                  "no sumar mas requests contra una cola que puede estar rate-limited). Volver a "
                  "correr mas tarde retoma cf donde quedo.")
            return

        if not args.skip_pf:
            run_source(historic_pf_tigge, "pf", args.max_batches_per_call, args.sync_every_calls, args.profile)
        else:
            print("[pf] Salteado por --skip-pf")

        print("Backfill de cf+pf completo.")
    finally:
        lock.release()


if __name__ == "__main__":
    main()
