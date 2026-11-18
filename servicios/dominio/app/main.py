"""Microservicio de dominio: la API pública del sistema y la lógica de negocio del caso.

Recibe la petición del front, la enriquece con la base, le pide la predicción al microservicio de IA,
aplica las reglas del caso, guarda todo y, en EP3, encola el texto para el LLM. Es el único que escribe
en la base. Lo propio de cada caso vive en app/casos/<caso>.py; este archivo es igual para los tres.
"""
import importlib
import time
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app import cola, db, ia, registro, seguridad
from app.registro import log
from comun.caso import caso_actual

CASO = caso_actual()
caso = importlib.import_module(f"app.casos.{CASO}")

PETICIONES = Counter("dominio_peticiones_total", "Peticiones HTTP", ["ruta", "codigo"])
LATENCIA = Histogram("dominio_latencia_segundos", "Latencia por ruta", ["ruta"],
                     buckets=(.01, .025, .05, .1, .2, .3, .5, 1, 2, 3, 5, 10))


@asynccontextmanager
async def ciclo_de_vida(_app):
    db.abrir()      # al arrancar: abre las conexiones a la base (se cierran solas al terminar el proceso)
    yield


app = FastAPI(title=f"API · {caso.TITULO}", description=caso.DESCRIPCION, version="1.0",
              docs_url="/docs", openapi_url="/openapi.json", lifespan=ciclo_de_vida)


@app.middleware("http")
async def medir(request: Request, siguiente):
    inicio = time.perf_counter()
    respuesta = await siguiente(request)
    ruta = request.scope.get("route").path if request.scope.get("route") else "desconocida"
    segundos = time.perf_counter() - inicio
    PETICIONES.labels(ruta, respuesta.status_code).inc()
    LATENCIA.labels(ruta).observe(segundos)
    if ruta not in ("/metrics", "/api/health"):
        log(evento="http", metodo=request.method, ruta=ruta, codigo=respuesta.status_code,
            ms=round(segundos * 1000, 1))
    return respuesta


# ---------------------------------------------------------------------------------------------------
# Rutas comunes a los tres casos (EP3 §2.5)
# ---------------------------------------------------------------------------------------------------

@app.get("/api/health", tags=["sistema"])
def health():
    piezas = {}
    try:
        db.uno("SELECT 1")
        piezas["base"] = "ok"
    except Exception as e:
        piezas["base"] = f"error: {type(e).__name__}"
    piezas["ia"] = ia.salud()
    piezas["cola"] = cola.estado()
    try:
        ultimo = db.uno("SELECT estado_llm, motivo_llm FROM predicciones WHERE estado_llm IN ('listo','degradado') "
                        "ORDER BY creada DESC LIMIT 1")
        piezas["llm"] = ("sin llamadas todavía" if not ultimo else
                         "ok" if ultimo["estado_llm"] == "listo" else f"degradado: {ultimo['motivo_llm']}")
    except Exception:
        piezas["llm"] = "desconocido"
    sano = piezas["base"] == "ok" and piezas["ia"].get("estado") == "ok"
    return {"estado": "ok" if sano else "degradado", "caso": CASO,
            "autenticacion": "activa" if seguridad.API_KEYS else "desactivada", "piezas": piezas}


@app.get("/api/caso", tags=["sistema"])
def info_caso():
    """Lo que el front necesita para dibujar el formulario de este caso."""
    return {"caso": CASO, "titulo": caso.TITULO, "descripcion": caso.DESCRIPCION,
            "requiere_clave": bool(seguridad.API_KEYS), **caso.FRONT}


@app.post("/api/predict", tags=["prediccion"], dependencies=[Depends(seguridad.requiere_clave)])
def predict(entrada: caso.Entrada):
    inicio = time.perf_counter()
    return registro.registrar(caso.predecir(entrada), inicio)


@app.get("/api/predicciones/{id}", tags=["prediccion"], dependencies=[Depends(seguridad.requiere_clave)])
def prediccion(id: str):
    fila = db.uno("SELECT * FROM predicciones WHERE id = %s", id)
    if not fila:
        raise HTTPException(status_code=404, detail="No existe esa predicción")
    return db.jsonable(fila)


@app.get("/api/predicciones", tags=["prediccion"], dependencies=[Depends(seguridad.requiere_clave)])
def predicciones(limite: int = 20):
    filas = db.todos("SELECT id, creada, decision, probabilidad, origen, version_modelo, latencia_ms, estado_llm "
                     "FROM predicciones ORDER BY creada DESC LIMIT %s", min(max(limite, 1), 200))
    return [db.jsonable(f) for f in filas]


@app.get("/api/dashboard", tags=["sistema"], dependencies=[Depends(seguridad.requiere_clave)])
def dashboard():
    comun = db.uno(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE origen = 'modelo') AS por_modelo,
                  count(*) FILTER (WHERE origen = 'reserva') AS por_reserva,
                  count(*) FILTER (WHERE origen = 'regla') AS por_regla,
                  count(*) FILTER (WHERE estado_llm = 'listo') AS llm_listo,
                  count(*) FILTER (WHERE estado_llm = 'degradado') AS llm_degradado,
                  percentile_cont(0.5) WITHIN GROUP (ORDER BY latencia_ms) AS latencia_p50_ms,
                  percentile_cont(0.95) WITHIN GROUP (ORDER BY latencia_ms) AS latencia_p95_ms
           FROM predicciones""")
    return {"caso": CASO, "general": db.jsonable(comun), **caso.dashboard()}


# Solo para el worker (EP3). El gateway no publica /interno: se llega únicamente desde la red de Docker.
@app.get("/interno/predicciones/{id}/llm", include_in_schema=False)
def estado_llm(id: str):
    fila = db.uno("SELECT estado_llm FROM predicciones WHERE id = %s", id)
    if not fila:
        raise HTTPException(status_code=404, detail="No existe esa predicción")
    return {"estado": fila["estado_llm"]}


@app.put("/interno/predicciones/{id}/llm", include_in_schema=False)
def guardar_llm(id: str, datos: dict = Body(...)):
    filas = db.ejecutar("UPDATE predicciones SET estado_llm=%s, texto_llm=%s, motivo_llm=%s, latencia_llm_ms=%s "
                        "WHERE id=%s", datos.get("estado"), datos.get("texto"), datos.get("motivo"),
                        datos.get("latencia_ms"), id)
    if not filas:
        raise HTTPException(status_code=404, detail="No existe esa predicción")
    return {"ok": True}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(caso.router, prefix="/api", dependencies=[Depends(seguridad.requiere_clave)], tags=["caso"])
