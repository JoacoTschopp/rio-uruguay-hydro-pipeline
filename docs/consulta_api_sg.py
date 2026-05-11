#!/usr/bin/env python3
"""
Script para consultar precipitaciones del día de ayer desde la API de Salto Grande.
Descarga datos de todas las estaciones activas y genera un CSV con los resultados.
"""

import xml.etree.ElementTree as ET
import requests
import pandas as pd
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Configuración
warnings.filterwarnings("ignore", category=InsecureRequestWarning)
SESSION = requests.Session()
SESSION.verify = False

ENDPOINT = "https://www.saltogrande.org/ws.php"
NAMESPACE = "https://www.saltogrande.org/ws.php"
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"

NS = {"soap": SOAP_ENV}


def _find_first_by_localname(elem: ET.Element, local: str):
    """Busca el primer hijo cuyo tag termine en ...}local o sea exactamente 'local' (sin ns)."""
    for ch in elem.iter():
        tag = ch.tag
        if tag == local or tag.endswith("}" + local):
            return ch
    return None


def _findall_children_by_localname(elem: ET.Element, local: str):
    """Devuelve hijos directos con local-name == local (con o sin ns)."""
    out = []
    for ch in list(elem):
        tag = ch.tag
        if tag == local or tag.endswith("}" + local):
            out.append(ch)
    return out


def build_hidroserie_payload(id_estacion: str, variable: str, fecha_desde: str, fecha_hasta: str) -> str:
    """Genera el XML SOAP para HidroSerieHistorica."""
    return f'''<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="{SOAP_ENV}" xmlns:tns="{NAMESPACE}">
  <soapenv:Body>
    <tns:HidroSerieHistorica>
      <idEstacion>{id_estacion}</idEstacion>
      <variable>{variable}</variable>
      <fechaDesde>{fecha_desde}</fechaDesde>
      <fechaHasta>{fecha_hasta}</fechaHasta>
    </tns:HidroSerieHistorica>
  </soapenv:Body>
</soapenv:Envelope>'''


def fetch_precipitacion(id_estacion: str, fecha_desde: str, fecha_hasta: str, timeout=60):
    """Devuelve lista de dicts con Fecha, Id_Estacion, P para la estación indicada."""
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"{NAMESPACE}#HidroSerieHistorica",
    }
    payload = build_hidroserie_payload(id_estacion, "P", fecha_desde, fecha_hasta)

    resp = SESSION.post(ENDPOINT, data=payload.encode("utf-8"), headers=headers, timeout=timeout)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    body = root.find(".//soap:Body", namespaces={"soap": SOAP_ENV})
    if body is None:
        return []

    resp_node = _find_first_by_localname(body, "HidroSerieHistoricaResponse")
    if resp_node is None:
        return []

    ret = _find_first_by_localname(resp_node, "return")
    if ret is None:
        return []

    items = _findall_children_by_localname(ret, "item")
    out = []
    for it in items:
        fecha = _find_first_by_localname(it, "Fecha")
        valor = _find_first_by_localname(it, "Valor")
        out.append({
            "Fecha": fecha.text if fecha is not None else None,
            "Id_Estacion": id_estacion,
            "P": float(valor.text) if (valor is not None and valor.text) else None
        })
    return out


def get_yesterday_date():
    """Devuelve la fecha de ayer en formato YYYY-MM-DD."""
    ayer = datetime.now() - timedelta(days=1)
    return ayer.strftime("%Y-%m-%d")


def main():
    """Función principal para descargar precipitaciones del día de ayer."""
    
    # Calcular fecha de ayer
    fecha_ayer = get_yesterday_date()
    print(f"Descargando datos para la fecha: {fecha_ayer}")
    
    # Cargar estaciones activas
    # Buscar en varias ubicaciones posibles
    posibles_rutas = [
        "estaciones_activas.csv",
        "../datos/estaciones_activas.csv",
        "../datos/Backup-ProcesoIntermedio/estaciones_activas.csv",
        "datos/estaciones_activas.csv",
        "datos/Backup-ProcesoIntermedio/estaciones_activas.csv",
    ]
    
    estaciones_path = None
    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            estaciones_path = ruta
            break
    
    if estaciones_path is None:
        print(f"ERROR: No se encuentra el archivo estaciones_activas.csv")
        print("Buscado en:")
        for ruta in posibles_rutas:
            print(f"  - {ruta}")
        print("Ejecuta primero el notebook 00-estaciones_precipitaciones.ipynb para generar este archivo.")
        return
    
    estaciones_df = pd.read_csv(estaciones_path)
    
    # Filtrar estaciones con variable P
    estaciones_filtradas = estaciones_df[estaciones_df["Variables"].str.contains("P", na=False)]
    ids_estaciones = estaciones_filtradas["Id"].tolist()
    
    print(f"Consultando {len(ids_estaciones)} estaciones con variable P...")
    
    # Descargar datos
    resultados = []
    errores = []
    
    for est_id in ids_estaciones:
        try:
            datos = fetch_precipitacion(est_id, fecha_ayer, fecha_ayer)
            if datos:
                resultados.extend(datos)
                print(f"{est_id}: {len(datos)} registros")
            else:
                print(f"{est_id}: Sin datos")
                errores.append(est_id)
        except Exception as e:
            print(f"Error con estación {est_id}: {e}")
            errores.append(est_id)
    
    # Guardar resultados
    if resultados:
        salida = f"precipitaciones_{fecha_ayer}.csv"
        df_out = pd.DataFrame(resultados, columns=["Fecha", "Id_Estacion", "P"])
        df_out.to_csv(salida, index=False)
        print(f"\n✓ CSV generado: {os.path.abspath(salida)}")
        print(f"✓ Total de registros: {len(resultados)}")
    else:
        print("\n✗ No se obtuvieron datos de ninguna estación")
    
    if errores:
        print(f"\n⚠ Estaciones con errores o sin datos: {len(errores)}")
    
    # TEST: Verificar que se trajeron datos
    print("\n" + "="*50)
    print("TEST DE VERIFICACIÓN")
    print("="*50)
    
    if resultados:
        print(f"✓ TEST PASADO: Se obtuvieron {len(resultados)} registros de precipitación")
        print(f"✓ Fecha de los datos: {resultados[0]['Fecha']}")
        print(f"✓ Estaciones con datos: {len(set(r['Id_Estacion'] for r in resultados))}")
        
        # Mostrar muestra de datos
        print("\nMuestra de datos (primeros 5 registros):")
        for i, reg in enumerate(resultados[:5]):
            print(f"  {i+1}. Estación: {reg['Id_Estacion']}, Fecha: {reg['Fecha']}, P: {reg['P']}")
    else:
        print("✗ TEST FALLADO: No se obtuvieron datos de ninguna estación")
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
