"""Monitoreo en la nube (EP3): un dashboard de CloudWatch, dos métricas sacadas de tus logs y tres alarmas.

    python3 herramientas/cloudwatch.py                         # desde AWS CloudShell, en us-east-1
    python3 herramientas/cloudwatch.py --instancia i-0abc123   # si hay varias EC2, cuál es la tuya
    python3 herramientas/cloudwatch.py --borrar                # lo quita todo

Crea:
  · Dashboard «proyecto-ep3»: invocaciones, latencia del modelo y cold start (ModelSetupTime) del
    endpoint serverless, CPU de la EC2, predicciones y decisiones de reserva sacadas de los logs.
  · Filtros de métricas sobre el grupo de logs /ity1102/proyecto (lo llena compose.cloudwatch.yaml):
    cada línea JSON {"evento": "prediccion", ...} cuenta como una predicción, y las de origen «reserva»
    cuentan aparte. Así una línea de log se convierte en un número que se puede graficar y alarmar.
  · Alarmas: latencia del modelo alta, errores del endpoint y demasiadas decisiones por reserva.
    Quedan en la consola (CloudWatch → Alarms) con su estado OK / ALARM. Sin SNS: el Learner Lab no
    garantiza poder crear temas; el informe dice a quién avisaría cada una en producción.

Solo usa boto3 (CloudShell lo trae). Si algún paso responde AccessDenied, el script lo dice y sigue:
lo que el Learner Lab no deje crear por API se hace en la consola con los mismos valores.
"""
import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
RAIZ = Path(__file__).resolve().parent.parent
CASO = (RAIZ / "CASO").read_text().strip()
ENDPOINT = f"ep3-{CASO}"
GRUPO = "/ity1102/proyecto"
ESPACIO = "Proyecto/EP3"
TABLERO = "proyecto-ep3"

cw = boto3.client("cloudwatch", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)
ec2 = boto3.client("ec2", region_name=REGION)


def intentar(descripcion, funcion, **kwargs):
    try:
        funcion(**kwargs)
        print(f"  ok · {descripcion}")
    except ClientError as e:
        print(f"  NO · {descripcion}: {e.response['Error']['Code']} — hazlo en la consola con los mismos valores")


def instancia_ec2():
    """La EC2 del proyecto: la de --instancia, o la que corre con el perfil LabInstanceProfile y un nombre
    que empieza con «ep3», o la primera que esté corriendo."""
    if "--instancia" in sys.argv:
        return sys.argv[sys.argv.index("--instancia") + 1]
    r = ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["running"]}])
    todas = [i for res in r["Reservations"] for i in res["Instances"]]
    nombre = lambda i: next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
    preferidas = [i for i in todas if nombre(i).startswith("ep3")
                  and "LabInstanceProfile" in i.get("IamInstanceProfile", {}).get("Arn", "")]
    elegida = (preferidas or todas or [None])[0]
    return elegida["InstanceId"] if elegida else None


def sagemaker(metrica, estadistica="Sum"):
    return ["AWS/SageMaker", metrica, "EndpointName", ENDPOINT, "VariantName", "principal", {"stat": estadistica}]


def tablero(id_ec2):
    w = lambda x, y, titulo, metricas, extra=None: {
        "type": "metric", "x": x, "y": y, "width": 12, "height": 6,
        "properties": {"title": titulo, "region": REGION, "metrics": metricas, "period": 60, "view": "timeSeries",
                       **(extra or {})}}
    widgets = [
        w(0, 0, f"Invocaciones del endpoint {ENDPOINT}", [sagemaker("Invocations")]),
        w(12, 0, "Latencia del modelo p95 (microsegundos)", [sagemaker("ModelLatency", "p95")]),
        w(0, 6, "Cold start: ModelSetupTime (microsegundos)", [sagemaker("ModelSetupTime", "Maximum")]),
        w(12, 6, "Errores del endpoint", [sagemaker("Invocation4XXErrors"), sagemaker("Invocation5XXErrors")]),
        w(0, 12, "Predicciones y decisiones por reserva (desde los logs)",
          [[ESPACIO, "Predicciones", {"stat": "Sum"}], [ESPACIO, "DecisionesReserva", {"stat": "Sum"}]]),
    ]
    if id_ec2:
        widgets.append(w(12, 12, f"CPU de la EC2 {id_ec2}", [["AWS/EC2", "CPUUtilization", "InstanceId", id_ec2]]))
    widgets.append({"type": "log", "x": 0, "y": 18, "width": 24, "height": 6, "properties": {
        "title": "Últimas predicciones (logs del dominio)", "region": REGION,
        "query": f"SOURCE '{GRUPO}' | fields @timestamp, id, decision, origen, version_modelo, latencia_ms "
                 "| filter evento = 'prediccion' | sort @timestamp desc | limit 20"}})
    return {"widgets": widgets}


