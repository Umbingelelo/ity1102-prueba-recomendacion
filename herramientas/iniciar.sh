#!/usr/bin/env bash
# Deja la plantilla lista para TU equipo. Se corre UNA vez, recién creado tu repositorio:
#
#   herramientas/iniciar.sh fraude          # o recomendacion, o chatbot
#
# Hace tres cosas:
#   1. Escribe tu caso en el archivo CASO.
#   2. Cambia «tu-usuario/tu-repo» por tu repositorio de GitHub en compose.yaml y compose.nube.yaml,
#      para que las imágenes sean ghcr.io/<tu-usuario>/<tu-repo>-<servicio>.
#   3. Borra los datos crudos de los otros dos casos (no los necesitas y pesan).
set -euo pipefail
cd "$(dirname "$0")/.."

CASO="${1:-}"
case "$CASO" in recomendacion|chatbot|fraude) ;; *) echo "Uso: herramientas/iniciar.sh recomendacion|chatbot|fraude"; exit 1 ;; esac

ORIGEN="$(git remote get-url origin 2>/dev/null || true)"
REPO="$(echo "$ORIGEN" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##' | tr '[:upper:]' '[:lower:]')"
if [[ -z "$REPO" || "$REPO" != */* ]]; then
  echo "No encontré el remoto «origin» de GitHub. Clona tu repositorio con git clone y corre esto adentro."; exit 1
fi

echo "$CASO" > CASO
rm -f .plantilla
sed -i.bak "s#ghcr.io/tu-usuario/tu-repo-#ghcr.io/$REPO-#g" compose.yaml compose.nube.yaml
rm -f compose.yaml.bak compose.nube.yaml.bak
for otro in recomendacion chatbot fraude; do
  if [[ "$otro" != "$CASO" ]]; then rm -rf "datos/crudos/$otro"; fi
done

echo "Caso: $CASO"
echo "Imágenes: ghcr.io/$REPO-<servicio>"
grep -n "image: ghcr.io" compose.yaml | head -3
echo
echo "Siguiente: git add -A && git commit -m 'Inicia el proyecto con el caso $CASO' && git push"
