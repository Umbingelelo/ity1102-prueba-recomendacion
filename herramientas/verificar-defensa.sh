#!/usr/bin/env bash
# Revisa compose.yaml contra las nueve reglas de EP2 §2.3 antes de entregar. También lo corre el pipeline.
#
#   herramientas/verificar-defensa.sh
#   herramientas/verificar-defensa.sh --pull    # además intenta descargar las imágenes sin sesión
#                                               # (como el computador de la defensa): detecta las privadas
set -uo pipefail
cd "$(dirname "$0")/.."
fallas=0
mal() { echo "  FALLA: $*"; fallas=$((fallas + 1)); }
bien() { echo "  ok: $*"; }

CONFIG="$(TAG=ep2 docker compose -f compose.yaml config --format json 2>&1)" || { echo "$CONFIG"; exit 1; }
revisar() { python3 -c "import json,sys; c=json.loads(sys.stdin.read()); $1" <<< "$CONFIG"; }

echo "Regla 1 · sin build:, solo imágenes de GHCR"
grep -qE '^\s+build:' compose.yaml && mal "compose.yaml tiene build:" || bien "sin build:"
if grep -q "ghcr.io/tu-usuario/tu-repo-" compose.yaml; then
  if [[ -f .plantilla ]]; then echo "  aviso: es la plantilla sin iniciar (herramientas/iniciar.sh <caso> lo arregla)"
  else mal "quedó «tu-usuario/tu-repo»: corre herramientas/iniciar.sh <caso>"; fi
else bien "imágenes con tu repositorio"; fi

echo "Regla 3 · sin bind mounts"
revisar 'm=[(n,v["source"]) for n,s in c["services"].items() for v in s.get("volumes",[]) if v["type"]=="bind"]; print("\n".join(f"{n}:{s}" for n,s in m))' | grep -q . \
  && mal "hay bind mounts" || bien "solo volúmenes con nombre"

echo "Regla 4 · solo el gateway publica puerto"
PUBLICAN="$(revisar 'print(" ".join(n for n,s in c["services"].items() if s.get("ports")))')"
[[ "$PUBLICAN" == "gateway" ]] && bien "solo gateway" || mal "publican puerto: $PUBLICAN"

echo "Regla 5 y 6 · healthcheck, cpus y mem_limit en cada servicio propio"
for s in $(revisar 'print(" ".join(n for n,s in c["services"].items() if "ghcr.io" in s.get("image","")))'); do
  r="$(revisar "s=c['services']['$s']; print(('healthcheck' in s) or '$s'=='carga', 'cpus' in s, 'mem_limit' in s)")"
  [[ "$r" == "True True True" ]] && bien "$s" || mal "$s (healthcheck cpus mem_limit = $r)"
done

echo "Regla 8 · nada secreto en el repositorio"
git ls-files 2>/dev/null | grep -E '(^|/)\.env$|\.pem$' && mal "hay .env o .pem versionados" || bien "sin .env ni .pem en git"
git grep -nE 'nvapi-[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}' -- . ':!*.md' 2>/dev/null && mal "parece haber una clave en el código" || bien "sin claves a la vista"

if [[ "${1:-}" == "--pull" ]]; then
  echo "Regla 2 · imágenes públicas y linux/amd64 (sin sesión de Docker)"
  TMP="$(mktemp -d)"
  for img in $(revisar 'print(" ".join(s["image"] for s in c["services"].values() if "ghcr.io" in s.get("image","")))'); do
    if DOCKER_CONFIG="$TMP" docker manifest inspect "$img" > "$TMP/m.json" 2>/dev/null; then
      grep -q '"architecture": "amd64"' "$TMP/m.json" && bien "$img" || mal "$img no tiene linux/amd64"
    else
      mal "$img no se puede descargar sin sesión (¿privada o sin el tag ep2?)"
    fi
  done
  rm -rf "$TMP"
fi

echo
(( fallas == 0 )) && echo "Todo en orden." || { echo "$fallas falla(s)."; exit 1; }
