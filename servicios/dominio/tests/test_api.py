"""Las pruebas que sirven para los tres casos. Las seis obligatorias de EP3 §4.3 están marcadas.

Cada caso declara en app/casos/<caso>.py:
    EJEMPLOS["valido"]   un cuerpo válido para POST /api/predict
    EJEMPLOS["con_llm"]  una petición que tiene que encolar texto para el LLM
"""
import pytest

from app import ia, seguridad
from conftest import CLAVE


def _valido(sistema):
    return sistema["caso"].EJEMPLOS["valido"]


def _con_llm(sistema):
    pedido = sistema["caso"].EJEMPLOS["con_llm"]
    return sistema["cliente"].request(pedido["metodo"], pedido["ruta"], json=pedido.get("json"), headers=CLAVE)


# Prueba obligatoria 1
def test_prediccion_valida_responde_200_con_resultado_y_version_de_modelo(sistema):
    r = sistema["cliente"].post("/api/predict", json=_valido(sistema), headers=CLAVE)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["decision"] and cuerpo["origen"] == "modelo"
    assert cuerpo["version_modelo"] not in ("", "desconocida", "reserva")
    guardada = sistema["cliente"].get(f"/api/predicciones/{cuerpo['id']}", headers=CLAVE).json()
    assert guardada["version_modelo"] == cuerpo["version_modelo"]          # quedó guardada con su versión
    assert guardada["entrada"] and guardada["resultado"] is not None


# Prueba obligatoria 2
def test_campo_faltante_o_de_tipo_incorrecto_responde_422(sistema):
    valido = _valido(sistema)
    r = sistema["cliente"].post("/api/predict", json={}, headers=CLAVE)
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "missing"
    texto = [k for k, v in valido.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if texto:
        r = sistema["cliente"].post("/api/predict", json={**valido, texto[0]: "mucho"}, headers=CLAVE)
        assert r.status_code == 422
    r = sistema["cliente"].post("/api/predict", json={**valido, "campo_que_no_existe": 1}, headers=CLAVE)
    assert r.status_code == 422, "Entrada tiene que rechazar campos desconocidos (extra='forbid')"


# Prueba obligatoria 3
def test_sin_clave_o_con_clave_incorrecta_responde_401(sistema):
    assert sistema["cliente"].post("/api/predict", json=_valido(sistema)).status_code == 401
    r = sistema["cliente"].post("/api/predict", json=_valido(sistema), headers={"X-API-Key": "otra"})
    assert r.status_code == 401


# Prueba obligatoria 4
def test_rafaga_sobre_el_limite_responde_429(sistema, monkeypatch):
    monkeypatch.setattr(seguridad, "LIMITE_POR_MINUTO", 5)
    codigos = [sistema["cliente"].post("/api/predict", json=_valido(sistema), headers=CLAVE).status_code
               for _ in range(6)]
    assert codigos == [200] * 5 + [429]


# Prueba obligatoria 6 (mitad dominio): la cola caída no tumba la predicción
def test_cola_caida_la_prediccion_responde_igual_en_modo_degradado(sistema, monkeypatch):
    from app import cola

    def caida(_pedido):
        raise ConnectionError("RabbitMQ no responde")
    monkeypatch.setattr(cola, "publicar", caida)
    r = _con_llm(sistema)
    assert r.status_code == 200, r.text
    assert r.json()["estado_llm"] == "degradado"


def test_lo_que_va_al_llm_sale_anonimizado_y_en_la_cola(sistema):
    r = _con_llm(sistema)
    assert r.status_code == 200 and r.json()["estado_llm"] == "pendiente"
    pedido = sistema["publicados"][0]
    assert pedido["id"] == r.json()["id"] and pedido["instruccion"] and pedido["contenido"]
    for dato in ("12.345.678-9", "@correo.cl", "4111 1111"):
        assert dato not in pedido["contenido"]


def test_modelo_caido_se_responde_con_la_politica_de_reserva(sistema, monkeypatch):
    def caido(*_args, **_kwargs):
        raise ia.ModeloNoDisponible("sin respuesta en 300 ms")
    monkeypatch.setattr(ia, "predecir", caido)
    r = sistema["cliente"].post("/api/predict", json=_valido(sistema), headers=CLAVE)
    assert r.status_code == 200, r.text
    assert r.json()["origen"] == "reserva"


def test_prediccion_inexistente_responde_404(sistema):
    assert sistema["cliente"].get("/api/predicciones/no-existe", headers=CLAVE).status_code == 404


def test_health_y_docs_son_publicos(sistema):
    assert sistema["cliente"].get("/api/health").json()["piezas"]["base"] == "ok"
    assert sistema["cliente"].get("/docs").status_code == 200


@pytest.mark.parametrize("ruta", ["/api/dashboard", "/api/caso"])
def test_dashboard_y_caso_responden(sistema, ruta):
    assert sistema["cliente"].get(ruta, headers=CLAVE).status_code == 200
