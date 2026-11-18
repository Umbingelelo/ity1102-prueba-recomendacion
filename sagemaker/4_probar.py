"""Paso 4: invoca el endpoint, mide el cold start y evalúa el modelo con el conjunto de prueba.

    python3 sagemaker/4_probar.py
    UMBRAL=0.3 python3 sagemaker/4_probar.py      # otro umbral de decisión (modelos binarios)

El conjunto de prueba nunca subió a S3: el modelo lo ve por primera vez aquí. Las métricas son las del
apartado 1 y 5 del informe de EP3. Para medir el cold start de verdad, córrelo después de 10 minutos
sin usar el endpoint (IE6).
"""
import csv
import os
import re
import statistics
import time

from comun_sm import ARTEFACTOS, ENDPOINT, METADATOS, guardar_estado, requiere, sesion

UMBRAL = float(os.getenv("UMBRAL", "0.5"))
NUMERO = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
runtime = sesion.client("sagemaker-runtime")
CLASES = METADATOS["clases"]
BINARIA = METADATOS["tipo"] == "binaria"


def invocar(filas: list[list[str]]):
    """Devuelve (probabilidades por fila, milisegundos). Igual que servicios/ia/app/motores.py."""
    t = time.perf_counter()
    r = runtime.invoke_endpoint(EndpointName=ENDPOINT, ContentType="text/csv", Accept="text/csv",
                                Body="\n".join(",".join(f) for f in filas))
    ms = (time.perf_counter() - t) * 1000
    numeros = [float(x) for x in NUMERO.findall(r["Body"].read().decode())]
    if BINARIA:
        return [[1 - p, p] for p in numeros], ms
    k = len(CLASES)
    return [numeros[i:i + k] for i in range(0, len(numeros), k)], ms


def pr_auc(reales, puntajes):
    """Precisión promedio (área bajo la curva precision-recall), sin sklearn."""
    orden = sorted(zip(puntajes, reales), key=lambda x: -x[0])
    total_pos, vp, suma = sum(reales), 0, 0.0
    for i, (_, r) in enumerate(orden, start=1):
        if r == 1:
            vp += 1
            suma += vp / i
    return suma / total_pos if total_pos else 0.0


def main():
    requiere("endpoint", "3_endpoint.py")
    with open(ARTEFACTOS / "xgboost" / "test.csv") as f:
        filas = list(csv.reader(f))[1:]
    reales = [f[0] for f in filas]
    x = [f[1:] for f in filas]

    # 1. Una fila dos veces: la primera puede traer cold start; la segunda no
    _, ms1 = invocar(x[:1])
    _, ms2 = invocar(x[:1])
    print(f"Endpoint {ENDPOINT}\n  1.ª invocación: {ms1:7.0f} ms\n  2.ª invocación: {ms2:7.0f} ms")
    # 2. Latencia en caliente: 20 invocaciones de una fila
    tiempos = sorted(invocar(x[:1])[1] for _ in range(20))
    p50, p95 = statistics.median(tiempos), tiempos[18]
    print(f"  20 en caliente: p50 {p50:.0f} ms · p95 {p95:.0f} ms (medido desde donde corres el script)")

    # 3. Métricas sobre la prueba, en lotes de 100 filas por invocación
    probas = []
    for i in range(0, len(x), 100):
        probas += invocar(x[i:i + 100])[0]
    resultado = {"cold_ms": round(ms1), "caliente_ms": round(ms2), "p50_ms": round(p50), "p95_ms": round(p95)}
    if BINARIA:
        y = [int(float(r)) for r in reales]
        p = [fila[1] for fila in probas]
        pred = [int(v >= UMBRAL) for v in p]
        vp = sum(1 for a, b in zip(y, pred) if a == 1 and b == 1)
        fp = sum(1 for a, b in zip(y, pred) if a == 0 and b == 1)
        fn = sum(1 for a, b in zip(y, pred) if a == 1 and b == 0)
        vn = len(y) - vp - fp - fn
        precision = vp / (vp + fp) if vp + fp else 0.0
        recall = vp / (vp + fn) if vp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        resultado.update(umbral=UMBRAL, vp=vp, fp=fp, fn=fn, vn=vn, accuracy=round((vp + vn) / len(y), 4),
                         precision=round(precision, 4), recall=round(recall, 4), f1=round(f1, 4),
                         pr_auc=round(pr_auc(y, p), 4), linea_base_todo_0=round((vn + fp) / len(y), 4),
                         tasa_falsos_positivos=round(fp / (fp + vn), 4) if fp + vn else 0.0)
    else:
        pred = [CLASES[max(range(len(f)), key=f.__getitem__)] for f in probas]
        aciertos = sum(1 for a, b in zip(reales, pred) if a == b)
        f1s = []
        for c in CLASES:
            vp = sum(1 for a, b in zip(reales, pred) if a == c and b == c)
            fp = sum(1 for a, b in zip(reales, pred) if a != c and b == c)
            fn = sum(1 for a, b in zip(reales, pred) if a == c and b != c)
            pr, rc = (vp / (vp + fp) if vp + fp else 0.0), (vp / (vp + fn) if vp + fn else 0.0)
            f1s.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
        mas_frecuente = max(set(reales), key=reales.count)
        resultado.update(accuracy=round(aciertos / len(reales), 4), f1_macro=round(sum(f1s) / len(f1s), 4),
                         f1_por_clase=dict(zip(CLASES, [round(v, 3) for v in f1s])),
                         linea_base_clase_mas_frecuente=round(reales.count(mas_frecuente) / len(reales), 4))
    print(f"Conjunto de prueba: {len(reales)} filas")
    for k, v in resultado.items():
        print(f"  {k}: {v}")
    print(f"Compáralo con modelo/artefactos/METRICAS.md (el modelo de EP2): deberían parecerse.")
    guardar_estado(prueba=resultado)


if __name__ == "__main__":
    main()
