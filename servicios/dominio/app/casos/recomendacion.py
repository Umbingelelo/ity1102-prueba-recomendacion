"""Caso 1 · Nexus Retail · recomendar entre 4 y 8 productos a un cliente identificado.

Orden de la decisión:
    1. Interruptor: con RECOMENDADOR_ACTIVO=0 se responde la lista de más vendidos (RNF9).
    2. Consentimiento: sin acepta_marketing = 1 no se personaliza; más vendidos (RN2).
    3. Sin historial (no hay filas en perfil_usuario_categoria): más vendidos (RF8, arranque en frío).
    4. El modelo da la probabilidad de compra en cada categoría (una fila por categoría, en UNA llamada).
       Si no responde en TIMEOUT_MODELO_MS: más vendidos (RNF3).
    5. Los productos salen de las categorías más probables: activos, con precio y con stock (RF5), sin la
       ficha que el cliente está mirando ni lo que ya compró, y sin las categorías vetadas (RF6).
    6. Cada producto lleva su motivo en lenguaje común (RN3: el cliente puede preguntar por qué).
El LLM no participa de la recomendación: solo redacta el texto de campaña (POST /api/campanas/{usuario}).
"""
import os
import time
import unicodedata

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from app import db, ia

TITULO = "Nexus Retail · recomendación de productos"
DESCRIPCION = ("Entre 4 y 8 productos para un cliente, según su probabilidad de compra en cada categoría. "
               "Sin consentimiento, sin historial o sin modelo: los más vendidos con stock.")

# RNF3 · si el modelo no responde en 200 ms, la ficha se muestra igual con los más vendidos.
# DESAFÍO D1: 200 ms sale del caso. Con SageMaker serverless el arranque en frío tarda segundos: mide
# cuántas respuestas caen en reserva con este valor y decide si lo mantienes o cambias el despliegue.
# (Una variable vacía vale lo mismo que no definirla: así compose puede declararlas todas con «${X:-}»)
TIMEOUT_MODELO_MS = int(os.getenv("TIMEOUT_MODELO_MS") or "200")
# RNF9 · apagar el recomendador sin desplegar nada: RECOMENDADOR_ACTIVO=0 en el .env y reiniciar el dominio
RECOMENDADOR_ACTIVO = (os.getenv("RECOMENDADOR_ACTIVO") or "1").strip() == "1"
# RF6 · categorías que marketing veta, separadas por coma («Smartphones,Gaming»). No se recomiendan nunca.
# DESAFÍO D3: RNF10 pide que marketing lo cambie sin pedirle nada a tecnología. Con una variable de
# entorno no se cumple del todo: ¿qué propones y qué cuesta?
CATEGORIAS_VETADAS = os.getenv("CATEGORIAS_VETADAS") or ""
# DESAFÍO D4 · cuántas categorías se mezclan en la lista. Con 1 se apuesta todo a una categoría; con 3 se
# diversifica. Mídelo con n_categorias de lista_por_categorias (datos/casos/recomendacion.py) y elige.
CATEGORIAS_EN_LISTA = int(os.getenv("CATEGORIAS_EN_LISTA") or "3")

INSTRUCCION_LLM = (
    "Eres redactor de campañas de correo de una tienda de tecnología. Con la lista de productos y el motivo "
    "de cada uno, escribe dos o tres líneas para un correo de Mailchimp que expliquen por qué se le "
    "recomiendan. No inventes productos, precios ni descuentos, no cambies la lista y no incluyas saludos "
    "con nombre ni datos personales."
)


