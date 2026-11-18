"""Un módulo por caso. Cada uno expone:

    CLAVES: dict[tabla, list[columna]]   columnas que no pueden quedar nulas ni repetidas (las prueba el pipeline)
    preparar(crudos: Path, reporte: Reporte) -> (tablas: dict[str, DataFrame], dataset: DataFrame)
"""
import random


def particion_estratificada(etiquetas, prueba=0.25, semilla=1102):
    """Marca 'prueba' o 'entrenamiento' manteniendo la proporción de cada clase en los dos lados."""
    rng = random.Random(semilla)
    salida = ["entrenamiento"] * len(etiquetas)
    por_clase = {}
    for i, y in enumerate(etiquetas):
        por_clase.setdefault(y, []).append(i)
    for indices in por_clase.values():
        rng.shuffle(indices)
        for i in indices[: round(len(indices) * prueba)]:
            salida[i] = "prueba"
    return salida
