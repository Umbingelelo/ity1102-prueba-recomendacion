"""Reglas propias del caso 3 (Kipu Pagos). Solo corren con CASO=fraude (ver conftest.py)."""
from app import ia
from app.casos import fraude
from conftest import CLAVE

LISTADO = {"usuario_id": "KP300267", "dispositivo_id": "D-1da29c52b0ed", "monto": 9000, "canal": "web"}


def test_lista_negra_bloquea_antes_del_modelo(sistema, monkeypatch):
    def no_deberia_llamarse(*_a, **_k):
        raise AssertionError("con una regla dura no se consulta el modelo")
    monkeypatch.setattr(ia, "predecir", no_deberia_llamarse)
    r = sistema["cliente"].post("/api/predict", json=LISTADO, headers=CLAVE).json()
    assert r["decision"] == "bloquear" and r["origen"] == "regla"
    assert r["razones"][0]["descripcion"] == "dispositivo en lista negra"


def test_cada_decision_del_modelo_trae_sus_razones_ordenadas(sistema):
    r = sistema["cliente"].post("/api/predict", json=fraude.EJEMPLOS["valido"], headers=CLAVE).json()
    assert r["origen"] == "modelo" and r["razones"]
    aportes = [x["aporte"] for x in r["razones"]]
    assert aportes == sorted(aportes, reverse=True)


def test_los_umbrales_vienen_de_configuracion(sistema, monkeypatch):
    monkeypatch.setattr(fraude, "UMBRAL_REVISAR", 0.0)
    monkeypatch.setattr(fraude, "UMBRAL_BLOQUEAR", 1.01)
    r = sistema["cliente"].post("/api/predict", json=fraude.EJEMPLOS["valido"], headers=CLAVE).json()
    assert r["decision"] == "revisar" and r["umbrales"] == {"revisar": 0.0, "bloquear": 1.01}


def test_reserva_por_reglas_usa_las_senales_de_la_transaccion(sistema, monkeypatch):
    def caido(*_a, **_k):
        raise ia.ModeloNoDisponible("sin respuesta en 300 ms")
    monkeypatch.setattr(ia, "predecir", caido)
    madrugada = {**fraude.EJEMPLOS["valido"], "hora_local": 2, "intentos_previos_1h": 6}
    r = sistema["cliente"].post("/api/predict", json=madrugada, headers=CLAVE).json()
    assert r["origen"] == "reserva" and r["decision"] in ("revisar", "bloquear")
    assert any("madrugada" in x["descripcion"] for x in r["razones"])


def test_el_numero_de_tarjeta_no_se_acepta(sistema):
    r = sistema["cliente"].post("/api/predict", json={**fraude.EJEMPLOS["valido"], "tarjeta": "4111111111111111"},
                                headers=CLAVE)
    assert r.status_code == 422


def test_la_cola_de_revision_incluye_lo_bloqueado(sistema):
    sistema["cliente"].post("/api/predict", json=LISTADO, headers=CLAVE)
    cola = sistema["cliente"].get("/api/revision", headers=CLAVE).json()
    assert cola and {f["decision"] for f in cola} <= {"revisar", "bloquear"}
