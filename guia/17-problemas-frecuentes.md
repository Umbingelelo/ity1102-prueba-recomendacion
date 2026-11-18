# Problemas frecuentes

Síntoma → causa probable → qué hacer. Ordenados por dónde aparecen. Muchos salieron de las entregas
reales de EP2: son los errores que más nota costaron.

[← 16 · Informe y presentación](16-informe-presentacion-ep3.md) · [Índice](../README.md) · [18 · Para un 7 →](18-respuestas-de-7.md)

---

## En tu computador

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop no está corriendo | Ábrelo y espera a que el ícono deje de moverse |
| `herramientas/...sh: Permission denied` o no se ejecuta en Windows | Estás en PowerShell, o Git quitó el permiso | Usa Git Bash; si persiste: `bash herramientas/levantar-local.sh` |
| `CASO='' no es válido` | El archivo `CASO` está vacío | `herramientas/iniciar.sh <caso>` |
| `Falta datos/tratados` / `Falta modelo/artefactos` | No corriste el tratamiento ni el entrenamiento | `herramientas/levantar-local.sh` (sin `--sin-datos`) |
| `GATE: ... NO se publica` | El modelo no llega al mínimo de `modelo/config.json` | Revisa el último cambio en la limpieza o las variables; si el mínimo estaba mal fijado, justifícalo (DESAFÍO M1) |
| `Bind for 0.0.0.0:8080 failed: port is already allocated` | Otro programa usa el 8080 | `PUERTO_GATEWAY=8081 herramientas/levantar-local.sh` |
| `dependency failed to start: container ... is unhealthy` | Un servicio no pasó su health check | `docker compose -p proyecto logs <servicio> --tail 30` |
| La IA no arranca: `Las columnas del modelo no coinciden` | Cambiaste `comun/caracteristicas` y no reentrenaste | `python modelo/entrenar.py` y reconstruir |
| `curl` en PowerShell da un error raro de parámetros | `curl` en PowerShell es otro comando | Usa `curl.exe` |

## En la defensa de EP2

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `pull` → `denied` | Paquetes privados en GHCR | Package settings → Change visibility → Public (los seis) |
| `pull` → `manifest unknown` | No existe el tag `ep2` (no lo pusiste o el pipeline falló) | `git tag ep2 && git push origin ep2` y espera el workflow |
| `exec format error` | Imagen `arm64` construida en un Mac y subida a mano | Solo publica el pipeline (`linux/amd64`) |
| El compose pide un `.env` o un tercer comando | Una variable sin valor por defecto | Toda variable con `${VAR:-valor}`; regla 9 |
| `ghcr.io/tu-usuario/...` o `REEMPLAZAR_USUARIO` en el compose del tag | No corriste `iniciar.sh` antes del tag | `herramientas/verificar-defensa.sh` lo detecta |
| La carga deja la base vacía | Los CSV tratados no están en la imagen de carga | La plantilla los copia (`COPY datos/tratados/tablas/`); el pipeline los genera antes del build |
| El balanceo manda todo a una réplica | Nombres del upstream distintos a los del compose | Con `deploy.replicas` y `server ia:8000 resolve` no pasa |
| Trabajo en `dev` que no está en las imágenes | `dev` no llegó a `main` antes del tag | PR `dev → main`, después el tag |

