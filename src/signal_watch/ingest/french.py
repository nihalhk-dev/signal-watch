"""Descarga y lectura de los factores de Kenneth French (datos reales).

Qué trae: los tres factores de Fama-French en frecuencia DIARIA, desde 1926.
    Mkt-RF · SMB · HML · RF

Por qué solo el fichero diario, y no el mensual:
    La métrica que vigilamos es un Sharpe MENSUAL calculado con los días
    hábiles de cada mes (ver `processing/factor_returns.py`). Se construye
    desde los retornos diarios, así que el fichero mensual no aporta nada
    y sería una segunda cosa que puede romperse.

Las DOS trampas de este fichero, que cuestan un bug cada una si no se saben:

  1. NO es un CSV limpio. Lleva varias líneas de texto de cortesía arriba
     (quién lo generó, con qué base de datos) y una línea de copyright
     abajo. Un `pd.read_csv` directo falla o, peor, se traga la cabecera
     como si fueran datos. Aquí no se usa `skiprows=N` con un número fijo,
     porque ese número cambia cuando French reedita el fichero: se busca
     el bloque de datos por su FORMA (líneas que empiezan por ocho dígitos
     seguidos de una coma). Robusto a que muevan el texto de arriba.

  2. Los valores vienen en PORCENTAJE. `0.53` significa 0,53%, no 53%.
     Si no se divide por 100, cualquier Sharpe sale 100 veces mal — el
     mismo tipo de error que el factor ×100 del PSI sintético, que ya nos
     costó una tanda entera de resultados inservibles. Aquí se convierte
     a decimal en la lectura, UNA vez, y a partir de ahí todo el proyecto
     trabaja en decimales.

  También: los valores que faltan se marcan con -99.99 o -999, no con
  celdas vacías. Si no se traducen a NaN, entran en las medias como si
  fueran retornos de -9.999%.

Uso:
    python -m signal_watch.ingest.french     # descarga + diagnóstico
    from signal_watch.ingest.french import cargar_factores_diarios
"""

from __future__ import annotations

import re
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from signal_watch.ingest.checksums import registrar_descarga, verificar_descarga
from signal_watch.paths import PATHS

# ── Fuente ───────────────────────────────────────────────────────────

FUENTE = "kenneth_french"
URL_FACTORES_DIARIOS = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)
NOMBRE_ZIP = "F-F_Research_Data_Factors_daily_CSV.zip"

# Códigos con los que French marca "no hay dato". No son retornos.
CODIGOS_FALTANTE = (-99.99, -999.0)

# Una línea de datos diaria empieza por una fecha AAAAMMDD y una coma.
_PATRON_FILA = re.compile(r"^\s*(\d{8})\s*,(.*)$")


def carpeta_french() -> Path:
    """`data/raw/french/` — creada si no existe."""
    return PATHS.ensure(PATHS.data_raw / "french")


# ── Descarga ─────────────────────────────────────────────────────────

def descargar_factores_diarios(forzar: bool = False) -> Path:
    """Descarga el zip a `data/raw/french/` y lo registra en el manifiesto.

    Si el fichero ya está y su hash coincide con el registrado, NO se
    vuelve a descargar: `data/raw/` es una capa inmutable por diseño, y
    rebajarse el fichero cada vez introduciría el riesgo de que los
    resultados cambien por debajo sin que nadie lo decida. Para forzar una
    actualización consciente, `forzar=True`.
    """
    destino = carpeta_french() / NOMBRE_ZIP

    if destino.exists() and not forzar:
        if verificar_descarga(destino):
            print(f"Ya está descargado y el hash coincide: {destino.name}")
            return destino
        print(
            f"AVISO: {destino.name} está en disco pero su hash no coincide con "
            "el manifiesto (o no estaba registrado). Se vuelve a registrar."
        )
        registrar_descarga(destino, URL_FACTORES_DIARIOS, FUENTE)
        return destino

    print(f"Descargando {URL_FACTORES_DIARIOS} ...")
    # urllib, no requests: requests no está entre las dependencias del
    # proyecto y no merece añadir una por una descarga de un fichero.
    peticion = urllib.request.Request(
        URL_FACTORES_DIARIOS,
        headers={"User-Agent": "signal-watch/0.1 (TFM; descarga de datos públicos)"},
    )
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        contenido = respuesta.read()

    destino.write_bytes(contenido)
    entrada = registrar_descarga(destino, URL_FACTORES_DIARIOS, FUENTE)
    print(f"  Guardado: {destino}")
    print(f"  {entrada['bytes']:,} bytes · sha256[:12] = {entrada['sha256_12']}")
    return destino


# ── Lectura ──────────────────────────────────────────────────────────

def _texto_del_zip(ruta_zip: Path) -> str:
    """Saca el único CSV que hay dentro del zip, como texto."""
    with zipfile.ZipFile(ruta_zip) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(
                f"Esperaba exactamente un CSV dentro de {ruta_zip.name}, "
                f"encontré {csvs}"
            )
        crudo = z.read(csvs[0])
    # utf-8-sig se come el BOM si lo hubiera; errors='replace' evita que un
    # carácter raro en el texto de cortesía tumbe la lectura de los datos.
    return crudo.decode("utf-8-sig", errors="replace")


