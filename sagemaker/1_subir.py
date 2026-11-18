"""Paso 1: sube a S3 los datos tratados de entrenamiento y validación (la prueba queda local).

    python3 sagemaker/1_subir.py

El dataset de EP3 (IE5) es este bucket: los datos que salieron de TU datos/preparar.py.
"""
from botocore.exceptions import ClientError

from comun_sm import ARTEFACTOS, BUCKET, CASO, METADATOS, guardar_estado, s3


def main():
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=BUCKET)          # en us-east-1 no lleva LocationConstraint
        print(f"Bucket creado: {BUCKET}")
    for nombre in ("train", "validation"):
        archivo = ARTEFACTOS / "xgboost" / f"{nombre}.csv"
        s3.upload_file(str(archivo), BUCKET, f"{CASO}/{nombre}/{nombre}.csv")
        filas = sum(1 for _ in open(archivo))
        print(f"  s3://{BUCKET}/{CASO}/{nombre}/{nombre}.csv  ·  {filas} filas")
    print(f"Caso {CASO} · modelo {METADATOS['tipo']} · {len(METADATOS['columnas'])} variables"
          f"{' · clases: ' + ', '.join(METADATOS['clases']) if METADATOS['tipo'] == 'multiclase' else ''}")
    print("Siguiente: python3 sagemaker/2_entrenar.py")
    guardar_estado(caso=CASO, datos=f"s3://{BUCKET}/{CASO}/")


if __name__ == "__main__":
    main()