## En AWS (EP3)

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La instancia nueva pasa a `shutting-down` segundos después de lanzarla (motivo `User initiated`) | El Learner Lab no permite más de 9 instancias por región, **contando las detenidas** | Termina (no detengas) una instancia que no uses y vuelve a lanzar. Comprobado el 17-11-2026 |
| `ssh: Connection timed out` | Falta la regla del 22, la EC2 está detenida, o la IP cambió | Security group; estado de la instancia; IP elástica |
| `permission denied ... docker.sock` | El grupo `docker` aún no se aplica | `exit` y vuelve a entrar |
| `/api/health` → `ia ... error: NoCredentialsError` | Hop limit en 1 o EC2 sin `LabInstanceProfile` | Capítulo 10.3 y `docker compose restart ia` |
| `/api/health` → `ia ... error: ClientError` o `ValidationException` | El endpoint `ep3-<caso>` no existe o `ENDPOINT` está mal | `python3 sagemaker/3_endpoint.py` en CloudShell; revisa el `.env` |
| `ModelError` / `ValueError: SageMaker devolvió N valores` | El modelo de SageMaker se entrenó con otras columnas | Vuelve a correr `preparar`, `entrenar` y `sagemaker/1_subir.py` a `3_endpoint.py` con el código actual |
| Todas las decisiones salen con `origen: reserva` | El endpoint tarda más que `TIMEOUT_MODELO_MS` (cold start, o p95 alto) | Mide (`latencia_ms`, `ModelLatency`); decide entre subir el timeout, calentar el endpoint o aceptarlo, y escríbelo |
| Las primeras 1–2 predicciones del día salen por reserva y después no | Cold start del serverless: medido `ModelSetupTime` ≈ 6 s | Esperado; es tu política de RNF3 funcionando. Haz 2 predicciones antes de la demo y explícalo |
| En el log de la IA: `ThrottlingException`; muchas reservas solo bajo carga | La concurrencia máxima del endpoint (2) es menor que las invocaciones simultáneas | `python3 sagemaker/3_endpoint.py --concurrencia 10` (medido: reservas de ~23% a 1%) |
| `3_endpoint.py` termina en `Failed` | El Learner Lab rechazó el serverless | `--tiempo-real` (cobra por hora: bórralo cada día) |
| `ExpiredToken` en CloudShell | La sesión del laboratorio venció (4 h) | Start Lab y reabrir CloudShell; los scripts retoman desde `estado.json` |
| `pip install` en CloudShell sin espacio | CloudShell tiene 1 GB | Ruta B del capítulo 11.2 (artefacto del pipeline) |
| `required variable NVIDIA_MODEL is missing` | Falta en el `.env` | `nano .env` |
| Caddy no obtiene el certificado | El 80 cerrado, o `DOMINIO` no es tu IP elástica con guiones | Security group; `.env`; `docker compose logs caddy` |
| `estado_llm` se queda en `pendiente` | El worker no está corriendo | `docker compose ps worker`; `docker compose logs worker` |
| `motivo_llm: HTTP 401` / `HTTP 404` / `HTTP 410` | Clave mal copiada / nombre del modelo mal escrito / modelo retirado por NVIDIA | Revisa el `.env`, prueba el modelo con el `curl` de 12.2 y `docker compose up -d worker` |
| `motivo_llm` con `Timeout` o texto vacío | Modelo lento (> 20 s) o de razonamiento (`content: null`) | Cambia a un modelo rápido (12.2: `nvidia/nemotron-3.5-bolt-e4b` respondió en 0,6 s) |
| Después de la prueba de carga, las predicciones nuevas quedan `pendiente` minutos | La carga encoló cientos de textos (medido: 871) y el LLM despacha ~1,6/s | `docker compose exec -T rabbitmq rabbitmqctl purge_queue llm` |
| `cloudwatch.py` puso la CPU de otra EC2 en el dashboard | Hay varias instancias corriendo en la cuenta | `python3 herramientas/cloudwatch.py --instancia <tu id>` |
| El front muestra columnas viejas o JSON crudo después de desplegar | El navegador guardó el `app.js` anterior | Recarga forzada (Ctrl+Shift+R / Cmd+Shift+R) |
| `docker compose up` falla con `awslogs` / `AccessDenied` | El rol no deja escribir en CloudWatch | Quita `compose.cloudwatch.yaml` de `COMPOSE_FILE` y avisa al docente |
| La base no acepta la contraseña nueva | El volumen se creó con la contraseña anterior | `docker compose down -v` y `up -d` (la carga la vuelve a llenar) |
| `desplegar` en rojo: `ssh: handshake failed` o `Permission denied (publickey)` | `EC2_SSH_KEY` incompleta o `EC2_HOST` con otra IP | Pega el `.pem` entero; usa la IP elástica |
| `desplegar` en rojo: `No such file or directory` | El repo no está en `~/<nombre-del-repo>` en la EC2, o creaste `DESPLEGAR` antes de clonarlo | `git clone` en el home con ese nombre exacto |
| `desplegar` en rojo: `denied` al hacer `pull` | Paquetes privados y sin `GHCR_PAT` (o sin `read:packages`) | Hazlos públicos (capítulo 7.4) o crea `GHCR_USUARIO` y `GHCR_PAT` |
| Avisos amarillos «Node.js 20 is deprecated» en Actions | Las acciones `@v4` de GitHub usan Node 20; GitHub las corre con Node 24 | Son avisos, no fallas: el pipeline queda en verde (comprobado el 17-11-2026) |
| Me quedé sin crédito | EC2 o endpoint de tiempo real encendidos | Contacta al docente de inmediato; en adelante, Stop al terminar |
