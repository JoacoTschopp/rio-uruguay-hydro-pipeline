"""Prueba puntual (Bloque 1 de la investigacion de lluvia, sesion 2026-08-21): confirmar si el
endpoint autenticado de ANA (HidroinfoanaSerieTelemetricaAdotada/v2) tiene Chuva_Adotada real para
las 22 estaciones de alta_frontera en ventanas ANTERIORES a 2026-03-03 (la fecha en la que el
hallazgo de la Decision 023 dice que arranca toda la lluvia observada en esas estaciones).

No hace ningun backfill ni escribe nada en Bronze: solo imprime un resumen por estacion x ventana
para decidir si vale la pena ampliar run_backfill_local.py a estas 22 estaciones.
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
OUTPUT_DIR = Path(__file__).parent / "output_probe_chuva"

BASE_URL = "https://www.ana.gov.br/hidrowebservice"

# Las 22 estaciones de alta_frontera (weather.silver.estacion_subcuenca, consultado 2026-08-21)
STATIONS_ALTA_FRONTERA = [
    "70100000", "70200000", "70300000", "70500000", "71200000", "71250000", "71300000",
    "71350001", "72430000", "72630000", "72680000", "72715000", "72810000", "72849000",
    "73300000", "73350000", "73600000", "73765000", "73770000", "73900000", "73960000",
    "74100000",
]

# 9 estaciones que SI reportan chuva desde 2026-03-03 (segun la consulta SQL previa)
STATIONS_CON_CHUVA_RECIENTE = [
    "71200000", "71300000", "71350001", "72715000", "72810000", "72849000",
    "73770000", "73960000", "74100000",
]


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


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def main():
    session = requests.Session()
    token = login(session)
    print("Login OK\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Ventanas historicas a probar, incluyendo antes y despues de 2026-03-03
    casos = [
        ("2026-02-15", "justo antes del hallazgo 2026-03-03"),
        ("2024-06-15", "1.5 anios antes"),
        ("2020-06-15", "6 anios antes"),
        ("2015-06-15", "11 anios antes"),
        ("2010-06-15", "16 anios antes"),
        ("2005-06-15", "21 anios antes"),
        ("2001-06-15", "cerca del piso 2000"),
    ]

    stations = STATIONS_ALTA_FRONTERA
    print(f"Probando {len(stations)} estaciones de alta_frontera en {len(casos)} ventanas\n")

    resumen_global: dict[str, dict[str, int]] = {}

    for data_busca, label in casos:
        con_chuva_total = 0
        con_cota_total = 0
        codigos_con_chuva: set[str] = set()
        all_items: list[dict] = []

        for batch in _chunked(stations, 5):
            status, payload = consultar_batch(session, token, batch, data_busca)
            items = payload.get("items") if isinstance(payload, dict) else None
            if isinstance(items, list):
                all_items.extend(items)
            time.sleep(0.5)

        con_cota = sum(1 for it in all_items if it.get("Cota_Adotada") not in (None, "", "null"))
        con_chuva = sum(1 for it in all_items if it.get("Chuva_Adotada") not in (None, "", "null"))
        codigos_con_chuva = {
            str(it.get("codigoestacao")) for it in all_items
            if it.get("Chuva_Adotada") not in (None, "", "null")
        }

        print(f"=== {data_busca} ({label}) === n_items={len(all_items)}, con_Cota={con_cota}, con_Chuva={con_chuva}")
        if codigos_con_chuva:
            print(f"  estaciones con Chuva_Adotada real: {sorted(codigos_con_chuva)}")
        print()

        resumen_global[data_busca] = {
            "n_items": len(all_items),
            "con_cota": con_cota,
            "con_chuva": con_chuva,
            "estaciones_con_chuva": sorted(codigos_con_chuva),
        }

        out_path = OUTPUT_DIR / f"probe_{data_busca}.json"
        out_path.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(resumen_global, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Resumen guardado en {summary_path}")


if __name__ == "__main__":
    main()
