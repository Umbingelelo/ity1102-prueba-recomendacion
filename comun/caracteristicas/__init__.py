"""Las variables de entrada del modelo, una definición por caso.

Cada módulo de caso expone lo mismo, para que el resto del código no tenga que saber de qué caso se trata:

    TIPO          "binaria" o "multiclase"
    COLUMNAS      los nombres de las variables, en el orden exacto en que el modelo las recibe
    LEGIBLE       nombre en lenguaje común de cada columna (para explicar decisiones)
    vectorizar(fila: dict) -> list[float]   de una fila «de negocio» a la lista de números del modelo
    EJEMPLO_FILA  una fila de negocio de ejemplo (la usan /ejemplo, las pruebas y la prueba de carga)

datos/preparar.py usa vectorizar() para armar el conjunto de entrenamiento, y servicios/ia la usa para
armar lo que manda al modelo. Es la misma función en los dos lados: así no hay diferencia entre lo que
el modelo vio al entrenar y lo que ve en producción.
"""
import importlib

FALTANTE = -1.0   # valor para un dato que no se conoce. Los árboles lo aprenden como «no se sabe»


def modulo(caso: str):
    return importlib.import_module(f"comun.caracteristicas.{caso}")


def numero(valor, defecto=FALTANTE) -> float:
    """Convierte a float. None, '' o algo que no es número quedan como FALTANTE."""
    if valor is None or valor == "":
        return defecto
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return defecto
    return defecto if x != x else x   # x != x solo es cierto para NaN
