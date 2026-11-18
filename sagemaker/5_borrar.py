"""Paso 5: borra el endpoint, sus configuraciones y modelos. Con --todo, también el bucket.

    python3 sagemaker/5_borrar.py           # después de la presentación, o si usaste --tiempo-real
    python3 sagemaker/5_borrar.py --todo

Un endpoint serverless sin uso no cobra; uno de tiempo real cobra cada hora. El modelo entrenado queda en
S3 (salvo con --todo): con 3_endpoint.py se vuelve a publicar en minutos, sin reentrenar.
"""
import sys

from botocore.exceptions import ClientError

from comun_sm import BUCKET, ENDPOINT, ESTADO, PREFIJO, guardar_estado, sesion, sm


def main():
    try:
        sm.delete_endpoint(EndpointName=ENDPOINT)
        print(f"Endpoint borrado: {ENDPOINT}")
    except ClientError:
        print(f"No había endpoint {ENDPOINT}")
    for c in sm.list_endpoint_configs(NameContains=PREFIJO, MaxResults=100)["EndpointConfigs"]:
        sm.delete_endpoint_config(EndpointConfigName=c["EndpointConfigName"])
        print(f"Configuración borrada: {c['EndpointConfigName']}")
    for m in sm.list_models(NameContains=PREFIJO, MaxResults=100)["Models"]:
        sm.delete_model(ModelName=m["ModelName"])
        print(f"Modelo borrado: {m['ModelName']}")
    if "--todo" in sys.argv:
        try:
            sesion.resource("s3").Bucket(BUCKET).objects.all().delete()
            sesion.client("s3").delete_bucket(Bucket=BUCKET)
            print(f"Bucket borrado: {BUCKET}")
        except ClientError as e:
            print(f"No se pudo borrar el bucket {BUCKET}: {e}")
        ESTADO.unlink(missing_ok=True)
    else:
        guardar_estado(endpoint=None, modelo=None, version=None, tipo=None)


if __name__ == "__main__":
    main()
