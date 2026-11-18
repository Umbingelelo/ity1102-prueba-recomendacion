"""Caso 1 · Nexus Retail · tratamiento de productos, usuarios, transacciones y clickstream.

El modelo es de propensión: para cada par (usuario, categoría) estima la probabilidad de que el usuario
compre en esa categoría en los próximos 90 días. Las variables salen SOLO de lo que pasó antes de una
fecha de corte; la etiqueta, de lo que pasó después. La misma función (perfil_por_categoria) arma el
conjunto de entrenamiento (corte = fin de los datos − 90 días) y la tabla que usa el dominio para servir
(corte = fin de los datos).

Las líneas marcadas «DESAFÍO» son decisiones que tu equipo tiene que revisar, cambiar si no está de
acuerdo y defender con su número. Están explicadas en casos/recomendacion.md.

Después de entrenar, la métrica de ranking contra la línea base de «los más vendidos» se calcula con:
    python -m datos.casos.recomendacion
"""
import random
from pathlib import Path

import pandas as pd

from comun.caracteristicas import recomendacion as variables
from datos.limpieza import ZONA_CHILE, Reporte, booleano, entero, fecha, leer, mapear, monto_clp, texto

CLAVES = {
    "productos": ["sku"],
    "usuarios": ["usuario_id"],
    "transacciones": ["pedido_id", "linea"],
    "perfil_usuario_categoria": ["usuario_id", "categoria"],
}

SEMILLA = 1102

# DESAFÍO R1 · la fecha de extracción. El clickstream y el grueso de las transacciones terminan el
# 31-07-2026; lo que viene después (transacciones de 2027, registros con fecha futura) no puede haber
# ocurrido cuando se sacaron los datos. ¿La fijarías a mano, la calcularías, o usarías la fecha de hoy?
FIN_DATOS = pd.Timestamp("2026-08-01", tz=ZONA_CHILE)

# DESAFÍO R4 · el horizonte de la etiqueta: «compra en la categoría en los próximos 90 días». Con 30 días
# hay pocos positivos; con 180, el corte queda tan atrás que las variables envejecen. Defiende el tuyo.
HORIZONTE_DIAS = 90
CORTE = FIN_DATOS - pd.Timedelta(days=HORIZONTE_DIAS)

# Robots: la lista de L2B. Se compara sin distinguir mayúsculas («SemrushBot», «Scrapy»)
ROBOTS = r"bot|crawler|spider|python-requests|curl|scrapy"

CATEGORIAS = {
    "notebooks": "Notebooks", "notebook": "Notebooks",
    "monitores": "Monitores", "monitor": "Monitores",
    "perifericos": "Periféricos", "periferico": "Periféricos",
    "componentes": "Componentes", "componente": "Componentes",
    "almacenamiento": "Almacenamiento",
    "redes": "Redes",
    "smartphones": "Smartphones", "smartphone": "Smartphones",
    "audio": "Audio",
    "gaming": "Gaming",
    # «Cables» y «Cables y adaptadores» son la misma familia: los nombres de los productos lo confirman
    "cables_y_adaptadores": "Cables y adaptadores", "cables": "Cables y adaptadores",
}
REGIONES = {
    "tarapaca": "Tarapacá", "antofagasta": "Antofagasta", "coquimbo": "Coquimbo",
    "valparaiso": "Valparaíso", "v_region": "Valparaíso",
    "metropolitana": "Metropolitana", "rm": "Metropolitana", "r_metropolitana": "Metropolitana",
    "region_metropolitana": "Metropolitana",
    "o'higgins": "O'Higgins", "ohiggins": "O'Higgins", "libertador_b_o'higgins": "O'Higgins",
    "maule": "Maule", "del_maule": "Maule",
    "biobio": "Biobío", "bio_bio": "Biobío",
    "araucania": "La Araucanía", "la_araucania": "La Araucanía",
    "los_lagos": "Los Lagos",
}
CANALES_CAPTACION = {"organico": "organico", "pagado": "pagado", "directo": "directo", "email": "correo",
                     "correo": "correo", "referido": "referido"}
CANALES_VENTA = {"web": "web", "app": "app", "movil": "app", "tienda": "tienda"}
ESTADOS = {"pagado": "pagado", "anulado": "anulado", "devuelto": "devuelto"}
TIPOS_EVENTO = {"vista": "vista", "view": "vista", "clic": "clic", "click": "clic", "busqueda": "busqueda",
                "search": "busqueda", "agregar_carrito": "agregar_carrito", "add_to_cart": "agregar_carrito"}
DISPOSITIVOS = {"movil": "movil", "mobile": "movil", "escritorio": "escritorio", "desktop": "escritorio",
                "tablet": "tablet"}
USUARIO_SIN_ID = {"invitado", "n/a", "unknown"}


