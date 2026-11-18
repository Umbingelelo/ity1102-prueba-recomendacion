"""Caso 2 · Andesnet · variables del clasificador de intenciones.

La fila de negocio es un mensaje de texto: {"texto": "..."}. El modelo no lee palabras, lee números: cada
palabra y cada par de palabras seguidas (bigrama) se convierte en un casillero de 0 a N-1 con un hash
estable (zlib.crc32), y el valor del casillero es log(1 + veces que aparece). Al final la fila se divide
por su largo (norma L2) para que un mensaje largo no pese más que uno corto. Es la técnica «feature
hashing»: no necesita guardar un vocabulario, y la misma función sirve al entrenar y al servir.

Antes de contar palabras el texto se anonimiza (comun.anonimizar) y se normaliza: entidades HTML
(&amp; &#241;), saltos de línea escritos como «\\n», la firma «Enviado desde mi iPhone», mayúsculas,
tildes y espacios repetidos. Los marcadores [RUT], [CORREO], [TELEFONO] y [TARJETA] quedan como palabras.
En estos datos «&amp;» reemplaza a la letra «y» («a&amp;uda», «@&amp;ahoo.es»): se devuelve la «y», y
eso además permite reconocer el correo, que con el «&» se le escapaba al anonimizador.

No se usa hash() de Python: cambia en cada proceso (PYTHONHASHSEED) y el modelo vería otra cosa en
producción. Estas mismas N columnas son las que recibe el XGBoost de SageMaker en EP3 (CSV numérico).
"""
import html
import math
import re
import unicodedata
import zlib

from comun.anonimizar import anonimizar

TIPO = "multiclase"
N_CASILLEROS = 512   # DESAFÍO M3 · más casilleros = menos choques entre palabras, pero más columnas

COLUMNAS = [f"h{i:03d}" for i in range(N_CASILLEROS)]
LEGIBLE = {c: f"casillero {c[1:]} del hash de palabras y bigramas" for c in COLUMNAS}

EJEMPLO_FILA = {"texto": "Hola, me llego la boleta con un cobro que no reconozco. Mi rut es [RUT]."}

_FIRMA = re.compile(r"enviado desde mi (iphone|android|celular|samsung)", re.IGNORECASE)
_SALTO = re.compile(r"(\\r)?\\n|[\r\n\t]", re.IGNORECASE)   # también «\N» en los textos en mayúsculas
_ESPACIOS = re.compile(r"\s+")
_TOKEN = re.compile(r"\[[a-z]+\]|[a-z0-9]+")


def sin_entidades(texto: str) -> str:
    """«&#241;» -> «ñ» y «&amp;» -> «y». Va ANTES de anonimizar: un correo con entidades no se reconoce."""
    return html.unescape(texto or "").replace("&", "y")


def limpiar(texto: str) -> str:
    """Texto legible y sin datos personales: es lo que se guarda en la base y se muestra."""
    t = _SALTO.sub(" ", sin_entidades(texto))
    t = _FIRMA.sub(" ", t)
    t = anonimizar(t)
    return _ESPACIOS.sub(" ", t).strip()


def normalizar(texto: str) -> str:
    """Lo que el modelo lee: limpio, en minúsculas y sin tildes («señal» -> «senal»)."""
    t = limpiar(texto).lower()
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def palabras(texto: str) -> list[str]:
    return _TOKEN.findall(normalizar(texto))


def _casillero(termino: str) -> int:
    return zlib.crc32(termino.encode("utf-8")) % N_CASILLEROS


def vectorizar(fila: dict) -> list[float]:
    tokens = palabras(fila.get("texto") or "")
    terminos = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
    conteo = [0.0] * N_CASILLEROS
    for t in terminos:
        conteo[_casillero(t)] += 1.0
    # log1p amortigua la repetición («no no no no»); importa la presencia más que la cantidad
    valores = [math.log1p(v) for v in conteo]
    norma = sum(v * v for v in valores) ** 0.5
    return [v / norma for v in valores] if norma else valores
