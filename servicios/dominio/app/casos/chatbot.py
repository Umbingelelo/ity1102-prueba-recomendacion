"""Caso 2 · Andesnet · reconocer la intención de un mensaje y responder con la base de conocimiento, o derivar.

Orden de la decisión (RF2, RF6, RF8, RNF11):
    1. El mensaje se anonimiza ANTES de todo lo demás: solo el texto anonimizado se guarda, va al modelo
       o va al LLM (RNF5).
    2. Reglas sin modelo: una conversación ya derivada sigue derivada; si el cliente pide una persona, se
       deriva de inmediato (RNF11); un saludo sin contenido pide más detalle y cuenta como intento fallido.
    3. El modelo reconoce la intención (RF2). Si no responde a tiempo: se deriva con aviso honesto (reserva).
    4. Reglas sobre lo que dijo el modelo (RF8): intención de anular -> derivar; molestia -> derivar;
       confianza baja -> intento fallido, y al tercero -> derivar.
    5. Si no se derivó: hasta 3 artículos vigentes de esa intención (RF6) y, en EP3, se encola para el LLM
       la redacción de la respuesta con esos artículos. El LLM nunca decide si se deriva.
"""
import os
import re
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import db, ia
from app.registro import log, registrar
from comun.caracteristicas import chatbot as variables

TITULO = "Andesnet · asistente de atención al cliente"
DESCRIPCION = ("Reconoce la intención de un mensaje, responde con la base de conocimiento o deriva a un "
               "ejecutivo. El texto se anonimiza antes de guardarlo o enviarlo a cualquier modelo.")

# DESAFÍO D1 · bajo esta confianza el mensaje cuenta como «no entendido». Con 0,45 un «hola» suelto pasaría
# (el modelo le da cerca de 0,6 a facturación): por eso existe la regla de mensaje sin contenido. Súbelo y mide
# cuántos mensajes buenos pasan a «aclarar»; bájalo y mide cuántos se responden con la intención equivocada.
UMBRAL_CONFIANZA = float(os.getenv("UMBRAL_CONFIANZA") or "0.45")
# DESAFÍO D2 · cuánto se espera al modelo. RNF1 da 3 s para TODA la respuesta (con el LLM incluido en EP3)
# y RNF8 da 30 s para derivar. Con SageMaker serverless el arranque en frío mide ~6 s (L10): ¿qué haces?
TIMEOUT_MODELO_MS = int(os.getenv("TIMEOUT_MODELO_MS") or "1500")
MAX_INTENTOS_FALLIDOS = int(os.getenv("MAX_INTENTOS_FALLIDOS") or "3")   # RF8
MAX_ARTICULOS = int(os.getenv("MAX_ARTICULOS") or "3")

AVISO = ("Estás conversando con el asistente automático de Andesnet. Escribe «ejecutivo» cuando quieras "
         "hablar con una persona.")   # RN3 y DA5: el cliente sabe que habla con un sistema
NOMBRES = {
    "facturacion": "tu boleta, pagos o cobros", "falla_tecnica": "una falla de tu servicio",
    "cobertura": "cobertura o señal", "cambio_plan": "un cambio de plan", "visita_tecnica": "una visita técnica",
    "anulacion": "anular tu servicio", "equipos": "tus equipos", "portabilidad": "portabilidad",
    "roaming": "roaming", "tv": "televisión",
}

INSTRUCCION_LLM = (
    "Eres el asistente automatico de Andesnet, una empresa de telecomunicaciones chilena. Redacta una "
    "respuesta cordial de maximo tres lineas para el cliente, en espanol de Chile, usando SOLO la "
    "informacion de los articulos entregados. Di que eres un asistente automatico. No inventes montos, "
    "fechas, planes ni plazos, no prometas descuentos y no pidas datos personales. Si los articulos no "
    "responden la consulta, ofrece derivar con un ejecutivo."
)

# DESAFÍO D3 · las tres listas de palabras de abajo son reglas, no modelo: se leen en voz alta y se
# auditan. ¿Qué frase de un cliente real se les escapa? ¿Cuál derivaría sin necesidad? Pruébalas con
# los textos de tickets y conversaciones (comando en casos/chatbot.md).
PIDE_PERSONA = re.compile(
    r"\b(ejecutiv[oa]s?|humano|persona real|una persona|alguien de verdad|que me atienda alguien"
    r"|hablar con alguien|operador(a)? por favor|con (un|una) operador(a)?"
    r"|no quiero (hablar con )?(un )?(bot|robot|maquina))\b")
