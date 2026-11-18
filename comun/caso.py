"""Qué caso es este proyecto: recomendacion, chatbot o fraude.

Se lee de la variable de entorno CASO. Si no está, del archivo CASO en la raíz del repositorio.
En las imágenes, el pipeline la fija al construir (ARG CASO → ENV CASO), así que el compose.yaml no
necesita declararla.
"""
import os
from pathlib import Path

CASOS_VALIDOS = ("recomendacion", "chatbot", "fraude")
RAIZ = Path(__file__).resolve().parent.parent


def caso_actual() -> str:
    caso = os.getenv("CASO")
    if not caso:
        archivo = RAIZ / "CASO"
        caso = archivo.read_text().strip() if archivo.exists() else ""
    if caso not in CASOS_VALIDOS:
        raise SystemExit(f"CASO='{caso}' no es válido. Usa uno de: {', '.join(CASOS_VALIDOS)}")
    return caso
