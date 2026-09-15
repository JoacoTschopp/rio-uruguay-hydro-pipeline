"""Helper minimo para correr SQL ad hoc contra el warehouse serverless desde un script
local, via el CLI de `databricks` ya autenticado (mismo patron manual usado en las
Decisiones 023/024/025/028/029 -- `databricks api post /api/2.0/sql/statements`), pero
invocado con `subprocess` en vez de a mano. No agrega la dependencia
`databricks-sql-connector`: ningun otro script de `notebooks_local/` la usa.

Uso:
    from db_query import run_sql
    df = run_sql("SELECT ...")
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

WAREHOUSE_ID = "d8aaafcf1fdb6645"  # "Serverless Starter Warehouse", ver memoria de sesion
PROFILE = "joaquintschopp@gmail.com"


def _api_post(path: str, payload: dict) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(payload, fh)
        payload_path = Path(fh.name)
    try:
        result = subprocess.run(
            ["databricks", "api", "post", path, "-p", PROFILE, "--json", f"@{payload_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        payload_path.unlink(missing_ok=True)
    return json.loads(result.stdout)


def _api_get(path: str) -> dict:
    result = subprocess.run(
        ["databricks", "api", "get", path, "-p", PROFILE],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def run_sql(statement: str, wait_timeout: str = "50s") -> pd.DataFrame:
    """Ejecuta `statement` contra el warehouse serverless y devuelve un DataFrame.
    Sigue los `chunks` si el resultado no entra en uno solo (statements grandes)."""
    resp = _api_post(
        "/api/2.0/sql/statements",
        {"warehouse_id": WAREHOUSE_ID, "statement": statement, "wait_timeout": wait_timeout},
    )
    state = resp["status"]["state"]
    if state == "FAILED":
        raise RuntimeError(f"SQL fallo: {resp['status'].get('error')}")
    if state != "SUCCEEDED":
        raise RuntimeError(f"SQL no termino en {wait_timeout} (estado {state}); subir wait_timeout o simplificar la query")

    columns = [c["name"] for c in resp["manifest"]["schema"]["columns"]]
    types = [c["type_name"] for c in resp["manifest"]["schema"]["columns"]]
    statement_id = resp["statement_id"]
    total_chunks = resp["manifest"]["total_chunk_count"]

    rows: list[list] = []
    if total_chunks > 0:
        rows.extend(resp["result"]["data_array"])
        for chunk_index in range(1, total_chunks):
            chunk = _api_get(f"/api/2.0/sql/statements/{statement_id}/result/chunks/{chunk_index}")
            rows.extend(chunk["data_array"])

    df = pd.DataFrame(rows, columns=columns)
    for col, type_name in zip(columns, types):
        if type_name in ("LONG", "INT", "INTEGER"):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        elif type_name in ("DOUBLE", "FLOAT", "DECIMAL"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif type_name == "DATE":
            df[col] = pd.to_datetime(df[col]).dt.date
    return df