def _clave(texto: str) -> str:
    """'Periféricos ' -> 'perifericos': para comparar categorías escritas por personas."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return sin_tildes.strip().lower()


VETADAS = {_clave(c) for c in CATEGORIAS_VETADAS.split(",") if c.strip()}


class Entrada(BaseModel):
    # extra="forbid": un campo que no está aquí (por ejemplo «email») se rechaza con 422. RNF7.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "usuario_id": "U100255", "cantidad": 6, "sku_actual": "NX-11040"}})

    usuario_id: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$",
                            description="Cliente identificado. Un visitante anónimo recibe los más vendidos")
    cantidad: int = Field(6, ge=4, le=8, description="Cuántos productos mostrar (RF1: entre 4 y 8)")
    sku_actual: str | None = Field(None, max_length=20, description="Ficha de producto que está mirando: "
                                                                     "no se recomienda a sí misma")


# Para las pruebas: un cuerpo válido (usuario con consentimiento e historial) y una petición que encola
# texto para el LLM (la campaña del mismo usuario)
EJEMPLOS = {
    "valido": Entrada.model_config["json_schema_extra"]["example"],
    "con_llm": {"metodo": "POST", "ruta": "/api/campanas/U100255", "json": None},
}

FRONT = {
    "boton": "Recomendar",
    "campos": [
        {"nombre": "usuario_id", "etiqueta": "Usuario", "tipo": "texto", "valor": "U100255"},
        {"nombre": "cantidad", "etiqueta": "Productos (4 a 8)", "tipo": "numero", "valor": 6},
        {"nombre": "sku_actual", "etiqueta": "Ficha que está mirando (SKU, opcional)", "tipo": "texto",
         "valor": "NX-11040"},
    ],
    "listas": [{"ruta": "/api/mas-vendidos", "titulo": "Más vendidos con stock: la lista de reserva (RF8, RNF3)"},
               {"ruta": "/api/campanas", "titulo": "Campañas para Mailchimp (RF4)"}],
}

# RF5: solo productos que se pueden vender ahora. El stock llega del ERP cada 30 min (RT6): DESAFÍO D2,
# ¿exigirías un margen (stock > 2) para no recomendar el último que ya se vendió?
DISPONIBLE = "activo = 1 AND stock > 0 AND precio IS NOT NULL"
COLUMNAS_PRODUCTO = "sku, coalesce(nombre, sku) AS nombre, categoria, marca, precio, stock"


def _mas_vendidos(cantidad: int, excluir: set[str]) -> list[dict]:
    filas = db.todos(f"SELECT {COLUMNAS_PRODUCTO} FROM productos WHERE {DISPONIBLE} "
                     "ORDER BY ventas_90d DESC, sku LIMIT %s", cantidad + len(excluir) + 40)
    elegidos = [f for f in filas if f["sku"] not in excluir and _clave(f["categoria"] or "") not in VETADAS]
    return [{**f, "motivo": "de los más vendidos de la tienda en los últimos 90 días"} for f in elegidos[:cantidad]]


def _reserva(cantidad: int, excluir: set[str], origen: str, motivo: str) -> dict:
    """La lista que no depende del modelo ni del usuario: los más vendidos con stock."""
    return {"decision": "mas_vendidos", "probabilidad": None, "origen": origen, "version_modelo": origen,
            "resultado": {"mensaje": f"Lista de más vendidos: {motivo}.", "productos": _mas_vendidos(cantidad, excluir)}}


def _motivo(p: dict) -> str:
    """Por qué se recomienda esta categoría, con el dato del perfil que más la explica (RN3)."""
    categoria = p["categoria"]
    if p["compras_cat"]:
        veces = "vez" if p["compras_cat"] == 1 else "veces"
        return f"compraste {p['compras_cat']} {veces} en {categoria}"
    if p["carrito_cat"]:
        return f"agregaste productos de {categoria} al carrito"
    if p["vistas_cat"]:
        return f"miraste {p['vistas_cat']} productos de {categoria}"
    return f"según el modelo, {categoria} es de lo que más probablemente compres ahora"


def _por_categorias(ranking: list[str], perfil: dict, cantidad: int, excluir: set[str]) -> list[dict]:
    """Reparte los cupos por turnos entre las categorías más probables y completa con las siguientes."""
    filas = db.todos(
        f"""SELECT * FROM (
               SELECT {COLUMNAS_PRODUCTO}, row_number() OVER (PARTITION BY categoria ORDER BY ventas_90d DESC, sku) AS n
               FROM productos WHERE {DISPONIBLE} AND categoria = ANY(%s) AND NOT (sku = ANY(%s))) x
           WHERE n <= %s""", ranking, sorted(excluir), cantidad)
    colas = {c: [] for c in ranking}
    for f in sorted(filas, key=lambda f: f["n"]):
        f.pop("n")
        colas[f["categoria"]].append({**f, "motivo": _motivo(perfil[f["categoria"]])})
    elegidos = []
    primeras = [colas[c] for c in ranking[:CATEGORIAS_EN_LISTA]]
    while len(elegidos) < cantidad and any(primeras):
        for cola in primeras:
            if cola and len(elegidos) < cantidad:
                elegidos.append(cola.pop(0))
    for c in ranking[CATEGORIAS_EN_LISTA:]:
        elegidos += colas[c][: cantidad - len(elegidos)]
    return elegidos


def recomendar(usuario_id: str, cantidad: int, sku_actual: str | None = None) -> dict:
    """La recomendación sin guardar nada. La usan POST /api/predict y POST /api/campanas/{usuario}."""
    excluir = {sku_actual} if sku_actual else set()
    if not RECOMENDADOR_ACTIVO:
        return _reserva(cantidad, excluir, "regla", "el recomendador está apagado por configuración (RNF9)")
    usuario = db.uno("SELECT acepta_marketing FROM usuarios WHERE usuario_id = %s", usuario_id)
    if not usuario:
        return _reserva(cantidad, excluir, "regla", "visitante sin registro, no hay historial (RF8)")
    if usuario["acepta_marketing"] != 1:
        # Vacío no es consentimiento: RN2 lo exige explícito (DESAFÍO R3 en datos/casos/recomendacion.py)
        return _reserva(cantidad, excluir, "regla", "sin consentimiento explícito para personalizar (RN2)")
    perfil = db.todos("SELECT * FROM perfil_usuario_categoria WHERE usuario_id = %s ORDER BY categoria", usuario_id)
    if not perfil:
        return _reserva(cantidad, excluir, "regla", "cliente sin historial de compras, arranque en frío (RF8)")

    try:
        r = ia.predecir(perfil, TIMEOUT_MODELO_MS)
    except ia.ModeloNoDisponible as error:
        return _reserva(cantidad, excluir, "reserva", f"el modelo no respondió a tiempo ({error}) (RNF3)")
    probabilidad = {f["categoria"]: x["probabilidad"] for f, x in zip(perfil, r["resultados"])}
    ranking = sorted((c for c in probabilidad if _clave(c) not in VETADAS), key=lambda c: (-probabilidad[c], c))
    if not ranking:
        return _reserva(cantidad, excluir, "regla", "todas las categorías están vetadas (RF6)")

    compradas = {f["sku"] for f in db.todos(
        "SELECT DISTINCT sku FROM transacciones WHERE usuario_id = %s AND es_venta = 1 AND sku IS NOT NULL", usuario_id)}
    por_categoria = {f["categoria"]: f for f in perfil}
    productos = _por_categorias(ranking, por_categoria, cantidad, excluir | compradas)
    if len(productos) < cantidad:   # categorías sin stock suficiente: se completa con los más vendidos
        productos += _mas_vendidos(cantidad - len(productos), excluir | compradas | {p["sku"] for p in productos})
    return {
        "decision": "personalizada", "probabilidad": probabilidad[ranking[0]], "origen": "modelo",
        "version_modelo": r["version_modelo"],
        "resultado": {
            "mensaje": f"Productos de las categorías donde es más probable que compre: {', '.join(ranking[:3])}.",
            "productos": productos,
            "categorias": [{"categoria": c, "probabilidad": probabilidad[c]} for c in ranking[:5]],
        },
    }


def predecir(e: Entrada) -> dict:
    salida = recomendar(e.usuario_id, e.cantidad, e.sku_actual)
    return {**salida, "entrada_guardada": e.model_dump(), "llm": None}   # la respuesta de 200 ms no espera al LLM


def dashboard() -> dict:
    g = db.uno(
        """SELECT count(*) FILTER (WHERE decision IN ('personalizada', 'mas_vendidos')) AS entregadas,
                  count(*) FILTER (WHERE decision = 'personalizada') AS personalizadas,
                  count(*) FILTER (WHERE decision IN ('personalizada', 'mas_vendidos') AND origen = 'reserva') AS reserva,
                  count(*) FILTER (WHERE decision IN ('personalizada', 'mas_vendidos') AND origen = 'regla') AS regla,
                  count(*) FILTER (WHERE decision = 'campana') AS campanas
           FROM predicciones""")
    pct = (lambda n: round(100 * n / g["entregadas"], 1)) if g["entregadas"] else (lambda n: None)
    categorias = db.todos(
        """SELECT p->>'categoria' AS categoria, count(*) AS productos_recomendados
           FROM predicciones, jsonb_array_elements(resultado->'productos') AS p
           GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
    por_dia = db.todos(
        """SELECT date(creada AT TIME ZONE 'America/Santiago') AS dia, count(*) AS entregadas,
                  round(100.0 * count(*) FILTER (WHERE origen = 'reserva') / count(*), 1) AS reserva_pct
           FROM predicciones WHERE decision IN ('personalizada', 'mas_vendidos') GROUP BY 1 ORDER BY 1 DESC LIMIT 14""")
    return {"recomendaciones_entregadas": g["entregadas"], "personalizadas": g["personalizadas"],
            "proporcion_reserva_pct": pct(g["reserva"]), "proporcion_regla_pct": pct(g["regla"]),
            "campanas": g["campanas"],
            "top_categorias_recomendadas": [db.jsonable(f) for f in categorias],
            "por_dia": [db.jsonable(f) for f in por_dia]}