MOLESTIA = re.compile(
    r"\b(mierda|weon\w*|hueon\w*|ctm|conchetumare|csm|chucha|culiao\w*|estafa\w*|ladron\w*|sinverguenza\w*"
    r"|verguenza|pesimo servicio|estoy (harto|harta|chato|chata)|sernac|subtel|demanda\w*|reclamo formal"
    r"|inutil(es)?|incompetentes?)\b|\U0001F621|\U0001F92C|!{3,}")
VACIAS = {"hola", "buenas", "buenos", "buen", "dia", "dias", "tardes", "noches", "alo", "hey", "gracias",
          "por", "favor", "porfa", "necesito", "quiero", "queria", "ayuda", "ayudar", "ayudarme", "consulta",
          "consultar", "pregunta", "preguntar", "preguntarle", "hacer", "una", "un", "algo", "con", "de",
          "sobre", "mi", "cuenta", "general", "pero", "no", "se", "a", "quien", "que", "la", "el", "y",
          "me", "puede", "puedes", "tengo", "es", "para", "o",
          # las frases con que el cliente deja su dato («mi rut es [RUT]», «escribanme a [CORREO]»)
          "rut", "numero", "correo", "escribanme", "pague", "tarjeta", "telefono", "fono"}


class Entrada(BaseModel):
    # extra="forbid": un campo que no está aquí (por ejemplo «rut») se rechaza con 422. RNF5.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "mensaje": "Hola, quiero saber cuanto debo y cuando vence mi cuenta.", "canal": "web"}})

    mensaje: str = Field(min_length=1, max_length=1000, description="Lo que escribió el cliente, tal cual")
    cliente_id: str | None = Field(None, max_length=20, description="Si el canal ya lo identificó (AN######)")
    conversacion_id: str | None = Field(None, max_length=64,
                                        description="Mismo id en cada mensaje de la conversación: así se cuentan "
                                                    "los intentos fallidos (RF8)")
    canal: Literal["web", "whatsapp", "app"] = "web"


# Para las pruebas: un cuerpo válido, y una petición que tiene que pasar por el LLM (con datos personales
# dentro del mensaje, para comprobar que a la cola llegan enmascarados)
EJEMPLOS = {
    "valido": Entrada.model_config["json_schema_extra"]["example"],
    "con_llm": {"metodo": "POST", "ruta": "/api/conversacion",
                "json": {"mensaje": "Hola, me llego la boleta con un cobro que no reconozco de $12.990. Mi rut es "
                                    "12.345.678-9, mi correo ana.perez@correo.cl y pague con la tarjeta "
                                    "4111 1111 1111 1111", "canal": "whatsapp"}},
}

FRONT = {
    "boton": "Enviar mensaje",
    "campos": [
        {"nombre": "mensaje", "etiqueta": "Mensaje del cliente", "tipo": "area",
         "valor": "Hola, me llego la boleta con un cobro que no reconozco. Mi rut es 12.345.678-9"},
        {"nombre": "conversacion_id", "etiqueta": "Conversación (opcional, para contar intentos)", "tipo": "texto",
         "valor": ""},
        {"nombre": "cliente_id", "etiqueta": "Cliente (opcional)", "tipo": "texto", "valor": ""},
        {"nombre": "canal", "etiqueta": "Canal", "tipo": "opciones", "opciones": ["web", "whatsapp", "app"],
         "valor": "web"},
    ],
    "listas": [{"ruta": "/api/derivaciones", "titulo": "Derivaciones a ejecutivo (RF7, RF8)"},
               {"ruta": "/api/faq", "titulo": "Artículos publicables de la base de conocimiento (RF6)"}],
}


def _pide_persona(normal: str) -> bool:
    return bool(PIDE_PERSONA.search(normal))


def _molestia(limpio: str, normal: str) -> bool:
    if MOLESTIA.search(normal):
        return True
    letras = [c for c in re.sub(r"\[[A-Z]+\]", "", limpio) if c.isalpha()]   # sin [RUT], [CORREO]...
    return len(letras) >= 12 and sum(c.isupper() for c in letras) / len(letras) >= 0.7   # GRITANDO


def _sin_contenido(normal: str) -> bool:
    sin_marcadores = re.sub(r"\[[a-z]+\]", " ", normal)
    return not [p for p in re.findall(r"[a-z0-9]+", sin_marcadores) if p not in VACIAS]


def _sesion(conversacion_id: str | None) -> dict | None:
    if not conversacion_id:
        return None
    return db.uno("SELECT * FROM sesiones_chat WHERE conversacion_id = %s", conversacion_id)


