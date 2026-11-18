"""Dónde vive el modelo. El resto del servicio no sabe cuál de los dos está usando.

    MOTOR=local      EP2: el modelo viene dentro de la imagen (modelo.joblib) y se carga en memoria
    MOTOR=sagemaker  EP3: el modelo vive en un endpoint de SageMaker y se invoca con boto3

Los dos reciben una lista de filas ya convertidas a números (vectorizar) y devuelven, por fila, la lista
de probabilidades de cada clase en el orden de metadatos["clases"].
"""
import json
import os
import re
import time
from pathlib import Path

MODELO_DIR = Path(os.getenv("MODELO_DIR", "/srv/modelo"))
NUMERO = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def cargar_metadatos() -> dict:
    return json.loads((MODELO_DIR / "metadatos.json").read_text())


class MotorLocal:
    nombre = "local"

    def __init__(self, metadatos: dict):
        import joblib  # solo se importa si de verdad se usa el modelo local
        self.modelo = joblib.load(MODELO_DIR / "modelo.joblib")
        self.version = metadatos["version"]

    def probabilidades(self, filas: list[list[float]]) -> list[list[float]]:
        return self.modelo.predict_proba(filas).tolist()

    def estado(self) -> str:
        return "cargado"


class MotorSageMaker:
    """Invoca el endpoint con las credenciales del rol de la EC2: no hay claves en ninguna parte."""
    nombre = "sagemaker"

    def __init__(self, metadatos: dict):
        import boto3
        from botocore.config import Config
        region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.endpoint = os.getenv("ENDPOINT") or f"ep3-{metadatos['caso']}"
        self.clases = metadatos["clases"]
        self.binaria = metadatos["tipo"] == "binaria"
        # Sin reintentos de boto3 y con tiempo máximo: si SageMaker no responde, se sabe rápido y el
        # dominio aplica su plan de reserva. 10 s de lectura cubren un cold start (~6 s medido en L10).
        config = Config(connect_timeout=2, read_timeout=float(os.getenv("SAGEMAKER_TIMEOUT", "10")),
                        retries={"total_max_attempts": 1, "mode": "standard"})
        self.runtime = boto3.client("sagemaker-runtime", region_name=region, config=config)
        self.sagemaker = boto3.client("sagemaker", region_name=region, config=config)
        fija = os.getenv("MODELO_VERSION")
        self._version, self._version_hasta = fija, (float("inf") if fija else 0.0)

    @property
    def version(self) -> str:
        # La versión es la configuración del endpoint: cambia cada vez que se publica un modelo nuevo.
        # Se pregunta a SageMaker a lo más una vez por minuto, no en cada predicción.
        if time.monotonic() > self._version_hasta:
            try:
                self._version = self.sagemaker.describe_endpoint(EndpointName=self.endpoint)["EndpointConfigName"]
                self._version_hasta = time.monotonic() + 60
            except Exception:
                return self._version or "desconocida"
        return self._version

    def probabilidades(self, filas: list[list[float]]) -> list[list[float]]:
        cuerpo = "\n".join(",".join(repr(float(v)) for v in fila) for fila in filas)
        r = self.runtime.invoke_endpoint(EndpointName=self.endpoint, ContentType="text/csv",
                                         Accept="text/csv", Body=cuerpo)
        # Binaria: una probabilidad por línea. Multiclase (multi:softprob): una lista por fila, que según
        # la versión del contenedor viene como «0.1,0.7,0.2» o «[0.1, 0.7, 0.2]». Se leen todos los
        # números y se reparten por fila: funciona con los dos formatos.
        numeros = [float(x) for x in NUMERO.findall(r["Body"].read().decode())]
        if self.binaria:
            if len(numeros) != len(filas):
                raise ValueError(f"SageMaker devolvió {len(numeros)} valores para {len(filas)} filas")
            return [[1 - p, p] for p in numeros]
        k = len(self.clases)
        if len(numeros) != k * len(filas):
            raise ValueError(f"SageMaker devolvió {len(numeros)} valores; se esperaban {k} por fila")
        return [numeros[i:i + k] for i in range(0, len(numeros), k)]

    def estado(self) -> str:
        try:
            return self.sagemaker.describe_endpoint(EndpointName=self.endpoint)["EndpointStatus"]
        except Exception as e:
            return f"error: {type(e).__name__}"


def crear_motor(metadatos: dict):
    motor = os.getenv("MOTOR", "local")
    return {"local": MotorLocal, "sagemaker": MotorSageMaker}[motor](metadatos)
