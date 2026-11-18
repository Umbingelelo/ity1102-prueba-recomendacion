"""Pruebas del dominio contra un PostgreSQL de verdad y el modelo de verdad, sin red entre servicios.

- La base: la de DATABASE_URL (en el pipeline, un servicio postgres del runner). Se llena con el mismo
  cargar.py del servicio de carga, a partir de datos/tratados/tablas.
- La IA: en vez de ir por HTTP al gateway, se usa el motor local de servicios/ia con modelo/artefactos.
  Es el mismo código que corre en el contenedor, sin el viaje por la red.
- La cola: un doble que guarda lo que se publicó.

En tu computador:
    docker run -d --name pg-pruebas -p 5433:5432 -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app \
        -e POSTGRES_DB=proyecto postgres:16-alpine
    DATABASE_URL=postgresql://app:app@localhost:5433/proyecto PYTHONPATH=servicios/dominio:. pytest servicios/dominio/tests
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("CASO", (RAIZ / "CASO").read_text().strip())
os.environ.setdefault("DATABASE_URL", "postgresql://app:app@localhost:5433/proyecto")
os.environ.update(API_KEYS="clave-de-prueba", LIMITE_POR_MINUTO="1000", MODELO_DIR=str(RAIZ / "modelo" / "artefactos"),
                  TABLAS=str(RAIZ / "datos" / "tratados" / "tablas"), ESQUEMAS=str(RAIZ / "servicios" / "carga" / "esquemas"))

CLAVE = {"X-API-Key": "clave-de-prueba"}

# Las pruebas propias de cada caso (test_caso_<caso>.py) solo corren con ese caso
collect_ignore_glob = [f"test_caso_{c}.py" for c in ("recomendacion", "chatbot", "fraude") if c != os.environ["CASO"]]


def _cargar_modulo(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 1. La base con los datos tratados (idempotente: correrlo en cada sesión no duplica)
_cargar_modulo("cargar", RAIZ / "servicios" / "carga" / "cargar.py").main()

# 2. El motor de IA real, cargado por ruta (el paquete «app» de la IA chocaría con el del dominio)
_motores = _cargar_modulo("ia_motores", RAIZ / "servicios" / "ia" / "app" / "motores.py")
_explicar = _cargar_modulo("ia_explicar", RAIZ / "servicios" / "ia" / "app" / "explicar.py")

from comun.caracteristicas import modulo  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import cola, ia, main, seguridad  # noqa: E402

METADATOS = _motores.cargar_metadatos()
MOTOR = _motores.MotorLocal(METADATOS)
VARIABLES = modulo(os.environ["CASO"])


def predecir_local(filas, timeout_ms, explicar=False):
    """Lo mismo que POST /api/ia/predict, sin HTTP. Ver servicios/ia/app/main.py."""
    vectores = [VARIABLES.vectorizar(f) for f in filas]
    probas = MOTOR.probabilidades(vectores)
    resultados = []
    for v, p in zip(vectores, probas):
        if METADATOS["tipo"] == "binaria":
            r = {"probabilidad": round(p[1], 4)}
            if explicar:
                p_var = [x[1] for x in MOTOR.probabilidades(_explicar.variantes(v, METADATOS["referencia"]))]
                r["razones"] = _explicar.razones(p_var, v, METADATOS["referencia"], VARIABLES.COLUMNAS,
                                                 VARIABLES.LEGIBLE)
        else:
            orden = sorted(range(len(p)), key=lambda i: p[i], reverse=True)
            r = {"clase": METADATOS["clases"][orden[0]], "probabilidad": round(p[orden[0]], 4),
                 "alternativas": [{"clase": METADATOS["clases"][i], "probabilidad": round(p[i], 4)} for i in orden[1:3]]}
        resultados.append(r)
    return {"version_modelo": METADATOS["version"], "motor": "local", "latencia_ms": 1, "resultados": resultados}


@pytest.fixture
def sistema(monkeypatch):
    publicados = []
    monkeypatch.setattr(ia, "predecir", predecir_local)
    monkeypatch.setattr(ia, "salud", lambda: {"estado": "ok", "motor": "local", "version_modelo": METADATOS["version"]})
    monkeypatch.setattr(cola, "configurada", lambda: True)
    monkeypatch.setattr(cola, "publicar", publicados.append)
    monkeypatch.setattr(cola, "estado", lambda: {"estado": "ok", "pendientes": len(publicados), "fallidos": 0})
    seguridad._contadores.clear()
    with TestClient(main.app) as cliente:
        yield {"cliente": cliente, "publicados": publicados, "caso": main.caso}
