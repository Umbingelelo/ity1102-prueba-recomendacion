#!/usr/bin/env bash
# Corre las pruebas como el pipeline, pero en tu computador o en la EC2, con solo Docker instalado:
# un PostgreSQL desechable y Python 3.12 en contenedores. No hace falta Python ni venv en tu máquina.
#
#   herramientas/probar.sh                          # todo: datos, IA, dominio y worker
#   herramientas/probar.sh dominio                  # solo el dominio
#   herramientas/probar.sh dominio -k monto         # solo las pruebas cuyo nombre contiene «monto» (IE13)
#   herramientas/probar.sh ia | worker | datos
#
# Si faltan datos/tratados o modelo/artefactos, los genera primero (preparar.py y entrenar.py).
# La primera vez descarga imágenes e instala dependencias (~2 min); después quedan en caché.
set -euo pipefail
cd "$(dirname "$0")/.."

PARTE="${1:-todo}"; [ $# -gt 0 ] && shift
RED=probar-ity1102; PG=probar-ity1102-pg

case "$PARTE" in
  todo|datos|ia|dominio|worker) ;;
  *) echo "Uso: herramientas/probar.sh [todo|datos|ia|dominio|worker] [opciones de pytest]"; exit 2 ;;
esac

limpiar() { docker rm -f "$PG" >/dev/null 2>&1 || true; docker network rm "$RED" >/dev/null 2>&1 || true; }
trap limpiar EXIT
limpiar
docker network create "$RED" >/dev/null
docker run -d --name "$PG" --network "$RED" -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app \
  -e POSTGRES_DB=proyecto postgres:16-alpine >/dev/null

# Lo que corre dentro del contenedor de Python: mismos comandos que .github/workflows/ci.yml
read -r -d '' GUION <<'EOF' || true
set -euo pipefail
# Lo que se genere aquí (datos, modelo) queda a nombre de tu usuario, no de root (importa en Linux/EC2)
trap 'chown -R "$DUENO" datos/tratados modelo/artefactos .pytest_cache 2>/dev/null || true' EXIT
pip install -q --root-user-action=ignore -r datos/requirements.txt -r requirements-dev.txt
if [ ! -f modelo/artefactos/metadatos.json ] || [ ! -d datos/tratados/tablas ]; then
  echo "== Faltan datos tratados o modelo: preparar.py y entrenar.py"
  python datos/preparar.py && python modelo/entrenar.py
fi
until python -c "import psycopg; psycopg.connect('$DATABASE_URL').close()" 2>/dev/null; do sleep 1; done
case "$PARTE" in
  datos)   pytest -v tests "$@" ;;
  ia)      PYTHONPATH=servicios/ia:. pytest -v servicios/ia/tests "$@" ;;
  dominio) PYTHONPATH=servicios/dominio:. pytest -v servicios/dominio/tests "$@" ;;
  worker)  PYTHONPATH=servicios/worker pytest -v servicios/worker/tests "$@" ;;
  todo)    pytest -q tests && PYTHONPATH=servicios/ia:. pytest -q servicios/ia/tests \
           && PYTHONPATH=servicios/dominio:. pytest -q servicios/dominio/tests \
           && PYTHONPATH=servicios/worker pytest -q servicios/worker/tests ;;
esac
EOF

docker run --rm --network "$RED" -v "$PWD:/repo" -w /repo -v probar-ity1102-pip:/root/.cache/pip \
  -e PARTE="$PARTE" -e DUENO="$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  -e DATABASE_URL="postgresql://app:app@$PG:5432/proyecto" \
  python:3.12-slim bash -c "$GUION" -- "$@"
