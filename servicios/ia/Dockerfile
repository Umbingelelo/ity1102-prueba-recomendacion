# Se construye desde la RAÍZ del repositorio (contexto «.»), porque necesita comun/ y modelo/artefactos/:
#   docker build -f servicios/ia/Dockerfile --build-arg CASO=fraude -t ia .
# Antes hay que haber corrido datos/preparar.py y modelo/entrenar.py (el pipeline lo hace solo).
FROM python:3.12-slim

ARG CASO
ENV CASO=${CASO} \
    PYTHONUNBUFFERED=1 \
    MODELO_DIR=/srv/modelo

WORKDIR /srv
COPY servicios/ia/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY comun/ comun/
COPY servicios/ia/app/ app/
# El modelo viaja DENTRO de la imagen (regla 3 de EP2: nada de bind mounts)
COPY modelo/artefactos/modelo.joblib modelo/artefactos/metadatos.json /srv/modelo/

USER nobody
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
