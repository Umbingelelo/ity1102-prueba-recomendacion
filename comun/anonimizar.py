"""Quita los datos personales de un texto antes de que salga del sistema o entre a un modelo.

Es la misma función de L11. El orden importa: el correo va primero, porque si la tarjeta o el teléfono
corrieran antes, ana1234567890123@correo.cl quedaría «ana[TARJETA]@correo.cl» con el dominio a la vista.

No detecta nombres ni direcciones: eso no se resuelve con una expresión regular. La forma segura de
resolverlo es no mandar nunca esos campos (por ejemplo, al LLM se le mandan categorías, no el cliente).
"""
import re

PATRONES = [
    ("[CORREO]", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    # tarjeta: 13 a 19 dígitos, con o sin espacios o guiones entre grupos
    ("[TARJETA]", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")),
    # RUT: 12.345.678-9, 12345678-9, 9.876.543-K
    ("[RUT]", re.compile(r"(?<![\d.])\d{1,2}(?:\.?\d{3}){2}\s?-\s?[\dkK](?![\w])")),
    # teléfono chileno: +56 9 1234 5678, 56912345678, 912345678, (2) 2345 6789
    ("[TELEFONO]", re.compile(r"(?<!\d)(?:\+?56[ -]?)?\(?[2-9]\)?[ -]?\d{4}[ -]?\d{4}(?!\d)")),
]


def anonimizar(texto: str) -> str:
    for reemplazo, patron in PATRONES:
        texto = patron.sub(reemplazo, texto)
    return texto
