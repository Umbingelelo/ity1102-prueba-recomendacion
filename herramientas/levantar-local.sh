#!/usr/bin/env bash
# Levanta el sistema completo en tu computador, construyendo desde el código:
#   1. trata los datos (datos/preparar.py)       3. construye las imágenes
#   2. entrena y pasa el gate (modelo/entrenar.py) 4. levanta todo en http://localhost:8080
#
#   herramientas/levantar-local.sh            # todo
#   herramientas/levantar-local.sh --sin-datos  # salta 1 y 2 (si ya los corriste y no cambiaste nada)
#
# Usa Docker para los pasos 1 y 2: no necesitas Python ni pandas instalados.
set -euo pipefail
cd "$(dirname "$0")/.."
export CASO="$(tr -d '[:space:]' < CASO)"
echo "== Caso: $CASO"

if [[ "${1:-}" != "--sin-datos" ]]; then
  echo "== 1-2. Tratamiento de datos y entrenamiento (en un contenedor python:3.12-slim)"
  docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e CASO -v "$PWD":/trabajo -w /trabajo python:3.12-slim \
    bash -c "pip install -q --user --disable-pip-version-check -r datos/requirements.txt && python datos/preparar.py && python modelo/entrenar.py"
fi

echo "== 3-4. Construir y levantar"
docker compose -p proyecto -f compose.yaml -f compose.dev.yaml up -d --build
docker compose -p proyecto -f compose.yaml -f compose.dev.yaml ps
echo
echo "Listo: http://localhost:${PUERTO_GATEWAY:-8080}   ·   API: http://localhost:${PUERTO_GATEWAY:-8080}/docs"
echo "Bajar todo (y borrar la base):  docker compose -p proyecto down -v"