def _a_texto_fecha(serie: pd.Series) -> pd.Series:
    return serie.dt.strftime("%Y-%m-%d %H:%M:%S%z")


def _productos(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "productos.csv")
    r.perfil_antes("productos", df)

    con_espacios = int((df["sku"] != df["sku"].str.strip()).sum())
    df["sku"] = texto(df["sku"])
    r.regla("productos", "sku con espacios al inicio o al final", "corregir", con_espacios,
            "« NX-10637 » y «NX-10637» son el mismo producto; sin quitar los espacios el cruce con ventas falla")
    n = len(df)
    df = df.drop_duplicates().drop_duplicates(subset=["sku"], keep="first")
    r.regla("productos", "el mismo SKU dos veces (filas idénticas una vez quitados los espacios)", "descartar",
            n - len(df), "Es la misma ficha exportada dos veces; conservar una no pierde nada")

    crudo = texto(df["categoria"])
    df["categoria"], sin_mapa = mapear(df["categoria"], CATEGORIAS)
    r.regla("productos", "categoría escrita de 20 formas («Notebooks », «NOTEBOOKS», «cables y adaptadores»)",
            "corregir", int((crudo.notna() & (crudo != df["categoria"])).sum()),
            f"Se llevan a {len(set(CATEGORIAS.values()))} categorías con un mapa escrito a mano; "
            "cada variante sería una categoría distinta para el modelo")
    if len(sin_mapa):
        r.nota(f"productos.categoria sin mapa: {dict(sin_mapa)}")

    df["nombre"] = texto(df["nombre"])
    r.regla("productos", "nombre vacío", "conservar vacío", int(df["nombre"].isna().sum()),
            "No se inventa un nombre comercial: el dominio muestra el SKU en su lugar")
    df["marca"] = texto(df["marca"])
    r.regla("productos", "marca vacía o «N/D»", "marcar como desconocida", int(df["marca"].isna().sum()),
            "«N/D» no es una marca: queda nulo para no agruparlo como si lo fuera")

    precio_crudo = texto(df["precio_lista"])
    precio = monto_clp(precio_crudo).astype("Float64")
    r.regla("productos", "precio_lista como texto con «$» y puntos de miles", "corregir",
            int(precio_crudo.str.contains(r"[$.]", regex=True).fillna(False).sum()),
            "«$19.990» es 19990: en CLP el punto separa miles")
    en_edicion = precio.notna() & (precio <= 0)
    r.regla("productos", "precio 0 (el ERP lo manda así cuando el producto está en edición) o vacío",
            "marcar como desconocido", int(en_edicion.sum() + precio.isna().sum()),
            "No es un producto gratis: sin precio no se recomienda (el dominio lo excluye)")
    df["precio"] = precio.mask(en_edicion).round().astype("Int64")

    costo = monto_clp(df["costo"]).astype("Float64")
    sobre = costo.notna() & df["precio"].notna() & (costo > df["precio"])
    r.regla("productos", "costo mayor que el precio", "marcar", int(sobre.sum()),
            "Puede ser un error del ERP o una liquidación; se marca para que comercial lo revise. "
            "El costo no se guarda en la base: no lo necesita la recomendación")
    df["costo_sobre_precio"] = sobre.astype("Int64").mask(costo.isna() | df["precio"].isna())

    stock = entero(df["stock"])
    r.regla("productos", "stock «ERROR»", "marcar como desconocido", int(stock.isna().sum()),
            "Stock desconocido no es stock disponible: RF5 exige no recomendarlo")
    negativo = stock.notna() & (stock < 0)
    r.regla("productos", "stock negativo", "corregir a 0", int(negativo.sum()),
            "El ERP vendió de más; para la tienda es «sin stock» y RF5 lo deja fuera")
    df["stock"] = stock.mask(negativo, 0)

    activo_crudo = texto(df["activo"]).str.lower()
    df["activo"] = booleano(df["activo"])
    r.regla("productos", "activo escrito como 1/0, true/false y Si/No", "corregir",
            int((~activo_crudo.isin(["1", "0"])).sum()), "Un solo formato: 1 o 0")

    alta = texto(df["fecha_alta"])
    df["fecha_alta"] = fecha(alta, ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]).dt.date
    r.regla("productos", "fecha_alta en tres formatos", "corregir",
            int((~alta.str.match(r"^\d{4}-\d{2}-\d{2}$")).sum()),
            "Cada formato se lee con el suyo; adivinar con dayfirst confunde 03/04 con 04/03")
    return df[["sku", "nombre", "categoria", "marca", "precio", "stock", "activo", "costo_sobre_precio",
               "fecha_alta"]].reset_index(drop=True)


