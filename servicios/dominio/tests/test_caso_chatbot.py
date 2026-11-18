"""Pruebas de las reglas de negocio del caso 2 (RF6, RF8, RNF5, RNF11). Usan la base y el modelo de verdad.

Cada prueba usa su propio conversacion_id (uuid): la tabla sesiones_chat queda entre una corrida y otra.
"""
import uuid

from app import ia
from conftest import CLAVE


def _enviar(sistema, mensaje, conversacion_id=None, ruta="/api/predict"):
    cuerpo = {"mensaje": mensaje, "canal": "whatsapp"}
    if conversacion_id:
        cuerpo["conversacion_id"] = conversacion_id
    r = sistema["cliente"].post(ruta, json=cuerpo, headers=CLAVE)
    assert r.status_code == 200, r.text
    return r.json()


def test_pedir_una_persona_deriva_sin_preguntar_al_modelo(sistema, monkeypatch):
    def no_deberia_llamarse(*_args, **_kwargs):
        raise AssertionError("RNF11: la derivación pedida no pasa por el modelo")
    monkeypatch.setattr(ia, "predecir", no_deberia_llamarse)
    for mensaje in ("quiero hablar con una persona", "EJECUTIVO", "me pasas con alguien de verdad?"):
        r = _enviar(sistema, mensaje)
        assert (r["decision"], r["origen"], r["derivar"]) == ("derivar", "regla", True)
        assert r["estado_llm"] == "no_solicitado"   # la derivación no depende del LLM


def test_intencion_de_anular_deriva_y_no_se_responde_con_el_llm(sistema):
    r = _enviar(sistema, "me voy a la competencia, como cancelo?")
    assert r["decision"] == "derivar" and r["intencion"] == "anulacion" and r["origen"] == "modelo"
    assert "anular" in r["motivo_derivacion"] and r["estado_llm"] == "no_solicitado"
    assert not sistema["publicados"]


def test_molestia_detectada_deriva(sistema):
    for mensaje in ("INTERNET LENTISIMO, CONTRATE 600 MEGAS Y ME LLEGAN 40", "no tengo internet!!! esto es una estafa"):
        r = _enviar(sistema, mensaje)
        assert r["decision"] == "derivar" and r["motivo_derivacion"].startswith("molestia")


def test_tres_intentos_fallidos_derivan_y_la_conversacion_queda_derivada(sistema):
    conversacion = f"prueba-{uuid.uuid4().hex[:12]}"
    decisiones = [_enviar(sistema, "hola", conversacion)["decision"] for _ in range(3)]
    assert decisiones == ["aclarar", "aclarar", "derivar"]
    sesion = sistema["cliente"].get(f"/api/sesiones/{conversacion}", headers=CLAVE).json()
    assert sesion["intentos_fallidos"] == 3 and sesion["derivada"] is True
    # Después de derivar, ni una pregunta clara la saca del ejecutivo
    r = _enviar(sistema, "quiero saber cuanto debo y cuando vence mi cuenta", conversacion)
    assert r["decision"] == "derivar" and r["origen"] == "regla"


def test_responde_con_articulos_vigentes_y_guarda_solo_el_texto_anonimizado(sistema):
    r = _enviar(sistema, "Hola, quiero saber cuanto debo y cuando vence mi cuenta. Mi rut es 12.345.678-9 y "
                         "mi correo ana@correo.cl", ruta="/api/conversacion")
    assert r["decision"] == "facturacion" and r["derivar"] is False and r["estado_llm"] == "pendiente"
    assert 1 <= len(r["articulos"]) <= 3 and r["mensaje"] == r["articulos"][0]["respuesta"]
    assert "vence" in r["articulos"][0]["pregunta"].lower()   # el más parecido al mensaje va primero
    assert r["respuesta_llm_en"] == f"/api/predicciones/{r['id']}"
    guardada = sistema["cliente"].get(r["respuesta_llm_en"], headers=CLAVE).json()
    assert "[RUT]" in guardada["entrada"]["mensaje"] and "[CORREO]" in guardada["entrada"]["mensaje"]
    assert "12.345.678-9" not in str(guardada) and "ana@correo.cl" not in str(guardada)
    faq = sistema["cliente"].get("/api/faq?intencion=facturacion", headers=CLAVE).json()
    assert {a["articulo_id"] for a in r["articulos"]} <= {a["articulo_id"] for a in faq}


def test_dashboard_trae_las_metricas_de_rnf9(sistema):
    _enviar(sistema, "EJECUTIVO")
    d = sistema["cliente"].get("/api/dashboard", headers=CLAVE).json()
    for clave in ("conversaciones_atendidas", "tasa_derivacion_pct", "tasa_modo_degradado_pct", "intenciones"):
        assert clave in d
    assert d["tasa_derivacion_pct"] > 0
