"""Prueba de carga de POST /api/predict (EP3 §4.3). Nunca contra el LLM: mediría el límite de NVIDIA.

    pip install locust==2.47.0
    API_KEY=<clave> locust -f pruebas/locustfile.py --host https://<ip-con-guiones>.sslip.io \
        --headless -u 20 -r 5 -t 3m --csv carga

Informa p50, p95, p99, solicitudes por segundo y errores en carga_stats.csv. El cuerpo es el ejemplo que
publica tu propia API en /openapi.json: sirve para los tres casos sin cambiar nada.

Ojo con el rate limiting: con 20 usuarios pasas de 60 solicitudes por minuto en segundos y verás 429.
Para medir el sistema, sube LIMITE_POR_MINUTO en el .env del servidor mientras dura la prueba (y
después vuelve a bajarlo). Los 429 son tu límite funcionando: infórmalos aparte.
"""
import os

from locust import HttpUser, between, task


class Cliente(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        spec = self.client.get("/openapi.json", name="openapi (preparación)").json()
        esquema = spec["paths"]["/api/predict"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.cuerpo = spec["components"]["schemas"][esquema["$ref"].split("/")[-1]]["example"]
        self.cabeceras = {"X-API-Key": os.getenv("API_KEY", "")}

    @task
    def predecir(self):
        self.client.post("/api/predict", json=self.cuerpo, headers=self.cabeceras)
