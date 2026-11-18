# Contexto: la raíz del repositorio (necesita comun/).
#   docker build -f servicios/dominio/Dockerfile --build-arg CASO=fraude -t dominio .
FROM python:3.12-slim

ARG CASO
ENV CASO=${CASO} \
    PYTHONUNBUFFERED=1

WORKDIR /srv
COPY servicios/dominio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY comun/ comun/
COPY servicios/dominio/app/ app/

USER nobody
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
