"""Valida localmente el mecanismo propuesto para el backfill historico de ANA antes de
escribir/desplegar el notebook de Databricks: pedir series historicas en LOTES de 5
codigos de estacion x ventana de 30 dias contra el endpoint autenticado moderno
(HidroinfoanaSerieTelemetricaAdotada/v2, el mismo que ya usa Daily_ANA.ipynb), en vez
del endpoint legado sin autenticar que usaba Historic_ANA.ipynb (confirmado muerto: 401).

No hace el backfill completo (14.000 requests) - solo prueba el formato de respuesta en
un par de ventanas (reciente, media, vieja) para confirmar:
  1. que el batching de 5 estaciones por request funciona igual que en Daily_ANA.ipynb.
  2. que la respuesta trae Cota_Adotada Y Chuva_Adotada juntos por estacion (un solo
     mecanismo cubre ambas variables).
  3. como se comporta una ventana sin datos para ninguna estacion del lote (piso 2000).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
STATIONS_FILE = Path(__file__).parent / "vigentes_sin_historia.json"
OUTPUT_DIR = Path(__file__).parent / "output_test"

BASE_URL = "https://www.ana.gov.br/hidrowebservice"


def load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def login(session: requests.Session) -> str:
    r = session.get(
        f"{BASE_URL}/EstacoesTelemetricas/OAUth/v1",
        headers={"Identificador": os.environ["USER_API_ANA"], "Senha": os.environ["PASS_API_ANA"]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["items"]["tokenautenticacao"]


def consultar_batch(
    session: requests.Session, token: str, codigos: list[str], data_busca: str, intervalo: str = "DIAS_30"
) -> tuple[int, Any]:
    url = f"{BASE_URL}/EstacoesTelemetricas/HidroinfoanaSerieTelemetricaAdotada/v2"
    params = {
        "Codigos_Estacoes": ",".join(codigos),
        "Tipo Filtro Data": "DATA_LEITURA",
        "Range Intervalo de busca": intervalo,
        "Data de Busca (yyyy-MM-dd)": data_busca,
    }
    resp = session.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=60)
    try:
        payload = resp.json()
    except ValueError:
        payload = {"raw_text": resp.text[:500]}
    return resp.status_code, payload


def main():
    stations = json.loads(STATIONS_FILE.read_text(encoding="utf-8"))
    batch = stations[:5]
    print("Lote de prueba (5 estaciones):", batch)

    session = requests.Session()
    token = login(session)
    print("Login OK\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    casos = [
        ("2025-06-15", "reciente (deberia tener datos)"),
        ("2015-06-15", "media (algunas estaciones pueden tener, otras no)"),
        ("2001-06-15", "piso 2000 (probablemente vacio para este lote)"),
    ]

    for data_busca, label in casos:
        status, payload = consultar_batch(session, token, batch, data_busca)
        items = payload.get("items") if isinstance(payload, dict) else None
        n = len(items) if isinstance(items, list) else "N/A"
        print(f"=== {data_busca} ({label}) === HTTP {status}, n_items={n}")

        out_path = OUTPUT_DIR / f"batch_test_{data_busca}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if isinstance(items, list) and items:
            codigos_presentes = sorted({str(it.get("codigoestacao")) for it in items})
            con_cota = sum(1 for it in items if it.get("Cota_Adotada") not in (None, "", "null"))
            con_chuva = sum(1 for it in items if it.get("Chuva_Adotada") not in (None, "", "null"))
            print(f"  codigos presentes en la respuesta: {codigos_presentes}")
            print(f"  registros con Cota_Adotada: {con_cota}, con Chuva_Adotada: {con_chuva}")
            print(f"  ejemplo: {json.dumps(items[0], ensure_ascii=False)}")
        print()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
