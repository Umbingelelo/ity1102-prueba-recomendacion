# 15 · Pruebas y carga

**Lo que vas a lograr:** las 10+ pruebas automatizadas de EP3 §4.3 (con las seis obligatorias) corriendo
en el pipeline, la prueba de carga de 3 minutos con Locust contra AWS, la latencia del LLM medida aparte,
y la capacidad de **escribir una prueba nueva en vivo** (IE13).

[← 14 · Monitoreo](14-monitoreo.md) · [Índice](../README.md) · [16 · Informe y presentación →](16-informe-presentacion-ep3.md)

**Ya lo tengo si…** el job `pruebas` está en verde con 10+ pruebas, tienes `carga_stats.csv` de 3 minutos
contra tu URL HTTPS, y sabes en qué archivo agregarías una prueba.

---

## 15.1 Las seis obligatorias, ya escritas

| # (EP3 §4.3) | Qué se espera | Prueba en la plantilla |
|---|---|---|
| 1 | Petición válida → `200` con resultado y versión | `servicios/dominio/tests/test_api.py::test_prediccion_valida_responde_200_con_resultado_y_version_de_modelo` |
| 2 | Campo faltante o de tipo incorrecto → `422` con detalle | `test_api.py::test_campo_faltante_o_de_tipo_incorrecto_responde_422` |
| 3 | Sin clave → `401` | `test_api.py::test_sin_clave_o_con_clave_incorrecta_responde_401` |
| 4 | Ráfaga sobre el límite → `429` | `test_api.py::test_rafaga_sobre_el_limite_responde_429` |
| 5 | RUT, correo, teléfono y tarjeta no sobreviven a la anonimización | `test_api.py::test_lo_que_va_al_llm_sale_anonimizado_y_en_la_cola` y `tests/test_anonimizar.py::test_ningun_dato_personal_sobrevive` |
| 6 | LLM con `429` o caído → la predicción responde y queda degradado | `test_api.py::test_cola_caida_la_prediccion_responde_igual_en_modo_degradado` y `servicios/worker/tests/test_worker.py::test_llm_con_429_sostenido_queda_degradado_tras_los_reintentos` |

Y además: reserva cuando el modelo cae, 404, health y docs públicos, dashboard, las de tu caso
(`test_caso_<caso>.py`), las del modelo (`servicios/ia/tests/`), las de datos (`tests/`) y las del worker.
En total, **más de 30** por caso. Todas corren en el job `pruebas` (capítulo 7.6).

```mermaid
flowchart LR
    subgraph pirámide["Qué cubre cada nivel"]
        U["Unitarias<br/>anonimizar · llm (reintentos) · vectorizar"]
        S["De servicio<br/>dominio contra PostgreSQL real<br/>ia con el modelo real"]
        D["De datos<br/>claves, determinismo, columnas"]
        C["De carga<br/>Locust contra AWS"]
    end
    U --> S --> C
    D --> S
```

## 15.2 Correrlas

Con **solo Docker** (sin Python ni venv; sirve en tu computador, en el de la sala y en la EC2):

```bash
herramientas/probar.sh              # todas, como el pipeline: datos, IA, dominio contra PostgreSQL, worker
herramientas/probar.sh dominio      # solo el dominio
```

**Medido** (caso 3, desde cero): genera datos y modelo si faltan, y corre 10 + 8 + 17 + 6 pruebas en ~1
minuto; con todo en caché, ~25 s. Si ya tienes el venv del capítulo 7.6, también vale:
`DATABASE_URL=postgresql://app:app@localhost:5433/proyecto PYTHONPATH=servicios/dominio:. pytest -v servicios/dominio/tests`.

**Lo visible:** una línea `PASSED` por prueba. Para el informe, el log del paso
*Microservicio de dominio* del último workflow verde (Actions → ejecución → `pruebas`).

## 15.3 Escribir una prueba en vivo (IE13)