def _anotar(e: Entrada, fallido: bool = False, motivo: str | None = None) -> int:
    """Suma el mensaje a la sesión y devuelve los intentos fallidos acumulados. Sin conversacion_id no
    hay sesión: cada mensaje se evalúa solo (0 o 1 intento)."""
    if not e.conversacion_id:
        return int(fallido)
    fila = db.uno(
        """INSERT INTO sesiones_chat (conversacion_id, cliente_id, canal, mensajes, intentos_fallidos, derivada,
                                      motivo_derivacion)
           VALUES (%s, %s, %s, 1, %s, %s, %s)
           ON CONFLICT (conversacion_id) DO UPDATE SET
               mensajes = sesiones_chat.mensajes + 1,
               intentos_fallidos = sesiones_chat.intentos_fallidos + EXCLUDED.intentos_fallidos,
               derivada = sesiones_chat.derivada OR EXCLUDED.derivada,
               motivo_derivacion = coalesce(sesiones_chat.motivo_derivacion, EXCLUDED.motivo_derivacion),
               cliente_id = coalesce(EXCLUDED.cliente_id, sesiones_chat.cliente_id),
               canal = EXCLUDED.canal, actualizada = now()
           RETURNING intentos_fallidos""",
        e.conversacion_id, e.cliente_id, e.canal, int(fallido), motivo is not None, motivo)
    return fila["intentos_fallidos"]


def _articulos(intencion: str, mensaje: str) -> list[dict]:
    """Los publicables de la intención; primero los que comparten más palabras con el mensaje, después
    los más vistos. Así «cuándo vence mi cuenta» abre con «Cuando vence mi boleta» y no con «cómo pago»."""
    filas = db.todos(
        """SELECT articulo_id, pregunta, respuesta FROM faq
           WHERE intencion = %s AND vigente = 1 AND duplicado = 0 AND plan_descontinuado = 0
           ORDER BY vistas_12m DESC, articulo_id""", intencion)
    del_mensaje = set(variables.palabras(mensaje)) - VACIAS
    filas.sort(key=lambda a: -len(del_mensaje & set(variables.palabras(a["pregunta"]))))   # sort estable
    return filas[:MAX_ARTICULOS]


def _salida(decision, entrada, resultado, origen, version, probabilidad=None, llm=None) -> dict:
    return {"decision": decision, "probabilidad": probabilidad, "origen": origen, "version_modelo": version,
            "resultado": {"aviso": AVISO, "articulos": [], "alternativas": [], "derivar": False,
                          "motivo_derivacion": None, **resultado},
            "entrada_guardada": entrada, "llm": llm}


def _derivar(e, entrada, motivo, origen, version, intencion=None, probabilidad=None, alternativas=(),
             mensaje=None, intentos=None) -> dict:
    """RF7: el ejecutivo recibe la conversación con su intención y su motivo; el cliente no repite nada."""
    sesion = _sesion(e.conversacion_id)
    if e.conversacion_id and not (sesion and sesion["derivada"]):
        db.ejecutar("UPDATE sesiones_chat SET derivada = true, motivo_derivacion = %s, actualizada = now() "
                    "WHERE conversacion_id = %s", motivo, e.conversacion_id)
    texto = mensaje or ("Te estoy derivando con un ejecutivo. No necesitas repetir tu consulta: le llega todo "
                        "lo que conversamos.")
    return _salida("derivar", entrada, {"intencion": intencion, "mensaje": texto, "derivar": True,
                                        "motivo_derivacion": motivo, "alternativas": list(alternativas),
                                        "intentos_fallidos": intentos}, origen, version, probabilidad)


def _aclarar(entrada, origen, version, intentos, intencion=None, probabilidad=None, alternativas=()) -> dict:
    opciones = [NOMBRES[intencion]] if intencion else []
    opciones += [NOMBRES[a["clase"]] for a in alternativas if a["clase"] in NOMBRES][:1]
    pregunta = (f"¿Tu consulta es sobre {' o sobre '.join(opciones)}? " if opciones else
                "¿Me cuentas en una frase qué necesitas? Por ejemplo: «cuánto debo», «no tengo internet». ")
    return _salida("aclarar", entrada, {
        "intencion": intencion, "mensaje": "No estoy seguro de haber entendido. " + pregunta,
        "alternativas": list(alternativas), "intentos_fallidos": intentos}, origen, version, probabilidad)


