"""Caso 2 · Andesnet · tratamiento de tickets, clientes, artículos de ayuda (faq) y conversaciones.

El modelo aprende a reconocer la intención de un mensaje (RF2) con el texto de los tickets, ya
anonimizado, y la categoría del ticket traducida a una intención con un mapa escrito a mano.

Las líneas marcadas «DESAFÍO» son decisiones que tu equipo tiene que revisar, cambiar si no está de
acuerdo y defender con su número. Están explicadas en casos/chatbot.md.
"""
import re
from pathlib import Path

import pandas as pd

from comun.anonimizar import PATRONES
from comun.caracteristicas import chatbot as variables
from datos.casos import particion_estratificada
from datos.limpieza import ZONA_CHILE, Reporte, booleano, clave_normalizada, entero, fecha, leer, mapear, \
    monto_clp, texto

CLAVES = {
    "clientes": ["cliente_id"],
    "faq": ["articulo_id"],
    "tickets": ["ticket_id"],
    "conversaciones": ["conversacion_id"],
}

# Las intenciones que el modelo aprende. La clave es la categoría ya normalizada con clave_normalizada()
# («Fact.» -> «fact», «Cambio de Plan» -> «cambio_de_plan»).
# DESAFÍO C2 · «cobros» se junta con facturación y «señal» con cobertura, no con falla técnica: los
# textos de esos tickets son exactamente los mismos que los de facturación y cobertura (compruébalo con
# el comando de casos/chatbot.md). ¿Separarías «cobro no reconocido» como intención propia? ¿Con qué datos?
INTENCIONES = {
    "facturacion": "facturacion", "fact": "facturacion", "cobros": "facturacion",
    "falla_tecnica": "falla_tecnica", "tecnico": "falla_tecnica", "soporte": "falla_tecnica",
    "soporte_tecnico": "falla_tecnica",
    "cobertura": "cobertura", "senal": "cobertura",
    "cambio_plan": "cambio_plan", "cambio_de_plan": "cambio_plan", "upgrade": "cambio_plan",
    "visita_tecnica": "visita_tecnica", "visita": "visita_tecnica", "agenda_tecnico": "visita_tecnica",
    "anulacion": "anulacion", "baja": "anulacion", "cancelacion": "anulacion",
    "equipos": "equipos", "equipo": "equipos", "router": "equipos",
    "portabilidad": "portabilidad", "porta": "portabilidad",
    "roaming": "roaming", "internacional": "roaming",
    "tv": "tv", "television": "tv",
}
SIN_INTENCION = {"otros", "consulta_general"}   # categorías que no dicen qué quería el cliente

# El bot de reglas anterior escribía sus propias etiquetas (conversaciones.intencion_detectada)
INTENCIONES_BOT = {
    "consulta_saldo": "facturacion", "saldo": "facturacion", "falla_conexion": "falla_tecnica",
    "sin_internet": "falla_tecnica", "falla": "falla_tecnica", "cambio_plan": "cambio_plan",
    "cambio_de_plan": "cambio_plan", "estado_visita": "visita_tecnica", "visita": "visita_tecnica",
    "portabilidad": "portabilidad", "anulacion": "anulacion", "baja": "anulacion",
}

CANALES_TICKET = {"telefono": "telefono", "fono": "telefono", "call": "telefono", "web": "web",
                  "sitio_web": "web", "whatsapp": "whatsapp", "wa": "whatsapp", "app": "app",
                  "app_movil": "app", "aplicacion": "app", "presencial": "presencial", "sucursal": "presencial"}
