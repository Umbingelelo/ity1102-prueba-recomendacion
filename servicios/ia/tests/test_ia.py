"""Pruebas del microservicio de IA con el modelo de verdad (modelo/artefactos), sin red.

    PYTHONPATH=servicios/ia:. pytest servicios/ia/tests
"""
import io
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("CASO", (RAIZ / "CASO").read_text().strip())
os.environ.setdefault("MODELO_DIR", str(RAIZ / "modelo" / "artefactos"))
os.environ["MOTOR"] = "local"     # las pruebas nunca salen a AWS

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main, motores  # noqa: E402

cliente = TestClient(main.app)
EJEMPLO = main.VARIABLES.EJEMPLO_FILA


def test_health_dice_motor_y_version():
    r = cliente.get("/health").json()
    assert r["estado"] == "ok" and r["motor"] == "local" and r["version_modelo"]


def test_prediccion_valida_trae_resultado_y_version():
    r = cliente.post("/predict", json={"filas": [EJEMPLO, EJEMPLO]})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["version_modelo"] == main.METADATOS["version"]
    assert len(cuerpo["resultados"]) == 2
    assert 0 <= cuerpo["resultados"][0]["probabilidad"] <= 1


def test_sin_filas_responde_422():
    assert cliente.post("/predict", json={"filas": []}).status_code == 422
    assert cliente.post("/predict", json={}).status_code == 422


@pytest.mark.skipif(main.METADATOS["tipo"] != "binaria", reason="las razones son para modelos binarios")
def test_las_razones_salen_del_modelo_y_vienen_ordenadas():
    r = cliente.post("/predict", json={"filas": [EJEMPLO], "explicar": True}).json()
    razones = r["resultados"][0]["razones"]
    assert all(set(x) >= {"variable", "descripcion", "valor", "aporte"} for x in razones)
    aportes = [x["aporte"] for x in razones]
    assert aportes == sorted(aportes, reverse=True)


class RuntimeFalso:
    def __init__(self, cuerpo: bytes):
        self.cuerpo, self.pedidos = cuerpo, []

    def invoke_endpoint(self, **kwargs):
        self.pedidos.append(kwargs)
        return {"Body": io.BytesIO(self.cuerpo)}


def _motor_sagemaker(tipo, clases, cuerpo):
    motor = motores.MotorSageMaker({"caso": "prueba", "tipo": tipo, "clases": clases})
    motor.runtime = RuntimeFalso(cuerpo)
    return motor


def test_sagemaker_binario_lee_una_probabilidad_por_fila():
    motor = _motor_sagemaker("binaria", ["0", "1"], b"0.25\n0.9\n")
    assert motor.probabilidades([[1.0, 2.0], [3.0, 4.0]]) == [[0.75, 0.25], [pytest.approx(0.1), 0.9]]
    assert motor.runtime.pedidos[0]["Body"] == "1.0,2.0\n3.0,4.0"   # CSV sin cabecera, en el orden de COLUMNAS


@pytest.mark.parametrize("cuerpo", [b"0.1,0.7,0.2\n0.5,0.3,0.2\n", b"[0.1, 0.7, 0.2]\n[0.5, 0.3, 0.2]\n"])
def test_sagemaker_multiclase_entiende_los_dos_formatos(cuerpo):
    motor = _motor_sagemaker("multiclase", ["a", "b", "c"], cuerpo)
    assert motor.probabilidades([[0.0], [1.0]]) == [[0.1, 0.7, 0.2], [0.5, 0.3, 0.2]]


def test_sagemaker_con_respuesta_incompleta_falla_en_vez_de_inventar():
    motor = _motor_sagemaker("multiclase", ["a", "b", "c"], b"0.1,0.9\n")
    with pytest.raises(ValueError):
        motor.probabilidades([[0.0]])
