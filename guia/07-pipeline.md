# 7 · Pipeline y GHCR

**Lo que vas a lograr:** el workflow de GitHub Actions en verde, que trata los datos, entrena con gate,
corre todas las pruebas, revisa las reglas del compose y publica las seis imágenes en GHCR como
`linux/amd64`, con el tag del commit, `latest`, y `ep2`/`ep3` cuando corresponde.

[← 6 · Compose](06-compose-defensa.md) · [Índice](../README.md) · [8 · Documento EP2 →](08-documento-ep2.md)

**Ya lo tengo si…** el último workflow de `main` está en verde, tus paquetes en GHCR son públicos y
`docker image inspect` de una imagen te dice de qué commit salió.

---

## 7.1 La cadena

```mermaid
flowchart LR
    T(["pull request<br/>push a main<br/>tag ep2 / ep3"]) --> A
    subgraph A["datos-y-modelo"]
        A1["preparar.py"] --> A2["entrenar.py<br/>GATE"]
    end
    A --> B["pruebas<br/>datos · ia · dominio (con PostgreSQL) · worker"]
    T --> C["reglas-compose<br/>verificar-defensa.sh"]
    B & C --> D["imagenes ×6 en paralelo<br/>gateway · front · dominio · ia · carga · worker"]
    D --> E{"¿push a main o tag ep3<br/>y DESPLEGAR = si?"}
    E -- sí --> F["desplegar<br/>SSH a la EC2 (EP3)"]
    E -- no --> G(["fin"])
```

| Evento | `datos-y-modelo` | `pruebas` | `imagenes` | `desplegar` |
|---|---|---|---|---|
| PR hacia `dev` o `main` | ✔ | ✔ | construye, **no publica** | — |
| Push a `main` (merge de `dev`) | ✔ | ✔ | publica `sha-xxxxxxx` y `latest` | si está activado |
| Tag `ep2` | ✔ | ✔ | publica `ep2` (+ `sha-…`) | — |
| Tag `ep3` | ✔ | ✔ | publica `ep3` (+ `sha-…`) | si está activado |

**Si cualquier paso falla, no se publica ninguna imagen.** Eso es lo que «habría detenido una imagen
rota» (IE10).

## 7.2 La primera ejecución

Después del primer push, en tu repositorio: **Actions**. Si dice que los workflows están desactivados
(pasa en repos creados desde plantilla), aprieta **I understand my workflows, go ahead and enable them**.
Para lanzarlo a mano: **Actions → ci → Run workflow**.

**Lo visible:** los cinco jobs; `desplegar` aparece como *skipped* (se activa en EP3). En el resumen de la
ejecución aparecen `METRICAS.md` y `REPORTE.md`: es la evidencia de que **el pipeline** ejecutó el
tratamiento y el gate (EP2 §2.2).

## 7.3 Lo que hace cada paso de `imagenes`

`.github/workflows/ci.yml`, job `imagenes`:

| Paso | Qué hace | Por qué |
|---|---|---|
| `download-artifact` | Trae `datos/tratados/` y `modelo/artefactos/` del primer job | La imagen de IA lleva el modelo adentro y la de carga los CSV: no se construyen sin ellos |
| `IMAGEN=ghcr.io/${GITHUB_REPOSITORY,,}-<servicio>` | Nombre en **minúsculas** | Docker rechaza mayúsculas: `repository name must be lowercase` |
| `docker/metadata-action` | Calcula los tags y agrega la etiqueta `org.opencontainers.image.revision` = commit | Con eso, `docker image inspect` dice qué commit corre (IE10) |
| `build-push-action` con `platforms: linux/amd64` | Construye para la arquitectura del PC de la defensa y de la EC2 | Una imagen de Mac M1/M2/M3 es `arm64`: `exec format error` |
| `push: ${{ github.event_name != 'pull_request' }}` | En un PR solo construye | Un PR no tiene que publicar nada |
| `cache-from/to: type=gha` | Reutiliza capas entre ejecuciones | De minutos a segundos |

## 7.4 Paquetes públicos

**Si el repositorio es público, los paquetes salen públicos solos:** en la prueba de esta guía
(repositorio público, 17-11-2026), las seis imágenes publicadas por el pipeline se pudieron descargar sin
sesión desde la primera ejecución. Compruébalo igual:

