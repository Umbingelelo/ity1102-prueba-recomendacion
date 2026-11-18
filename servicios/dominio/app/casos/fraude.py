"""Caso 3 · Kipu Pagos · decidir si una transacción se aprueba, se revisa o se bloquea.

Orden de la decisión (RF1, RF4, RF8):
    1. Reglas duras: lista negra vigente. Si aplica, se bloquea SIN preguntar al modelo.
    2. Se enriquece la transacción con su usuario y su dispositivo (desde la base).
    3. El modelo da la probabilidad y las razones (RF2). Los umbrales vienen de configuración (RF3).
    4. Si el modelo no responde a tiempo: política de reserva (RNF3).
    5. Si la decisión es revisar o bloquear, se encola un resumen para el analista (LLM, solo EP3).
"""
import os
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app import db, ia

TITULO = "Kipu Pagos · detección de fraude"
DESCRIPCION = "Evalúa una transacción antes de autorizarla: aprobar, revisar o bloquear, con sus razones."

# RF3 · los umbrales los fija riesgo, no ingeniería: se cambian en el .env y se reinicia, sin desplegar
# código. DESAFÍO D1: calcula tus umbrales sabiendo que en producción el fraude es 0,012% (no 11%).
UMBRAL_REVISAR = float(os.getenv("UMBRAL_REVISAR") or "0.5")
UMBRAL_BLOQUEAR = float(os.getenv("UMBRAL_BLOQUEAR") or "0.9")
# RNF3 · cuánto se espera al modelo y qué se hace si no responde. DESAFÍO D2: elige y defiende.
TIMEOUT_MODELO_MS = int(os.getenv("TIMEOUT_MODELO_MS") or "300")
POLITICA_RESERVA = os.getenv("POLITICA_RESERVA") or "reglas"   # reglas | aprobar | revisar | bloquear
TASA_USD_CLP = 950   # la misma de datos/casos/fraude.py

INSTRUCCION_LLM = (
    "Eres asistente de un analista de fraude. Con la decision ya tomada por el modelo y sus razones, "
    "escribe un resumen de tres lineas en lenguaje comun para la cola de revision. No inventes datos, "
    "no cambies la decision y no menciones datos personales."
)


class Entrada(BaseModel):
    # extra="forbid": un campo que no está aquí (por ejemplo «tarjeta») se rechaza con 422. RNF5.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "usuario_id": "KP300267", "comercio_id": "CM40847", "dispositivo_id": "D-1358e431cbe4",
        "monto": 250000, "moneda": "CLP", "canal": "app", "hora_local": 3, "intentos_previos_1h": 4,
        "pais_transaccion": "CL", "ip": "72.152.180.159"}})

    usuario_id: str = Field(min_length=3, max_length=20)
    comercio_id: str | None = Field(None, max_length=20)
    dispositivo_id: str | None = Field(None, max_length=40)
    monto: float = Field(gt=0, description="Monto en la moneda indicada")
    moneda: Literal["CLP", "USD"] = "CLP"
    canal: Literal["app", "web", "pos", "api"]
    hora_local: int | None = Field(None, ge=0, le=23, description="Si no viene, la hora actual de Chile")
    intentos_previos_1h: int = Field(0, ge=0, le=1000)
    pais_transaccion: str = Field("CL", min_length=2, max_length=2)
    ip: str | None = Field(None, max_length=45)


# Para las pruebas: un cuerpo válido, y una petición que tiene que pasar por el LLM (dispositivo listado)
EJEMPLOS = {
    "valido": Entrada.model_config["json_schema_extra"]["example"],
    "con_llm": {"metodo": "POST", "ruta": "/api/predict",
                "json": {"usuario_id": "KP300267", "dispositivo_id": "D-1da29c52b0ed", "monto": 9000, "canal": "web"}},
}

