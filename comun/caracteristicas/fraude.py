"""Caso 3 · Kipu Pagos · variables del modelo de fraude.

La fila de negocio es una transacción ya enriquecida con su usuario y su dispositivo (el dominio hace el
cruce con la base; preparar.py hace el mismo cruce con los CSV tratados). Ninguna de estas variables se
conoce DESPUÉS de decidir: revisado_por_analista, motivo_bloqueo y resultado_autorizacion quedan fuera
porque son fuga de información.
"""
from comun.caracteristicas import numero

TIPO = "binaria"
CANALES = ("app", "web", "pos", "api")

COLUMNAS = [
    "monto_clp", "hora_local", "madrugada", "intentos_previos_1h", "edad_cuenta_dias", "nivel_kyc",
    "verificado", "telefono_verificado", "email_desechable", "usuarios_distintos", "emulador",
    "pais_distinto", "sin_dispositivo",
] + [f"canal_{c}" for c in CANALES]

LEGIBLE = {
    "monto_clp": "monto de la transacción",
    "hora_local": "hora del día",
    "madrugada": "ocurrió entre las 00:00 y las 06:00",
    "intentos_previos_1h": "transacciones del usuario en la hora previa",
    "edad_cuenta_dias": "antigüedad de la cuenta",
    "nivel_kyc": "nivel de verificación de identidad",
    "verificado": "usuario verificado",
    "telefono_verificado": "teléfono verificado",
    "email_desechable": "correo de dominio desechable",
    "usuarios_distintos": "usuarios distintos en el mismo dispositivo",
    "emulador": "dispositivo es un emulador",
    "pais_distinto": "país de la transacción distinto al del usuario",
    "sin_dispositivo": "transacción sin huella de dispositivo",
    **{f"canal_{c}": f"canal {c}" for c in CANALES},
}

# La misma transacción ya enriquecida por el dominio: así le llega al microservicio de IA
EJEMPLO_FILA = {
    "monto_clp": 250000, "hora_local": 3, "canal": "app", "intentos_previos_1h": 4, "edad_cuenta_dias": 12,
    "nivel_kyc": 0, "verificado": 0, "telefono_verificado": 0, "email_desechable": 1, "usuarios_distintos": 3,
    "emulador": 1, "pais_distinto": 1, "dispositivo_id": "D-1358e431cbe4",
}


def vectorizar(fila: dict) -> list[float]:
    hora = numero(fila.get("hora_local"))
    canal = (fila.get("canal") or "").strip().lower()
    valores = {
        "monto_clp": numero(fila.get("monto_clp")),
        "hora_local": hora,
        "madrugada": float(0 <= hora < 6) if hora != -1 else -1.0,
        "intentos_previos_1h": numero(fila.get("intentos_previos_1h")),
        "edad_cuenta_dias": numero(fila.get("edad_cuenta_dias")),
        "nivel_kyc": numero(fila.get("nivel_kyc")),
        "verificado": numero(fila.get("verificado")),
        "telefono_verificado": numero(fila.get("telefono_verificado")),
        "email_desechable": numero(fila.get("email_desechable")),
        "usuarios_distintos": numero(fila.get("usuarios_distintos")),
        "emulador": numero(fila.get("emulador")),
        "pais_distinto": numero(fila.get("pais_distinto")),
        "sin_dispositivo": float(not fila.get("dispositivo_id")),
        **{f"canal_{c}": float(canal == c) for c in CANALES},
    }
    return [valores[c] for c in COLUMNAS]
