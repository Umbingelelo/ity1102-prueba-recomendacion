"""Caso 3 · Kipu Pagos · tratamiento de transacciones, usuarios, dispositivos y lista negra.

Las líneas marcadas «DESAFÍO» son decisiones que tu equipo tiene que revisar, cambiar si no está de
acuerdo y defender con su número. Están explicadas en casos/fraude.md.
"""
from pathlib import Path

import pandas as pd

from comun.caracteristicas import fraude as variables
from datos.casos import particion_estratificada
from datos.limpieza import Reporte, booleano, clave_normalizada, entero, fecha, leer, mapear, monto_clp, \
    monto_decimal, texto

CLAVES = {
    "usuarios": ["usuario_id"],
    "dispositivos": ["dispositivo_id"],
    "lista_negra": ["tipo", "valor"],
    "transacciones": ["transaccion_id"],
}

# DESAFÍO F1 · tasa fija para convertir USD a CLP. ¿De dónde sale? ¿La actualizarías? Defiéndela.
TASA_USD_CLP = 950

PAISES = {"cl": "CL", "chile": "CL", "ar": "AR", "argentina": "AR", "pe": "PE", "peru": "PE",
          "br": "BR", "brasil": "BR", "brazil": "BR", "co": "CO", "colombia": "CO", "us": "US", "usa": "US",
          "eeuu": "US", "estados_unidos": "US", "ve": "VE", "venezuela": "VE", "ru": "RU", "rusia": "RU",
          "russia": "RU", "ng": "NG", "nigeria": "NG", "mx": "MX", "mexico": "MX"}
SEGMENTOS = {"persona": "persona", "individuo": "persona", "comercio_pequeno": "comercio_pequeno",
             "pyme": "comercio_pequeno", "comercio_grande": "comercio_grande", "empresa": "comercio_grande"}
CANALES = {"app": "app", "movil": "app", "web": "web", "pos": "pos", "punto_venta": "pos", "api": "api"}
TIPOS_DISPOSITIVO = {"android": "android", "ios": "ios", "web": "web", "pos": "pos"}
TIPOS_LISTA = {"ip": "ip", "dispositivo": "dispositivo", "device": "dispositivo", "comercio": "comercio",
               "merchant": "comercio", "tarjeta": "tarjeta", "card": "tarjeta"}
DOMINIOS_DESECHABLES = {"mailinator.com", "guerrillamail.com", "tempmail.io", "10minutemail.com", "yopmail.com"}


def _usuarios(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "usuarios.csv")
    r.perfil_antes("usuarios", df)
    n = len(df)
    df = df.drop_duplicates()
    r.regla("usuarios", "filas repetidas idénticas", "descartar", n - len(df),
            "Misma persona exportada dos veces: conservar una no pierde información")
    df["usuario_id"] = texto(df["usuario_id"])
    df = df.drop_duplicates(subset=["usuario_id"], keep="first")

    crudo_pais = texto(df["pais"])
    df["pais"], sin_mapa = mapear(df["pais"], PAISES)
    r.regla("usuarios", "país escrito en ISO2 y en nombre completo («CL», «chile », «CHILE»)", "corregir",
            int((crudo_pais.notna() & (crudo_pais != df["pais"])).sum()),
            "Se lleva todo a ISO2 con un mapa escrito a mano; lo que no está en el mapa queda nulo")
    if len(sin_mapa):
        r.nota(f"usuarios.pais sin mapa: {dict(sin_mapa)}")
    df["segmento"], _ = mapear(df["segmento"], SEGMENTOS)

    kyc = entero(df["nivel_kyc"])
    fuera = kyc.notna() & ~kyc.between(0, 3)
    r.regla("usuarios", "nivel_kyc fuera de 0 a 3 (ej. -1)", "marcar como desconocido", int(fuera.sum()),
            "Un nivel inválido no es nivel 0: se deja nulo y el modelo lo ve como «no se sabe»")
    df["nivel_kyc"] = kyc.mask(fuera)

    df["verificado"] = booleano(df["verificado"])
    df["telefono_verificado"] = booleano(df["telefono_verificado"])

    edad = entero(df["edad_cuenta_dias"])
    negativa = edad.notna() & (edad < 0)
    r.regla("usuarios", "edad_cuenta_dias negativa", "marcar como desconocido", int(negativa.sum()),
            "Una cuenta no puede tener edad negativa; corregirla con la fecha de registro mezclaría dos errores")
    df["edad_cuenta_dias"] = edad.mask(negativa)

    previas = entero(df["transacciones_previas"])
    r.regla("usuarios", "transacciones_previas vacía", "imputar 0", int(previas.isna().sum()),
            "El diccionario de datos dice que el nulo significa cero")
    df["transacciones_previas"] = previas.fillna(0)

    dominio = texto(df["email_dominio"]).str.lower()
    df["email_desechable"] = dominio.isin(DOMINIOS_DESECHABLES).astype("Int64").mask(dominio.isna())

    df["fecha_registro"] = fecha(df["fecha_registro"], ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]).dt.date
    return df[["usuario_id", "fecha_registro", "pais", "segmento", "nivel_kyc", "verificado",
               "telefono_verificado", "edad_cuenta_dias", "transacciones_previas", "email_desechable"]]


