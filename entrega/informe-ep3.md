<!--
Plantilla del informe de EP3 (EP3 §4.2). Máximo 10 páginas del apartado 1 al 5; portada, índice y anexos no
cuentan. Cada ‹…› se reemplaza con un dato de TU sistema; al lado dice de dónde sacarlo. Borra estos
comentarios y las notas «De dónde» antes de exportar a PDF (por ejemplo, con pandoc o desde VS Code).
Nombre del archivo: EP3_Equipo<N>_<Apellidos>.pdf
-->

# Informe técnico EP3 · ‹nombre de la empresa del caso› · Equipo ‹N›

**ITY1102 Arquitectura de Sistemas IA · ‹integrantes›** · ‹fecha›

---

## 1. Modelo y endpoint (IE1)

**Qué predice.** ‹una frase: la salida del modelo y la decisión que alimenta (ficha del caso, sección 1)›.

| | |
|---|---|
| Tipo de modelo | XGBoost ‹`binary:logistic` / `multi:softprob` con N clases› (algoritmo integrado de SageMaker) |
| Datos de entrenamiento | ‹filas de entrenamiento / validación / prueba› salidas de `datos/preparar.py` (`sagemaker/1_subir.py`) |
| Cómo se separó la prueba | ‹estratificado / por usuario / …, semilla 1102, antes de entrenar› |
| Hiperparámetros | ‹de `sagemaker/estado.json` → `hiperparametros`› |
| Training Job | ‹nombre›, ‹tiempo facturado› s, métrica de validación ‹`validation:…` = …› |
| Endpoint | `ep3-‹caso›`, serverless, ‹memoria› MB, concurrencia ‹N›, versión ‹`ep3-‹caso›-AAAAMMDD-HHMMSS`› |
| Cómo lo consume el sistema | El microservicio de IA (`MOTOR=sagemaker`) con el rol `LabInstanceProfile` de la EC2, sin access keys |

![Endpoint InService](‹captura›)

![Una invocación: 4_probar.py](‹captura›)

> De dónde: `sagemaker/estado.json`, la salida de `2_entrenar.py` y `4_probar.py` (capítulo 11).

## 2. Consumo e interpretabilidad (IE2)

**La decisión.** ‹quién recibe la salida y qué hace con ella; el requerimiento del caso que lo pide›.

**Lo que ve el usuario.** ‹descripción + captura del front: decisión, probabilidad, razones / productos
con motivo / intención y artículos›. ‹Por qué con eso entiende la decisión: RF2 / RN3 / RF6›.

![El front con una predicción](‹captura›)

**Qué agrega el LLM.** ‹su rol según EP3 §3 para tu caso›. **No decide**: redacta a partir de lo que el
modelo y las reglas ya decidieron. Llega por la cola, después de la respuesta.

**Sin el LLM.** La predicción responde igual; el usuario ve «degradado» con el motivo. ‹captura›.

## 3. Plataforma, infraestructura y costos (IE4, IE5)

**Despliegue en AWS.** ‹diagrama de despliegue: EC2 con los contenedores, IP elástica, SageMaker, S3,
RabbitMQ y worker, NVIDIA, CloudWatch; puede partir del diagrama del capítulo 13.1›.

| Pieza | Configuración | Por qué |
|---|---|---|
| EC2 | `t3.medium`, Ubuntu 24.04, 20 GiB gp3, IP elástica ‹IP›, `LabInstanceProfile` | ‹consumo medido: RAM ‹x› de 3,8 GB con todo arriba (`evidencias.sh`)› |
| Endpoint | serverless ‹memoria› MB, concurrencia ‹N› | ‹medición que lo justifica: throttling / reservas con otra concurrencia› |
| Bucket S3 | `ity1102-ep3-‹cuenta›`: datos tratados y modelo | Entrada del Training Job |
| Cola y worker | RabbitMQ + worker, un mensaje a la vez | El LLM fuera del camino de la respuesta |

**Cold start, medido dos veces.**

| Medición | Recién invocado | Después de 10 min sin uso |
|---|---|---|
| Latencia de la invocación | ‹ms› | ‹ms› |
| `ModelSetupTime` (CloudWatch) | — | ‹s› |
| Efecto en el sistema | ‹origen modelo› | ‹origen reserva, por `TIMEOUT_MODELO_MS` = ‹ms›› |

**Costo mensual al volumen del caso** (`herramientas/costos.py`, precios públicos de us-east-1 al
‹fecha›):

| Componente | Volumen del caso | Cálculo | USD/mes |
|---|---|---|---|
| EC2 `t3.medium` | 730 h | 730 × 0,0416 | ‹› |
| IPv4 pública | 730 h | 730 × 0,005 | ‹› |
| Disco gp3 20 GB | | 20 × 0,08 | ‹› |
| SageMaker serverless | ‹invocaciones/mes› | inv × ‹ms medido› × ‹GB› × 0,00002 | ‹› |
| Reentrenamiento | ‹veces/mes› | | ‹› |
| S3 | ‹GB› | | ‹› |
| CloudWatch Logs | ‹GB/mes› | | ‹› |
| LLM en un proveedor pagado | ‹textos/mes› | ‹tokens› × ‹precio› | ‹› |
| **Total** | | | **‹›** frente a un presupuesto de ‹› |

**Alternativa comparada:** ‹tiempo real `ml.t2.medium` USD 40,88/mes / modelo en el contenedor / Bedrock no
aplica porque…› y el punto de equilibrio.

