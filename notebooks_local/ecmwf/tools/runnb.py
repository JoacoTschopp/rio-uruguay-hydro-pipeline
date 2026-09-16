import json, os, subprocess, sys, time, datetime

PROFILE = "joaquintschopp@gmail.com"
NB = "/Workspace/Users/joaquintschopp@gmail.com/rio-uruguay-hydro-pipeline/notebooks/02_Bronze/ETL_Bronze_ECMWF_PF"
ENV = dict(os.environ); ENV["MSYS_NO_PATHCONV"] = "1"

def api(method, path, payload=None):
    cmd = ["databricks", "api", method, path, "-p", PROFILE]
    if payload is not None:
        cmd += ["--json", json.dumps(payload)]
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if p.returncode != 0:
        raise SystemExit(f"CLI error ({method} {path}): {p.stderr}\n{p.stdout}")
    return json.loads(p.stdout) if p.stdout.strip() else {}

def submit(start, end, name=None):
    payload = {
        "run_name": name or f"PF_Bronze_backfill_{start}_{end}",
        "tasks": [{
            "task_key": "ETL_Bronze_ECMWF_PF_Chunk",
            "notebook_task": {
                "notebook_path": NB,
                "source": "WORKSPACE",
                "base_parameters": {"range_start": start, "range_end": end},
            },
        }],
    }
    d = api("post", "/api/2.2/jobs/runs/submit", payload)
    return d["run_id"]

def wait(run_id, poll=30):
    t0 = time.time()
    while True:
        d = api("get", f"/api/2.2/jobs/runs/get?run_id={run_id}")
        st = d.get("status", {})
        state = st.get("state") or d.get("state", {}).get("life_cycle_state")
        if state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            return d, time.time() - t0
        time.sleep(poll)

def result_msg(d):
    t = d["tasks"][0]
    return t.get("status", {}), t.get("run_page_url"), t.get("run_id")

if __name__ == "__main__":
    start, end = sys.argv[1], sys.argv[2]
    rid = submit(start, end)
    print(f"[{datetime.datetime.now():%H:%M:%S}] submitted run {rid} for {start}..{end}", flush=True)
    d, secs = wait(rid)
    st, url, trid = result_msg(d)
    print(f"[{datetime.datetime.now():%H:%M:%S}] run {rid} finished in {secs/60:.1f} min")
    print("status:", json.dumps(st)[:1500])
    print("url:", url)
    # notebook output
    try:
        o = api("get", f"/api/2.2/jobs/runs/get-output?run_id={trid}")
        print("notebook_output:", json.dumps(o.get("notebook_output"))[:1000])
        if o.get("error"):
            print("ERROR:", str(o["error"])[:3000])
    except SystemExit as e:
        print("no output:", e)
    ok = st.get("termination_details", {}).get("code") == "SUCCESS"
    sys.exit(0 if ok else 1)
