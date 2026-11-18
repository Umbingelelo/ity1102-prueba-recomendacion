#!/usr/bin/env bash
# Junta en un archivo Markdown las evidencias que piden el informe y el anexo C, sacadas del sistema que
# está corriendo: así ningún número del informe se escribe de memoria.
#
#   herramientas/evidencias.sh                 # en la carpeta del repo, con el sistema arriba (EC2 o local)
#   URL=http://localhost:8080 herramientas/evidencias.sh
#
# Deja evidencias/EVIDENCIAS-<fecha>.md. No copia secretos: del .env solo lee TAG, CASO, COMPOSE_FILE,
# ENDPOINT, NVIDIA_MODEL, MOTOR y LIMITE_POR_MINUTO.
set -uo pipefail
cd "$(dirname "$0")/.."

URL="${URL:-http://localhost:8080}"
mkdir -p evidencias
SALIDA="evidencias/EVIDENCIAS-$(date +%Y%m%d-%H%M).md"

seccion() { printf '\n## %s\n\n' "$1" >> "$SALIDA"; }
bloque()  { { echo '```'"${1:-text}"; cat; echo '```'; } >> "$SALIDA"; }
de_env()  { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }

{
  echo "# Evidencias del sistema"
  echo
  echo "Generado el $(date '+%Y-%m-%d %H:%M %Z') en \`$(hostname)\` con \`herramientas/evidencias.sh\`."
} > "$SALIDA"

seccion "Versión que corre"
{
  echo "CASO          $(cat CASO 2>/dev/null)"
  echo "commit        $(git rev-parse --short HEAD 2>/dev/null || echo 'sin git')"
  echo "rama          $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo "tags          $(git tag --points-at HEAD 2>/dev/null | tr '\n' ' ')"
  for v in TAG MOTOR ENDPOINT NVIDIA_MODEL LIMITE_POR_MINUTO COMPOSE_FILE; do
    printf '%-13s %s\n' "$v" "$(de_env "$v")"
  done
} | bloque

seccion "Contenedores"
docker compose ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}' 2>&1 | bloque

seccion "Salud: GET /api/health"
curl -s --max-time 10 "$URL/api/health" | python3 -m json.tool 2>&1 | bloque json

seccion "Consumo de recursos: docker stats (una muestra)"
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' \
  $(docker compose ps -q) 2>&1 | bloque

seccion "Predicciones por origen (base de datos)"
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
  select origen, count(*) as n, round(avg(latencia_ms)) as ms_promedio,
         percentile_cont(0.95) within group (order by latencia_ms) as ms_p95
  from predicciones group by origen order by n desc;"' 2>&1 | bloque

docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
  select estado_llm, count(*) from predicciones group by 1 order by 2 desc;"' 2>/dev/null | bloque

if docker compose ps --services 2>/dev/null | grep -qx rabbitmq; then
  seccion "Cola del LLM"
  docker compose exec -T rabbitmq rabbitmqctl list_queues name messages consumers 2>&1 | bloque
fi

seccion "Servidor"
{ free -m 2>/dev/null || vm_stat 2>/dev/null | head -5; echo; df -h / ; } 2>&1 | bloque

if [ -f modelo/artefactos/METRICAS.md ]; then
  seccion "Modelo: modelo/artefactos/METRICAS.md"
  sed 's/^#/###/' modelo/artefactos/METRICAS.md >> "$SALIDA"
fi

if [ -f sagemaker/estado.json ]; then
  seccion "SageMaker: sagemaker/estado.json"
  python3 -m json.tool sagemaker/estado.json 2>&1 | bloque json
fi

if [ -f datos/tratados/REPORTE.md ]; then
  seccion "Tratamiento de datos: primeras líneas de datos/tratados/REPORTE.md"
  head -40 datos/tratados/REPORTE.md | sed 's/^#/###/' >> "$SALIDA"
fi

CSV=$(ls -t carga_stats.csv carga*_stats.csv 2>/dev/null | head -1)
if [ -n "$CSV" ]; then
  seccion "Prueba de carga: $CSV"
  python3 - "$CSV" >> "$SALIDA" <<'EOF'
import csv, sys
filas = list(csv.DictReader(open(sys.argv[1])))
print("| Ruta | Solicitudes | Fallas | % fallas | req/s | p50 | p95 | p99 |")
print("|---|---|---|---|---|---|---|---|")
for f in filas:
    n, e = int(f["Request Count"]), int(f["Failure Count"])
    print(f'| {f["Type"]} {f["Name"]} | {n} | {e} | {100 * e / max(n, 1):.1f} | {float(f["Requests/s"]):.2f} '
          f'| {f["50%"]} | {f["95%"]} | {f["99%"]} |')
EOF
fi

echo "Listo: $SALIDA"