CANALES_CHAT = {"web": "web", "sitio_web": "web", "whatsapp": "whatsapp", "wa": "whatsapp"}
SUBCATEGORIAS = {"n2": "nivel2", "nivel2": "nivel2", "nivel1": "nivel1", "escalado": "escalado"}
TIPOS_SERVICIO = {"movil": "movil", "fibra": "fibra", "tv": "tv", "combo": "combo", "paquete": "combo"}
SEGMENTOS = {"residencial": "residencial", "pyme": "pyme", "empresa": "empresa"}
REGIONES = {
    "i": "Tarapacá", "tarapaca": "Tarapacá", "ii": "Antofagasta", "antofagasta": "Antofagasta",
    "iv": "Coquimbo", "coquimbo": "Coquimbo", "v": "Valparaíso", "valparaiso": "Valparaíso",
    "rm": "Metropolitana", "metropolitana": "Metropolitana", "region_metropolitana": "Metropolitana",
    "vi": "O'Higgins", "o'higgins": "O'Higgins", "vii": "Maule", "maule": "Maule",
    "xvi": "Ñuble", "nuble": "Ñuble", "viii": "Biobío", "biobio": "Biobío",
    "ix": "Araucanía", "araucania": "Araucanía", "xiv": "Los Ríos", "los_rios": "Los Ríos",
    "x": "Los Lagos", "los_lagos": "Los Lagos",
}
# Planes: la clave es el nombre en minúsculas y sin espacios («Fibra 600», «FIBRA600» -> «fibra600»).
PLANES = {
    "fibra600": "Fibra 600", "fibra900": "Fibra 900", "fibra1000": "Fibra 1000",
    "movillibre": "Movil Libre", "movilfull40gb": "Movil Full 40GB", "movilprepago": "Movil Prepago",
    "tvfull": "TV Full", "combototal": "Combo Total", "combohogarplus": "Combo Hogar Plus",
    "planandes200": "Plan Andes 200", "plancobre10m": "Plan Cobre 10M", "bandaancha20m": "Banda Ancha 20M",
    "movilcontrol3g": "Movil Control 3G", "tvbasicoanalogo": "TV Basico Analogo", "duoclasico": "Duo Clasico",
}
# R7 del caso: planes que ya no se venden. Se reconocen por tecnología retirada (cobre, 3G, analógico,
# 20 Mbps) y porque tienen la cuarta parte de clientes que los demás. Confírmalo con negocio.
PLANES_DESCONTINUADOS = {"Plan Andes 200", "Plan Cobre 10M", "Banda Ancha 20M", "Movil Control 3G",
                         "TV Basico Analogo", "Duo Clasico"}

# Artículos de ayuda: el tema y la intención salen de la PREGUNTA, no de la columna categoria (C5)
TEMAS_FAQ = [
    (r"porto|portabilidad", "portarse a andesnet", "portabilidad"),
    (r"pago atrasado", "pago atrasado", "facturacion"),
    (r"vence", "vencimiento de la boleta", "facturacion"),
    (r"pago mi cuenta", "medios de pago", "facturacion"),
    (r"devuelvo el equipo", "devolver un equipo", "equipos"),
    (r"cobertura", "cobertura en mi comuna", "cobertura"),
    (r"tv en el celular", "tv en el celular", "tv"),
    (r"visita tecnica", "agendar visita técnica", "visita_tecnica"),
    (r"no tengo internet", "sin internet", "falla_tecnica"),
    (r"roaming", "costo del roaming", "roaming"),
    (r"cambio mi plan", "cambiar de plan", "cambio_plan"),
    (r"anulo", "anular el servicio", "anulacion"),
]
RELLENO_FAQ = re.compile(r"^(quiero saber|necesito ayuda) "
                         r"| (paso a paso|de tv|de fibra|movil|prepago|empresa|desde la app)$")

# DESAFÍO C1 · los cuatro formatos de fecha se leen como hora de Chile, también los que terminan en «Z»
# o «-03:00». Si se cree en la «Z» (UTC), aparecen 2.211 cierres antes de la apertura, casi todos entre
# 2 y 4 horas antes (el desfase con UTC): la «Z» la escribe un sistema que guarda la hora local y le pega la letra.
# Leyendo los cuatro como hora local quedan 274 (L2B: 279 sobre el archivo con duplicados).
FORMATOS_FECHA_HORA = ["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S-03:00"]


def _fecha_hora(serie: pd.Series) -> pd.Series:
    return fecha(serie, formatos_locales=FORMATOS_FECHA_HORA)


def _iso(serie: pd.Series) -> pd.Series:
    return serie.dt.strftime("%Y-%m-%d %H:%M:%S%z")


