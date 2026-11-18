"""Acceso a la base. El dominio es el ÚNICO servicio que lee y escribe aquí (regla de EP2)."""
import json
import os

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

URL = os.getenv("DATABASE_URL", "postgresql://app:app@db:5432/proyecto")
pool = ConnectionPool(URL, min_size=1, max_size=int(os.getenv("DB_CONEXIONES", "10")), open=False,
                      kwargs={"row_factory": dict_row}, timeout=5)


_abierto = [False]


def abrir():
    """Abre el pool una sola vez por proceso (las pruebas levantan la app varias veces)."""
    if not _abierto[0]:
        pool.open(wait=True, timeout=30)
        _abierto[0] = True


def todos(sql: str, *params) -> list[dict]:
    with pool.connection() as c:
        return c.execute(sql, params).fetchall()


def uno(sql: str, *params) -> dict | None:
    with pool.connection() as c:
        return c.execute(sql, params).fetchone()


def ejecutar(sql: str, *params) -> int:
    with pool.connection() as c:
        return c.execute(sql, params).rowcount


def guardar_prediccion(id, caso, entrada, resultado, decision, probabilidad, version_modelo, origen,
                       latencia_ms, estado_llm) -> None:
    """Cada predicción queda con su entrada, su resultado, la versión del modelo y la fecha (EP2 §2.1)."""
    ejecutar(
        """INSERT INTO predicciones (id, caso, entrada, resultado, decision, probabilidad, version_modelo,
                                     origen, latencia_ms, estado_llm)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        id, caso, Jsonb(entrada), Jsonb(resultado), decision, probabilidad, version_modelo, origen,
        latencia_ms, estado_llm)


def jsonable(fila: dict) -> dict:
    return json.loads(json.dumps(fila, default=str))