La pregunta: *«agrega un caso de prueba que mande una entrada inválida y muéstrame el `422`»*. La forma
de toda prueba de API en la plantilla es la misma:

```python
# servicios/dominio/tests/test_caso_<caso>.py  (al final)
def test_monto_negativo_responde_422(sistema):
    malo = {**sistema["caso"].EJEMPLOS["valido"], "monto": -5}       # caso 3; usa un campo de TU Entrada
    r = sistema["cliente"].post("/api/predict", json=malo, headers=CLAVE)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "monto"]
```

| Lo que escribiste | Qué hace |
|---|---|
| `sistema` | La *fixture* de `conftest.py`: la app con la base de prueba, el modelo real y una cola falsa |
| `EJEMPLOS["valido"]` | El cuerpo válido de tu caso; lo copias y rompes un campo |
| `headers=CLAVE` | Con la clave: si no, la respuesta sería 401 y no probarías la validación |
| `detail[0]["loc"]` | FastAPI dice **qué** campo falló: `["body", "monto"]` |

```bash
herramientas/probar.sh dominio -k monto_negativo
```

**Lo visible** (ensayado así, con esta misma prueba): `1 passed, 17 deselected`. Para que el docente vea
que la prueba **sí detecta** algo, cambia `-5` por `5000` y córrela otra vez: falla con
`assert 200 == 422`. Vuelve a `-5`. Eso es lo que distingue escribir una prueba de copiarla.

**Ensáyalo cronometrado antes de la presentación**, una vez por integrante y con otro campo cada vez
(un canal que no existe, un texto vacío, una cantidad fuera de rango). Meta: menos de 3 minutos.

La de anonimización (prueba 5, unitaria) ya está en `tests/test_anonimizar.py`; tiene esta forma:

```python
# tests/test_anonimizar.py
from comun.anonimizar import anonimizar

def test_ningun_dato_personal_sobrevive():
    limpio = anonimizar("Soy Ana, RUT 12.345.678-9, ana@correo.cl, +56 9 8765 4321, tarjeta 4111 1111 1111 1111")
    for dato in ["12.345.678-9", "ana@correo.cl", "8765 4321", "4111"]:
        assert dato not in limpio
```

## 15.4 La prueba de carga con Locust

Contra el sistema **desplegado en AWS**, sobre `POST /api/predict`, **nunca contra el LLM** (mediría el
límite de NVIDIA, no tu sistema). Desde tu computador:

```bash
pip install locust==2.47.0
# en la EC2, mientras dura la prueba: LIMITE_POR_MINUTO=100000 en .env y docker compose up -d dominio
API_KEY=<tu clave> locust -f pruebas/locustfile.py --host https://<tu-nombre>.sslip.io \
  --headless -u 20 -r 5 -t 3m --csv carga
# después: vuelve LIMITE_POR_MINUTO a 60 y docker compose up -d dominio
```

**Lo visible:** al final, una tabla con `# reqs`, `# fails`, `Avg`, `Min`, `Max`, `Med`, `req/s` y los
percentiles; y los archivos `carga_stats.csv` (p50, p95, p99 por ruta) y `carga_failures.csv`.

| Lo que informas (EP3 §4.3) | De dónde |
|---|---|
| p50, p95, p99 | `carga_stats.csv`, columnas `50%`, `95%`, `99%` de la fila `POST /api/predict` |
| Solicitudes por segundo | Columna `Requests/s` |
| Tasa de errores | `Failure Count / Request Count` |
| ¿Cumple el RNF? | Caso 1: p95 < 200 ms · caso 2: p95 < 3 s **con el LLM** · caso 3: p99 < 100 ms |

> **Ojo con el caso 2:** su `/api/predict` encola el LLM. Para la carga del sistema, Locust mide la
> respuesta inmediata (la intención); la latencia completa con el LLM se mide aparte (15.5).
> **Caso 1:** con `TIMEOUT_MODELO_MS=200`, si el p95 de SageMaker es mayor, verás muchas respuestas de
> reserva: cuéntalas en el dashboard (`por_reserva`) e infórmalo como hallazgo.