def _anonimizar_y_contar(crudo: pd.Series, tabla: str, columna: str, r: Reporte) -> pd.Series:
    """Cuenta cuántas filas traen cada tipo de dato personal y lo reemplaza por su marcador (RNF5)."""
    alguno = pd.Series(False, index=crudo.index)
    nombres = {"[CORREO]": "correo", "[TARJETA]": "número de tarjeta", "[RUT]": "RUT", "[TELEFONO]": "teléfono"}
    texto_actual = crudo.map(variables.sin_entidades)   # «@&amp;ahoo.es» también es un correo
    for marcador, patron in PATRONES:
        tiene = texto_actual.str.contains(patron)
        alguno |= tiene
        r.regla(tabla, f"{columna} con {nombres[marcador]}", f"corregir (reemplazar por {marcador})",
                int(tiene.sum()), "Dato personal pegado en texto libre: no entra al modelo, a la base ni al LLM (RNF5)")
        texto_actual = texto_actual.str.replace(patron, marcador, regex=True)
    r.nota(f"{tabla}.{columna}: {int(alguno.sum())} filas ({alguno.mean():.2%}) traían al menos un dato personal. "
           "Nombres y direcciones no se detectan con expresiones regulares: por eso al LLM no se manda el cliente.")
    return crudo.map(variables.limpiar)


def _clientes(crudos: Path, r: Reporte, corte: pd.Timestamp) -> pd.DataFrame:
    df = leer(crudos / "clientes.csv")
    r.perfil_antes("clientes", df)
    n = len(df)
    df = df.drop_duplicates()
    r.regla("clientes", "filas idénticas (migración de 2024)", "descartar", n - len(df),
            "El mismo cliente exportado dos veces: conservar una no pierde información")
    df["cliente_id"] = texto(df["cliente_id"])
    df = df.drop_duplicates(subset=["cliente_id"], keep="first")

    alta = fecha(df["fecha_alta"], ["%Y-%m-%d", "%d/%m/%Y"])
    futura = alta.notna() & (alta > corte)
    r.regla("clientes", f"fecha_alta posterior a la extracción ({corte:%Y-%m-%d})", "marcar como desconocido",
            int(futura.sum()), "Nadie se hace cliente en el futuro: es un error de digitación, no una fecha")
    df["fecha_alta"] = alta.mask(futura).dt.date

    crudo_plan = texto(df["plan"])
    clave_plan = crudo_plan.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    df["plan"] = clave_plan.map(lambda v: PLANES.get(v, pd.NA) if pd.notna(v) else pd.NA).astype("string")
    r.regla("clientes", "plan escrito de varias formas («TVFull», «TV FULL», «tv full»)", "corregir",
            int((crudo_plan.notna() & (crudo_plan != df["plan"])).sum()),
            "Se lleva al nombre comercial con un mapa; lo que no está en el mapa queda nulo")
    df["plan_descontinuado"] = df["plan"].isin(PLANES_DESCONTINUADOS).astype("Int64").mask(df["plan"].isna())
    r.regla("clientes", "cliente en un plan que ya no se vende (R7)", "marcar", int(df["plan_descontinuado"].sum()),
            "Siguen siendo clientes, pero una respuesta genérica sobre planes estará mal para ellos")

    for columna, mapa in (("tipo_servicio", TIPOS_SERVICIO), ("segmento", SEGMENTOS)):
        crudo = texto(df[columna])
        df[columna], sin_mapa = mapear(df[columna], mapa)
        r.regla("clientes", f"{columna} con mayúsculas, tildes y sinónimos", "corregir",
                int((crudo.notna() & (crudo != df[columna])).sum()), "Un mapa escrito a mano lleva todo a un valor")
        if len(sin_mapa):
            r.nota(f"clientes.{columna} sin mapa: {dict(sin_mapa)}")
    crudo_region = texto(df["region"])
    df["region"], sin_mapa = mapear(df["region"], REGIONES)
    r.regla("clientes", "región con número romano, nombre largo o sin tilde («VIII», «Biobio»)", "corregir",
            int((crudo_region.notna() & (crudo_region != df["region"])).sum()),
            "Una región escrita de tres formas son tres regiones para un GROUP BY")
    if len(sin_mapa):
        r.nota(f"clientes.region sin mapa: {dict(sin_mapa)}")

    meses = entero(df["antiguedad_meses"])
    negativa = meses.notna() & (meses < 0)
    r.regla("clientes", "antiguedad_meses negativa", "marcar como desconocido", int(negativa.sum()),
            "Una antigüedad negativa no existe; recalcularla con fecha_alta mezclaría dos campos que no concuerdan")
    df["antiguedad_meses"] = meses.mask(negativa)
    calculada = ((corte - alta).dt.days / 30.44).round()
    r.nota(f"clientes: en {int(((df['antiguedad_meses'] - calculada).abs() > 3).sum())} filas antiguedad_meses "
           f"difiere en más de 3 meses de lo que dice fecha_alta. Ninguna de las dos se usa en el modelo.")

    deuda = monto_clp(df["deuda_vigente"])
    negativa = deuda.notna() & (deuda < 0)
    r.regla("clientes", "deuda_vigente con «$» y separador de miles («$9.570»)", "corregir",
            int(texto(df["deuda_vigente"]).str.contains(r"[$.]", regex=True).fillna(False).sum()),
            "En pesos chilenos el punto es separador de miles: se quita antes de convertir")
    r.regla("clientes", "deuda_vigente negativa", "corregir (pasa a saldo_a_favor_clp)", int(negativa.sum()),
            "El diccionario dice que negativo es saldo a favor: no es error, es otro dato")
    df["deuda_vigente_clp"] = deuda.clip(lower=0).round().astype("Int64")
    df["saldo_a_favor_clp"] = (-deuda).clip(lower=0).round().astype("Int64")

    df["canal_preferido"] = texto(df["canal_preferido"])
    consentimiento = booleano(df["acepta_contacto"])
    r.regla("clientes", "acepta_contacto vacío", "imputar 0 (no acepta)", int(consentimiento.isna().sum()),
            "Sin consentimiento registrado no se contacta (Ley 21.719 y GDPR): el silencio no es un sí")
    df["acepta_contacto"] = consentimiento.fillna(0)
    return df[["cliente_id", "fecha_alta", "plan", "plan_descontinuado", "tipo_servicio", "region", "segmento",
               "antiguedad_meses", "deuda_vigente_clp", "saldo_a_favor_clp", "canal_preferido", "acepta_contacto"]]


