#!/usr/bin/env bash
# Genera carga sobre POST /api/predict y mide con docker stats: de aquí salen los números del capítulo 7.2
# (dimensionamiento) y la primera pregunta de la defensa de EP2 (IE2).
#   herramientas/medir.sh                       # 60 s contra http://localhost:8080, 8 en paralelo
#   URL=https://3-85-10-20.sslip.io CLAVE=xxx SEGUNDOS=120 PARALELO=16 herramientas/medir.sh
#
# OJO: el dominio limita a LIMITE_POR_MINUTO (120 por defecto) y responde 429 al pasarse. Para medir el
# sistema y no el límite, levántalo con el límite alto mientras mides:
#   LIMITE_POR_MINUTO=1000000 herramientas/levantar-local.sh --sin-datos
# Usa como cuerpo el ejemplo que publica la propia API en /openapi.json. Deja todo en medicion-<fecha>/.
set -euo pipefail
URL="${URL:-http://localhost:8080}"
SEGUNDOS="${SEGUNDOS:-60}"
PARALELO="${PARALELO:-8}"
CABECERA=(-H "content-type: application/json")
[[ -n "${CLAVE:-}" ]] && CABECERA+=(-H "X-API-Key: $CLAVE")
SALIDA="medicion-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$SALIDA"

CUERPO="$(curl -sk "$URL/openapi.json" | python3 -c '
import json, sys
spec = json.load(sys.stdin)
ref = spec["paths"]["/api/predict"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
print(json.dumps(spec["components"]["schemas"][ref.split("/")[-1]]["example"]))')"
echo "Cuerpo: $CUERPO"

echo "== docker stats cada 2 s durante la carga (en $SALIDA/stats.txt)"
( fin=$((SECONDS + SEGUNDOS)); while (( SECONDS < fin )); do
    docker stats --no-stream --format '{{.Name}};{{.CPUPerc}};{{.MemUsage}};{{.MemPerc}}' >> "$SALIDA/stats.txt"; sleep 2
  done ) &

echo "== $PARALELO clientes en paralelo durante $SEGUNDOS s"
for _ in $(seq "$PARALELO"); do
  ( fin=$((SECONDS + SEGUNDOS)); while (( SECONDS < fin )); do
      curl -sk -o /dev/null -w '%{http_code} %{time_total}\n' -X POST "$URL/api/predict" "${CABECERA[@]}" -d "$CUERPO"
    done >> "$SALIDA/tiempos.txt" ) &
done
wait

python3 - "$SALIDA" <<'PY'
import collections, sys
carpeta = sys.argv[1]
filas = [l.split() for l in open(f"{carpeta}/tiempos.txt") if l.strip()]
ms = sorted(float(t) * 1000 for _, t in filas)
codigos = collections.Counter(c for c, _ in filas)
p = lambda q: ms[min(len(ms) - 1, int(q * len(ms)))]
print(f"\nSolicitudes: {len(ms)} · códigos: {dict(codigos)}")
print(f"Latencia ms  p50 {p(.5):.0f} · p95 {p(.95):.0f} · p99 {p(.99):.0f} · máx {ms[-1]:.0f}")
if codigos.get("429", 0) > 0.1 * len(ms):
    print("AVISO: más del 10% fueron 429 (límite de solicitudes). Estás midiendo el límite, no el sistema:")
    print("       levanta con LIMITE_POR_MINUTO=1000000 mientras mides (ver el encabezado de este script).")
pico = {}
for l in open(f"{carpeta}/stats.txt"):
    nombre, cpu, mem, _ = l.strip().split(";")
    usado = mem.split("/")[0].strip()
    valor = float(usado[:-3]) * (1024 if usado.endswith("GiB") else 1) if usado.endswith("iB") else 0
    cpu = float(cpu.rstrip("%"))
    a = pico.get(nombre, (0, 0, mem.split("/")[1].strip()))
    pico[nombre] = (max(a[0], cpu), max(a[1], valor), a[2])
print("\nPico por contenedor (para el capítulo 7.2):")
print(f"{'contenedor':<28}{'CPU máx %':>10}{'RAM máx MiB':>13}  límite")
for n, (c, m, lim) in sorted(pico.items()):
    print(f"{n:<28}{c:>10.1f}{m:>13.1f}  {lim}")
PY