FRONT = {
    "boton": "Evaluar transacción",
    "campos": [
        {"nombre": "usuario_id", "etiqueta": "Usuario", "tipo": "texto", "valor": "KP300267"},
        {"nombre": "comercio_id", "etiqueta": "Comercio", "tipo": "texto", "valor": "CM40847"},
        {"nombre": "dispositivo_id", "etiqueta": "Dispositivo", "tipo": "texto", "valor": "D-1358e431cbe4"},
        {"nombre": "monto", "etiqueta": "Monto", "tipo": "numero", "valor": 250000},
        {"nombre": "moneda", "etiqueta": "Moneda", "tipo": "opciones", "opciones": ["CLP", "USD"]},
        {"nombre": "canal", "etiqueta": "Canal", "tipo": "opciones", "opciones": ["app", "web", "pos", "api"]},
        {"nombre": "hora_local", "etiqueta": "Hora (0-23)", "tipo": "numero", "valor": 3},
        {"nombre": "intentos_previos_1h", "etiqueta": "Transacciones en la hora previa", "tipo": "numero", "valor": 4},
        {"nombre": "pais_transaccion", "etiqueta": "País (ISO2)", "tipo": "texto", "valor": "CL"},
    ],
    "listas": [{"ruta": "/api/revision", "titulo": "Cola de revisión (RF5)"}],
}


def _lista_negra(e: Entrada) -> list[dict]:
    return db.todos(
        """SELECT tipo, valor, motivo FROM lista_negra
           WHERE vigente = 1 AND ((tipo = 'dispositivo' AND valor = %s) OR (tipo = 'comercio' AND valor = %s)
                                  OR (tipo = 'ip' AND valor = %s))""",
        e.dispositivo_id, e.comercio_id, e.ip)


def _enriquecer(e: Entrada) -> dict:
    usuario = db.uno("SELECT * FROM usuarios WHERE usuario_id = %s", e.usuario_id) or {}
    dispositivo = (db.uno("SELECT * FROM dispositivos WHERE dispositivo_id = %s", e.dispositivo_id)
                   if e.dispositivo_id else None) or {}
    hora = e.hora_local if e.hora_local is not None else datetime.now(ZoneInfo("America/Santiago")).hour
    pais_usuario = usuario.get("pais")
    return {
        "monto_clp": round(e.monto * (TASA_USD_CLP if e.moneda == "USD" else 1)),
        "hora_local": hora, "canal": e.canal, "intentos_previos_1h": e.intentos_previos_1h,
        "edad_cuenta_dias": usuario.get("edad_cuenta_dias"), "nivel_kyc": usuario.get("nivel_kyc"),
        "verificado": usuario.get("verificado"), "telefono_verificado": usuario.get("telefono_verificado"),
        "email_desechable": usuario.get("email_desechable"),
        "usuarios_distintos": dispositivo.get("usuarios_distintos"), "emulador": dispositivo.get("emulador"),
        "pais_distinto": None if not pais_usuario else int(e.pais_transaccion.upper() != pais_usuario),
        "dispositivo_id": e.dispositivo_id,
        "usuario_conocido": bool(usuario),
    }


def _decidir(p: float) -> str:
    return "bloquear" if p >= UMBRAL_BLOQUEAR else "revisar" if p >= UMBRAL_REVISAR else "aprobar"


def _reserva(fila: dict) -> tuple[str, list[dict]]:
    """Política de reserva cuando el modelo no responde a tiempo (RNF3)."""
    if POLITICA_RESERVA != "reglas":
        return POLITICA_RESERVA, [{"descripcion": f"modelo no disponible: política «{POLITICA_RESERVA}»"}]
    # Motor de reglas mínimo: las mismas señales que más pesan en el modelo, contadas a mano
    senales = [
        ("ocurrió de madrugada", (fila["hora_local"] or 12) < 6),
        ("3 o más transacciones en la hora previa", (fila["intentos_previos_1h"] or 0) >= 3),
        ("dispositivo emulado", fila["emulador"] == 1),
        ("3 o más usuarios en el mismo dispositivo", (fila["usuarios_distintos"] or 0) >= 3),
        ("país distinto al del usuario", fila["pais_distinto"] == 1),
        ("cuenta de menos de 30 días", fila["edad_cuenta_dias"] is not None and fila["edad_cuenta_dias"] < 30),
    ]
    activas = [{"descripcion": s} for s, activa in senales if activa]
    decision = "bloquear" if len(activas) >= 4 else "revisar" if len(activas) >= 2 else "aprobar"
    return decision, activas


