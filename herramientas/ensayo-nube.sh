#!/usr/bin/env bash
# Ensayo de EP3 en tu computador: el sistema de la nube completo (Caddy con HTTPS, RabbitMQ, worker,
# IA en modo SageMaker) con SageMaker y NVIDIA reemplazados por dobles. Sin AWS y sin gastar crédito.
#
#   herramientas/ensayo-nube.sh                 # levanta (antes corre herramientas/levantar-local.sh una vez)
#   DOBLE_LLM=429 herramientas/ensayo-nube.sh   # NVIDIA respondiendo siempre 429
#   NVIDIA_API_KEY=invalida herramientas/ensayo-nube.sh   # clave inválida: modo degradado
#
# Después: https://localhost:8443 (el navegador avisa del certificado local: es normal en el ensayo).
set -euo pipefail
cd "$(dirname "$0")/.."
export CASO="$(tr -d '[:space:]' < CASO)"
export DOMINIO=localhost MOTOR=sagemaker
export NVIDIA_MODEL="${NVIDIA_MODEL:-modelo-de-ensayo}"
export API_KEYS="${API_KEYS:-clave-de-ensayo}"
export PUERTO_GATEWAY="127.0.0.1:${PUERTO_GATEWAY:-8080}"
ARCHIVOS=(-f compose.yaml -f compose.dev.yaml -f compose.nube.yaml -f compose.ensayo.yaml)

if [[ ! -f modelo/artefactos/modelo.joblib ]]; then
  echo "Falta el modelo: corre primero herramientas/levantar-local.sh"; exit 1
fi
docker compose -p ensayo "${ARCHIVOS[@]}" up -d --build
docker compose -p ensayo "${ARCHIVOS[@]}" ps
echo
echo "Listo: https://localhost:${PUERTO_HTTPS:-8443}  ·  clave de API: $API_KEYS"
echo "Prueba:  curl -sk https://localhost:${PUERTO_HTTPS:-8443}/api/health"
echo "Bajar:   docker compose -p ensayo ${ARCHIVOS[*]} down -v"
