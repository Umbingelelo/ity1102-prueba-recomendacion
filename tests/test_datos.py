"""Pruebas del tratamiento de datos. Corren sobre lo que dejó datos/preparar.py en datos/tratados/.

EP2 §2.5: «en el tratamiento, que los datos tratados no tengan duplicados ni nulos en las columnas clave».
"""
import importlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from comun.caracteristicas import modulo  # noqa: E402
from comun.caso import caso_actual  # noqa: E402

CASO = caso_actual()
TRATADOS = RAIZ / "datos" / "tratados"
CLAVES = importlib.import_module(f"datos.casos.{CASO}").CLAVES

if not (TRATADOS / "dataset.csv").exists():
    pytest.exit("Falta datos/tratados: corre antes  python datos/preparar.py", returncode=1)


@pytest.mark.parametrize("tabla,columnas", list(CLAVES.items()))
def test_columnas_clave_sin_nulos_ni_duplicados(tabla, columnas):
    df = pd.read_csv(TRATADOS / "tablas" / f"{tabla}.csv", dtype=str, keep_default_na=False)
    assert not (df[columnas] == "").any().any(), f"{tabla}: hay nulos en {columnas}"
    assert not df.duplicated(subset=columnas).any(), f"{tabla}: hay filas repetidas en {columnas}"


def test_dataset_tiene_exactamente_las_columnas_del_modelo_y_sin_nulos():
    df = pd.read_csv(TRATADOS / "dataset.csv")
    columnas = modulo(CASO).COLUMNAS
    assert list(df.columns) == columnas + ["y", "particion"]
    assert not df[columnas + ["y"]].isna().any().any(), "vectorizar() tiene que dejar todo en números"


def test_la_prueba_se_separo_antes_y_tiene_todas_las_clases():
    df = pd.read_csv(TRATADOS / "dataset.csv")
    assert set(df["particion"]) == {"entrenamiento", "prueba"}
    prueba = df[df["particion"] == "prueba"]
    assert 0.1 <= len(prueba) / len(df) <= 0.4
    assert set(prueba["y"].astype(str)) == set(df["y"].astype(str)), "falta alguna clase en la prueba"


def test_cada_regla_de_limpieza_tiene_su_conteo():
    reporte = json.loads((TRATADOS / "reporte.json").read_text())
    assert len(reporte["reglas"]) >= 5
    for regla in reporte["reglas"]:
        assert regla["filas"] >= 0 and regla["porque"], regla


def test_el_tratamiento_es_determinista(tmp_path):
    """Correrlo dos veces da exactamente el mismo dataset: sin eso no se puede reproducir un modelo."""
    import subprocess
    antes = (TRATADOS / "dataset.csv").read_bytes()
    subprocess.run([sys.executable, str(RAIZ / "datos" / "preparar.py")], check=True, capture_output=True)
    assert (TRATADOS / "dataset.csv").read_bytes() == antes
