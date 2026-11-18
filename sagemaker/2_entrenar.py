"""Paso 2: entrena tu modelo con un Training Job de SageMaker (XGBoost integrado) y deja el artefacto en S3.

    python3 sagemaker/2_entrenar.py

SageMaker enciende una ml.m5.large, entrena con tus CSV de S3, guarda el modelo y apaga la máquina. Se
cobra solo el tiempo encendida (2 a 5 minutos). Si cortas el script, el entrenamiento sigue: vuelve a
correrlo y retoma ese trabajo en vez de lanzar otro.
"""
import time
from datetime import datetime

from comun_sm import (ARTEFACTOS, BUCKET, CASO, IMAGEN_XGBOOST, METADATOS, PREFIJO, ROL, TIPO_ENTRENAMIENTO,
                      estado, guardar_estado, requiere, sm)


def hiperparametros() -> dict:
    # DESAFÍO S2 · los hiperparámetros. Si los cambias, compara la métrica de 4_probar.py antes y después.
    base = {"num_round": "150", "max_depth": "5", "eta": "0.1", "subsample": "0.8", "min_child_weight": "3"}
    if CASO == "recomendacion":
        # 19.630 filas con 5% de positivos: con los valores de arriba el modelo memoriza (aucpr 0,61 en
        # entrenamiento y 0,11 en validación). Árboles más bajos y hojas de 50 filas como mínimo, igual que el
        # modelo de EP2, lo corrigen: PR-AUC de prueba 0,098 → 0,134, recall 0,38 → 0,63 (medido 18-11-2026).
        base = {"num_round": "200", "max_depth": "3", "eta": "0.05", "subsample": "0.8", "min_child_weight": "50",
                "lambda": "1"}
    if METADATOS["tipo"] == "multiclase":
        return {**base, "objective": "multi:softprob", "num_class": str(len(METADATOS["clases"])),
                "eval_metric": "mlogloss"}
    # Clase positiva rara (fraude): se le da más peso, igual que class_weight="balanced" en EP2
    etiquetas = [linea.split(",", 1)[0] for linea in open(ARTEFACTOS / "xgboost" / "train.csv")]
    positivos = sum(1 for e in etiquetas if float(e) == 1)
    peso = round((len(etiquetas) - positivos) / max(positivos, 1), 2)
    return {**base, "objective": "binary:logistic", "eval_metric": "aucpr", "scale_pos_weight": str(peso)}


def canal(nombre):
    return {"ChannelName": nombre, "ContentType": "text/csv",
            "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix", "S3Uri": f"s3://{BUCKET}/{CASO}/{nombre}/",
                                            "S3DataDistributionType": "FullyReplicated"}}}


def main():
    requiere("datos", "1_subir.py")
    previo = estado().get("trabajo_en_curso")
    if previo and sm.describe_training_job(TrainingJobName=previo)["TrainingJobStatus"] in ("InProgress", "Completed"):
        trabajo = previo
        print(f"Retomo el Training Job {trabajo}.")
    else:
        trabajo = f"{PREFIJO}{datetime.now():%Y%m%d-%H%M%S}"
        hp = hiperparametros()
        sm.create_training_job(
            TrainingJobName=trabajo,
            AlgorithmSpecification={"TrainingImage": IMAGEN_XGBOOST, "TrainingInputMode": "File"},
            RoleArn=ROL,
            InputDataConfig=[canal("train"), canal("validation")],
            OutputDataConfig={"S3OutputPath": f"s3://{BUCKET}/{CASO}/modelos/"},
            ResourceConfig={"InstanceType": TIPO_ENTRENAMIENTO, "InstanceCount": 1, "VolumeSizeInGB": 5},
            StoppingCondition={"MaxRuntimeInSeconds": 1200},
            HyperParameters=hp,
        )
        guardar_estado(trabajo_en_curso=trabajo, hiperparametros=hp)
        print(f"Training Job {trabajo} en {TIPO_ENTRENAMIENTO} · {hp['objective']}. Se revisa cada 20 s.")

    inicio, anterior = time.time(), None
    while True:
        d = sm.describe_training_job(TrainingJobName=trabajo)
        actual = (d["TrainingJobStatus"], d.get("SecondaryStatus"))
        if actual != anterior:
            print(f"  {int(time.time() - inicio):>4} s · {actual[0]} · {actual[1]}")
            anterior = actual
        if d["TrainingJobStatus"] in ("Completed", "Failed", "Stopped"):
            break
        time.sleep(20)
    if d["TrainingJobStatus"] != "Completed":
        guardar_estado(trabajo_en_curso=None)
        raise SystemExit(f"El entrenamiento terminó en {d['TrainingJobStatus']}: {d.get('FailureReason')}")
    for m in d.get("FinalMetricDataList", []):
        print(f"  {m['MetricName']}: {m['Value']:.4f}")
    artefacto = d["ModelArtifacts"]["S3ModelArtifacts"]
    print(f"  Tiempo facturado: {d.get('BillableTimeInSeconds', 0)} s · modelo: {artefacto}")
    print("Siguiente: python3 sagemaker/3_endpoint.py")
    guardar_estado(trabajo=trabajo, trabajo_en_curso=None, artefacto=artefacto,
                   segundos_facturados=d.get("BillableTimeInSeconds", 0))


if __name__ == "__main__":
    main()
