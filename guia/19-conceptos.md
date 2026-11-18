# 19 · Los conceptos, dichos con precisión

**Para qué:** el IE12 de EP3 (4%) y el IE9 de EP2 (3%) se evalúan **durante toda la presentación**, y una
palabra mal usada también delata en IE6, IE8 e IE13. Cada concepto tiene: qué es en dos líneas, **dónde
está en tu sistema** (para mostrarlo, no recitarlo) y el error típico que baja la nota.

[← 18 · Respuestas de 7](18-respuestas-de-7.md) · [Índice](../README.md)

> Regla para usar esta tabla: **no la memorices**. Para cada concepto, abre lo que dice la columna
> «dónde» en tu propio sistema y explícaselo a un compañero. Si no puedes mostrarlo, todavía no lo sabes.

---

## Los siete que nombra el IE12 de EP3

| Concepto | Qué es | Dónde está en tu sistema | Error típico |
|---|---|---|---|
| **Endpoint** | La URL administrada por SageMaker que recibe filas y devuelve predicciones del modelo desplegado. Tiene una **configuración** (tipo, memoria, concurrencia) y una **versión** de modelo | `ep3-<caso>` en *SageMaker → Endpoints*; `ENDPOINT` en el `.env`; `MotorSageMaker` en `servicios/ia/app/motores.py` | Llamar «endpoint» a cualquier ruta de la API. Las rutas de tu API son **rutas** (`POST /api/predict`); el endpoint es el de SageMaker |
| **Cold start** | La espera extra de la primera invocación cuando SageMaker serverless tiene que **arrancar un contenedor** porque no había ninguno caliente (tras ~10 min sin uso) | `ModelSetupTime` en CloudWatch (medido: 6,2 s); la 1.ª vs 2.ª invocación de `4_probar.py` | Decir que es «el modelo cargándose en memoria cada vez» o que «la primera siempre es lenta». Es **por contenedor**, y solo cuando no hay uno caliente |
| **Concurrencia** | Cuántas invocaciones **simultáneas** acepta el endpoint serverless. Las que sobran se rechazan con `ThrottlingException` | `MaxConcurrency` en la configuración del endpoint; `--concurrencia` de `3_endpoint.py` | Confundirla con «solicitudes por segundo». Con 60 ms por invocación, concurrencia 2 da hasta ~33 req/s **si llegan parejas**; el problema son las ráfagas |
| **Latencia de percentil** | p95 = el 95% de las solicitudes tardó eso o menos. El promedio esconde la cola lenta; los RNF se escriben en percentiles | `carga_stats.csv` (Locust); `latencia_ms` en los logs; `ModelLatency` p95 en CloudWatch | Decir «el p95 es el promedio del 95%». Y no decir **dónde** se midió: en el cliente (con la red) o en el servicio |
| **Rate limiting** | Un límite de solicitudes por clave y por minuto; al pasarlo, `429 Too Many Requests`. Protege el sistema y el costo | `LIMITE_POR_MINUTO` en el `.env`; el dominio responde 429; prueba obligatoria 4 | Confundirlo con el 429 **de NVIDIA**: ese es el límite del proveedor sobre ti, y se maneja con reintentos en el worker |
| **Modo degradado** | El sistema sigue cumpliendo su función principal cuando una pieza no esencial falla, y **lo dice**: la predicción sale, el texto del LLM no | `estado_llm: degradado` + `motivo_llm`; `/api/health` → `llm: degradado`; `servicios/worker/app/worker.py` | Decir «degradado» cuando el sistema está caído. Si la predicción no sale, no es degradado: es una falla |
| **Interpretabilidad** | Que la persona que recibe la decisión entienda **por qué** se decidió, a partir del propio modelo, no de un texto inventado después | Fraude: `razones` con su aporte; recomendación: `motivo` de cada producto; chatbot: intención, probabilidad y alternativas | Decir que el LLM «da la interpretabilidad». El LLM **redacta** las razones que ya calculó el modelo; si el LLM decide o inventa el porqué, es un error de IE2 |

## Los de la arquitectura (EP2 y EP3)

