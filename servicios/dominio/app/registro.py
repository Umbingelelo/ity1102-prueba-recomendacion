"""Lo que pasa con cada predicción después de que el caso decide: se guarda, se encola para el LLM y se
registra en el log. Lo usan POST /api/predict y las rutas propias de cada caso (por ejemplo, la de
campañas del caso 1 o la de conversación del caso 2): así todas guardan y encolan igual.
"""
import json
import time
import uuid

from prometheus_client import Counter

from app import cola, db
from comun.anonimizar import anonimizar
from comun.caso import caso_actual

CASO = caso_actual()
DECISIONES = Counter("dominio_decisiones_total", "Decisiones por origen", ["decision", "origen"])


def log(**campos):
    # Una línea JSON por evento: en CloudWatch se filtra por cualquier campo sin parsear nada
    print(json.dumps({"servicio": "dominio", **campos}, ensure_ascii=False, default=str), flush=True)


def registrar(salida: dict, inicio: float) -> dict:
    """salida: lo que devolvió predecir() del caso. inicio: time.perf_counter() del comienzo."""
    id_ = uuid.uuid4().hex
    ms = round((time.perf_counter() - inicio) * 1000)

    # El LLM va por la cola y nunca en este camino: la respuesta no lo espera (EP3 §2.3, regla 4)
    estado_llm = "no_solicitado"
    if salida.get("llm"):
        estado_llm = "pendiente" if cola.configurada() else "no_configurado"
    db.guardar_prediccion(id_, CASO, salida["entrada_guardada"], salida["resultado"], salida["decision"],
                          salida.get("probabilidad"), salida["version_modelo"], salida["origen"], ms, estado_llm)
    if estado_llm == "pendiente":
        try:
            # El contenido sale anonimizado: ni la cola, ni el worker, ni NVIDIA ven datos personales
            contenido = anonimizar(json.dumps(salida["llm"]["contenido"], ensure_ascii=False))
            cola.publicar({"id": id_, "caso": CASO, "instruccion": salida["llm"]["instruccion"],
                           "contenido": contenido})
        except Exception as e:   # RabbitMQ caído: la predicción se entrega igual, sin texto del LLM
            estado_llm = "degradado"
            db.ejecutar("UPDATE predicciones SET estado_llm='degradado', motivo_llm=%s WHERE id=%s",
                        f"cola: {type(e).__name__}", id_)

    DECISIONES.labels(salida["decision"], salida["origen"]).inc()
    log(evento="prediccion", id=id_, decision=salida["decision"], probabilidad=salida.get("probabilidad"),
        origen=salida["origen"], version_modelo=salida["version_modelo"], latencia_ms=ms, estado_llm=estado_llm)
    return {"id": id_, "caso": CASO, "decision": salida["decision"], "probabilidad": salida.get("probabilidad"),
            "origen": salida["origen"], "version_modelo": salida["version_modelo"], "latencia_ms": ms,
            "estado_llm": estado_llm, **salida["resultado"]}
