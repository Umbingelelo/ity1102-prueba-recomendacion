"""Autenticación con X-API-Key y límite de solicitudes por minuto.

API_KEYS vacío = autenticación apagada (EP2, defensa local). En EP3 el .env del servidor trae una o más
claves separadas por coma, y desde ese momento sin clave la respuesta es 401.

El límite vive en la memoria del proceso: sirve porque el dominio corre con UNA réplica. Si lo escalas a
dos, cada réplica contaría por su cuenta; ahí el límite se mueve al gateway o a Redis (deuda declarada).
"""
import hmac
import os
import threading
import time

from fastapi import Header, HTTPException, Request

API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
LIMITE_POR_MINUTO = int(os.getenv("LIMITE_POR_MINUTO", "120"))

_contadores: dict[tuple[str, int], int] = {}
_candado = threading.Lock()


def requiere_clave(request: Request, x_api_key: str | None = Header(default=None)):
    if API_KEYS and (not x_api_key or not any(hmac.compare_digest(x_api_key, k) for k in API_KEYS)):
        raise HTTPException(status_code=401, detail="Falta X-API-Key o no es válida")
    # Se cuenta por clave; si la autenticación está apagada, por IP de origen
    quien = x_api_key or request.headers.get("x-real-ip") or (request.client.host if request.client else "?")
    ventana = int(time.time() // 60)
    with _candado:
        for k in [k for k in _contadores if k[1] < ventana]:
            del _contadores[k]
        _contadores[(quien, ventana)] = usadas = _contadores.get((quien, ventana), 0) + 1
    if usadas > LIMITE_POR_MINUTO:
        raise HTTPException(status_code=429, detail=f"Más de {LIMITE_POR_MINUTO} solicitudes por minuto",
                            headers={"Retry-After": str(60 - int(time.time()) % 60)})
