"""Publica en RabbitMQ los pedidos de texto para el LLM (EP3). El worker los consume.

Sin RABBITMQ_URL (EP2) no hay cola: la predicción queda con estado_llm = «no_configurado». La
declaración de la cola es la misma que usa el worker (servicios/worker/app/cola.py): si no coinciden,
RabbitMQ rechaza la segunda con PRECONDITION_FAILED.
"""
import json
import os

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")
COLA, COLA_FALLIDOS = "llm", "llm.fallidos"


def configurada() -> bool:
    return bool(RABBITMQ_URL)


def _conectar():
    import pika
    parametros = pika.URLParameters(RABBITMQ_URL)
    parametros.connection_attempts = 1
    parametros.socket_timeout = 2
    parametros.blocked_connection_timeout = 5
    return pika.BlockingConnection(parametros)


def _declarar(canal):
    canal.queue_declare(queue=COLA_FALLIDOS, durable=True)
    canal.queue_declare(queue=COLA, durable=True,
                        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": COLA_FALLIDOS})


def publicar(pedido: dict) -> None:
    import pika
    conexion = _conectar()
    try:
        canal = conexion.channel()
        _declarar(canal)
        canal.basic_publish(exchange="", routing_key=COLA, body=json.dumps(pedido, ensure_ascii=False),
                            properties=pika.BasicProperties(delivery_mode=2))   # 2 = persistente
    finally:
        conexion.close()


def estado() -> dict:
    if not configurada():
        return {"estado": "no_configurada"}
    try:
        conexion = _conectar()
        canal = conexion.channel()
        _declarar(canal)
        datos = {"estado": "ok",
                 "pendientes": canal.queue_declare(queue=COLA, passive=True).method.message_count,
                 "fallidos": canal.queue_declare(queue=COLA_FALLIDOS, passive=True).method.message_count}
        conexion.close()
        return datos
    except Exception as e:
        return {"estado": f"error: {type(e).__name__}"}