| Concepto | Qué es | Dónde está | Error típico |
|---|---|---|---|
| **Réplica** | Otra copia idéntica del mismo servicio, para repartir carga y sobrevivir a la caída de una | `ia-1` e `ia-2` (`deploy.replicas: 2` en `compose.yaml`) | Llamar réplica a un servicio distinto |
| **Balanceo** | Repartir solicitudes entre réplicas | `upstream` en `servicios/gateway/nginx.conf` (round robin con `resolve`) | Decir que balancea el dominio |
| **Failover** | Si una réplica no responde, la solicitud se reintenta en otra sin que el usuario lo note | `proxy_next_upstream` y `proxy_connect_timeout 150ms` en nginx | Decir «Docker la reinicia»: reiniciar es `restart`, no failover |
| **Health check** | Una comprobación periódica de que un servicio responde; Docker no manda tráfico ni arranca dependientes hasta que pasa | `healthcheck:` en `compose.yaml`; `GET /health` de cada servicio | Confundirlo con `/api/health` del dominio, que **resume** el estado de todo |
| **Contrato** | La forma exacta de la entrada y la salida de una ruta (campos, tipos, códigos) | `/docs` (OpenAPI); `Entrada` en `servicios/dominio/app/casos/<caso>.py` | Decir «manda un JSON». ¿Qué campos? ¿Qué pasa si falta uno? → 422 |
| **Imagen / tag** | La imagen es el paquete inmutable del servicio; el tag es su nombre (`sha-abc1234`, `latest`, `ep3`) | GHCR; `TAG` en el `.env`; `docker image inspect` | Decir que `latest` identifica una versión. Lo que la identifica es el `sha-` |
| **Gate de calidad** | El paso del pipeline que **detiene** la publicación si el modelo nuevo no supera el mínimo | `modelo/config.json` + `modelo/entrenar.py` (sale con código 1) | Decir que el gate «avisa». Si no detiene, no es gate |
| **Línea base** | Lo que haría una regla trivial sin modelo; el modelo tiene que superarla para valer algo | `METRICAS.md`: «nunca es fraude», «más vendidos», «siempre facturación» | Comparar el modelo contra nada, o contra el accuracy |
| **Zona de disponibilidad (AZ)** | Un centro de datos independiente dentro de una región; multi-AZ = sobrevivir a la caída de uno | Tu despliegue **objetivo** (EP2 §8.2); la EC2 del Learner Lab está en **una sola** AZ | Afirmar que la EC2 actual es de alta disponibilidad. No lo es: decláralo como deuda |
| **RTO / RPO** | RTO: cuánto tiempo puedes estar abajo. RPO: cuántos datos puedes perder (medido en tiempo) | Capítulo 8.2 de tu documento de EP2 | Darlos sin decir cómo se cumplen (respaldo cada X, réplica en otra AZ) |

## Los de EP3