**Evidencias de CloudWatch:** `Invocations` y `ModelLatency` del endpoint, y los logs del microservicio
encontrados por `id`.

![Dashboard proyecto-ep3](‹captura›)

![Logs por id](‹captura›)

## 4. Integración y seguridad (IE7)

**Flujo principal** (predicción síncrona y texto del LLM por la cola, con el camino de falla):

‹diagrama de secuencia: puede partir del capítulo 12.1›

**Rutas de la API** (completa en `https://‹tu-nombre›.sslip.io/docs`):

| Método y ruta | Para | Autenticación | Códigos |
|---|---|---|---|
| `POST /api/predict` | ‹› | `X-API-Key` | 200 · 401 · 422 · 429 |
| `GET /api/predicciones/{id}` | Resultado y texto del LLM | `X-API-Key` | 200 · 401 · 404 |
| ‹ruta propia del caso› | ‹› | `X-API-Key` | ‹› |
| `GET /api/health` | Estado de cada pieza | pública | 200 |
| `GET /docs` | Contrato OpenAPI | pública | 200 |

| Control | Cómo está implementado | Evidencia |
|---|---|---|
| HTTPS | Caddy + Let's Encrypt sobre sslip.io; HTTP → 308 | ‹captura del candado› |
| Autenticación | Clave por `X-API-Key` en el dominio | `401` sin clave |
| Validación | Pydantic, `extra="forbid"` | `422` con el campo |
| Rate limiting | ‹N› por minuto y clave | `429` (prueba 4) |
| Secretos | `NVIDIA_API_KEY` y `POSTGRES_PASSWORD` solo en el `.env` del servidor (modo 600); sin access keys: rol de la EC2 | `git grep` sin resultados |
| Anonimización | `comun/anonimizar.py` antes de publicar en la cola | prueba 5 |
| Superficie | Solo 22, 80 y 443; `/api/ia`, `/interno` y `/metrics` bloqueados en Caddy | security group, `404` |
| **Deuda declarada** | El 22 abierto a internet para el despliegue por SSH; alternativa: runner propio o SSM | |

## 5. Pruebas y calidad (IE10)

**Pruebas automatizadas** (‹N› en total, ejecutadas por el pipeline: ‹link al workflow verde›):

| # | Prueba | Qué verifica | Resultado |
|---|---|---|---|
| 1 | `test_prediccion_valida_responde_200_con_resultado_y_version_de_modelo` | 200 con resultado y versión | PASSED |
| 2 | `test_campo_faltante_o_de_tipo_incorrecto_responde_422` | 422 con el detalle | PASSED |
| 3 | `test_sin_clave_o_con_clave_incorrecta_responde_401` | 401 | PASSED |
| 4 | `test_rafaga_sobre_el_limite_responde_429` | 429 | PASSED |
| 5 | `test_ningun_dato_personal_sobrevive` | anonimización | PASSED |
| 6 | `test_cola_caida_…` y pruebas del worker con 429 | modo degradado | PASSED |
| 7–‹N› | ‹las de tu caso› | ‹› | PASSED |

**Prueba de carga** (Locust, ‹usuarios›, **3 minutos**, contra `https://‹tu-nombre›.sslip.io`):

| Solicitudes | Errores | req/s | p50 | p95 | p99 | RNF del caso | ¿Cumple? |
|---|---|---|---|---|---|---|---|
| ‹› | ‹› (‹%›) | ‹› | ‹› ms | ‹› ms | ‹› ms | ‹› | ‹sí / no, y dónde se midió› |

**Camino del LLM** (medido aparte, pocas solicitudes): latencia ‹ms›; al pasar el límite, ‹comportamiento›.

**Métricas del modelo** (conjunto de prueba separado antes de entrenar):

| Métrica | Modelo | Línea base | Lectura |
|---|---|---|---|
| ‹según EP3 §3 para tu caso› | ‹› | ‹› | ‹› |

**Tres optimizaciones con su costo:**

| # | Optimización | Qué mejora (medido o estimado) | Costo |
|---|---|---|---|
| 1 | ‹› | ‹› | ‹USD/mes› |
| 2 | ‹› | ‹› | ‹› |
| 3 | ‹› | ‹› | ‹› |

---

## Anexo A · Referencias (APA 7, citadas en el texto)

‹Amazon Web Services. (2026). *Serverless Inference*. Amazon SageMaker Developer Guide. https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html›

‹Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of the 22nd ACM
SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.
https://doi.org/10.1145/2939672.2939785›

## Anexo B · Declaración de uso de IA generativa

Usamos ‹herramientas› para ‹informe / código›. El sistema parte de la plantilla `ity1102-guia-proyecto`;
lo que cambiamos y decidimos nosotros: ‹desafíos resueltos y decisiones propias›. Firman: ‹todos›.

## Anexo C · Repositorios y sistema

| | |
|---|---|
| Front | `https://‹tu-nombre›.sslip.io` |
| Documentación de la API | `https://‹tu-nombre›.sslip.io/docs` |
| Salud | `https://‹tu-nombre›.sslip.io/api/health` |
| Clave de API de prueba para el docente | `‹clave›` |
| Endpoint de SageMaker | `ep3-‹caso›` |
| Repositorio y tag | ‹link› · tag `ep3` |
| Último workflow en verde | ‹link› |

| Integrante | Usuario de GitHub | Piezas (sus PR) |
|---|---|---|
| ‹› | ‹› | ‹› |
