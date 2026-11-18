"""Pruebas del worker sin RabbitMQ, sin NVIDIA y sin dominio: cada pieza externa es un doble.

    PYTHONPATH=servicios/worker pytest servicios/worker/tests
"""
import os

os.environ.setdefault("NVIDIA_MODEL", "modelo-de-prueba")

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402

from app import llm, worker  # noqa: E402


def error_http(codigo):
    respuesta = httpx.Response(codigo, request=httpx.Request("POST", "https://integrate.api.nvidia.com/v1"))
    return openai.APIStatusError(f"HTTP {codigo}", response=respuesta, body=None)


class NvidiaFalso:
    """Responde como cliente.chat.completions.create: primero los errores de la lista, después texto."""

    def __init__(self, errores=(), texto="Resumen para el analista."):
        self.errores, self.texto, self.llamadas = list(errores), texto, 0
        self.chat = self.completions = self

    def create(self, **_):
        self.llamadas += 1
        if self.errores:
            raise self.errores.pop(0)
        mensaje = type("M", (), {"content": self.texto})
        return type("R", (), {"choices": [type("C", (), {"message": mensaje})]})


class DominioFalso:
    """Hace de la ruta interna del dominio: guarda lo que el worker le entrega."""

    def __init__(self, estado="pendiente"):
        self.estado, self.entregas = estado, []

    def get(self, url, timeout):
        if self.estado is None:   # la predicción ya no existe en el dominio
            return httpx.Response(404, json={"detail": "No existe"}, request=httpx.Request("GET", url))
        return httpx.Response(200, json={"estado": self.estado}, request=httpx.Request("GET", url))

    def put(self, url, json, timeout):
        self.entregas.append(json)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("PUT", url))


PEDIDO = {"id": "abc", "caso": "fraude", "instruccion": "Resume.", "contenido": '{"decision": "revisar"}'}


@pytest.fixture
def esperas():
    return []


def test_respuesta_normal_se_entrega_como_listo(monkeypatch):
    monkeypatch.setattr(llm, "cliente", NvidiaFalso())
    dominio = DominioFalso()
    assert worker.procesar(PEDIDO, cliente=dominio) == "listo"
    assert dominio.entregas[0]["estado"] == "listo" and dominio.entregas[0]["texto"] == "Resumen para el analista."


# Prueba obligatoria 6 (mitad worker): NVIDIA con 429 sostenido → modo degradado, sin bucle
def test_llm_con_429_sostenido_queda_degradado_tras_los_reintentos(monkeypatch, esperas):
    falso = NvidiaFalso(errores=[error_http(429)] * llm.INTENTOS)
    monkeypatch.setattr(llm, "cliente", falso)
    dominio = DominioFalso()
    estado = worker.procesar(PEDIDO, redactar=lambda i, c: llm.redactar(i, c, dormir=esperas.append), cliente=dominio)
    assert estado == "degradado"
    assert falso.llamadas == llm.INTENTOS and len(esperas) == llm.INTENTOS - 1
    assert dominio.entregas == [{"estado": "degradado", "motivo": f"HTTP 429 después de {llm.INTENTOS} intentos"}]


def test_reintenta_con_espera_creciente_y_luego_responde(monkeypatch, esperas):
    monkeypatch.setattr(llm, "cliente", NvidiaFalso(errores=[error_http(429), error_http(503)]))
    assert llm.redactar("instrucción", "contenido", dormir=esperas.append) == "Resumen para el analista."
    assert len(esperas) == 2 and esperas[1] > esperas[0] * 1.3


def test_clave_invalida_no_se_reintenta(monkeypatch, esperas):
    falso = NvidiaFalso(errores=[error_http(401)])
    monkeypatch.setattr(llm, "cliente", falso)
    with pytest.raises(llm.LLMNoDisponible, match="401"):
        llm.redactar("instrucción", "contenido", dormir=esperas.append)
    assert falso.llamadas == 1 and esperas == []


def test_no_repite_una_llamada_ya_hecha():
    def no_deberia_llamarse(*_):
        raise AssertionError("llamó al LLM otra vez")
    dominio = DominioFalso(estado="listo")
    assert worker.procesar(PEDIDO, redactar=no_deberia_llamarse, cliente=dominio) == "listo"
    assert dominio.entregas == []


def test_prediccion_borrada_se_descarta_sin_llamar_al_llm():
    """Si la predicción ya no existe (se vació la base), el mensaje no puede quedar dando vueltas en la cola."""
    def no_deberia_llamarse(*_):
        raise AssertionError("llamó al LLM para una predicción que no existe")
    dominio = DominioFalso(estado=None)
    assert worker.procesar(PEDIDO, redactar=no_deberia_llamarse, cliente=dominio) == "descartado"
    assert dominio.entregas == []
