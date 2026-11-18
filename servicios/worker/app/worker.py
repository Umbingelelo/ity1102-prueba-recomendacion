"""El worker (EP3): saca un pedido de la cola, le pide el texto al LLM y lo entrega al dominio.

Nunca toma la decisión: la decisión ya la tomó el modelo. El LLM solo redacta. Tampoco escribe en la base:
le entrega el texto al dominio por su ruta interna, porque el dominio es el único que escribe ahí.
"""
import json
import os
import time

import httpx

from app import llm

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")
URL_DOMINIO = os.getenv("URL_DOMINIO", "http://dominio:8000")
COLA, COLA_FALLIDOS = "llm", "llm.fallidos"


def log(**campos):
    print(json.dumps({"servicio": "worker", **campos}, ensure_ascii=False), flush=True)


def entregar(id_: str, datos: dict, cliente=None) -> None:
    cliente = cliente or httpx
    r = cliente.put(f"{URL_DOMINIO}/interno/predicciones/{id_}/llm", json=datos, timeout=5)
    r.raise_for_status()


def estado_actual(id_: str, cliente=None) -> str | None:
    """El estado del texto de esa predicción en el dominio, o None si la predicción ya no existe."""
    cliente = cliente or httpx
    r = cliente.get(f"{URL_DOMINIO}/interno/predicciones/{id_}/llm", timeout=5)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("estado")


def procesar(pedido: dict, redactar=llm.redactar, cliente=None) -> str:
    estado = estado_actual(pedido["id"], cliente)
    if estado is None:
        # La predicción se borró (por ejemplo, se vació la base): no tiene sentido gastar una llamada al LLM
        # ni devolver el mensaje a la cola, donde daría vueltas para siempre.
        return "descartado"
    # Idempotencia: si el worker murió después de entregar y antes del ack, RabbitMQ entrega el mismo
    # mensaje otra vez. No se vuelve a gastar una llamada al LLM.
    if estado == "listo":
        return "listo"
    inicio = time.perf_counter()
    try:
        texto = redactar(pedido["instruccion"], pedido["contenido"])
    except llm.LLMNoDisponible as e:
        entregar(pedido["id"], {"estado": "degradado", "motivo": str(e)}, cliente)
        return "degradado"
    entregar(pedido["id"], {"estado": "listo", "texto": texto,
                            "latencia_ms": round((time.perf_counter() - inicio) * 1000)}, cliente)
    return "listo"


def main():
    import pika
    parametros = pika.URLParameters(RABBITMQ_URL)
    # heartbeat largo: con los reintentos una llamada puede tardar más de un minuto, y mientras tanto el
    # worker no atiende la conexión. Con el heartbeat por defecto RabbitMQ lo daría por muerto.
    parametros.heartbeat = 600
    conexion = pika.BlockingConnection(parametros)
    canal = conexion.channel()
    canal.queue_declare(queue=COLA_FALLIDOS, durable=True)
    canal.queue_declare(queue=COLA, durable=True,
                        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": COLA_FALLIDOS})
    canal.basic_qos(prefetch_count=1)   # de a un mensaje: el siguiente no llega hasta el ack

    def al_recibir(ch, metodo, _propiedades, cuerpo):
        pedido = json.loads(cuerpo)
        try:
            estado = procesar(pedido)
        except httpx.HTTPError as e:      # el dominio no respondió: el mensaje vuelve a la cola
            log(evento="llm", id=pedido.get("id"), estado="reintentar", motivo=type(e).__name__)
            time.sleep(2)
            ch.basic_nack(delivery_tag=metodo.delivery_tag, requeue=True)
            return
        log(evento="llm", id=pedido["id"], estado=estado)
        if estado in ("listo", "descartado"):
            ch.basic_ack(delivery_tag=metodo.delivery_tag)
        else:
            # requeue=False: no vuelve a la cola (sería un bucle contra una clave mala), va a llm.fallidos
            ch.basic_nack(delivery_tag=metodo.delivery_tag, requeue=False)

    canal.basic_consume(queue=COLA, on_message_callback=al_recibir)
    log(evento="inicio", modelo=llm.MODELO or "(falta NVIDIA_MODEL)", cola=COLA)
    canal.start_consuming()


if __name__ == "__main__":
    main()