router = APIRouter()


@router.post("/campanas/{usuario_id}")
def campana(usuario_id: str = Path(max_length=20), cantidad: int = Query(5, ge=4, le=8)):
    """Recomienda y encola el texto de campaña para Mailchimp (RF4). El LLM recibe categorías y productos,
    nunca la identidad del cliente (RNF7). Sin consentimiento no hay campaña (RN2)."""
    from app.registro import registrar
    inicio = time.perf_counter()
    usuario = db.uno("SELECT acepta_marketing FROM usuarios WHERE usuario_id = %s", usuario_id)
    if not usuario or usuario["acepta_marketing"] != 1:
        raise HTTPException(status_code=409, detail="El cliente no tiene consentimiento explícito de marketing (RN2)")
    salida = recomendar(usuario_id, cantidad)
    resultado = salida["resultado"]
    contenido = {
        "categorias": [c["categoria"] for c in resultado.get("categorias", [])[:3]],
        "productos": [{"nombre": p["nombre"], "categoria": p["categoria"], "marca": p["marca"],
                       "precio_clp": p["precio"], "motivo": p["motivo"]} for p in resultado["productos"]],
    }
    return registrar({**salida, "decision": "campana",
                      "entrada_guardada": {"usuario_id": usuario_id, "cantidad": cantidad, "ruta": "campanas"},
                      "llm": {"instruccion": INSTRUCCION_LLM, "contenido": contenido}}, inicio)


