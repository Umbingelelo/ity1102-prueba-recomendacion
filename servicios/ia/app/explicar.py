"""Por qué el modelo dijo lo que dijo, calculado con el propio modelo.

Método de oclusión: para cada variable, se repite la fila cambiando SOLO esa variable por su valor
típico (la mediana del entrenamiento) y se mira cuánto cambia la probabilidad. Si al «normalizar» la hora
la probabilidad de fraude baja de 0,91 a 0,40, la hora aportó +0,51.

La fila original y sus variantes viajan en UNA sola llamada al modelo junto con la predicción: cuesta un
viaje a SageMaker, no dos. No es SHAP, pero se puede explicar a un auditor en una frase (caso 3, RT8).
"""


def variantes(fila: list[float], referencia: list[float]) -> list[list[float]]:
    """La fila original seguida de una copia por variable, con esa variable en su valor típico."""
    salida = [fila]
    for j in range(len(fila)):
        copia = list(fila)
        copia[j] = referencia[j]
        salida.append(copia)
    return salida


def razones(p_variantes: list[float], fila: list[float], referencia: list[float], columnas: list[str],
            legible: dict, maximo: int = 4, minimo: float = 0.01) -> list[dict]:
    """p_variantes: probabilidad de la clase positiva para cada fila de variantes(), en el mismo orden."""
    base = p_variantes[0]
    aportes = []
    for j, columna in enumerate(columnas):
        aporte = base - p_variantes[j + 1]
        if abs(aporte) >= minimo and fila[j] != referencia[j]:
            aportes.append({"variable": columna, "descripcion": legible.get(columna, columna),
                            "valor": fila[j], "aporte": round(aporte, 4)})
    aportes.sort(key=lambda a: a["aporte"], reverse=True)   # primero lo que más empuja hacia la clase
    return aportes[:maximo]
