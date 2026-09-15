"""Valida localmente, contra la API real, la logica de 'ir hacia atras y sacar del lote
la estacion que se quede sin registros en una ventana' antes de confiar en la version
Databricks (Historic_ANA.ipynb). Corre sobre un subconjunto chico de estaciones reales y
un rango acotado (no las 362 ni hasta el piso 2000) solo para confirmar mecanica: que el
active_stations se va achicando, que las que se agotan no se vuelven a consultar, y que
los registros escritos tienen sentido.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
STATIONS_FILE = Path(__file__).parent / "vigentes_sin_historia.json"
OUTPUT_DIR = Path(__file__).parent / "output_stateful_test"

BASE_URL = "https://www.ana.gov.br/hidrowebservice"
WINDOW_DAYS = 30
STATION_BATCH_SIZE = 5
N_WINDOWS_TEST = 20  # ~20 meses hacia atras desde end_date, suficiente para ver dropouts reales


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


def consultar_batch(session, token, codigos, data_busca, intervalo="DIAS_30"):
    url = f"{BASE_URL}/EstacoesTelemetricas/HidroinfoanaSerieTelemetricaAdotada/v2"
    params = {
        "Codigos_Estacoes": ",".join(codigos),
        "Tipo Filtro Data": "DATA_LEITURA",
        "Range Intervalo de busca": intervalo,
        "Data de Busca (yyyy-MM-dd)": data_busca,
    }
    resp = session.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=60)
    if resp.status_code == 401:
        return None
    resp.raise_for_status()
    return resp.json().get("items") or []


def _chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _has_real_value(item: dict) -> bool:
    return any(item.get(k) not in (None, "", "null") for k in ("Cota_Adotada", "Chuva_Adotada", "Vazao_Adotada"))


def main():
    all_stations = json.loads(STATIONS_FILE.read_text(encoding="utf-8"))
    # Mezcla deliberada: algunas que ya sabemos tienen historia hasta 2015 (del sondeo previo)
    # y otras al azar, para ver dropouts variados en pocas ventanas.
    sample = ["72818000", "73582900", "2752032", "2753029", "2753058"] + all_stations[100:110]
    print(f"Muestra de prueba: {len(sample)} estaciones")

    session = requests.Session()
    token = login(session)
    print("Login OK\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    active = list(sample)
    window_end = date(2025, 6, 15)
    exhausted = {}

    for w in range(N_WINDOWS_TEST):
        if not active:
            print("Todas las estaciones de la muestra se agotaron, corte anticipado.")
            break
        window_start = date.fromordinal(window_end.toordinal() - WINDOW_DAYS + 1)
        data_busca = window_end.isoformat()

        window_records = []
        codigos_con_datos = set()
        for batch in _chunked(active, STATION_BATCH_SIZE):
            items = consultar_batch(session, token, batch, data_busca)
            if items is None:
                token = login(session)
                items = consultar_batch(session, token, batch, data_busca)
            for item in items:
                if _has_real_value(item):
                    window_records.append(item)
                    codigos_con_datos.add(str(item.get("codigoestacao")))
            time.sleep(0.4)

        sin_datos = [c for c in active if c not in codigos_con_datos]
        for c in sin_datos:
            exhausted[c] = window_end.isoformat()
        active = [c for c in active if c in codigos_con_datos]

        print(
            f"[{w+1}/{N_WINDOWS_TEST}] ventana {window_start}..{window_end}: "
            f"{len(window_records)} registros, {len(codigos_con_datos)} con datos, "
            f"agotadas esta ventana={sin_datos}, activas restantes={len(active)}"
        )

        if window_records:
            (OUTPUT_DIR / f"ANA_HIST_{window_start}_{window_end}.json").write_text(
                json.dumps(window_records, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        window_end = date.fromordinal(window_start.toordinal() - 1)

    print("\nResumen final:")
    print("activas al terminar la prueba:", active)
    print("agotadas (codigo -> ventana en que se agotaron):")
    for c, w in exhausted.items():
        print(" ", c, "->", w)


if __name__ == "__main__":
    main()