def predecir(e: Entrada) -> dict:
    entrada = e.model_dump()
    listada = _lista_negra(e)
    if listada:   # Regla dura: va antes de cualquier modelo (RF4, RF8)
        razones = [{"descripcion": f"{x['tipo']} en lista negra", "valor": x["valor"], "motivo": x["motivo"]}
                   for x in listada]
        return {"decision": "bloquear", "probabilidad": None, "origen": "regla", "version_modelo": "regla",
                "resultado": {"razones": razones}, "entrada_guardada": entrada,
                "llm": {"instruccion": INSTRUCCION_LLM,
                        "contenido": {"decision": "bloquear", "razones": razones, "canal": e.canal}}}

    fila = _enriquecer(e)
    try:
        r = ia.predecir([fila], TIMEOUT_MODELO_MS, explicar=True)
        p = r["resultados"][0]["probabilidad"]
        decision, razones, origen, version = _decidir(p), r["resultados"][0]["razones"], "modelo", r["version_modelo"]
    except ia.ModeloNoDisponible as error:
        p, origen, version = None, "reserva", "reserva"
        decision, razones = _reserva(fila)
        razones = [{"descripcion": f"modelo no disponible ({error})"}] + razones

    resultado = {"razones": razones, "umbrales": {"revisar": UMBRAL_REVISAR, "bloquear": UMBRAL_BLOQUEAR},
                 "usuario_conocido": fila["usuario_conocido"], "monto_clp": fila["monto_clp"]}
    llm = None
    if decision in ("revisar", "bloquear"):   # El LLM solo redacta para el analista; nunca decide
        llm = {"instruccion": INSTRUCCION_LLM,
               "contenido": {"decision": decision, "probabilidad": p, "razones": razones,
                             "monto_clp": fila["monto_clp"], "canal": e.canal, "hora_local": fila["hora_local"]}}
    return {"decision": decision, "probabilidad": p, "origen": origen, "version_modelo": version,
            "resultado": resultado, "entrada_guardada": {**entrada, "monto_clp": fila["monto_clp"]}, "llm": llm}


def dashboard() -> dict:
    por_decision = db.todos("SELECT decision, count(*) AS n FROM predicciones GROUP BY decision ORDER BY n DESC")
    por_dia = db.todos(
        """SELECT date(creada AT TIME ZONE 'America/Santiago') AS dia, count(*) AS evaluadas,
                  round(100.0 * count(*) FILTER (WHERE decision = 'bloquear') / count(*), 2) AS tasa_bloqueo_pct
           FROM predicciones GROUP BY 1 ORDER BY 1 DESC LIMIT 14""")
    cola = db.uno("SELECT count(*) AS n FROM predicciones WHERE decision IN ('revisar', 'bloquear')")
    return {"decisiones": [db.jsonable(f) for f in por_decision],
            "tasa_bloqueo_por_dia": [db.jsonable(f) for f in por_dia], "en_cola_de_revision": cola["n"]}


router = APIRouter()


@router.get("/revision")
def revision(limite: int = 50):
    """Cola de revisión priorizada por riesgo y monto (RF5), con el resumen del LLM cuando está listo."""
    filas = db.todos(
        """SELECT id, creada, decision, probabilidad, origen, entrada->>'monto_clp' AS monto_clp,
                  resultado->'razones' AS razones, estado_llm, texto_llm
           FROM predicciones WHERE decision IN ('revisar', 'bloquear')
           ORDER BY coalesce(probabilidad, 1) * coalesce((entrada->>'monto_clp')::float, 0) DESC
           LIMIT %s""", min(max(limite, 1), 200))
    return [db.jsonable(f) for f in filas]
