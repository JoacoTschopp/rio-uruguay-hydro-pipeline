import datetime, json, subprocess, sys, time, os
from datetime import date, timedelta
import runnb

START = date.fromisoformat(sys.argv[1])
END = date.fromisoformat(sys.argv[2])
CHUNK = int(sys.argv[3]) if len(sys.argv) > 3 else 60
MAX_TRIES = 2            # un reintento: PHOTON_OUT_OF_MEMORY del SimdJsonReader es transitorio
THROTTLE_WAIT = 300      # el bloqueo "Triggering new runs ... disabled temporarily" es de cuenta
MAX_THROTTLE_WAIT = 6 * 3600

def ts():
    return f"[{datetime.datetime.now():%H:%M:%S}]"

def submit_waiting(lo, hi):
    """Espera a que la cuenta vuelva a permitir disparar runs. No es un reintento de un
    chunk fallado: es esperar disponibilidad de compute."""
    waited = 0
    while True:
        try:
            return runnb.submit(lo, hi)
        except SystemExit as e:
            msg = str(e)
            if "disabled temporarily" not in msg:
                raise
            if waited == 0:
                print(f"{ts()} cuenta con disparo de runs deshabilitado; esperando...", flush=True)
            if waited >= MAX_THROTTLE_WAIT:
                print(f"FAILED: bloqueo de cuenta persiste tras {waited/3600:.1f} h. Se corta.", flush=True)
                sys.exit(2)
            time.sleep(THROTTLE_WAIT)
            waited += THROTTLE_WAIT

def details(trid):
    try:
        o = runnb.api("get", f"/api/2.2/jobs/runs/get-output?run_id={trid}")
        return str(o.get("error"))[:500]
    except SystemExit as e:
        return f"(sin output: {e})"

cur, n, t_all = START, 0, time.time()
while cur <= END:
    hi = min(cur + timedelta(days=CHUNK - 1), END)
    n += 1
    for attempt in range(1, MAX_TRIES + 1):
        rid = submit_waiting(cur.isoformat(), hi.isoformat())
        print(f"{ts()} chunk {n} ({cur}..{hi}) intento {attempt} run={rid}", flush=True)
        d, secs = runnb.wait(rid)
        st, url, trid = runnb.result_msg(d)
        code = st.get("termination_details", {}).get("code")
        print(f"{ts()} chunk {n} intento {attempt}: {code} in {secs/60:.1f} min", flush=True)
        if code == "SUCCESS":
            break
        print(f"  causa: {details(trid)}", flush=True)
        print(f"  url: {url}", flush=True)
        if attempt == MAX_TRIES:
            print(f"FAILED chunk {n} ({cur}..{hi}) tras {MAX_TRIES} intentos. Se corta.", flush=True)
            sys.exit(1)
    cur = hi + timedelta(days=1)
print(f"TODOS LOS CHUNKS OK: {n} chunks en {(time.time()-t_all)/60:.1f} min", flush=True)
