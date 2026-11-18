"""La llamada a la API de NVIDIA, con tiempo máximo de espera, reintentos y espera creciente (igual que L11).

La API de NVIDIA es compatible con el cliente de OpenAI: cambia la base_url y la clave, nada más.
"""
import os
import random
import time

from openai import APIConnectionError, APIStatusError, OpenAI

BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODELO = os.getenv("NVIDIA_MODEL", "")
TIMEOUT = float(os.getenv("NVIDIA_TIMEOUT", "20"))          # segundos por intento
INTENTOS = int(os.getenv("NVIDIA_INTENTOS", "4"))           # intentos en total, no reintentos
ESPERA_BASE = float(os.getenv("NVIDIA_ESPERA_BASE", "2"))   # 2, 4, 8 s... más un poco al azar
MAX_TOKENS = int(os.getenv("NVIDIA_MAX_TOKENS", "400"))

# max_retries=0: los reintentos los hacemos nosotros, para poder verlos, medirlos y explicarlos.
cliente = OpenAI(base_url=BASE_URL, api_key=os.getenv("NVIDIA_API_KEY") or "sin-clave",
                 timeout=TIMEOUT, max_retries=0)


class LLMNoDisponible(Exception):
    """El LLM no respondió después de los reintentos, o respondió algo que no se arregla reintentando."""


def redactar(instruccion: str, contenido: str, dormir=time.sleep) -> str:
    for intento in range(1, INTENTOS + 1):
        espera_pedida = None
        try:
            r = cliente.chat.completions.create(
                model=MODELO,
                messages=[{"role": "system", "content": instruccion},
                          {"role": "user", "content": contenido}],
                max_tokens=MAX_TOKENS,
                temperature=0.3,
            )
            texto = (r.choices[0].message.content or "").strip()
            if not texto:
                raise LLMNoDisponible("respuesta vacía")
            return texto
        except APIStatusError as e:
            # 429 (límite de solicitudes) y 5xx (NVIDIA con problemas) pueden arreglarse esperando.
            # 401 (clave inválida), 404 (modelo que no existe) o 400 no: reintentar solo gasta cuota.
            if e.status_code != 429 and e.status_code < 500:
                raise LLMNoDisponible(f"HTTP {e.status_code}") from e
            motivo = f"HTTP {e.status_code}"
            espera_pedida = e.response.headers.get("retry-after")
        except APIConnectionError as e:   # incluye APITimeoutError: pasó el TIMEOUT sin respuesta
            motivo = type(e).__name__
        if intento == INTENTOS:
            raise LLMNoDisponible(f"{motivo} después de {INTENTOS} intentos")
        espera = float(espera_pedida) if espera_pedida else ESPERA_BASE * 2 ** (intento - 1)
        espera += random.uniform(0, espera / 2)   # jitter: que no reintenten todos en el mismo segundo
        print(f'{{"servicio": "worker", "evento": "reintento", "motivo": "{motivo}", "intento": {intento}, '
              f'"espera_s": {espera:.1f}}}', flush=True)
        dormir(min(espera, 30))