def _dispositivos(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "dispositivos.csv")
    r.perfil_antes("dispositivos", df)
    df["dispositivo_id"] = texto(df["dispositivo_id"])
    df["tipo"], _ = mapear(df["tipo"], TIPOS_DISPOSITIVO)
    df["usuarios_distintos"] = entero(df["usuarios_distintos"])
    emulador = booleano(df["emulador"])
    r.regla("dispositivos", "emulador vacío", "marcar como desconocido", int(emulador.isna().sum()),
            "Vacío no significa «no es emulador»: significa que no se midió")
    df["emulador"] = emulador
    df["pais_declarado"], _ = mapear(df["pais_declarado"], PAISES)
    return df[["dispositivo_id", "tipo", "usuarios_distintos", "emulador", "pais_declarado"]]


def _lista_negra(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "lista_negra.csv")
    r.perfil_antes("lista_negra", df)
    df["tipo"], _ = mapear(df["tipo"], TIPOS_LISTA)
    df["valor"] = texto(df["valor"])
    vigente = booleano(df["vigente"])
    # DESAFÍO F2 · una entrada con «vigente» vacío ¿bloquea o no? Aquí se trata como vigente: ante la
    # duda se manda a revisión. Hay entradas de 2019 nunca revisadas: ¿las dejarías?
    r.regla("lista_negra", "vigente vacío", "imputar 1 (vigente)", int(vigente.isna().sum()),
            "Ante la duda la regla dura se aplica y un analista decide; dejar pasar un fraude listado cuesta más")
    df["vigente"] = vigente.fillna(1)
    df["fecha_alta"] = fecha(df["fecha_alta"], ["%Y-%m-%d", "%d/%m/%Y"]).dt.date
    n = len(df)
    df = df.dropna(subset=["tipo", "valor"]).drop_duplicates(subset=["tipo", "valor"])
    r.regla("lista_negra", "tipo o valor vacío, o la misma entrada dos veces", "descartar", n - len(df),
            "Una entrada sin valor no se puede aplicar; una repetida no agrega nada")
    return df[["tipo", "valor", "motivo", "fecha_alta", "vigente"]].assign(motivo=texto(df["motivo"]))


