"""Cliente del microservicio de IA.

Se llama a través del gateway (http://gateway:8080/api/ia/...), no directo a «ia:8000»: así el gateway
reparte entre las dos réplicas y, si una se cae, reintenta en la otra. Es la misma ruta que se muestra
en la defensa.
"""
import os
import time

import httpx

URL_IA = os.getenv("URL_IA", "http://gateway:8080/api/ia")
cliente = httpx.Client(base_url=URL_IA)


class ModeloNoDisponible(Exception):
    """El modelo no respondió a tiempo o respondió con error. El caso decide qué hacer (plan de reserva)."""


def predecir(filas: list[dict], timeout_ms: int, explicar: bool = False) -> dict:
    inicio = time.perf_counter()
    try:
        r = cliente.post("/predict", json={"filas": filas, "explicar": explicar}, timeout=timeout_ms / 1000)
        r.raise_for_status()
    except httpx.TimeoutException as e:
        raise ModeloNoDisponible(f"sin respuesta en {timeout_ms} ms") from e
    except httpx.HTTPError as e:
        raise ModeloNoDisponible(f"{type(e).__name__}: {str(e)[:120]}") from e
    respuesta = r.json()
    respuesta["latencia_total_ms"] = round((time.perf_counter() - inicio) * 1000)
    return respuesta


def salud() -> dict:
    try:
        return cliente.get("/health", timeout=3).json()
    except httpx.HTTPError as e:
        return {"estado": f"error: {type(e).__name__}"}