def _tickets(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "tickets.csv")
    r.perfil_antes("tickets", df)
    n = len(df)
    df = df.drop_duplicates()
    r.regla("tickets", "filas idénticas en todas las columnas (reproceso)", "descartar", n - len(df),
            "El mismo ticket cargado dos veces: contarlo doble infla el volumen de esa intención")
    df["ticket_id"] = texto(df["ticket_id"])
    df = df.drop_duplicates(subset=["ticket_id"], keep="first")
    df["cliente_id"] = texto(df["cliente_id"])
    df["agente_id"] = texto(df["agente_id"])

    crudo = texto(df["canal"])
    df["canal"], sin_mapa = mapear(df["canal"], CANALES_TICKET)
    r.regla("tickets", f"canal escrito de {crudo.nunique()} formas para 5 valores («fono», «WA», «sitio_web»)",
            "corregir", int((crudo.notna() & (crudo != df["canal"])).sum()), "Mapa escrito a mano a los cinco canales")
    if len(sin_mapa):
        r.nota(f"tickets.canal sin mapa: {dict(sin_mapa)}")

    apertura, cierre = _fecha_hora(df["fecha_apertura"]), _fecha_hora(df["fecha_cierre"])
    r.regla("tickets", "cuatro formatos de fecha y hora (dos con una zona que no es real)", "corregir",
            int(apertura.notna().sum()), "Se reconoce cada formato por separado y todo queda en hora de Chile (C1)")
    invertida = cierre.notna() & apertura.notna() & (cierre < apertura)
    r.regla("tickets", "fecha_cierre anterior a fecha_apertura", "marcar (cierre queda desconocido)",
            int(invertida.sum()),
            "No se sabe cuál de las dos está mal: el tiempo de resolución de esas filas no se calcula")
    r.nota(f"tickets: {int(cierre.isna().sum() - invertida.sum())} sin fecha de cierre (siguen abiertos).")
    df["fecha_apertura"], df["fecha_cierre"] = _iso(apertura), _iso(cierre.mask(invertida))
    df["cierre_invalido"] = invertida.astype(int)

    crudo = texto(df["categoria"])
    clave = clave_normalizada(df["categoria"])
    df["intencion"], sin_mapa = mapear(df["categoria"], INTENCIONES)
    r.regla("tickets", f"categoría escrita de {df['categoria'].nunique()} formas", "corregir",
            int((crudo.notna() & (crudo != df["intencion"])).sum()),
            "Mapa escrito a mano a 10 intenciones; strip y lower no bastan («falla tecnica» ≠ «falla_tecnica»)")
    sin_intencion = df["intencion"].isna()
    r.regla("tickets", "categoría «otros», «consulta_general», vacía o «N/A»",
            "conservar, fuera del entrenamiento", int(sin_intencion.sum()),
            "No dicen qué quería el cliente: enseñarle esa clase al modelo no ayuda a responder (C4)")
    desconocidas = {k: int(v) for k, v in sin_mapa.items() if k not in SIN_INTENCION}
    if desconocidas:
        r.nota(f"tickets.categoria sin mapa: {desconocidas}")
    df["categoria_original"] = clave

    crudo = df["texto_consulta"].astype(str)
    for problema, patron in (("entidades HTML («&amp;» en lugar de «y», «&#241;» en lugar de «ñ»)",
                              r"&(?:#\d+|[a-zA-Z]+);"),
                             ("saltos de línea escritos como «\\n»", r"(?i)\\n"),
                             ("firma «Enviado desde mi iPhone»", r"(?i)enviado desde mi"),
                             ("espacios dobles", r"\s{2,}")):
        r.regla("tickets", f"texto_consulta con {problema}", "corregir", int(crudo.str.contains(patron).sum()),
                "Es ruido de la transcripción: cambia las palabras que ve el modelo, no lo que pidió el cliente")
    df["texto"] = _anonimizar_y_contar(crudo, "tickets", "texto_consulta", r)

    espera = entero(df["tiempo_espera_seg"])
    negativa, dia = espera.notna() & (espera < 0), espera == 86400
    r.regla("tickets", "tiempo_espera_seg negativo", "marcar como desconocido", int(negativa.sum()),
            "Una espera negativa es un reloj mal sincronizado, no un dato")
    r.regla("tickets", "tiempo_espera_seg = 86.400 (justo un día)", "marcar como desconocido",
            int(dia.fillna(False).sum()),
            "Es el valor por defecto del sistema cuando no registró la atención; promediarlo infla la espera")
    df["tiempo_espera_seg"] = espera.mask(negativa | dia.fillna(False))

    crudo = texto(df["resuelto"])
    df["resuelto"] = booleano(df["resuelto"])
    r.regla("tickets", "resuelto en seis dialectos (1, 0, si, no, TRUE, vacío)", "corregir",
            int((crudo.notna() & ~crudo.isin(["0", "1"])).sum()),
            "Un mapa lleva todo a 1/0; vacío queda desconocido, no «no resuelto»")
    df["reabierto"] = booleano(df["reabierto"])

    csat = entero(df["csat"])
    fuera = csat.isin([0, 99]).fillna(False)
    r.regla("tickets", "csat 0 o 99", "marcar como desconocido", int(fuera.sum()),
            "No están en ninguna de las dos escalas: son el «no respondió» de cada sistema")
    csat = csat.mask(fuera)
    # DESAFÍO C3 · la escala cambió de 1-5 a 1-10. Desde el primer ticket con nota sobre 5 se asume que
    # TODO lo que sigue está en 1-10 (también los 3 y los 4) y se convierte con techo(x / 2). ¿Por qué no
    # dejar los 1-5 de ese período como están? ¿Cuánto cambia el CSAT promedio con una u otra decisión?
    cambio = apertura[(csat > 5).fillna(False)].min()
    nueva = (apertura >= cambio) & csat.notna()
    r.regla("tickets", f"csat en escala 1-10 desde {cambio:%Y-%m-%d}", "corregir (techo de x/2)", int(nueva.sum()),
            "El caso mide CSAT en 1-5: un 8 de la escala nueva no es un 8 de la vieja")
    df["csat"] = csat.mask(nueva, (csat + 1) // 2)   # techo(x / 2) en enteros

    df["subcategoria"], _ = mapear(df["subcategoria"], SUBCATEGORIAS)
    return df[["ticket_id", "cliente_id", "canal", "fecha_apertura", "fecha_cierre", "cierre_invalido",
               "categoria_original", "intencion", "subcategoria", "texto", "agente_id", "tiempo_espera_seg",
               "resuelto", "csat", "reabierto"]]


def _faq(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "faq.csv")
    r.perfil_antes("faq", df)
    df["articulo_id"] = texto(df["articulo_id"])
    df["pregunta"] = texto(df["pregunta"])

    crudo = df["respuesta"].astype(str)
    enlace = crudo.str.contains(r"<a\s", regex=True)
    r.regla("faq", "respuesta con etiquetas HTML crudas (<p>)", "corregir", int(crudo.str.contains("<").sum()),
            "El cliente vería «<p>» en el chat; se dejan solo las palabras")
    r.regla("faq", "respuesta con enlace «Ver mas» a /ayuda/NNN", "descartar el enlace", int(enlace.sum()),
            "Son enlaces del WordPress viejo que ya no existen (RF11): un enlace roto es peor que ninguno")
    respuesta = crudo.str.replace(r"<a\s[^>]*>.*?</a>", " ", regex=True).str.replace(r"<[^>]+>", " ", regex=True)
    df["respuesta"] = respuesta.str.replace(r"\s+", " ", regex=True).str.strip()

    # DESAFÍO C5 · la columna categoria del FAQ no describe el artículo («Cuando vence mi boleta» viene como
    # «agenda_tecnico»). La intención se saca de la pregunta con TEMAS_FAQ y la categoría declarada se guarda
    # solo para mostrar cuánto no coincide. Además: vigente vacío se trata como NO vigente, y los artículos
    # que mencionan un plan descontinuado se marcan y el dominio no los usa. ¿Quién debería corregir el FAQ?
    df["categoria_declarada"], _ = mapear(df["categoria"], INTENCIONES)
    norm = df["pregunta"].fillna("").map(variables.normalizar)
    df["tema"], df["intencion"] = pd.NA, pd.NA
    for patron, tema, intencion in reversed(TEMAS_FAQ):   # el primero de la lista gana
        coincide = norm.str.contains(patron, regex=True)
        df.loc[coincide, "tema"], df.loc[coincide, "intencion"] = tema, intencion
    sin_tema = df["intencion"].isna()
    if sin_tema.any():
        r.nota(f"faq: {int(sin_tema.sum())} artículos sin tema reconocido: {df.loc[sin_tema, 'pregunta'].tolist()[:5]}")
    r.regla("faq", "categoría declarada distinta de lo que dice la pregunta", "corregir (intención según la pregunta)",
            int((df["categoria_declarada"].fillna("") != df["intencion"].fillna("")).sum()),
            "Responder con la categoría declarada mandaría «cómo me porto» a quien pregunta por su TV (C5)")

    vistas = entero(df["vistas_12m"])
    r.regla("faq", "vistas_12m vacío", "imputar 0", int(vistas.isna().sum()),
            "Solo se usa para ordenar: un artículo sin medición va al final, no desaparece")
    df["vistas_12m"] = vistas.fillna(0)


    vigente = booleano(df["vigente"])
    r.regla("faq", "vigente vacío", "imputar 0 (no vigente)", int(vigente.isna().sum()),
            "RO5: toda respuesta la aprueba negocio. Si nadie dijo que sigue aplicando, no se publica (C5)")
    df["vigente"] = vigente.fillna(0)
    descontinuado = df["respuesta"].str.contains("|".join(map(re.escape, PLANES_DESCONTINUADOS)), regex=True)
    r.regla("faq", "artículo que menciona un plan descontinuado (R7)", "marcar", int(descontinuado.sum()),
            "Una respuesta para un plan que no se vende está mal para casi todos; el dominio no la usa")
    df["plan_descontinuado"] = descontinuado.astype(int)

    # Casi duplicados: misma pregunta salvo el relleno («de TV», «empresa», «paso a paso»). De cada grupo
    # se conserva UNA: la publicable (vigente y sin plan descontinuado) más vista.
    sin_puntuacion = df["pregunta"].fillna("").map(lambda p: " ".join(variables.palabras(p)))
    df["grupo"] = sin_puntuacion.str.replace(RELLENO_FAQ, "", regex=True).str.strip()
    df["_publicable"] = ((df["vigente"] == 1) & (df["plan_descontinuado"] == 0)).astype(int)
    orden = df.sort_values(["_publicable", "vistas_12m", "articulo_id"], ascending=[False, False, True])
    df["duplicado"] = orden.duplicated(subset=["grupo"]).reindex(df.index).astype(int)
    r.regla("faq", "preguntas casi idénticas («Como devuelvo el equipo movil» / «... empresa»)", "marcar",
            int(df["duplicado"].sum()), f"Quedan {df['grupo'].nunique()} preguntas distintas; de cada una se ofrece "
            "la publicable más vista, las demás no se muestran al cliente")

    edicion = fecha(df["ultima_edicion"], ["%Y-%m-%d"])
    r.nota(f"faq: {int((edicion.dt.year <= 2021).sum())} artículos sin editar desde 2021 o antes.")
    df["ultima_edicion"] = edicion.dt.date
    util = (df["vigente"] == 1) & (df["duplicado"] == 0) & (df["plan_descontinuado"] == 0) & df["intencion"].notna()
    r.nota(f"faq: quedan {int(util.sum())} de {len(df)} artículos utilizables; por intención: "
           f"{df[util]['intencion'].value_counts().sort_index().to_dict()}")
    return df[["articulo_id", "pregunta", "respuesta", "intencion", "tema", "categoria_declarada", "vigente",
               "duplicado", "plan_descontinuado", "vistas_12m", "ultima_edicion"]]


def _conversaciones(crudos: Path, r: Reporte, plantillas: dict) -> pd.DataFrame:
    df = leer(crudos / "conversaciones.csv")
    r.perfil_antes("conversaciones", df)
    n = len(df)
    df = df.drop_duplicates()
    r.regla("conversaciones", "conversaciones duplicadas por la migración de 2024", "descartar", n - len(df),
            "La misma conversación dos veces duplica turnos y derivaciones en cualquier indicador")
    df["conversacion_id"] = texto(df["conversacion_id"])
    df = df.drop_duplicates(subset=["conversacion_id"], keep="first")
    df["cliente_id"] = texto(df["cliente_id"])
    crudo = texto(df["canal"])
    df["canal"], _ = mapear(df["canal"], CANALES_CHAT)
    r.regla("conversaciones", "canal inconsistente («WA», «sitio_web», «WEB»)", "corregir",
            int((crudo.notna() & (crudo != df["canal"])).sum()), "Mapa a web y whatsapp")
    inicio, fin = _fecha_hora(df["inicio"]), _fecha_hora(df["fin"])
    df["inicio"], df["fin"] = _iso(inicio), _iso(fin)

    df["turnos"] = entero(df["turnos"])
    bucle = (df["turnos"] > 40).fillna(False)
    r.regla("conversaciones", "más de 40 turnos (bucle del bot anterior)", "marcar", int(bucle.sum()),
            "No es una conversación larga, es el bot repitiendo lo mismo: se excluye de cualquier promedio de turnos")
    df["bucle"] = bucle.astype(int)

    clave = clave_normalizada(df["intencion_detectada"])
    df["intencion_bot"] = clave.map(lambda v: INTENCIONES_BOT.get(v, pd.NA) if pd.notna(v) else pd.NA).astype("string")
    r.regla("conversaciones", "intencion_detectada «desconocida», «unknown», «general» o vacía",
            "marcar como desconocido",
            int(df["intencion_bot"].isna().sum()), "Es lo que el bot viejo no entendió; no es una intención")
    for columna in ("derivada_a_humano", "resuelta"):
        df[columna] = booleano(df[columna])
        r.nota(f"conversaciones.{columna}: {int(df[columna].isna().sum())} vacíos que se dejan desconocidos "
               "(vacío no es «no»).")
    df["idioma"] = texto(df["idioma"]).str.lower()

    crudo = df["transcripcion"].astype(str)
    df["transcripcion"] = _anonimizar_y_contar(crudo, "conversaciones", "transcripcion", r)

    # DESAFÍO C4 (segunda parte) · las conversaciones NO se usan para entrenar: su etiqueta la puso el bot
    # que se está reemplazando. Esta nota mide cuánto acertaba, con el primer mensaje del cliente.
    primero = df["transcripcion"].str.extract(r"^cliente: (.*?)(?: \|\| |$)")[0].fillna("").map(variables.normalizar)
    real = primero.map(plantillas)
    comparables = real.notna() & df["intencion_bot"].notna()
    acierto = (real[comparables] == df.loc[comparables, "intencion_bot"]).mean()
    r.nota(f"conversaciones: el bot anterior coincide con la intención del primer mensaje del cliente en "
           f"{acierto:.1%} de {int(comparables.sum())} conversaciones comparables, y no entendió el "
           f"{df['intencion_bot'].isna().mean():.0%}. Entrenar con su etiqueta sería copiar sus errores.")
    return df[["conversacion_id", "cliente_id", "canal", "inicio", "fin", "turnos", "bucle", "intencion_bot",
               "derivada_a_humano", "resuelta", "idioma", "transcripcion"]]


def preparar(crudos: Path, r: Reporte):
    tickets = _tickets(crudos, r)
    apertura = pd.to_datetime(tickets["fecha_apertura"], format="%Y-%m-%d %H:%M:%S%z", utc=True)
    corte = apertura.max().tz_convert(ZONA_CHILE).normalize() + pd.Timedelta(days=1)   # día de la extracción
    clientes = _clientes(crudos, r, corte)
    faq = _faq(crudos, r)

    huerfano = tickets["cliente_id"].notna() & ~tickets["cliente_id"].isin(clientes["cliente_id"])
    r.regla("tickets", "cliente_id que no existe en clientes.csv", "conservar", int(huerfano.sum()),
            "El ticket existió aunque el cliente no esté en la muestra; el texto y la intención siguen sirviendo")

    # DESAFÍO C4 · se entrena solo con tickets que tienen una intención (sin «otros» ni vacíos). El modelo
    # nunca vio un «hola»: frente a eso su confianza será baja y el dominio lo cuenta como intento fallido.
    # ¿Agregarías «otros» como clase para que el bot pida más detalle en vez de adivinar?
    etiquetados = tickets[tickets["intencion"].notna()].reset_index(drop=True)
    X = pd.DataFrame([variables.vectorizar({"texto": t}) for t in etiquetados["texto"]], columns=variables.COLUMNAS)
    X["y"] = etiquetados["intencion"].astype(str).to_numpy()
    X["particion"] = particion_estratificada(X["y"].tolist())
    r.nota(f"Etiquetados: {len(X)} de {len(tickets)} tickets; intenciones: {X['y'].value_counts().to_dict()}")

    # DESAFÍO M4 · los tickets se escriben con plantillas: muchos mensajes de prueba son idénticos a uno de
    # entrenamiento. La métrica de prueba mide «reconoce lo que ya vio», no «entiende frases nuevas».
    normal = etiquetados["texto"].map(variables.normalizar)
    vistos = set(normal[X["particion"] == "entrenamiento"])
    prueba = normal[X["particion"] == "prueba"]
    r.nota(f"Prueba: {prueba.isin(vistos).mean():.1%} de los {len(prueba)} mensajes de prueba aparecen idénticos "
           f"(tras normalizar) en entrenamiento. Hay {normal.nunique()} textos distintos en {len(normal)} tickets.")

    plantillas = etiquetados.assign(n=normal).groupby("n")["intencion"].agg(lambda s: s.mode().iloc[0]).to_dict()
    conversaciones = _conversaciones(crudos, r, plantillas)
    return {"clientes": clientes, "faq": faq, "tickets": tickets, "conversaciones": conversaciones}, X