def crear():
    id_ec2 = instancia_ec2()
    print(f"Caso {CASO} · endpoint {ENDPOINT} · EC2 {id_ec2 or '(ninguna corriendo)'}")
    if logs.describe_log_groups(logGroupNamePrefix=GRUPO)["logGroups"]:
        print(f"  ok · el grupo {GRUPO} ya existe")
    else:
        intentar("grupo de logs " + GRUPO, logs.create_log_group, logGroupName=GRUPO)
    intentar("filtro Predicciones", logs.put_metric_filter, logGroupName=GRUPO, filterName="predicciones",
             filterPattern='{ $.evento = "prediccion" }',
             metricTransformations=[{"metricName": "Predicciones", "metricNamespace": ESPACIO, "metricValue": "1",
                                     "defaultValue": 0}])
    intentar("filtro DecisionesReserva", logs.put_metric_filter, logGroupName=GRUPO, filterName="reserva",
             filterPattern='{ $.evento = "prediccion" && $.origen = "reserva" }',
             metricTransformations=[{"metricName": "DecisionesReserva", "metricNamespace": ESPACIO,
                                     "metricValue": "1", "defaultValue": 0}])
    intentar(f"dashboard {TABLERO}", cw.put_dashboard, DashboardName=TABLERO,
             DashboardBody=json.dumps(tablero(id_ec2)))
    # DESAFÍO O2 · los umbrales de las alarmas salen del RNF de rendimiento de tu caso
    comunes = dict(EvaluationPeriods=3, DatapointsToAlarm=2, Period=60, TreatMissingData="notBreaching")
    dims = [{"Name": "EndpointName", "Value": ENDPOINT}, {"Name": "VariantName", "Value": "principal"}]
    intentar("alarma latencia del modelo", cw.put_metric_alarm, AlarmName=f"{ENDPOINT}-latencia-alta",
             AlarmDescription="p95 de ModelLatency sobre 500 ms: revisar memoria del endpoint y cold starts",
             Namespace="AWS/SageMaker", MetricName="ModelLatency", Dimensions=dims, ExtendedStatistic="p95",
             Threshold=500_000, ComparisonOperator="GreaterThanThreshold", **comunes)
    intentar("alarma errores del endpoint", cw.put_metric_alarm, AlarmName=f"{ENDPOINT}-errores",
             AlarmDescription="Invocaciones con error 5XX en el endpoint",
             Namespace="AWS/SageMaker", MetricName="Invocation5XXErrors", Dimensions=dims, Statistic="Sum",
             Threshold=0, ComparisonOperator="GreaterThanThreshold", **comunes)
    intentar("alarma decisiones por reserva", cw.put_metric_alarm, AlarmName="proyecto-reserva-alta",
             AlarmDescription="Más de 5 decisiones por minuto salen de la política de reserva: el modelo no responde",
             Namespace=ESPACIO, MetricName="DecisionesReserva", Statistic="Sum",
             Threshold=5, ComparisonOperator="GreaterThanThreshold", **comunes)
    print(f"\nConsola: CloudWatch → Dashboards → {TABLERO}   ·   CloudWatch → Alarms")


def borrar():
    intentar("dashboard", cw.delete_dashboards, DashboardNames=[TABLERO])
    intentar("alarmas", cw.delete_alarms, AlarmNames=[f"{ENDPOINT}-latencia-alta", f"{ENDPOINT}-errores",
                                                       "proyecto-reserva-alta"])
    for f in ("predicciones", "reserva"):
        intentar(f"filtro {f}", logs.delete_metric_filter, logGroupName=GRUPO, filterName=f)


if __name__ == "__main__":
    borrar() if "--borrar" in sys.argv else crear()
