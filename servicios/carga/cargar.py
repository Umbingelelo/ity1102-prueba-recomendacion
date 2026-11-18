"""Servicio de carga: crea las tablas y mete los datos tratados en la base. Corre una vez y termina.

Es idempotente: si corre dos veces, no duplica filas. Lo logra así:
    1. CREATE TABLE IF NOT EXISTS: la segunda vez la tabla ya existe y no pasa nada.
    2. Cada tabla tiene clave primaria, y las filas se insertan con ON CONFLICT DO NOTHING: una fila que
       ya está no se vuelve a insertar.
Los CSV vienen DENTRO de la imagen (los dejó ahí el pipeline, después de correr datos/preparar.py).
"""
import csv
import os
import re
import sys
import time
from pathlib import Path

import psycopg

URL = os.getenv("DATABASE_URL", "postgresql://app:app@db:5432/proyecto")
CASO = os.environ["CASO"]
ESQUEMAS = Path(os.getenv("ESQUEMAS", "/srv/esquemas"))
TABLAS = Path(os.getenv("TABLAS", "/srv/tablas"))


def conectar(intentos=30):
    for i in range(intentos):
        try:
            return psycopg.connect(URL, autocommit=False)
        except psycopg.OperationalError as e:
            print(f"Base no disponible ({i + 1}/{intentos}): {e}".strip(), flush=True)
            time.sleep(2)
    sys.exit("No se pudo conectar a la base")


def orden_de_carga(sql: str) -> list[str]:
    """La primera línea «-- carga: a, b, c» del esquema dice en qué orden se cargan las tablas."""
    m = re.search(r"--\s*carga:\s*(.+)", sql)
    return [t.strip() for t in m.group(1).split(",")] if m else []


def cargar_tabla(con, tabla: str) -> tuple[int, int]:
    ruta = TABLAS / f"{tabla}.csv"
    with open(ruta, newline="") as f:
        columnas = next(csv.reader(f))
    lista = ", ".join(columnas)
    with con.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE tmp_{tabla} (LIKE {tabla} INCLUDING DEFAULTS) ON COMMIT DROP")
        with open(ruta, "rb") as f, cur.copy(f"COPY tmp_{tabla} ({lista}) FROM STDIN WITH (FORMAT csv, HEADER true)") as copia:
            while bloque := f.read(1 << 16):
                copia.write(bloque)
        cur.execute(f"SELECT count(*) FROM tmp_{tabla}")
        en_archivo = cur.fetchone()[0]
        cur.execute(f"INSERT INTO {tabla} ({lista}) SELECT {lista} FROM tmp_{tabla} ON CONFLICT DO NOTHING")
        return en_archivo, cur.rowcount


def main():
    inicio = time.time()
    con = conectar()
    sql_caso = (ESQUEMAS / f"{CASO}.sql").read_text()
    with con:   # una transacción: o se carga todo, o nada
        con.execute((ESQUEMAS / "comun.sql").read_text())
        con.execute(sql_caso)
        for tabla in orden_de_carga(sql_caso):
            en_archivo, nuevas = cargar_tabla(con, tabla)
            print(f"  {tabla:<28} {en_archivo:>7} en el archivo · {nuevas:>7} nuevas", flush=True)
    print(f"Carga del caso {CASO} terminada en {time.time() - inicio:.1f} s. Si corre otra vez, no duplica.")


if __name__ == "__main__":
    main()
