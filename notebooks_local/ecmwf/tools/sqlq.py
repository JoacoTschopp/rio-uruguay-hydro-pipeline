import json, subprocess, sys, os
WH = "d8aaafcf1fdb6645"
PROFILE = "joaquintschopp@gmail.com"
def run_sql(q, timeout="50s"):
    payload = {"warehouse_id": WH, "statement": q, "wait_timeout": timeout, "on_wait_timeout": "CONTINUE", "format": "JSON_ARRAY", "disposition": "INLINE"}
    env = dict(os.environ); env["MSYS_NO_PATHCONV"]="1"
    p = subprocess.run(["databricks","api","post","/api/2.0/sql/statements","-p",PROFILE,"--json",json.dumps(payload)],
                       capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise SystemExit("CLI error: "+p.stderr+p.stdout)
    d = json.loads(p.stdout)
    st = d["status"]["state"]
    sid = d["statement_id"]
    import time
    while st in ("PENDING","RUNNING"):
        time.sleep(3)
        p = subprocess.run(["databricks","api","get",f"/api/2.0/sql/statements/{sid}","-p",PROFILE], capture_output=True, text=True, env=env)
        d = json.loads(p.stdout); st = d["status"]["state"]
    if st != "SUCCEEDED":
        raise SystemExit("SQL failed: "+json.dumps(d.get("status"))[:2000])
    cols = [c["name"] for c in d["manifest"]["schema"]["columns"]]
    rows = d.get("result",{}).get("data_array",[]) or []
    return cols, rows
if __name__ == "__main__":
    q = sys.stdin.read()
    cols, rows = run_sql(q)
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join("NULL" if v is None else str(v) for v in r))
