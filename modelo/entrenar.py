"""Entrena el modelo con datos/tratados/dataset.csv, lo evalúa con la prueba y decide si se publica.

    python modelo/entrenar.py

Deja en modelo/artefactos/:
    modelo.joblib        el modelo entrenado (EP2: va dentro de la imagen de IA)
    metadatos.json       caso, tipo, columnas, clases, versión, métricas y la fila de referencia
    METRICAS.md          las métricas en una tabla, para el informe
    xgboost/             train.csv, validation.csv y test.csv en el formato del XGBoost de SageMaker (EP3)

Termina con código 1 si la métrica de modelo/config.json no llega a su mínimo: es el «gate» del pipeline.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix, f1_score,  # noqa: E402
                             precision_score, recall_score, roc_auc_score)

from comun.caracteristicas import modulo  # noqa: E402
from comun.caso import caso_actual  # noqa: E402

ARTEFACTOS = RAIZ / "modelo" / "artefactos"
SEMILLA = 1102

# DESAFÍO M2 · el estimador y sus hiperparámetros. Son razonables, no óptimos. Si los cambias, compara
# la métrica de prueba antes y después y deja las dos en el informe.
ESTIMADORES = {
    "fraude": lambda: HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08, max_iter=200,
                                                     class_weight="balanced", random_state=SEMILLA),
    "recomendacion": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                            min_samples_leaf=50, l2_regularization=1.0,
                                                            class_weight="balanced", random_state=SEMILLA),
    "chatbot": lambda: LogisticRegression(max_iter=3000, C=4.0, class_weight="balanced"),
}


def version(caso: str) -> str:
    if os.getenv("VERSION_MODELO"):
        return os.environ["VERSION_MODELO"]
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             cwd=RAIZ, check=True).stdout.strip()
        return f"{caso}-{sha}"
    except (OSError, subprocess.CalledProcessError):
        return f"{caso}-local-{datetime.now():%Y%m%d%H%M}"


def metricas_binarias(y, p, umbral=0.5) -> dict:
    pred = (p >= umbral).astype(int)
    vn, fp, fn, vp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "umbral": umbral, "accuracy": accuracy_score(y, pred), "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred), "f1": f1_score(y, pred), "roc_auc": roc_auc_score(y, p),
        "pr_auc": average_precision_score(y, p), "vp": int(vp), "fp": int(fp), "fn": int(fn), "vn": int(vn),
        # Las líneas base: lo que obtendría un sistema sin modelo
        "linea_base_accuracy_todo_0": float((y == 0).mean()), "linea_base_pr_auc_azar": float(y.mean()),
    }


def metricas_multiclase(y, proba, clases) -> dict:
    pred = np.array(clases)[proba.argmax(axis=1)]
    mas_frecuente = pd.Series(y).mode()[0]
    return {
        "accuracy": accuracy_score(y, pred), "f1_macro": f1_score(y, pred, average="macro"),
        "precision_macro": precision_score(y, pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y, pred, average="macro"),
        "f1_por_clase": dict(zip(clases, f1_score(y, pred, average=None, labels=clases).round(3).tolist())),
        "matriz_confusion": {"clases": clases, "filas_real_columnas_predicha":
                             confusion_matrix(y, pred, labels=clases).tolist()},
        "linea_base_accuracy_clase_mas_frecuente": float((np.array(y) == mas_frecuente).mean()),
    }


def escribir_xgboost(entrenamiento: pd.DataFrame, prueba: pd.DataFrame, columnas, clases, tipo):
    """El XGBoost integrado de SageMaker exige: etiqueta numérica en la PRIMERA columna, sin cabecera."""
    carpeta = ARTEFACTOS / "xgboost"
    carpeta.mkdir(parents=True, exist_ok=True)
    codificar = (lambda y: y.astype(int)) if tipo == "binaria" else (lambda y: y.map({c: i for i, c in enumerate(clases)}))
    mezclado = entrenamiento.sample(frac=1, random_state=SEMILLA)
    corte = int(len(mezclado) * 0.85)
    for nombre, df in (("train", mezclado.iloc[:corte]), ("validation", mezclado.iloc[corte:])):
        pd.concat([codificar(df["y"]), df[columnas]], axis=1).to_csv(carpeta / f"{nombre}.csv", index=False, header=False)
    # La prueba lleva cabecera y la etiqueta original: la usa sagemaker/4_probar.py para medir
    prueba[["y"] + columnas].to_csv(carpeta / "test.csv", index=False)


def main():
    caso = caso_actual()
    variables = modulo(caso)
    config = json.loads((RAIZ / "modelo" / "config.json").read_text())[caso]
    df = pd.read_csv(RAIZ / "datos" / "tratados" / "dataset.csv")
    columnas, tipo = variables.COLUMNAS, variables.TIPO
    entrenamiento, prueba = df[df["particion"] == "entrenamiento"], df[df["particion"] == "prueba"]

    inicio = time.time()
    modelo = ESTIMADORES[caso]()
    modelo.fit(entrenamiento[columnas].to_numpy(), entrenamiento["y"].to_numpy())
    segundos = time.time() - inicio

    proba = modelo.predict_proba(prueba[columnas].to_numpy())
    clases = [str(c) for c in modelo.classes_]
    if tipo == "binaria":
        m = metricas_binarias(prueba["y"].to_numpy(), proba[:, 1])
    else:
        m = metricas_multiclase(prueba["y"].astype(str).to_numpy(), proba, clases)
    m = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}

    ARTEFACTOS.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, ARTEFACTOS / "modelo.joblib")
    metadatos = {
        "caso": caso, "tipo": tipo, "version": version(caso), "columnas": columnas, "clases": clases,
        "entrenado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filas_entrenamiento": int(len(entrenamiento)), "filas_prueba": int(len(prueba)),
        "segundos_entrenamiento": round(segundos, 2), "metricas_prueba": m,
        # Fila «típica» (medianas del entrenamiento): contra ella se mide cuánto aporta cada variable
        "referencia": entrenamiento[columnas].median().round(4).tolist(),
        "gate": config,
    }
    (ARTEFACTOS / "metadatos.json").write_text(json.dumps(metadatos, indent=2, ensure_ascii=False))
    escribir_xgboost(entrenamiento, prueba, columnas, clases, tipo)

    filas = [f"| {k} | {v} |" for k, v in m.items() if not isinstance(v, (dict, list))]
    (ARTEFACTOS / "METRICAS.md").write_text(
        f"# Métricas del modelo · {caso} · {metadatos['version']}\n\nConjunto de prueba: {len(prueba)} filas, "
        f"separado antes de entrenar.\n\n| Métrica | Valor |\n|---|---|\n" + "\n".join(filas) + "\n")

    print(f"Modelo {metadatos['version']} entrenado en {segundos:.1f} s con {len(entrenamiento)} filas")
    for linea in filas:
        print("  " + linea.strip("| ").replace(" | ", ": "))
    valor = m[config["metrica"]]
    if valor < config["minimo"]:
        raise SystemExit(f"GATE: {config['metrica']} = {valor} < mínimo {config['minimo']}. El modelo NO se publica.")
    print(f"GATE: {config['metrica']} = {valor} >= {config['minimo']}. El modelo se puede publicar.")


if __name__ == "__main__":
    main()