def predecir(e: Entrada) -> dict:
    limpio = variables.limpiar(e.mensaje)          # 1. anonimizado: desde aquí, el original no se usa más
    normal = variables.normalizar(limpio)
    entrada = {"mensaje": limpio, "cliente_id": e.cliente_id, "conversacion_id": e.conversacion_id, "canal": e.canal}

    sesion = _sesion(e.conversacion_id)            # 2. reglas que no necesitan modelo (RNF8: inmediatas)
    if sesion and sesion["derivada"]:
        _anotar(e)
        return _derivar(e, entrada, "la conversación ya estaba derivada", "regla", "regla",
                        mensaje="Tu conversación ya está con un ejecutivo, que verá también este mensaje.")
    if _pide_persona(normal):
        _anotar(e, motivo="el cliente pidió una persona (RNF11)")
        return _derivar(e, entrada, "el cliente pidió una persona (RNF11)", "regla", "regla")
    if _sin_contenido(normal):
        intentos = _anotar(e, fallido=True)
        if intentos >= MAX_INTENTOS_FALLIDOS:
            return _derivar(e, entrada, f"{intentos} intentos fallidos (RF8)", "regla", "regla", intentos=intentos)
        return _aclarar(entrada, "regla", "regla", intentos)

    try:                                           # 3. el modelo
        r = ia.predecir([{"texto": limpio}], TIMEOUT_MODELO_MS)
    except ia.ModeloNoDisponible as error:
        # El motivo es fijo para poder contarlo en el dashboard; el detalle técnico va al log
        log(evento="modelo_no_disponible", detalle=str(error)[:200])
        motivo = "modelo no disponible: plan de reserva"
        _anotar(e, motivo=motivo)
        return _derivar(e, entrada, motivo, "reserva", "reserva", mensaje=(
            "En este momento no puedo procesar tu mensaje automáticamente. Te derivo con un ejecutivo para "
            "que no tengas que esperar; no necesitas repetir tu consulta."))
    pred, version = r["resultados"][0], r["version_modelo"]
    intencion, p, alternativas = pred["clase"], pred["probabilidad"], pred.get("alternativas", [])

    motivo = ("intención de anular: el asistente no cancela servicios (RF8, DA3)" if intencion == "anulacion" else
              "molestia detectada (RF8)" if _molestia(limpio, normal) else None)   # 4. reglas de RF8
    if motivo:
        _anotar(e, motivo=motivo)
        return _derivar(e, entrada, motivo, "modelo", version, intencion, p, alternativas)
    if p < UMBRAL_CONFIANZA:
        intentos = _anotar(e, fallido=True)
        if intentos >= MAX_INTENTOS_FALLIDOS:
            return _derivar(e, entrada, f"{intentos} intentos fallidos (RF8)", "modelo", version, intencion, p,
                            alternativas, intentos=intentos)
        return _aclarar(entrada, "modelo", version, intentos, intencion, p, alternativas)

    intentos = _anotar(e)                          # 5. respuesta con la base de conocimiento (RF6)
    articulos = _articulos(intencion, limpio)
    if not articulos:
        return _salida(intencion, entrada, {
            "intencion": intencion, "intentos_fallidos": intentos, "alternativas": alternativas,
            "mensaje": f"Entiendo que tu consulta es sobre {NOMBRES.get(intencion, intencion)}, pero no tengo un "
                       "artículo publicado para eso. Escribe «ejecutivo» y te derivo con una persona."},
            "modelo", version, p)
    llm = {"instruccion": INSTRUCCION_LLM,   # solo el mensaje ya anonimizado y artículos públicos (RNF5)
           "contenido": {"mensaje": limpio, "intencion": intencion,
                         "articulos": [{"pregunta": a["pregunta"], "respuesta": a["respuesta"]} for a in articulos]}}
    return _salida(intencion, entrada, {
        "intencion": intencion, "mensaje": articulos[0]["respuesta"], "articulos": articulos,
        "alternativas": alternativas, "intentos_fallidos": intentos}, "modelo", version, p, llm)


# Las tres tasas de RNF9, en porcentaje. «aclarar» no cuenta como resuelta: el cliente sigue esperando.
TASAS = """
    round(100.0 * count(*) FILTER (WHERE decision = 'derivar') / nullif(count(*), 0), 2)::float AS tasa_derivacion_pct,
    round(100.0 * count(*) FILTER (WHERE decision NOT IN ('derivar', 'aclarar')) / nullif(count(*), 0), 2)::float
        AS tasa_resuelta_sin_humano_pct,
    round(100.0 * count(*) FILTER (WHERE origen = 'reserva' OR estado_llm = 'degradado') / nullif(count(*), 0),
          2)::float
        AS tasa_modo_degradado_pct"""