def _usuarios(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "usuarios.csv")
    r.perfil_antes("usuarios", df)
    n = len(df)
    df = df.drop_duplicates()
    r.regla("usuarios", "filas repetidas idénticas", "descartar", n - len(df),
            "La misma persona exportada dos veces")
    df["usuario_id"] = texto(df["usuario_id"])
    df = df.drop_duplicates(subset=["usuario_id"], keep="first")

    registro = fecha(df["fecha_registro"], ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"])
    futura = registro.notna() & (registro >= FIN_DATOS)
    r.regla("usuarios", "fecha_registro en el futuro (posterior a la extracción)", "marcar como desconocida",
            int(futura.sum()), "Nadie se registra después de que se sacaron los datos: es un error de carga")
    df["fecha_registro"] = registro.mask(futura).dt.date

    crudo = texto(df["region"])
    df["region"], sin_mapa = mapear(df["region"], REGIONES)
    r.regla("usuarios", "región escrita de 33 formas («V region», «RM», «Bío Bío», «Ohiggins»)", "corregir",
            int((crudo.notna() & (crudo != df["region"])).sum()), "Mapa escrito a mano a las 10 regiones del archivo")
    if len(sin_mapa):
        r.nota(f"usuarios.region sin mapa: {dict(sin_mapa)}")

    r.regla("usuarios", "comuna (vacía en 304 filas y a veces de otra región)", "descartar columna", len(df),
            "No la necesita la recomendación y es un dato de ubicación: lo que no se usa no se guarda (Ley 21.719)")

    captacion = texto(df["canal_captacion"])
    df["canal_captacion"], _ = mapear(df["canal_captacion"], CANALES_CAPTACION)
    r.regla("usuarios", "canal_captacion vacío o «UNKNOWN»", "marcar como desconocido",
            int(captacion.isna().sum()), "«UNKNOWN» no es un canal")

    df["email_valido"] = booleano(df["email_valido"])
    df["acepta_marketing"] = booleano(df["acepta_marketing"])
    # DESAFÍO R3 · consentimiento vacío. NO se imputa: vacío no es «no» ni «sí», es «no se preguntó». Para
    # RN2 el perfilamiento exige consentimiento EXPLÍCITO, así que vacío no se personaliza (el dominio lo
    # trata como «no»), y además con esos usuarios no se entrena ni se calcula perfil (más abajo).
    r.regla("usuarios", "acepta_marketing vacío", "conservar vacío (no es lo mismo que «no»)",
            int(df["acepta_marketing"].isna().sum()),
            "RN2: perfilar exige consentimiento explícito; un vacío no lo es, pero tampoco es una negativa")

    edad = entero(df["edad"])
    fuera = edad.notna() & ~edad.between(1, 110)
    r.regla("usuarios", "edad 0, 999 o negativa", "marcar como desconocida", int(fuera.sum()),
            "Son valores de relleno del formulario, no edades")
    df["edad"] = edad.mask(fuera)
    return df[["usuario_id", "fecha_registro", "region", "canal_captacion", "email_valido", "acepta_marketing",
               "edad"]].reset_index(drop=True)


def _transacciones(crudos: Path, r: Reporte, productos: pd.DataFrame, usuarios: pd.DataFrame) -> pd.DataFrame:
    df = leer(crudos / "transacciones.csv")
    r.perfil_antes("transacciones", df)
    n = len(df)
    df = df.drop_duplicates()
    r.regla("transacciones", "filas idénticas en todas las columnas (el reproceso de marzo)", "descartar",
            n - len(df), "Es la misma línea cargada dos veces; contarla dos veces infla ventas y ticket")
    r.regla("transacciones", "pedido_id repetido", "conservar", int(df.duplicated(subset=["pedido_id"]).sum()),
            "Es legítimo: un pedido tiene varias líneas. Borrarlas deja un producto por pedido y arruina el "
            "ticket promedio. La clave es pedido_id + linea")

    df["pedido_id"] = texto(df["pedido_id"])
    df["linea"] = entero(df["linea"])
    crudo_usuario = df["usuario_id"].str.strip().str.lower()
    sin_id = crudo_usuario.isin(USUARIO_SIN_ID)
    df["usuario_id"] = texto(df["usuario_id"]).mask(sin_id)
    r.regla("transacciones", "usuario_id «invitado», «N/A» o «UNKNOWN»", "marcar como compra sin usuario",
            int(sin_id.sum()), "Es una compra real de alguien no identificado: cuenta para los más vendidos, "
            "no para el perfil de nadie")
    huerfano = df["usuario_id"].notna() & ~df["usuario_id"].isin(usuarios["usuario_id"])
    r.regla("transacciones", "usuario que no existe en usuarios.csv", "conservar", int(huerfano.sum()),
            "La venta ocurrió. Sin registro no hay consentimiento, así que ese usuario no se personaliza")

    df["sku"] = texto(df["sku"])
    sin_producto = ~df["sku"].isin(productos["sku"])
    r.regla("transacciones", "sku que no existe en productos.csv", "conservar sin categoría", int(sin_producto.sum()),
            "La venta ocurrió, pero sin ficha no se sabe su categoría: no aporta a las variables por categoría")
    df = df.merge(productos[["sku", "categoria"]], on="sku", how="left")

    ts = fecha(df["fecha"], formatos_locales=["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"],
               formatos_con_zona=["%Y-%m-%dT%H:%M:%SZ"])
    r.regla("transacciones", "tres formatos de fecha, uno en UTC («Z») y dos en hora de Chile", "corregir",
            int(ts.notna().sum()), "Cada formato se lee con el suyo y todo queda en hora de Chile")
    r.regla("transacciones", "fecha que no se puede leer (hora inexistente o ambigua por el cambio de horario)",
            "marcar como desconocida", int(ts.isna().sum()), "Adivinar la hora mezclaría dos errores")
    futura = ts.notna() & (ts >= FIN_DATOS)
    r.regla("transacciones", "fecha en el futuro (posterior a la extracción, hasta 2027)", "marcar como desconocida",
            int(futura.sum()), "Una venta no puede ocurrir después de que se sacaron los datos (DESAFÍO R1)")
    df["fecha"] = ts.mask(futura)

    df["cantidad"] = entero(df["cantidad"])
    no_positiva = df["cantidad"].isna() | (df["cantidad"] <= 0)
    r.regla("transacciones", "cantidad cero o negativa", "marcar como no venta", int(no_positiva.sum()),
            "Cero unidades no es una venta; una cantidad negativa es una devolución mal registrada")

    precio_crudo = texto(df["precio_unitario"])
    precio = monto_clp(precio_crudo).astype("Float64")
    r.regla("transacciones", "precio_unitario como texto con «$» y puntos de miles", "corregir",
            int(precio_crudo.str.contains(r"[$.]", regex=True).fillna(False).sum()), "«$19.990» es 19990")

    descuento = monto_clp(df["descuento"]).astype("Float64")
    r.regla("transacciones", "descuento vacío", "imputar 0", int(descuento.isna().sum()),
            "El diccionario de datos dice que el nulo significa cero")
    negativo = descuento.notna() & (descuento < 0)
    r.regla("transacciones", "descuento negativo", "marcar como desconocido", int(negativo.sum()),
            "Un descuento negativo sería un recargo; no hay cómo saber cuál era el valor real")
    descuento = descuento.fillna(0).mask(negativo)
    total = monto_clp(df["total"]).astype("Float64")

    recuperable = precio.isna() & ~no_positiva & total.notna() & descuento.notna()
    r.regla("transacciones", "precio_unitario vacío, recuperable desde (total + descuento) / cantidad", "imputar",
            int(recuperable.sum()), "La línea trae lo necesario para despejarlo; no hay que inventar nada")
    precio = precio.mask(recuperable, (total + descuento) / df["cantidad"].astype("Float64"))

    esperado = df["cantidad"].astype("Float64") * precio - descuento
    se_puede = esperado.notna() & total.notna()
    descuadre = se_puede & ((esperado - total).abs() > 1)
    # DESAFÍO R2 · el total que no cuadra con cantidad × precio − descuento. Se marca y se usa «total»
    # como lo pagado: es lo que cobró la pasarela. ¿Confiarías más en el precio unitario? ¿Por qué?
    r.regla("transacciones", "total ≠ cantidad × precio_unitario − descuento (descuento vacío leído como 0)",
            "marcar", int(descuadre.sum()),
            "No siempre es el descuento. Se conserva «total» como lo pagado y se marca la línea (total_cuadra = 0)")
    df["total_cuadra"] = (~descuadre).astype("Int64").mask(~se_puede)
    df["precio_unitario"] = precio.round().astype("Int64")
    df["descuento"] = descuento.round().astype("Int64")
    df["total"] = total.round().astype("Int64")

    canal = texto(df["canal"])
    df["canal"], _ = mapear(df["canal"], CANALES_VENTA)
    r.regla("transacciones", "canal escrito de 7 formas («WEB», «App», «movil»)", "corregir",
            int((canal.notna() & (canal != df["canal"])).sum()), "«movil» es la app; el resto es mayúsculas")

    df["estado"], _ = mapear(df["estado"], ESTADOS)
    r.regla("transacciones", "estado «-»", "marcar como desconocido", int(df["estado"].isna().sum()),
            "Sin estado no se sabe si se pagó: no se cuenta como venta")
    df["es_venta"] = ((df["estado"] == "pagado") & ~no_positiva & df["fecha"].notna()
                      & df["total"].notna() & (df["total"] > 0)).fillna(False).astype(int)
    r.regla("transacciones", "líneas anuladas, devueltas, sin estado, sin unidades, sin fecha o sin monto",
            "marcar como no venta (es_venta = 0)", int((df["es_venta"] == 0).sum()),
            "No son compras que ocurrieron: no entran a las variables, a la etiqueta ni a los más vendidos")
    ventas = df[df["es_venta"] == 1]
    pedidos = ventas.groupby("pedido_id")
    r.nota(f"Ventas reales: {len(ventas)} líneas de {n} ({1 - len(ventas) / n:.1%} del archivo no son ventas). "
           f"Ticket promedio de los pedidos pagados: ${pedidos['total'].sum().mean():,.0f} con "
           f"{pedidos.size().mean():.2f} líneas por pedido.".replace(",", "."))
    return df


def _clickstream(crudos: Path, r: Reporte, productos: pd.DataFrame) -> pd.DataFrame:
    df = leer(crudos / "clickstream.csv")
    r.perfil_antes("clickstream", df)
    robot = df["user_agent"].str.contains(ROBOTS, case=False, regex=True)
    r.regla("clickstream", "tráfico de robots no marcado (user_agent con bot, crawler, curl, Scrapy...)", "descartar",
            int(robot.sum()), f"Es el {robot.mean():.2%} de los eventos y no hay una persona detrás: infla las "
            "vistas y hunde cualquier tasa calculada por sesión (R8)")
    df = df[~robot].copy()
    n = len(df)
    df = df.drop_duplicates()
    r.regla("clickstream", "eventos idénticos (reintento del tag)", "descartar", n - len(df),
            "El mismo evento enviado dos veces cuenta una sola vista")
    df["evento_id"] = texto(df["evento_id"])
    n = len(df)
    df = df.drop_duplicates(subset=["evento_id"], keep="first")
    r.regla("clickstream", "evento_id repetido con contenido distinto", "descartar", n - len(df),
            "Un identificador debe identificar un solo evento")

    ts = fecha(df["timestamp"], formatos_locales=["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"],
               formatos_con_zona=["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S%z"])
    r.regla("clickstream", "cuatro formatos de fecha, con «Z», con «-03:00» y sin zona", "corregir",
            int(ts.notna().sum()), "Cada formato con el suyo; todo queda en hora de Chile")
    df["ts"] = ts

    tipo = texto(df["tipo_evento"])
    df["tipo_evento"], sin_mapa = mapear(df["tipo_evento"], TIPOS_EVENTO)
    r.regla("clickstream", "tipo_evento en español e inglés y con mayúsculas («view», «Clic », «add_to_cart»)",
            "corregir", int((tipo.notna() & (tipo != df["tipo_evento"])).sum()),
            "Son los mismos cuatro eventos escritos por dos versiones del tag")
    if len(sin_mapa):
        r.nota(f"clickstream.tipo_evento sin mapa: {dict(sin_mapa)}")
    df["dispositivo"], _ = mapear(df["dispositivo"], DISPOSITIVOS)

    for c in ("sesion_id", "usuario_id", "sku", "termino_busqueda"):
        df[c] = texto(df[c])
    r.regla("clickstream", "usuario_id vacío (visitante anónimo)", "conservar", int(df["usuario_id"].isna().sum()),
            "Cuenta para el tráfico, pero no se puede atribuir a ningún perfil")

    usuarios_por_sesion = df.dropna(subset=["usuario_id"]).groupby("sesion_id")["usuario_id"].nunique()
    compartidas = usuarios_por_sesion[usuarios_por_sesion > 1].index
    df["sesion_compartida"] = df["sesion_id"].isin(compartidas).astype(int)
    ultima = df.loc[df["sesion_compartida"] == 1, "ts"].max()
    # DESAFÍO R5 · sesiones con más de un usuario (el tag generó mal el id antes de noviembre de 2024). Se
    # conservan porque las variables se cuentan por USUARIO, no por sesión. Si midieras conversión por
    # sesión (RF10, RNF8), ¿qué harías con ellas?
    r.regla("clickstream", f"sesion_id compartida por usuarios distintos ({len(compartidas)} sesiones)",
            "conservar y marcar (sesion_compartida = 1)", int(df["sesion_compartida"].sum()),
            f"La última es del {ultima:%d-%m-%Y}: el tag se arregló. Las variables se cuentan por usuario, "
            "así que no las afecta; cualquier métrica por sesión debe excluirlas")
    df = df.merge(productos[["sku", "categoria"]], on="sku", how="left")
    # El user_agent ya cumplió su función (detectar robots) y sirve para identificar navegadores: no sigue
    return df[["evento_id", "sesion_id", "usuario_id", "ts", "tipo_evento", "sku", "categoria", "termino_busqueda",
               "dispositivo", "sesion_compartida"]].reset_index(drop=True)


def perfil_por_categoria(ventas: pd.DataFrame, eventos: pd.DataFrame, corte: pd.Timestamp,
                         usuarios_ids: list[str], categorias: list[str]) -> pd.DataFrame:
    """Las variables de cada par (usuario, categoría) con lo que se sabía ANTES de «corte».

    Es la única definición de las variables: la usan el entrenamiento (corte = fin − 90 días) y la tabla
    perfil_usuario_categoria que lee el dominio (corte = fin de los datos).
    ventas:  líneas con es_venta = 1 (usuario_id, pedido_id, categoria, cantidad, total, fecha)
    eventos: clickstream sin robots (usuario_id, categoria, tipo_evento, ts)
    """
    v = ventas[(ventas["fecha"] < corte) & ventas["usuario_id"].isin(usuarios_ids)]
    e = eventos[(eventos["ts"] < corte) & eventos["usuario_id"].isin(usuarios_ids) & eventos["categoria"].notna()]
    base = pd.MultiIndex.from_product([sorted(usuarios_ids), categorias], names=["usuario_id", "categoria"])
    salida = pd.DataFrame(index=base)

    por_cat = v.dropna(subset=["categoria"]).groupby(["usuario_id", "categoria"])
    salida["compras_cat"] = por_cat["pedido_id"].nunique()
    salida["unidades_cat"] = por_cat["cantidad"].sum()
    salida["gasto_cat"] = por_cat["total"].sum()
    salida["dias_desde_ultima_cat"] = (corte - por_cat["fecha"].max()).dt.days
    recientes = v[v["fecha"] >= corte - pd.Timedelta(days=90)].dropna(subset=["categoria"])
    salida["compras_cat_90d"] = recientes.groupby(["usuario_id", "categoria"])["pedido_id"].nunique()
    lineas_cat = por_cat.size()
    lineas_usuario = v.dropna(subset=["categoria"]).groupby("usuario_id").size()
    salida["share_cat"] = (lineas_cat / lineas_cat.index.get_level_values(0).map(lineas_usuario).to_numpy()).round(4)

    por_usuario = v.groupby("usuario_id")
    usuario = salida.index.get_level_values("usuario_id")
    salida["compras_totales"] = usuario.map(por_usuario["pedido_id"].nunique()).to_numpy()
    salida["dias_desde_ultima_compra"] = usuario.map((corte - por_usuario["fecha"].max()).dt.days).to_numpy()

    for columna, tipo in (("vistas_cat", "vista"), ("clics_cat", "clic"), ("carrito_cat", "agregar_carrito")):
        salida[columna] = e[e["tipo_evento"] == tipo].groupby(["usuario_id", "categoria"]).size()

    # Popularidad: de TODAS las ventas (incluidos invitados) de los 90 días previos al corte. Es un dato
    # agregado de la tienda, no del usuario
    tienda = ventas[(ventas["fecha"] < corte) & (ventas["fecha"] >= corte - pd.Timedelta(days=90))]
    popularidad = tienda.dropna(subset=["categoria"]).groupby("categoria").size()
    popularidad = (popularidad / popularidad.sum()).round(4)
    salida["popularidad_cat"] = salida.index.get_level_values("categoria").map(popularidad).to_numpy()

    conteos = ["compras_cat", "unidades_cat", "gasto_cat", "compras_cat_90d", "vistas_cat", "clics_cat", "carrito_cat"]
    salida[conteos] = salida[conteos].fillna(0)
    salida[["share_cat", "popularidad_cat"]] = salida[["share_cat", "popularidad_cat"]].fillna(0.0)
    enteros = conteos + ["compras_totales", "dias_desde_ultima_cat", "dias_desde_ultima_compra"]
    salida[enteros] = salida[enteros].round().astype("Int64")   # dias_desde_ultima_cat vacío = nunca compró
    return salida.reset_index()[["usuario_id", "categoria"] + variables.COLUMNAS]


def particion_por_usuario(usuarios_ids: list[str], prueba=0.25, semilla=SEMILLA) -> set[str]:
    """Los usuarios de prueba. Se separa por USUARIO: si sus 10 filas se repartieran entre entrenamiento y
    prueba, el modelo vería al mismo cliente en los dos lados y la métrica saldría inflada."""
    ids = sorted(usuarios_ids)
    random.Random(semilla).shuffle(ids)
    return set(ids[: round(len(ids) * prueba)])


def hit_rate(dataset: pd.DataFrame, puntaje: str, k: int) -> float:
    """De los usuarios que sí compraron algo en el horizonte: qué parte tenía al menos una de esas
    categorías entre sus k categorías con mayor puntaje."""
    con_compra = dataset.groupby("usuario_id")["y"].transform("max") == 1
    d = dataset[con_compra].sort_values(["usuario_id", puntaje, "categoria"], ascending=[True, False, True])
    return float(d.groupby("usuario_id").head(k).groupby("usuario_id")["y"].max().mean())


def preparar(crudos: Path, r: Reporte):
    productos = _productos(crudos, r)
    usuarios = _usuarios(crudos, r)
    tx = _transacciones(crudos, r, productos, usuarios)
    clics = _clickstream(crudos, r, productos)

    ventas = tx[tx["es_venta"] == 1]
    categorias = sorted(productos["categoria"].dropna().unique())

    # Popularidad de cada producto: lo que usa la lista de «más vendidos» (RF8, RNF3)
    ultimos_90 = ventas[ventas["fecha"] >= FIN_DATOS - pd.Timedelta(days=90)]
    productos["ventas_90d"] = productos["sku"].map(ultimos_90.groupby("sku")["cantidad"].sum()).fillna(0).astype(int)
    productos["ventas_total"] = productos["sku"].map(ventas.groupby("sku")["cantidad"].sum()).fillna(0).astype(int)
    nunca = int((productos["ventas_total"] == 0).sum())
    r.nota(f"SKU del catálogo que no se vendieron nunca: {nunca} de {len(productos)} ({nunca / len(productos):.0%}). "
           "Es la cola larga de R7: un modelo entrenado con compras no puede recomendarlos.")

    # DESAFÍO R3 (continuación) · solo se perfila a quien dio consentimiento explícito (acepta_marketing = 1).
    # Con el resto no se entrena ni se guarda perfil. ¿Entrenar un modelo agregado con su historial también
    # es «perfilar»? Si cambias esto, cambia también la regla del dominio.
    con_consentimiento = set(usuarios.loc[usuarios["acepta_marketing"] == 1, "usuario_id"])
    r.regla("usuarios", "sin consentimiento explícito (acepta_marketing 0 o vacío)",
            "excluir del entrenamiento y del perfil", int(len(usuarios) - len(con_consentimiento)),
            "RN2: el perfilamiento requiere consentimiento explícito. Sus compras sí cuentan para los más vendidos")

    # Entrenamiento: variables hasta CORTE, etiqueta = compró en la categoría entre CORTE y FIN_DATOS
    historia = ventas[(ventas["fecha"] < CORTE) & ventas["usuario_id"].isin(con_consentimiento)]
    ids = sorted(historia["usuario_id"].unique())
    dataset = perfil_por_categoria(ventas, clics, CORTE, ids, categorias)
    futuro = ventas[(ventas["fecha"] >= CORTE) & (ventas["fecha"] < FIN_DATOS)].dropna(subset=["categoria"])
    compro = set(zip(futuro["usuario_id"], futuro["categoria"]))
    dataset["y"] = [int((u, c) in compro) for u, c in zip(dataset["usuario_id"], dataset["categoria"])]
    filas = dataset.astype(object).where(dataset.notna(), None).to_dict("records")
    X = pd.DataFrame([variables.vectorizar(f) for f in filas], columns=variables.COLUMNAS)
    prueba = particion_por_usuario(ids)
    X["y"] = dataset["y"].to_numpy()
    X["particion"] = ["prueba" if u in prueba else "entrenamiento" for u in dataset["usuario_id"]]
    X["usuario_id"], X["categoria"] = dataset["usuario_id"].to_numpy(), dataset["categoria"].to_numpy()

    en_prueba = X[X["particion"] == "prueba"]
    r.nota(f"Entrenamiento: corte {CORTE:%d-%m-%Y}, etiqueta = compra entre el corte y el {FIN_DATOS:%d-%m-%Y} "
           f"({HORIZONTE_DIAS} días). {len(ids)} usuarios con consentimiento e historia × {len(categorias)} "
           f"categorías = {len(X)} filas; {X['y'].mean():.1%} positivas. Prueba: {len(prueba)} usuarios.")
    r.nota(f"Línea base sin modelo (recomendar las categorías más vendidas a todos), sobre los usuarios de "
           f"prueba que compraron algo: hit rate@2 = {hit_rate(en_prueba, 'popularidad_cat', 2):.3f}, "
           f"@3 = {hit_rate(en_prueba, 'popularidad_cat', 3):.3f}. "
           "El del modelo se calcula con  python -m datos.casos.recomendacion")

    # Para servir: las mismas variables con toda la historia, solo de quien dio consentimiento
    activos = sorted(set(ventas["usuario_id"].dropna()) & con_consentimiento)
    perfil = perfil_por_categoria(ventas, clics, FIN_DATOS, activos, categorias)
    r.nota(f"perfil_usuario_categoria: {len(activos)} usuarios × {len(categorias)} categorías, al {FIN_DATOS:%d-%m-%Y}.")

    # El clickstream tratado solo alimenta las variables: no va a la base (el front no lo muestra y son
    # datos de navegación). Su perfil «después» se registra aquí porque no es una tabla de salida
    r.perfil_despues("clickstream", clics)
    tablas = {
        "productos": productos,
        "usuarios": usuarios,
        "transacciones": tx.assign(fecha=_a_texto_fecha(tx["fecha"]))[
            ["pedido_id", "linea", "usuario_id", "sku", "categoria", "fecha", "cantidad", "precio_unitario",
             "descuento", "total", "total_cuadra", "canal", "estado", "es_venta"]],
        "perfil_usuario_categoria": perfil,
    }
    return tablas, X


def lista_por_categorias(categorias_ordenadas: list[str], mas_vendidos_por_cat: dict, excluir: set,
                         cantidad: int = 5, n_categorias: int = 3) -> list[str]:
    """Lo mismo que hace el dominio, sin stock: se reparten los cupos por turnos entre las n categorías
    más probables, tomando en cada una el producto más vendido que el usuario aún no compró."""
    colas = [[s for s in mas_vendidos_por_cat.get(c, []) if s not in excluir] for c in categorias_ordenadas[:n_categorias]]
    lista = []
    while len(lista) < cantidad and any(colas):
        for cola in colas:
            if cola and len(lista) < cantidad:
                lista.append(cola.pop(0))
    return lista


def _evaluar():
    """Métricas de ranking del modelo contra la línea base de los más vendidos, sobre los usuarios de prueba.
    Correr después de entrenar: python -m datos.casos.recomendacion"""
    import joblib
    raiz = Path(__file__).resolve().parents[2]
    tablas, X = preparar(raiz / "datos" / "crudos" / "recomendacion", Reporte("recomendacion"))
    modelo = joblib.load(raiz / "modelo" / "artefactos" / "modelo.joblib")
    prueba = X[X["particion"] == "prueba"].copy()
    prueba["p_modelo"] = modelo.predict_proba(prueba[variables.COLUMNAS].to_numpy())[:, 1]
    usuarios = prueba.groupby("usuario_id")["y"].max()
    print(f"Usuarios de prueba: {len(usuarios)}; compraron algo en los {HORIZONTE_DIAS} días: {int(usuarios.sum())}")
    print("\nCategorías: ¿alguna de las k primeras es una categoría donde sí compró?\n")
    print("| k | hit rate modelo | hit rate más vendidos |\n|---|---|---|")
    for k in (1, 2, 3, 5):
        print(f"| {k} | {hit_rate(prueba, 'p_modelo', k):.3f} | {hit_rate(prueba, 'popularidad_cat', k):.3f} |")

    # Productos: la lista de 5 SKU que vería el usuario, contra los 5 más vendidos de la tienda
    tx = tablas["transacciones"]
    tx = tx[tx["es_venta"] == 1].assign(fecha=pd.to_datetime(tx["fecha"], utc=True).dt.tz_convert(ZONA_CHILE))
    antes, despues = tx[tx["fecha"] < CORTE], tx[(tx["fecha"] >= CORTE) & (tx["fecha"] < FIN_DATOS)]
    recientes = antes[antes["fecha"] >= CORTE - pd.Timedelta(days=90)].dropna(subset=["categoria"])
    unidades = recientes.groupby(["categoria", "sku"])["cantidad"].sum().reset_index()
    unidades = unidades.sort_values(["cantidad", "sku"], ascending=[False, True])
    por_cat = unidades.groupby("categoria")["sku"].apply(list).to_dict()
    top_tienda = unidades["sku"].head(5).tolist()
    compro_antes = antes.groupby("usuario_id")["sku"].apply(set).to_dict()
    compro_despues = despues.groupby("usuario_id")["sku"].apply(set).to_dict()
    aciertos = {"modelo": [], "más vendidos": []}
    for u, filas in prueba[prueba["usuario_id"].isin(compro_despues)].groupby("usuario_id"):
        orden = filas.sort_values(["p_modelo", "categoria"], ascending=[False, True])["categoria"].tolist()
        listas = {"modelo": lista_por_categorias(orden, por_cat, compro_antes.get(u, set())),
                  "más vendidos": top_tienda}
        for nombre, lista in listas.items():
            aciertos[nombre].append(len(set(lista) & compro_despues[u]))
    print(f"\nProductos: lista de 5 SKU, {len(aciertos['modelo'])} usuarios de prueba que compraron en el horizonte\n")
    print("| lista | hit rate@5 | precision@5 |\n|---|---|---|")
    for nombre, a in aciertos.items():
        a = pd.Series(a)
        print(f"| {nombre} | {(a > 0).mean():.3f} | {(a / 5).mean():.3f} |")


if __name__ == "__main__":
    _evaluar()
