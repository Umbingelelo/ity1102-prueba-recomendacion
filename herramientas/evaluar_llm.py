"""Caso 2 (chatbot): el camino del LLM, medido y listo para evaluarlo a mano (EP3 §3.2 y §4.3).

Manda cada mensaje de pruebas/mensajes_llm.txt a POST /api/conversacion, espera a que el texto del LLM
esté listo y mide el tiempo TOTAL que vive el cliente: desde que envía el mensaje hasta que la respuesta
redactada existe. Ese es el número del RNF1 del caso (p95 bajo 3 s, con el LLM).

    API_KEY=<clave> python3 herramientas/evaluar_llm.py https://<ip-con-guiones>.sslip.io

Deja evaluacion_llm.csv con una columna «correcta» vacía: léanla y marquen sí o no en cada fila. Solo usa
la biblioteca estándar de Python: corre en CloudShell, en la EC2 o en tu computador.
Son 20 solicitudes en serie, muy por debajo del límite de NVIDIA: no es una prueba de carga.
"""
import csv
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESPERA_MAXIMA_S = 60


def llamar(metodo: str, url: str, cuerpo: dict | None = None) -> dict:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    pedido = urllib.request.Request(url, data=datos, method=metodo, headers={
        "X-API-Key": os.getenv("API_KEY", ""), "content-type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=30) as r:
        return json.load(r)


def percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(p / 100 * (len(ordenados) - 1)))]


def main():
    if len(sys.argv) < 2 or not os.getenv("API_KEY"):
        sys.exit("Uso: API_KEY=<clave> python3 herramientas/evaluar_llm.py https://<ip-con-guiones>.sslip.io")
    base = sys.argv[1].rstrip("/")
    mensajes = [l.strip() for l in (RAIZ / "pruebas" / "mensajes_llm.txt").read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    filas, totales = [], []
    for i, mensaje in enumerate(mensajes, 1):
        inicio = time.perf_counter()
        r = llamar("POST", f"{base}/api/conversacion", {"mensaje": mensaje, "canal": "web"})
        inmediata_ms = (time.perf_counter() - inicio) * 1000
        estado, d = r.get("estado_llm"), r
        while estado == "pendiente" and time.perf_counter() - inicio < ESPERA_MAXIMA_S:
            time.sleep(0.2)
            d = llamar("GET", f"{base}/api/predicciones/{r['id']}")
            estado = d.get("estado_llm")
        total_ms = (time.perf_counter() - inicio) * 1000
        if estado == "listo":
            totales.append(total_ms)
        filas.append({"n": i, "mensaje": mensaje, "intencion": r.get("decision"), "probabilidad": r.get("probabilidad"),
                      "origen": r.get("origen"), "derivar": r.get("derivar"), "estado_llm": estado,
                      "respuesta_inmediata_ms": round(inmediata_ms), "total_con_llm_ms": round(total_ms),
                      "latencia_llm_ms": d.get("latencia_llm_ms"), "texto_llm": d.get("texto_llm") or d.get("motivo_llm"),
                      "correcta": ""})
        print(f"{i:2d} · {r.get('decision', '?'):15s} · {estado:13s} · {total_ms:6.0f} ms")

    salida = Path("evaluacion_llm.csv")
    with salida.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"\n{len(totales)} de {len(filas)} con texto listo. Planilla: {salida} (marquen «correcta» a mano)")
    if totales:
        print(f"Tiempo total hasta la respuesta del LLM: p50 {statistics.median(totales):.0f} ms · "
              f"p95 {percentil(totales, 95):.0f} ms · máximo {max(totales):.0f} ms  (RNF1 del caso: p95 < 3000 ms)")


if __name__ == "__main__":
    main()
