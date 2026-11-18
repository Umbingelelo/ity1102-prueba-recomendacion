"""Caso 1 · Nexus Retail · variables del modelo de propensión de compra por usuario y categoría.

Una fila de negocio es un PAR (usuario, categoría) en una fecha de corte: «¿cuánto ha comprado, mirado y
dejado en el carrito este usuario en esta categoría hasta hoy, y qué tan vendida está la categoría?». El
modelo responde la probabilidad de que el usuario compre en esa categoría en los próximos 90 días.

Las filas las calcula una sola función de pandas (datos/casos/recomendacion.py: perfil_por_categoria) con
una fecha de corte: al entrenar, el corte es 90 días antes del fin de los datos; para servir, el corte es
el fin de los datos y el resultado se carga en la tabla perfil_usuario_categoria. El dominio lee esas
filas tal cual y se las manda al microservicio de IA, que las pasa por vectorizar(). Ninguna variable
mira lo que pasó después del corte: eso es la etiqueta, y usarlo sería fuga de información.
"""
from comun.caracteristicas import numero

TIPO = "binaria"

COLUMNAS = [
    "compras_cat", "unidades_cat", "gasto_cat", "dias_desde_ultima_cat", "compras_cat_90d",
    "share_cat", "compras_totales", "dias_desde_ultima_compra", "vistas_cat", "clics_cat",
    "carrito_cat", "popularidad_cat",
]

LEGIBLE = {
    "compras_cat": "pedidos del usuario en la categoría",
    "unidades_cat": "unidades compradas en la categoría",
    "gasto_cat": "monto gastado en la categoría",
    "dias_desde_ultima_cat": "días desde su última compra en la categoría",
    "compras_cat_90d": "pedidos en la categoría en los últimos 90 días",
    "share_cat": "parte de sus compras que fue a esta categoría",
    "compras_totales": "pedidos del usuario en total",
    "dias_desde_ultima_compra": "días desde su última compra",
    "vistas_cat": "fichas de la categoría que vio",
    "clics_cat": "clics en productos de la categoría",
    "carrito_cat": "veces que agregó al carrito un producto de la categoría",
    "popularidad_cat": "parte de las ventas recientes de la tienda que es de esta categoría",
}

# Una fila de perfil_usuario_categoria, tal como el dominio se la manda al microservicio de IA.
# usuario_id y categoria viajan para leer la respuesta, pero no son variables del modelo.
EJEMPLO_FILA = {
    "usuario_id": "U100255", "categoria": "Notebooks",
    "compras_cat": 5, "unidades_cat": 7, "gasto_cat": 1290272, "dias_desde_ultima_cat": 73,
    "compras_cat_90d": 1, "share_cat": 0.2941, "compras_totales": 15, "dias_desde_ultima_compra": 73,
    "vistas_cat": 1, "clics_cat": 1, "carrito_cat": 1, "popularidad_cat": 0.0737,
}


def vectorizar(fila: dict) -> list[float]:
    """Toma las columnas del modelo en su orden. Un dato que falta queda como FALTANTE (-1).

    dias_desde_ultima_cat también es -1 cuando el usuario nunca compró en la categoría: para el árbol
    «nunca» es un valor distinto de «hace mucho», y así lo aprende.
    """
    return [numero(fila.get(c)) for c in COLUMNAS]
