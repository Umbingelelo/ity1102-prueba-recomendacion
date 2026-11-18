"""Tratamiento de los datos del caso: perfilado, limpieza, integración, variables y separación.

    python datos/preparar.py            # usa el caso del archivo CASO
    CASO=chatbot python datos/preparar.py

Lee datos/crudos/<caso>/*.csv y deja en datos/tratados/:
    tablas/<tabla>.csv   lo que el servicio de carga mete en la base
    dataset.csv          las variables del modelo (COLUMNAS), la etiqueta «y» y la columna «particion»
    REPORTE.md           perfil antes/después y cada regla con su conteo: va al capítulo 8.4
    reporte.json         lo mismo, para las pruebas

Es determinista: misma entrada, misma salida. El pipeline lo ejecuta antes de entrenar.
"""
import importlib
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from comun.caracteristicas import modulo  # noqa: E402
from comun.caso import caso_actual  # noqa: E402
from datos.limpieza import Reporte  # noqa: E402

CRUDOS = RAIZ / "datos" / "crudos"
TRATADOS = RAIZ / "datos" / "tratados"


def main():
    caso = caso_actual()
    inicio = time.time()
    tratamiento = importlib.import_module(f"datos.casos.{caso}")
    reporte = Reporte(caso)

    tablas, dataset = tratamiento.preparar(CRUDOS / caso, reporte)

    # El conjunto de entrenamiento tiene exactamente las columnas que espera el modelo, en su orden
    columnas = modulo(caso).COLUMNAS
    faltan = [c for c in columnas + ["y", "particion"] if c not in dataset.columns]
    if faltan:
        raise SystemExit(f"Al dataset le faltan columnas: {faltan}")

    (TRATADOS / "tablas").mkdir(parents=True, exist_ok=True)
    for nombre, df in tablas.items():
        reporte.perfil_despues(nombre, df)
        df.to_csv(TRATADOS / "tablas" / f"{nombre}.csv", index=False)
    dataset[columnas + ["y", "particion"]].to_csv(TRATADOS / "dataset.csv", index=False)
    reporte.escribir(TRATADOS)

    entrenamiento = (dataset["particion"] == "entrenamiento").sum()
    print(f"Caso {caso}: {len(tablas)} tablas tratadas en {time.time() - inicio:.1f} s")
    for nombre, df in tablas.items():
        print(f"  {nombre:<28} {len(df):>7} filas")
    print(f"  dataset: {len(dataset)} filas ({entrenamiento} entrenamiento, {len(dataset) - entrenamiento} prueba),"
          f" {len(columnas)} variables")
    print(f"  {len(reporte.reglas)} reglas aplicadas. Detalle en datos/tratados/REPORTE.md")


if __name__ == "__main__":
    main()