```bash
herramientas/verificar-defensa.sh --pull     # necesita el tag ep2 publicado; antes, prueba con TAG=latest:
T=$(mktemp -d); DOCKER_CONFIG=$T docker manifest inspect ghcr.io/<tu-usuario>/<tu-repo>-ia:latest >/dev/null && echo pública
```

Si alguno sale privado (repositorio privado, o paquetes creados antes de hacerlo público): en tu perfil →
**Packages** → cada paquete → **Package settings** → **Danger Zone → Change visibility → Public**.

## 7.5 Qué commit está corriendo

```bash
docker image inspect ghcr.io/<tu-usuario>/<tu-repo>-ia:ep2 \
  --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
```

**Lo visible:** el hash completo del commit. En GitHub: `https://github.com/<tu-usuario>/<tu-repo>/commit/<hash>`
muestra el commit y el PR que lo trajo (*«… merged pull request #12 from …»*); en **Actions**, filtrando
por ese commit, el workflow que publicó la imagen.

```mermaid
flowchart LR
    I["docker image inspect<br/>revision = 9f3c2e1…"] --> C["commit 9f3c2e1<br/>en GitHub"]
    C --> P["PR #12 dev → main"]
    P --> F["PR #9 feat/datos-… → dev<br/>autor: integrante"]
    C --> W["workflow ci<br/>que publicó :ep2"]
```

## 7.6 Las pruebas del pipeline

| Job / paso | Archivo | Qué prueba |
|---|---|---|
| Datos tratados | `tests/test_datos.py` | Sin nulos ni duplicados en claves, columnas del modelo, prueba con todas las clases, determinismo |
| Microservicio de IA | `servicios/ia/tests/` | `/predict` con entrada conocida, 422, razones ordenadas, lectura de la respuesta de SageMaker (binaria y multiclase) |
| Dominio | `servicios/dominio/tests/` | Las **seis pruebas obligatorias de EP3** (200 con versión, 422, 401, 429, cola caída → degradado), reserva, 404, y las reglas de tu caso, contra **PostgreSQL real** |
| Worker | `servicios/worker/tests/` | 429 sostenido → degradado, reintentos crecientes, 401 sin reintentar, idempotencia |

Para correrlas en tu computador (el dominio necesita un PostgreSQL):

```bash
docker run -d --name pg-pruebas -p 5433:5432 -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app \
  -e POSTGRES_DB=proyecto postgres:16-alpine
pip install -r requirements-dev.txt
pytest tests
PYTHONPATH=servicios/ia:. pytest servicios/ia/tests
DATABASE_URL=postgresql://app:app@localhost:5433/proyecto PYTHONPATH=servicios/dominio:. pytest servicios/dominio/tests
PYTHONPATH=servicios/worker pytest servicios/worker/tests
```

## 7.7 Si el pipeline está en rojo

| Job en rojo | Lo más probable | Dónde mirar |
|---|---|---|
| `datos-y-modelo` | Un cambio en la limpieza rompió algo, o **el gate** detuvo un modelo peor | El log de *Entrenamiento y gate*: `GATE: ... NO se publica` |
| `pruebas` | Una regla de tu caso cambió y la prueba la detecta (¡bien!), o una tabla quedó con duplicados | La primera línea `FAILED` y su `assert` |
| `reglas-compose` | Quedó `tu-usuario/tu-repo`, alguien agregó `ports:` o `build:` al compose | La línea `FALLA:` |
| `imagenes` | `denied` al publicar: el repositorio no tiene permiso de escribir paquetes | **Settings → Actions → General → Workflow permissions → Read and write** |

## Al informe

**7.4 (EP2):** figura del pipeline — usa 7.1 y agrega las ramas del capítulo 1. **Anexo C:** link de la
última ejecución verde de `main` y de cada paquete.

## En la defensa

**IE10 (EP2):** *«¿Qué commit está corriendo ahora en este computador? Muéstrame el PR que lo llevó a
`main` y el workflow que publicó esa imagen. ¿Qué habría detenido una imagen rota?»* — 7.5 y 7.1.

[Siguiente: 8 · El documento de EP2 →](08-documento-ep2.md)