def _transacciones(crudos: Path, r: Reporte) -> pd.DataFrame:
    df = leer(crudos / "transacciones.csv")
    r.perfil_antes("transacciones", df)

    n = len(df)
    df = df.drop_duplicates()
    r.regla("transacciones", "filas idénticas en todas las columnas", "descartar", n - len(df),
            "Duplicado del sistema: mismo id, mismo segundo, mismo todo. Contarlo dos veces infla el volumen")
    clave = ["usuario_id", "comercio_id", "monto"]
    reintento = df.duplicated(subset=clave, keep=False)
    r.regla("transacciones", "misma persona, comercio y monto en otra fila (no idéntica)", "conservar",
            int(df.duplicated(subset=clave).sum()),
            "Son reintentos legítimos: son eventos distintos y velocidad es justamente una señal de fraude")
    df["es_reintento"] = reintento.astype(int)

    for c in ("transaccion_id", "usuario_id", "comercio_id", "dispositivo_id"):
        df[c] = texto(df[c])

    ts = fecha(df["timestamp"], formatos_locales=["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"],
               formatos_con_zona=["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S%z"])
    r.regla("transacciones", "cuatro formatos de fecha, unos en UTC y otros en hora de Chile", "corregir",
            int(ts.notna().sum()), "Se reconoce cada formato por separado y todo queda en hora de Chile")
    df["ts_local"] = ts
    df["hora_local"] = ts.dt.hour.astype("Int64")

    moneda = texto(df["moneda"]).str.upper()
    crudo = texto(df["monto"])
    # DESAFÍO F3 · sin moneda declarada: si el monto trae dos decimales («12.50» o «12,50») se asume USD.
    parece_usd = crudo.str.fullmatch(r"\$?-?\d+[.,]\d{1,2}").fillna(False)
    inferida = moneda.isna()
    r.regla("transacciones", "moneda vacía", "imputar según el formato del monto", int(inferida.sum()),
            "Dos decimales es formato de dólar; puntos de miles es formato de peso chileno")
    moneda = moneda.mask(inferida & parece_usd, "USD").mask(inferida & ~parece_usd, "CLP")
    clp = monto_clp(crudo)
    usd = monto_decimal(crudo)
    df["moneda_original"] = moneda
    df["monto_clp"] = clp.where(moneda == "CLP", usd * TASA_USD_CLP).round()
    r.regla("transacciones", "montos en USD mezclados con CLP", "corregir", int((moneda == "USD").sum()),
            f"Se convierten a CLP con tasa fija {TASA_USD_CLP}; sumar sin convertir no significa nada")

    invalido = df["monto_clp"].isna() | (df["monto_clp"] <= 0)
    r.regla("transacciones", "monto cero, negativo o ilegible", "descartar", int(invalido.sum()),
            "No es un pago que haya que evaluar: un monto negativo es una devolución, otro flujo")
    df = df[~invalido].copy()

    df["canal"], sin_mapa = mapear(df["canal"], CANALES)
    if len(sin_mapa):
        r.nota(f"transacciones.canal sin mapa: {dict(sin_mapa)}")
    df["pais_transaccion"], _ = mapear(df["pais_transaccion"], PAISES)
    df["intentos_previos_1h"] = entero(df["intentos_previos_1h"])

    lat = pd.to_numeric(texto(df["latitud"]), errors="coerce")
    lon = pd.to_numeric(texto(df["longitud"]), errors="coerce")
    isla = (lat == 0) & (lon == 0)
    r.regla("transacciones", "coordenadas (0, 0), en el Golfo de Guinea", "marcar como desconocido",
            int(isla.sum()), "Es un faltante disfrazado de valor válido")
    df["latitud"], df["longitud"] = lat.mask(isla), lon.mask(isla)

    df["es_fraude"] = booleano(df["es_fraude"])
    r.regla("transacciones", "es_fraude vacío", "conservar vacío (no revisada)", int(df["es_fraude"].isna().sum()),
            "Vacío significa que nadie la revisó, no que sea legítima. No se entrena con ellas")
    # revisado_por_analista y motivo_bloqueo se llenan DESPUÉS de decidir: son fuga de información.
    # resultado_autorizacion también ocurre después. Ninguna de las tres sale de aquí.
    r.regla("transacciones", "revisado_por_analista, motivo_bloqueo, resultado_autorizacion", "descartar columnas",
            len(df), "Fuga de información: en el momento de decidir no existen. motivo_bloqueo está lleno solo en fraudes")
    # El número de tarjeta (aunque venga enmascarado) no entra al modelo ni a la base (RNF5)
    return df[["transaccion_id", "usuario_id", "comercio_id", "dispositivo_id", "ts_local", "hora_local",
               "monto_clp", "moneda_original", "canal", "pais_transaccion", "intentos_previos_1h", "latitud",
               "longitud", "es_reintento", "es_fraude"]]


def preparar(crudos: Path, r: Reporte):
    usuarios = _usuarios(crudos, r)
    dispositivos = _dispositivos(crudos, r)
    lista = _lista_negra(crudos, r)
    tx = _transacciones(crudos, r)

    # Integración: cada transacción con su usuario y su dispositivo
    unido = tx.merge(usuarios, on="usuario_id", how="left").merge(dispositivos, on="dispositivo_id", how="left")
    r.regla("transacciones", "usuario que no existe en usuarios.csv", "conservar, con variables de usuario desconocidas",
            int((~tx["usuario_id"].isin(usuarios["usuario_id"])).sum()),
            "En producción también llegan usuarios sin perfil: el modelo tiene que saber decidir sin él")
    unido["pais_distinto"] = (unido["pais_transaccion"] != unido["pais"]).astype("Int64")
    unido.loc[unido["pais"].isna() | unido["pais_transaccion"].isna(), "pais_distinto"] = pd.NA

    # DESAFÍO F4 · se entrena solo con lo revisado por un analista (1.260 filas aprox., ~11% fraude).
    # Es un sesgo: se revisa lo que el motor viejo marcó. ¿Qué alternativa tienes y qué cuesta?
    etiquetadas = unido[unido["es_fraude"].notna()].reset_index(drop=True)
    filas = etiquetadas.astype(object).where(etiquetadas.notna(), None).to_dict("records")
    X = pd.DataFrame([variables.vectorizar(f) for f in filas], columns=variables.COLUMNAS)
    X["y"] = etiquetadas["es_fraude"].astype(int).to_numpy()
    X["particion"] = particion_estratificada(X["y"].tolist())
    tasa = X["y"].mean()
    r.nota(f"Etiquetadas: {len(X)} de {len(tx)} transacciones; fraude {X['y'].sum()} ({tasa:.2%} de las revisadas, "
           f"{X['y'].sum() / len(tx):.3%} del archivo). En producción la tasa es 0,012%: cualquier umbral o costo "
           f"calculado con estas tasas está mal por dos órdenes de magnitud (R3 del caso).")

    tx_tabla = tx.assign(ts_local=tx["ts_local"].dt.strftime("%Y-%m-%d %H:%M:%S%z"))
    return {"usuarios": usuarios, "dispositivos": dispositivos, "lista_negra": lista,
            "transacciones": tx_tabla}, X