@router.get("/campanas")
def campanas(limite: int = 20):
    """Las campañas generadas, con el texto del LLM cuando ya llegó: lo que marketing copia a Mailchimp."""
    filas = db.todos(
        """SELECT id, creada, entrada->>'usuario_id' AS usuario_id, origen, estado_llm, texto_llm
           FROM predicciones WHERE decision = 'campana' ORDER BY creada DESC LIMIT %s""", min(max(limite, 1), 200))
    return [db.jsonable(f) for f in filas]


@router.get("/mas-vendidos")
def mas_vendidos(limite: int = Query(10, ge=1, le=50)):
    """La lista de reserva tal como se entregaría ahora (RF8, RNF3)."""
    return [db.jsonable(f) for f in _mas_vendidos(limite, set())]


@router.get("/usuarios/{usuario_id}")
def usuario(usuario_id: str = Path(max_length=20)):
    """El cliente y sus últimas 10 compras: el historial que muestra el front."""
    datos = db.uno("SELECT * FROM usuarios WHERE usuario_id = %s", usuario_id)
    compras = db.todos(
        """SELECT t.fecha, t.pedido_id, t.sku, coalesce(p.nombre, t.sku) AS nombre, t.categoria, t.cantidad, t.total
           FROM transacciones t LEFT JOIN productos p USING (sku)
           WHERE t.usuario_id = %s AND t.es_venta = 1 ORDER BY t.fecha DESC LIMIT 10""", usuario_id)
    if not datos and not compras:
        raise HTTPException(status_code=404, detail="No existe ese usuario")
    return {"usuario": db.jsonable(datos) if datos else None, "ultimas_compras": [db.jsonable(f) for f in compras]}


@router.post("/usuarios/{usuario_id}/revocar-consentimiento")
def revocar(usuario_id: str = Path(max_length=20)):
    """RF11 y RN2: el cliente pide que no se use su historial. Desde esta respuesta recibe más vendidos y su
    perfil se borra. El próximo reentrenamiento ya no lo incluye (preparar.py solo usa acepta_marketing = 1)."""
    if not db.ejecutar("UPDATE usuarios SET acepta_marketing = 0 WHERE usuario_id = %s", usuario_id):
        raise HTTPException(status_code=404, detail="No existe ese usuario")
    borradas = db.ejecutar("DELETE FROM perfil_usuario_categoria WHERE usuario_id = %s", usuario_id)
    return {"usuario_id": usuario_id, "acepta_marketing": 0, "filas_de_perfil_borradas": borradas}