**Medido en la EC2 del Learner Lab** (caso 3, Locust desde un computador en Chile, 10 usuarios, 1 minuto,
endpoint serverless con concurrencia 10):

| Medida | Valor | Dónde se mide |
|---|---|---|
| Solicitudes / fallas | 475 / 0 | Locust |
| Rendimiento | 8,06 req/s | Locust |
| p50 · p95 · p99 | 210 · 310 · 500 ms | Locust: **incluye ~150 ms de ida y vuelta Chile–Virginia** |
| Predicción por el modelo: promedio · p95 | 59 · 102 ms | `latencia_ms` en el dominio (sin la red del cliente) |
| Decisiones por reserva | 5 de 483 (1%) | `/dashboard.html` o la base |
| RAM de la EC2 durante la prueba | 1,1 de 3,8 GB | `free -m` |

**Lee el RNF en el lugar correcto.** Lo que ve Locust desde tu casa suma la red de tu casa a Virginia, que
no es de tu sistema. Informa las dos: la del cliente (lo que vive un usuario en Chile) y la del dominio
(lo que tu arquitectura controla). En este ejemplo: el caso 3 **no cumple** p99 < 100 ms ni siquiera
dentro del dominio, y eso, bien explicado con una propuesta, vale más que un número maquillado. Con
concurrencia 2 en el endpoint, la misma prueba sacó ~23% de decisiones por reserva (capítulo 11.6).

> **Después de la carga, mira la cola.** Si tu ejemplo encola texto para el LLM, quedarán cientos de
> mensajes pendientes (capítulo 12.5): `docker compose exec -T rabbitmq rabbitmqctl purge_queue llm`.

## 15.5 El camino del LLM, aparte

Pocas solicitudes, midiendo cuánto tarda el texto en estar listo y qué pasa al pasar el límite:

```bash
B=https://<tu-nombre>.sslip.io; K="X-API-Key: <clave>"
for i in $(seq 10); do
  ID=$(curl -s -X POST $B/api/predict -H "$K" -H 'content-type: application/json' -d '<ejemplo que encola>' \
       | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
  sleep 6
  curl -s $B/api/predicciones/$ID -H "$K" | python3 -c \
    "import json,sys;d=json.load(sys.stdin);print(d['estado_llm'], d.get('latencia_llm_ms'), d.get('motivo_llm'))"
done
```

`latencia_llm_ms` es lo que tardó NVIDIA (con reintentos). Para el caso 2, la latencia total del RNF1 es
la respuesta inmediata + la espera en la cola + `latencia_llm_ms`.

## 15.6 Cold start, dos veces

Para el apartado 3 (y la pregunta del IE6): **recién invocado** y **después de 10 minutos sin uso**. Con
`python3 sagemaker/4_probar.py` (1.ª y 2.ª invocación) o con `ModelSetupTime` en CloudWatch (capítulo 14.4).

## Al informe

**Apartado 5:** tabla de casos de prueba y resultados (nombre de la prueba, qué verifica, resultado), la
carga (p50/p95/p99, req/s, errores, contra el RNF), las métricas del modelo de tu caso contra la línea
base, y **tres optimizaciones concretas con su costo** (por ejemplo: concurrencia provisionada en el
endpoint, cachear perfiles en el dominio, precalcular recomendaciones de noche, más réplicas, un modelo
más chico).

## En la presentación

**IE11 (7%):** *«Corre tu prueba de Locust durante un minuto contra el sistema desplegado. Léeme el p95.
¿Cumple el RNF de tu caso? Si no, ¿qué cambiarías primero y cuánto cuesta?»* — 15.4 con `-t 1m`.
**IE13 (12%):** 15.3.

[Siguiente: 16 · Informe y presentación EP3 →](16-informe-presentacion-ep3.md)
