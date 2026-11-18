"""Reglas de negocio del caso 1 (Nexus Retail) que no son el modelo: RF1, RF5, RF6, RF8, RF11, RN2 y RNF7.

Corren contra la base cargada con datos/tratados y el modelo de modelo/artefactos (ver conftest.py).
"""
import pytest

from app import db
from conftest import CLAVE

CON_HISTORIAL = "U100255"   # consentimiento 1 y 15 pedidos


def _usuario(sql: str) -> str:
    fila = db.uno(sql)
    assert fila, f"no hay un usuario de prueba para: {sql}"
    return fila["usuario_id"]


def _predecir(sistema, **cuerpo):
    r = sistema["cliente"].post("/api/predict", json=cuerpo, headers=CLAVE)
    assert r.status_code == 200, r.text
    return r.json()


def test_personalizada_respeta_stock_ficha_actual_y_lo_ya_comprado(sistema):
    r = _predecir(sistema, usuario_id=CON_HISTORIAL, cantidad=7, sku_actual="NX-11040")
    assert r["decision"] == "personalizada" and r["origen"] == "modelo"
    skus = [p["sku"] for p in r["productos"]]
    assert len(skus) == 7 == len(set(skus))                                  # RF1, sin repetidos
    assert "NX-11040" not in skus
    disponibles = db.todos("SELECT sku FROM productos WHERE sku = ANY(%s) AND activo = 1 AND stock > 0 "
                           "AND precio IS NOT NULL", skus)
    assert len(disponibles) == 7                                              # RF5
    compradas = db.todos("SELECT sku FROM transacciones WHERE usuario_id = %s AND es_venta = 1", CON_HISTORIAL)
    assert not set(skus) & {f["sku"] for f in compradas}
    assert all(p["motivo"] for p in r["productos"])                           # RN3: cada uno con su porqué
    probabilidades = [c["probabilidad"] for c in r["categorias"]]
    assert probabilidades == sorted(probabilidades, reverse=True) and r["probabilidad"] == probabilidades[0]


@pytest.mark.parametrize("consulta,motivo", [
    ("SELECT usuario_id FROM usuarios WHERE acepta_marketing = 0 ORDER BY usuario_id LIMIT 1", "consentimiento"),
    ("SELECT usuario_id FROM usuarios WHERE acepta_marketing IS NULL ORDER BY usuario_id LIMIT 1", "consentimiento"),
    ("""SELECT u.usuario_id FROM usuarios u WHERE u.acepta_marketing = 1 AND NOT EXISTS
          (SELECT 1 FROM perfil_usuario_categoria p WHERE p.usuario_id = u.usuario_id) ORDER BY 1 LIMIT 1""",
     "arranque en frío"),
    (None, "sin registro"),
], ids=["consentimiento_0", "consentimiento_vacio", "arranque_en_frio", "visitante_sin_registro"])
def test_sin_consentimiento_sin_historial_o_desconocido_recibe_mas_vendidos_sin_modelo(sistema, monkeypatch,
                                                                                         consulta, motivo):
    from app import ia

    def no_llamar(*_a, **_k):
        raise AssertionError("RN2 y RF8: a estos usuarios no se les consulta el modelo")
    monkeypatch.setattr(ia, "predecir", no_llamar)
    usuario = _usuario(consulta) if consulta else "VISITANTE-1"
    r = _predecir(sistema, usuario_id=usuario, cantidad=4)
    assert (r["decision"], r["origen"], r["version_modelo"]) == ("mas_vendidos", "regla", "regla")
    assert motivo in r["mensaje"] and len(r["productos"]) == 4


def test_cantidad_fuera_de_4_a_8_responde_422(sistema):
    for cantidad in (3, 9):
        r = sistema["cliente"].post("/api/predict", json={"usuario_id": CON_HISTORIAL, "cantidad": cantidad},
                                    headers=CLAVE)
        assert r.status_code == 422


def test_categoria_vetada_no_aparece(sistema, monkeypatch):
    from app.casos import recomendacion
    primera = _predecir(sistema, usuario_id=CON_HISTORIAL)["categorias"][0]["categoria"]
    monkeypatch.setattr(recomendacion, "VETADAS", {recomendacion._clave(primera)})
    r = _predecir(sistema, usuario_id=CON_HISTORIAL)
    assert primera not in [p["categoria"] for p in r["productos"]] + [c["categoria"] for c in r["categorias"]]


def test_campana_no_manda_identidad_al_llm_y_exige_consentimiento(sistema):
    r = sistema["cliente"].post(f"/api/campanas/{CON_HISTORIAL}", headers=CLAVE)
    assert r.status_code == 200 and r.json()["decision"] == "campana" and r.json()["estado_llm"] == "pendiente"
    contenido = sistema["publicados"][-1]["contenido"]
    assert CON_HISTORIAL not in contenido and "productos" in contenido      # RNF7: categorías y productos
    sin_consentimiento = _usuario("SELECT usuario_id FROM usuarios WHERE acepta_marketing = 0 LIMIT 1")
    assert sistema["cliente"].post(f"/api/campanas/{sin_consentimiento}", headers=CLAVE).status_code == 409


def test_revocar_consentimiento_deja_de_personalizar_al_instante(sistema):
    usuario = _usuario("""SELECT u.usuario_id FROM usuarios u JOIN perfil_usuario_categoria p USING (usuario_id)
                          WHERE u.acepta_marketing = 1 AND u.usuario_id <> 'U100255' ORDER BY 1 DESC LIMIT 1""")
    assert _predecir(sistema, usuario_id=usuario)["decision"] == "personalizada"
    r = sistema["cliente"].post(f"/api/usuarios/{usuario}/revocar-consentimiento", headers=CLAVE)
    assert r.status_code == 200 and r.json()["filas_de_perfil_borradas"] == 10
    despues = _predecir(sistema, usuario_id=usuario)
    assert (despues["decision"], despues["origen"]) == ("mas_vendidos", "regla")     # RF11, RN2
