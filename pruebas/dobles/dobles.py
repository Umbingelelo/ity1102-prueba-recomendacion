"""Dobles de SageMaker y de la API de NVIDIA, para ensayar EP3 en tu computador sin AWS ni clave.

Responde como responderían ellos, en las mismas rutas:
    POST /endpoints/<nombre>/invocations   SageMaker Runtime: probabilidades con TU modelo local
    POST /   (X-Amz-Target: SageMaker.DescribeEndpoint)  el estado del endpoint: InService
    POST /v1/chat/completions              NVIDIA (compatible OpenAI): un texto de ejemplo

Para provocar fallas en el ensayo (las preguntas del IE6 y el IE8):
    NVIDIA_API_KEY=invalida en el worker      -> el doble responde 401 (clave inválida)
    DOBLE_LLM=429                             -> siempre 429 (límite de solicitudes)
    DOBLE_COLD_START_MS=6000                  -> la primera invocación después de 60 s sin uso tarda eso

NO es parte del sistema: solo lo usa compose.ensayo.yaml. En la EC2 se habla con los servicios reales.
"""
import json
import os
import sys
import time

import joblib
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

MODELO_DIR = os.getenv("MODELO_DIR", "/srv/modelo")
modelo = joblib.load(f"{MODELO_DIR}/modelo.joblib")
metadatos = json.load(open(f"{MODELO_DIR}/metadatos.json"))
COLD_START_MS = int(os.getenv("DOBLE_COLD_START_MS", "0"))
ultima = [0.0]

app = FastAPI(title="Dobles de SageMaker y NVIDIA (solo ensayo)")


@app.post("/endpoints/{nombre}/invocations")
async def invocar(nombre: str, request: Request):
    if COLD_START_MS and time.time() - ultima[0] > 60:
        time.sleep(COLD_START_MS / 1000)
    ultima[0] = time.time()
    filas = [[float(v) for v in linea.split(",")] for linea in (await request.body()).decode().splitlines() if linea]
    probas = modelo.predict_proba(filas)
    if metadatos["tipo"] == "binaria":
        cuerpo = "\n".join(f"{p[1]:.6f}" for p in probas)
    else:
        cuerpo = "\n".join(",".join(f"{v:.6f}" for v in p) for p in probas)
    return PlainTextResponse(cuerpo, media_type="text/csv")


@app.post("/")
async def control(request: Request):
    destino = request.headers.get("x-amz-target", "")
    if destino.endswith("DescribeEndpoint"):
        nombre = (await request.json())["EndpointName"]
        return JSONResponse({"EndpointName": nombre, "EndpointArn": f"arn:aws:sagemaker:us-east-1:000000000000:endpoint/{nombre}",
                             "EndpointConfigName": f"{nombre}-ensayo", "EndpointStatus": "InService",
                             "CreationTime": time.time(), "LastModifiedTime": time.time()},
                            media_type="application/x-amz-json-1.1")
    return JSONResponse({"__type": "ValidationException", "message": f"{destino} no está en el doble"}, status_code=400)


@app.post("/v1/chat/completions")
async def chat(request: Request):
    if request.headers.get("authorization", "").endswith("invalida"):
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)
    if os.getenv("DOBLE_LLM") == "429":
        return JSONResponse({"error": {"message": "Too Many Requests"}}, status_code=429, headers={"retry-after": "1"})
    pedido = await request.json()
    time.sleep(0.8)   # un LLM tarda segundos, no milisegundos
    texto = ("[ensayo] Texto de ejemplo del LLM. En la EC2 aquí llega la respuesta real de NVIDIA a partir de: "
             + pedido["messages"][-1]["content"][:160])
    return {"id": "ensayo", "object": "chat.completion", "created": int(time.time()), "model": pedido.get("model", ""),
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": texto}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


if __name__ == "__main__":
    print(f"Dobles listos · caso {metadatos['caso']} · modelo {metadatos['version']}", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="warning")