def dashboard() -> dict:
    """RNF9: conversaciones, intenciones, tasa de derivación y tasa de respuestas en modo degradado."""
    g = db.uno(f"""SELECT count(DISTINCT coalesce(entrada->>'conversacion_id', id)) AS conversaciones_atendidas,
                          count(*) AS mensajes, {TASAS} FROM predicciones""")
    intenciones = db.todos(
        """SELECT coalesce(resultado->>'intencion', 'sin intención') AS intencion, count(*) AS mensajes,
                  count(*) FILTER (WHERE decision = 'derivar') AS derivados
           FROM predicciones GROUP BY 1 ORDER BY 2 DESC""")
    motivos = db.todos(
        """SELECT resultado->>'motivo_derivacion' AS motivo, count(*) AS n FROM predicciones
           WHERE decision = 'derivar' GROUP BY 1 ORDER BY 2 DESC""")
    semanas = db.todos(
        f"""SELECT date_trunc('week', creada AT TIME ZONE 'America/Santiago')::date AS semana, count(*) AS mensajes,
                   {TASAS} FROM predicciones GROUP BY 1 ORDER BY 1 DESC LIMIT 8""")
    return {**db.jsonable(g), "intenciones": [db.jsonable(f) for f in intenciones],
            "motivos_de_derivacion": [db.jsonable(f) for f in motivos],
            "por_semana": [db.jsonable(f) for f in semanas]}


router = APIRouter()


@router.post("/conversacion")
def conversacion(entrada: Entrada):
    """Un mensaje de la conversación (EP3 §3.2). Devuelve de inmediato la intención y la decisión; la
    respuesta redactada por el LLM se consulta después en GET /api/predicciones/{id} (campo texto_llm)."""
    inicio = time.perf_counter()
    r = registrar(predecir(entrada), inicio)
    return {**r, "respuesta_llm_en": f"/api/predicciones/{r['id']}"}


@router.get("/derivaciones")
def derivaciones(limite: int = 50):
    """La cola del ejecutivo (RF7): qué pidió el cliente, por qué se derivó y el mensaje ya anonimizado."""
    filas = db.todos(
        """SELECT id, creada, entrada->>'conversacion_id' AS conversacion_id, entrada->>'canal' AS canal,
                  resultado->>'intencion' AS intencion, resultado->>'motivo_derivacion' AS motivo, origen,
                  entrada->>'mensaje' AS mensaje
           FROM predicciones WHERE decision = 'derivar' ORDER BY creada DESC LIMIT %s""", min(max(limite, 1), 200))
    return [db.jsonable(f) for f in filas]


@router.get("/faq")
def faq(intencion: str | None = None, limite: int = 20):
    """Artículos que el asistente puede usar (vigentes, sin duplicar, sin planes descontinuados)."""
    filas = db.todos(
        """SELECT articulo_id, intencion, pregunta, respuesta, vistas_12m FROM faq
           WHERE vigente = 1 AND duplicado = 0 AND plan_descontinuado = 0
             AND (%s::text IS NULL OR intencion = %s)
           ORDER BY intencion, vistas_12m DESC LIMIT %s""", intencion, intencion, min(max(limite, 1), 200))
    return [db.jsonable(f) for f in filas]


@router.get("/tickets")
def tickets(cliente_id: str | None = None, intencion: str | None = None, limite: int = 20):
    """Historia de tickets tratada, con el texto ya anonimizado."""
    filas = db.todos(
        """SELECT ticket_id, cliente_id, canal, fecha_apertura, intencion, texto, resuelto, csat FROM tickets
           WHERE (%s::text IS NULL OR cliente_id = %s) AND (%s::text IS NULL OR intencion = %s)
           ORDER BY fecha_apertura DESC LIMIT %s""",
        cliente_id, cliente_id, intencion, intencion, min(max(limite, 1), 200))
    return [db.jsonable(f) for f in filas]


@router.get("/clientes/{cliente_id}")
def cliente(cliente_id: str):
    fila = db.uno("SELECT * FROM clientes WHERE cliente_id = %s", cliente_id)
    if not fila:
        raise HTTPException(status_code=404, detail="No existe ese cliente")
    return db.jsonable(fila)


@router.get("/sesiones/{conversacion_id}")
def sesion(conversacion_id: str):
    """Estado de una conversación: mensajes, intentos fallidos y si ya se derivó (RF8)."""
    fila = _sesion(conversacion_id)
    if not fila:
        raise HTTPException(status_code=404, detail="No existe esa conversación")
    return db.jsonable(fila)
