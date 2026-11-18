# Contexto: la raíz del repositorio. Necesita datos/tratados/tablas/ (lo genera datos/preparar.py).
#   docker build -f servicios/carga/Dockerfile --build-arg CASO=fraude -t carga .
FROM python:3.12-slim

ARG CASO
ENV CASO=${CASO} \
    PYTHONUNBUFFERED=1

WORKDIR /srv
RUN pip install --no-cache-dir "psycopg[binary]==3.2.9"
COPY servicios/carga/cargar.py .
COPY servicios/carga/esquemas/ esquemas/
# Los datos tratados viajan DENTRO de la imagen: el computador de la defensa no tiene el repositorio
COPY datos/tratados/tablas/ tablas/

USER nobody
CMD ["python", "cargar.py"]