def parsear_factores_diarios(ruta_zip: Path | str) -> pd.DataFrame:
    """Convierte el zip de French en un DataFrame limpio, en DECIMALES.

    Devuelve: índice `fecha` (DatetimeIndex, ordenado, sin duplicados) y
    columnas `mkt_rf`, `smb`, `hml`, `rf`, todas en decimal (0,0053 = 0,53%).

    Estrategia del parser: se localiza la línea de cabecera por su
    contenido (`Mkt-RF`) y las filas de datos por su forma (ocho dígitos
    y una coma). Todo lo demás del fichero —el texto de arriba, el
    copyright de abajo, líneas en blanco— se ignora sin tener que saber
    cuántas líneas ocupa.
    """
    ruta_zip = Path(ruta_zip)
    lineas = _texto_del_zip(ruta_zip).splitlines()

    # 1) la cabecera: la línea que nombra las columnas
    cabecera = None
    for linea in lineas:
        if "Mkt-RF" in linea:
            cabecera = [c.strip() for c in linea.split(",")]
            break
    if cabecera is None:
        raise ValueError(
            f"No encuentro la línea de cabecera (la que contiene 'Mkt-RF') "
            f"en {ruta_zip.name}. ¿Ha cambiado el formato del fichero?"
        )
    # La primera celda de la cabecera está vacía (es la columna de fechas)
    nombres = [c for c in cabecera if c]

    # 2) las filas de datos, reconocidas por su forma
    fechas: list[str] = []
    valores: list[list[float]] = []
    for linea in lineas:
        m = _PATRON_FILA.match(linea)
        if not m:
            continue
        celdas = [c.strip() for c in m.group(2).split(",")]
        celdas = [c for c in celdas if c != ""]
        if len(celdas) != len(nombres):
            # Una fila con otro número de columnas no es de este bloque
            # (el fichero mensual, por ejemplo, trae un bloque anual al final).
            continue
        fechas.append(m.group(1))
        valores.append([float(c) for c in celdas])

    if not fechas:
        raise ValueError(
            f"No he encontrado ni una fila de datos en {ruta_zip.name}. "
            "El parser busca líneas que empiecen por AAAAMMDD y una coma."
        )

    df = pd.DataFrame(valores, columns=nombres)
    df.index = pd.to_datetime(pd.Series(fechas), format="%Y%m%d")
    df.index.name = "fecha"

    # 3) faltantes -> NaN, ANTES de dividir (los códigos son valores crudos)
    for codigo in CODIGOS_FALTANTE:
        df = df.mask(df == codigo)

    # 4) porcentaje -> decimal. Aquí, una sola vez, para todo el proyecto.
    df = df / 100.0

    # 5) nombres de columna manejables
    df = df.rename(
        columns={"Mkt-RF": "mkt_rf", "SMB": "smb", "HML": "hml", "RF": "rf"}
    )

    df = df.sort_index()

    # ── validaciones: fallar alto y claro, no devolver algo raro ──
    if df.index.has_duplicates:
        duplicadas = df.index[df.index.duplicated()][:5].tolist()
        raise ValueError(f"Hay fechas duplicadas en el fichero: {duplicadas}")
    if len(df) < 20_000:
        raise ValueError(
            f"Solo he leído {len(df)} filas. El fichero diario de French tiene "
            "más de 25.000 (desde 1926). Algo ha ido mal en el parseo."
        )
    esperadas = {"mkt_rf", "smb", "hml", "rf"}
    if not esperadas.issubset(df.columns):
        raise ValueError(
            f"Faltan columnas esperadas. Tengo {list(df.columns)}, "
            f"esperaba al menos {sorted(esperadas)}"
        )

    return df


def cargar_factores_diarios(forzar_descarga: bool = False) -> pd.DataFrame:
    """Punto de entrada: descarga si hace falta y devuelve el DataFrame limpio."""
    return parsear_factores_diarios(descargar_factores_diarios(forzar=forzar_descarga))


# ── Diagnóstico ──────────────────────────────────────────────────────

def main() -> None:
    """Descarga, parsea e imprime lo necesario para verificar que está bien.

    Esto NO es un test automático: es la comprobación manual que hay que
    mirar con desconfianza la primera vez, porque el parser no se ha podido
    probar contra el fichero real hasta ahora.
    """
    df = cargar_factores_diarios()

    print("\n" + "=" * 68)
    print("DIAGNÓSTICO — factores diarios de French")
    print("=" * 68)
    print(f"Filas: {len(df):,}")
    print(f"Rango: {df.index.min().date()}  ->  {df.index.max().date()}")
    print(f"Columnas: {list(df.columns)}")

    print("\nPrimeras 3 filas (en DECIMAL: 0.0010 = 0,10%):")
    print(df.head(3).to_string())
    print("\nÚltimas 3 filas:")
    print(df.tail(3).to_string())

    print("\nValores faltantes por columna:")
    print(df.isna().sum().to_string())

    print("\nEstadísticos diarios (decimal):")
    print(df.describe().loc[["mean", "std", "min", "max"]].to_string())

    print("\nComprobación de escala — media ANUALIZADA de cada factor:")
    for col in df.columns:
        anual = df[col].mean() * 252
        print(f"  {col:7} {anual:+7.2%} al año")
    print(
        "\n  Qué tiene que salir: mkt_rf alrededor de +6% a +9% anual (la prima\n"
        "  de mercado histórica) y rf entre +3% y +4% (letras del Tesoro). Si\n"
        "  mkt_rf sale +650% o +0,07%, la conversión de porcentaje a decimal\n"
        "  está mal y TODO lo que venga después estará mal."
    )
    print("=" * 68)


if __name__ == "__main__":
    main()