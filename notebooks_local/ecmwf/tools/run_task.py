"""Dispara un notebook del workspace como job efimero y espera el resultado.

Generaliza runnb.py, que tiene el notebook de Bronze PF hardcodeado. Uso:

    python run_task.py 04_Silver/ETL_Silver_ECMWF_Subcuenca modelo=pf load_mode=incremental
"""
import datetime
import json
import os
import subprocess
import sys
import time

PROFILE = "joaquintschopp@gmail.com"
BASE = "/Workspace/Users/joaquintschopp@gmail.com/rio-uruguay-hydro-pipeline/notebooks"
ENV = dict(os.environ)
ENV["MSYS_NO_PATHCONV"] = "1"


def api(method, path, payload=None):
    cmd = ["databricks", "api", method, path, "-p", PROFILE]
    if payload is not None:
        cmd += ["--json", json.dumps(payload)]
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if p.returncode != 0:
        raise SystemExit(f"CLI error ({method} {path}): {p.stderr}\n{p.stdout}")
    return json.loads(p.stdout) if p.stdout.strip() else {}


def run(nb, params, name=None, poll=30):
    payload = {
        "run_name": name or f"adhoc_{nb.rsplit('/', 1)[-1]}",
        "tasks": [{
            "task_key": "task",
            "notebook_task": {
                "notebook_path": f"{BASE}/{nb}",
                "source": "WORKSPACE",
                "base_parameters": params,
            },
        }],
    }
    rid = api("post", "/api/2.2/jobs/runs/submit", payload)["run_id"]
    print(f"[{datetime.datetime.now():%H:%M:%S}] run {rid}  {nb}  {params}", flush=True)
    t0 = time.time()
    while True:
        d = api("get", f"/api/2.2/jobs/runs/get?run_id={rid}")
        state = d.get("status", {}).get("state") or d.get("state", {}).get("life_cycle_state")
        if state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            break
        time.sleep(poll)
    task = d["tasks"][0]
    code = task.get("status", {}).get("termination_details", {}).get("code")
    mins = (time.time() - t0) / 60
    print(f"[{datetime.datetime.now():%H:%M:%S}] {code} en {mins:.1f} min", flush=True)
    out = api("get", f"/api/2.2/jobs/runs/get-output?run_id={task['run_id']}")
    if out.get("error"):
        print("ERROR:", str(out["error"])[:4000], flush=True)
    if out.get("notebook_output", {}).get("result"):
        print("salida:", out["notebook_output"]["result"][:1000], flush=True)
    print("url:", task.get("run_page_url"), flush=True)
    return code == "SUCCESS"


if __name__ == "__main__":
    nb = sys.argv[1]
    params = dict(a.split("=", 1) for a in sys.argv[2:])
    sys.exit(0 if run(nb, params) else 1)
