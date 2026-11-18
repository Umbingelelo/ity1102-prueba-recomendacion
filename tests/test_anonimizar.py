"""Prueba obligatoria 5 de EP3 §4.3: ningún dato personal sobrevive a la anonimización."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comun.anonimizar import anonimizar  # noqa: E402


def test_ningun_dato_personal_sobrevive():
    texto = ("Hola, soy Ana. Mi RUT es 12.345.678-9, el de mi papá 9876543-K, escríbanme a "
             "ana.perez+tele@correo.cl o al +56 9 8765 4321. Me cobraron en la 4111 1111 1111 1111.")
    limpio = anonimizar(texto)
    for dato in ["12.345.678-9", "9876543-K", "ana.perez+tele@correo.cl", "8765 4321", "4111"]:
        assert dato not in limpio
    assert limpio.count("[RUT]") == 2
    assert "[CORREO]" in limpio and "[TELEFONO]" in limpio and "[TARJETA]" in limpio


def test_no_toca_montos_ni_horas():
    texto = "Transferí $250.000 a las 03:15 y luego 3 intentos más"
    assert anonimizar(texto) == texto