| Concepto | Qué es | Dónde está | Error típico |
|---|---|---|---|
| **Serverless (inference)** | SageMaker pone y quita contenedores según el uso; pagas por GB·segundo invocado, no por hora | Configuración `ServerlessConfig` (memoria, concurrencia) | Decir que «no hay servidor». Hay; no lo administras ni lo pagas encendido |
| **Endpoint de tiempo real** | Una instancia (`ml.t2.medium`) siempre encendida con el modelo; sin cold start, cobra cada hora | `3_endpoint.py --tiempo-real` (plan B) | Dejarlo encendido toda la semana: se acaba el crédito |
| **Throttling** | El rechazo de invocaciones que pasan la concurrencia permitida | `ThrottlingException` en el log de la IA | Confundirlo con un error del modelo |
| **Rol de la instancia / sin claves** | La EC2 obtiene credenciales temporales del rol `LabRole` por el servicio de metadatos; ningún archivo guarda access keys | `LabInstanceProfile`; hop limit 2; capítulo 10.6 | Poner `AWS_ACCESS_KEY_ID` en el `.env`: es un error de IE7 |
| **Cola (mensajería)** | Un buzón donde el dominio deja un pedido y el worker lo toma cuando puede. Desacopla tiempos y fallas | RabbitMQ, cola `llm`; `servicios/dominio/app/cola.py` | Decir que la cola «hace más rápido» el LLM. No lo acelera: lo saca del camino de la respuesta |
| **Asíncrono** | La respuesta no espera el resultado; este llega después y se consulta | `estado_llm: pendiente` → `listo`; `GET /api/predicciones/{id}` | Llamar asíncrono a un `await` que igual espera la respuesta |
| **Reintento con espera creciente (backoff)** | Ante un 429 o 5xx, esperar 1, 2, 4… s (más un azar, *jitter*) antes de reintentar | `servicios/worker/app/llm.py`: `INTENTOS`, `ESPERA_BASE * 2 ** (intento - 1)` | Reintentar ante un 401: una clave mala no se arregla esperando |
| **Cola de fallidos (DLQ)** | Donde van los mensajes que no se pudieron procesar, para no perderlos ni reintentarlos para siempre | `llm.fallidos` (`x-dead-letter-routing-key`) | No saber dónde quedó el mensaje que falló (pregunta del IE8) |
| **Anonimización** | Reemplazar datos personales por marcadores **antes** de que el texto salga del sistema | `comun/anonimizar.py`; prueba obligatoria 5 | Anonimizar en el worker (ya pasó por la cola) o creer que detecta nombres: no lo hace |
| **HTTPS / TLS** | El tráfico va cifrado y el navegador verifica que el servidor es quien dice; el certificado lo emite Let's Encrypt | Caddy (`Caddyfile`), `DOMINIO` con sslip.io | Decir que HTTPS «protege la API». Cifra el transporte; la autenticación es la clave de API |
| **Despliegue continuo (CD)** | Cada cambio aprobado en `main` llega solo al servidor, sin pasos a mano | Job `desplegar` de `.github/workflows/ci.yml` | Confundirlo con CI (que prueba y construye) |
| **Rollback** | Volver a la versión anterior en segundos | `TAG=sha-<anterior>` y `docker compose up -d` | Decir «hacemos revert y esperamos el pipeline»: funciona, pero no es en segundos |

## Las métricas del modelo

| Concepto | Qué es | Cuándo importa |
|---|---|---|
| **Precision** | De lo que el modelo marcó positivo, cuánto lo era | Cuando el **falso positivo** cuesta (fraude: bloquear a un cliente bueno) |
| **Recall** | De lo que era positivo, cuánto encontró | Cuando el **falso negativo** cuesta (fraude que pasa) |
| **F1** | Media armónica de las dos; un solo número cuando ambas importan | Comparar modelos en un umbral |
| **PR-AUC** | Calidad del ranking en todos los umbrales, sensible a la clase rara | Clases muy desbalanceadas (fraude, recomendación) |
| **ROC-AUC** | Probabilidad de que un positivo quede arriba de un negativo | Ranking cuando el desbalance no es extremo |
| **Accuracy** | Aciertos sobre el total | Casi nunca con desbalance: «nunca es fraude» da 99,988% |
| **Umbral** | Desde qué probabilidad se decide «positivo»; mueve precision contra recall | Se lee de configuración (fraude RF3), no del código |
| **Fuga de información** | Una variable que solo se conoce **después** del hecho que se quiere predecir | Fraude: `motivo_bloqueo`; recomendación: el horizonte de la etiqueta |
| **Matriz de confusión** | VP, FP, FN, VN en una tabla | Calcular el costo de los errores con el negocio |

## Cómo se ve una respuesta precisa

> **Impreciso:** «el serverless es más lento al principio porque se demora en partir».
>
> **Preciso:** «la primera invocación tardó 6,2 s y las siguientes entre 45 y 130 ms. La diferencia es el cold start:
> SageMaker no tenía un contenedor caliente y tuvo que arrancarlo y cargar el modelo; lo mide la métrica
> `ModelSetupTime`. Como nuestro dominio espera 300 ms, esa primera predicción salió por la política de
> reserva. Lo aceptamos porque pasa una vez cada 10 minutos sin tráfico, y en producción, con 200.000
> transacciones diarias, el contenedor no se enfría».

La segunda tiene **número, causa, métrica que lo prueba, consecuencia en el sistema y decisión**. Esa
estructura sirve para cualquier pregunta.
