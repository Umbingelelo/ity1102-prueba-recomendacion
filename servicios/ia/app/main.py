"""Microservicio de IA: recibe filas de negocio, las convierte en variables y devuelve la predicción.

No toca la base de datos: lo que necesita le llega en la petición (lo arma el dominio). Corre con dos
réplicas detrás del gateway; por eso no guarda nada en memoria entre peticiones.
"""
import json
import os
import socket
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from app.explicar import razones, variantes
from app.motores import cargar_metadatos, crear_motor
from comun.caracteristicas import modulo
from comun.caso import caso_actual

CASO = caso_actual()
VARIABLES = modulo(CASO)
METADATOS = cargar_metadatos()
if METADATOS["columnas"] != VARIABLES.COLUMNAS:
    # Si alguien cambió las variables y no reentrenó, el modelo recibiría columnas en otro orden
    raise SystemExit("Las columnas del modelo no coinciden con comun/caracteristicas: reentrena con entrenar.py")
MOTOR = crear_motor(METADATOS)
REPLICA = socket.gethostname()   # el id del contenedor: sirve para ver qué réplica respondió

PREDICCIONES = Counter("ia_predicciones_total", "Filas predichas", ["motor", "resultado"])
LATENCIA = Histogram("ia_latencia_segundos", "Tiempo de /predict", buckets=(.01, .025, .05, .1, .2, .5, 1, 2, 5, 10))

app = FastAPI(title=f"Microservicio de IA · caso {CASO}", description="Predicción con el modelo propio del equipo")


class Pedido(BaseModel):
    filas: list[dict] = Field(min_length=1, max_length=100, description="Filas de negocio, ver /ejemplo")
    explicar: bool = Field(False, description="Agrega las razones de cada predicción (solo modelos binarios)")


def log(**campos):
    print(json.dumps({"servicio": "ia", "replica": REPLICA, **campos}, ensure_ascii=False), flush=True)


@app.get("/health")
def health():
    return {"estado": "ok", "caso": CASO, "motor": MOTOR.nombre, "modelo": MOTOR.estado(),
            "version_modelo": MOTOR.version, "replica": REPLICA}


@app.get("/ejemplo")
def ejemplo():
    return {"filas": [VARIABLES.EJEMPLO_FILA], "columnas": VARIABLES.COLUMNAS}


@app.post("/predict")
def predict(pedido: Pedido):
    inicio = time.perf_counter()
    filas = [VARIABLES.vectorizar(f) for f in pedido.filas]
    binaria = METADATOS["tipo"] == "binaria"
    explicar = pedido.explicar and binaria
    # Con explicación, cada fila viaja junto a sus variantes en la MISMA llamada al modelo (un solo viaje)
    lotes = [variantes(f, METADATOS["referencia"]) if explicar else [f] for f in filas]
    try:
        probas = MOTOR.probabilidades([v for lote in lotes for v in lote])
    except Exception as e:
        PREDICCIONES.labels(MOTOR.nombre, "error").inc(len(filas))
        log(evento="error_modelo", motor=MOTOR.nombre, error=type(e).__name__, detalle=str(e)[:200])
        raise HTTPException(status_code=503, detail=f"El modelo no respondió: {type(e).__name__}")
    clases = METADATOS["clases"]
    resultados, i = [], 0
    for fila, lote in zip(filas, lotes):
        p, propias = probas[i], probas[i:i + len(lote)]
        i += len(lote)
        if binaria:
            r = {"probabilidad": round(p[1], 4)}
            if explicar:
                r["razones"] = razones([x[1] for x in propias], fila, METADATOS["referencia"], VARIABLES.COLUMNAS,
                                       VARIABLES.LEGIBLE)
        else:
            orden = sorted(range(len(clases)), key=lambda k: p[k], reverse=True)
            r = {"clase": clases[orden[0]], "probabilidad": round(p[orden[0]], 4),
                 "alternativas": [{"clase": clases[k], "probabilidad": round(p[k], 4)} for k in orden[1:3]]}
        resultados.append(r)
    ms = round((time.perf_counter() - inicio) * 1000)
    LATENCIA.observe(ms / 1000)
    PREDICCIONES.labels(MOTOR.nombre, "ok").inc(len(filas))
    log(evento="prediccion", filas=len(filas), latencia_ms=ms, version_modelo=MOTOR.version)
    return {"version_modelo": MOTOR.version, "motor": MOTOR.nombre, "replica": REPLICA, "latencia_ms": ms,
            "resultados": resultados}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
