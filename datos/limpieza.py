"""Herramientas de limpieza que sirven para los tres casos.

Cada función hace UNA cosa y devuelve cuántas filas tocó, para que el reporte pueda decir «esta regla
cambió N filas». Una regla de limpieza sin su número no se puede defender.
"""
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

ZONA_CHILE = "America/Santiago"

# Textos que significan «no hay dato» pero que pandas lee como un valor más (paso 3.1 de L2B)
CENTINELAS = {"-", "--", "n/a", "na", "null", "none", "unknown", "desconocido", "desconocida", "error",
              "sin categoria", "n/d", "?", "nan"}

VERDADERO = {"1", "true", "si", "sí", "s", "yes", "y", "verdadero"}
FALSO = {"0", "false", "no", "n", "falso"}


def leer(ruta: Path) -> pd.DataFrame:
    """Lee todo como texto y sin convertir vacíos: así se ve el dato tal como vino."""
    return pd.read_csv(ruta, dtype=str, keep_default_na=False)


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def texto(serie: pd.Series) -> pd.Series:
    """Quita espacios a los lados y convierte vacíos y centinelas en nulo de verdad (pd.NA)."""
    s = serie.astype("string").str.strip()
    return s.mask(s.str.lower().isin(CENTINELAS) | (s == ""))


def clave_normalizada(serie: pd.Series) -> pd.Series:
    """'  Falla Técnica ' -> 'falla_tecnica'. Sirve para comparar categorías escritas de mil formas."""
    s = texto(serie)
    return s.map(lambda v: re.sub(r"[\s\-\.]+", "_", sin_tildes(v).lower()).strip("_") if pd.notna(v) else v,
                 na_action="ignore").astype("string")


def mapear(serie: pd.Series, mapa: dict) -> tuple[pd.Series, pd.Series]:
    """Normaliza y traduce con un mapa escrito a mano. Devuelve (resultado, variantes_sin_mapa).

    Lo que no está en el mapa queda nulo y aparece en variantes_sin_mapa con su conteo: así se ve qué
    falta agregar al mapa en vez de perderlo en silencio.
    """
    clave = clave_normalizada(serie)
    resultado = clave.map(lambda v: mapa.get(v, pd.NA) if pd.notna(v) else pd.NA).astype("string")
    sin_mapa = clave[resultado.isna() & clave.notna()].value_counts()
    return resultado, sin_mapa


def booleano(serie: pd.Series) -> pd.Series:
    """1/0/si/no/TRUE/vacío -> 1, 0 o nulo. Vacío NO es falso: es «no se sabe»."""
    s = texto(serie).str.lower()
    return s.map(lambda v: 1 if v in VERDADERO else (0 if v in FALSO else pd.NA), na_action="ignore").astype("Int64")


def entero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(texto(serie), errors="coerce").astype("Float64").round().astype("Int64")


def monto_clp(serie: pd.Series) -> pd.Series:
    """'$9.570' -> 9570. En pesos chilenos el punto es separador de miles y no hay decimales."""
    s = texto(serie).str.replace("$", "", regex=False).str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False).str.replace(" ", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def monto_decimal(serie: pd.Series) -> pd.Series:
    """'$12,50' o '12.50' -> 12.5. Para monedas con decimales (USD)."""
    s = texto(serie).str.replace("$", "", regex=False).str.replace(",", ".", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce")


def fecha(serie: pd.Series, formatos_locales: list[str], formatos_con_zona: list[str] = ()) -> pd.Series:
    """Convierte a fecha y hora de Chile, reconociendo cada formato por separado.

    formatos_locales: escritos en hora de Chile sin decirlo (ej. '%Y-%m-%d %H:%M:%S').
    formatos_con_zona: traen Z o -03:00 (ej. '%Y-%m-%dT%H:%M:%S%z').
    No se usa format="mixed" ni dayfirst: adivinar no es limpiar (L2B, paso 3.3).
    """
    s = texto(serie)
    salida = pd.Series(pd.NaT, index=s.index, dtype=f"datetime64[ns, {ZONA_CHILE}]")
    for f in formatos_con_zona:
        falta = salida.isna() & s.notna()
        if falta.any():
            p = pd.to_datetime(s[falta], format=f, errors="coerce", utc=True)
            salida.loc[falta] = p.dt.tz_convert(ZONA_CHILE)
    for f in formatos_locales:
        falta = salida.isna() & s.notna()
        if falta.any():
            p = pd.to_datetime(s[falta], format=f, errors="coerce")
            salida.loc[falta] = p.dt.tz_localize(ZONA_CHILE, ambiguous="NaT", nonexistent="shift_forward")
    return salida


def perfil(df: pd.DataFrame) -> dict:
    """Filas, columnas, nulos de verdad (vacíos + centinelas) y duplicados exactos."""
    nulos = {}
    for c in df.columns:
        if pd.api.types.is_string_dtype(df[c]) or pd.api.types.is_object_dtype(df[c]):
            n = int(texto(df[c].astype("string")).isna().sum())
        else:
            n = int(df[c].isna().sum())
        if n:
            nulos[c] = n
    return {"filas": int(len(df)), "columnas": int(df.shape[1]), "nulos": nulos,
            "nulos_total": int(sum(nulos.values())), "duplicados_exactos": int(df.duplicated().sum())}


class Reporte:
    """Junta el perfil antes y después de cada tabla y cada regla aplicada con su conteo."""

    def __init__(self, caso: str):
        self.caso = caso
        self.antes, self.despues, self.reglas, self.notas = {}, {}, [], []

    def perfil_antes(self, nombre: str, df: pd.DataFrame):
        self.antes[nombre] = perfil(df)

    def perfil_despues(self, nombre: str, df: pd.DataFrame):
        self.despues[nombre] = perfil(df)

    def regla(self, tabla: str, problema: str, decision: str, filas: int, porque: str):
        """decision: corregir, descartar, marcar o imputar."""
        self.reglas.append({"tabla": tabla, "problema": problema, "decision": decision,
                            "filas": int(filas), "porque": porque})

    def nota(self, texto: str):
        self.notas.append(texto)

    def escribir(self, carpeta: Path):
        datos = {"caso": self.caso, "antes": self.antes, "despues": self.despues,
                 "reglas": self.reglas, "notas": self.notas}
        (carpeta / "reporte.json").write_text(json.dumps(datos, indent=2, ensure_ascii=False))
        lineas = [f"# Reporte del tratamiento de datos · caso {self.caso}", "",
                  "Generado por `datos/preparar.py`. Copia estas tablas al capítulo 8.4 del arc42.", "",
                  "## Perfil antes y después", "",
                  "| Tabla | Filas antes | Filas después | Nulos antes | Nulos después | Duplicados antes | Duplicados después |",
                  "|---|---|---|---|---|---|---|"]
        for t in self.antes:
            a, d = self.antes[t], self.despues.get(t, {})
            lineas.append(f"| {t} | {a['filas']} | {d.get('filas', '—')} | {a['nulos_total']} | "
                          f"{d.get('nulos_total', '—')} | {a['duplicados_exactos']} | {d.get('duplicados_exactos', '—')} |")
        lineas += ["", "## Reglas de limpieza", "", "| Tabla | Problema | Decisión | Filas | Por qué |",
                   "|---|---|---|---|---|"]
        lineas += [f"| {r['tabla']} | {r['problema']} | {r['decision']} | {r['filas']} | {r['porque']} |"
                   for r in self.reglas]
        if self.notas:
            lineas += ["", "## Notas", ""] + [f"- {n}" for n in self.notas]
        (carpeta / "REPORTE.md").write_text("\n".join(lineas) + "\n")
