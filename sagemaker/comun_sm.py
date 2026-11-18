"""Lo que comparten los cinco scripts de SageMaker (EP3). Igual que L10, pero con TUS datos tratados.

Solo usan boto3 y la biblioteca estándar: corren en AWS CloudShell sin instalar nada. Leen:
    CASO                              el caso del proyecto
    modelo/artefactos/metadatos.json  tipo de modelo, columnas y clases (lo escribe modelo/entrenar.py)
    modelo/artefactos/xgboost/*.csv   los datos tratados en el formato del XGBoost de SageMaker

En AWS Academy Learner Lab no se pueden crear usuarios ni roles: todo usa el rol LabRole.
"""
import json
import sys
from pathlib import Path

import boto3

RAIZ = Path(__file__).resolve().parent.parent
ARTEFACTOS = RAIZ / "modelo" / "artefactos"
ESTADO = RAIZ / "sagemaker" / "estado.json"

REGION = "us-east-1"
# Imagen oficial del algoritmo XGBoost de SageMaker en us-east-1 (versión 1.7-1), la misma de L10
IMAGEN_XGBOOST = "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-xgboost:1.7-1"
TIPO_ENTRENAMIENTO = "ml.m5.large"

CASO = (RAIZ / "CASO").read_text().strip()
if not (ARTEFACTOS / "metadatos.json").exists():
    sys.exit("Falta modelo/artefactos/metadatos.json: corre antes datos/preparar.py y modelo/entrenar.py "
             "(o descarga el artefacto «artefactos» del último workflow en verde).")
METADATOS = json.loads((ARTEFACTOS / "metadatos.json").read_text())

sesion = boto3.Session(region_name=REGION)
CUENTA = sesion.client("sts").get_caller_identity()["Account"]
ROL = f"arn:aws:iam::{CUENTA}:role/LabRole"
BUCKET = f"ity1102-ep3-{CUENTA}"
ENDPOINT = f"ep3-{CASO}"
PREFIJO = f"ep3-{CASO}-"

sm = sesion.client("sagemaker")
s3 = sesion.client("s3")


def estado() -> dict:
    return json.loads(ESTADO.read_text()) if ESTADO.exists() else {}


def guardar_estado(**datos) -> dict:
    """Anota lo que hizo cada paso, para poder retomar si la sesión de CloudShell se corta."""
    actual = {**estado(), **datos}
    actual = {k: v for k, v in actual.items() if v is not None}
    ESTADO.write_text(json.dumps(actual, indent=2, ensure_ascii=False))
    return actual


def requiere(clave: str, paso: str):
    valor = estado().get(clave)
    if valor is None:
        sys.exit(f"Falta '{clave}'. Corre primero {paso}.")
    return valor
