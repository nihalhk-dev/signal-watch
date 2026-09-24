"""Datos de la app: qué streams existen y qué se sabe de cada uno.

Esta capa NO importa streamlit, a propósito: son funciones puras que leen lo
que el pipeline ya dejó en disco (configs, stream gold, tablas selladas). Así
se pueden probar sin levantar la app, y las páginas se quedan en dibujar.

LA APP NO CALCULA RESULTADOS (R6). Todo número que enseña sale de una tabla
de outputs/tables/ sellada con su huella R7, o de una función de src/. Si la
app mostrara un número que no está en ninguna tabla, no habría forma de
auditarlo.

DESCUBRIMIENTO DE STREAMS
La app no tiene una lista de streams escrita a mano. Un stream aparece en
pantalla si cumple dos cosas:
    1. existe configs/streams/<id>.yaml con un bloque `monitorizacion:`
    2. existe outputs/tables/alarmas_<id>.csv (es decir, ya se monitorizó)
Por eso añadir un modelo nuevo —un scorecard, una señal de ML— no requiere
tocar la app: basta con su YAML y con correr scripts/run_monitoring.py. Es la
demostración práctica de que el sistema es agnóstico al modelo.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from signal_watch.gold.metric_stream import load_metric_stream
from signal_watch.paths import PATHS


def ruta_tabla(nombre: str) -> Path:
    """outputs/tables/<nombre>.csv"""
    return PATHS.outputs_tables / f"{nombre}.csv"


def cargar_tabla(nombre: str) -> pd.DataFrame | None:
    """Lee una tabla sellada. None si todavía no existe (la app lo dice, no falla)."""
    ruta = ruta_tabla(nombre)
    return pd.read_csv(ruta) if ruta.exists() else None


def cargar_config(stream_id: str) -> dict:
    with open(PATHS.configs / "streams" / f"{stream_id}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def streams_monitorizados() -> list[str]:
    """Streams con config de monitorización Y con resultados ya generados."""
    carpeta = PATHS.configs / "streams"
    encontrados = []
    for ruta in sorted(carpeta.glob("*.yaml")):
        try:
            cfg = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue  # un YAML roto no debe tumbar la pantalla de los demás
        if "monitorizacion" in cfg and ruta_tabla(f"alarmas_{ruta.stem}").exists():
            encontrados.append(ruta.stem)
    return encontrados


def serie(stream_id: str) -> pd.DataFrame:
    """El stream gold como tabla: índice fecha, columnas value / value_se / n_obs."""
    ruta = PATHS.data_gold_real / f"{stream_id}.parquet"
    obs = load_metric_stream(ruta)
    return pd.DataFrame(
        {
            "value": [o.value for o in obs],
            "value_se": [o.value_se for o in obs],
            "n_obs": [o.n_obs for o in obs],
        },
        index=pd.to_datetime([o.timestamp for o in obs]),
    )


def observaciones_referencia(stream_id: str) -> list:
    """Las observaciones de la ventana de referencia (solo calibra)."""
    cfg = cargar_config(stream_id)
    corte = date.fromisoformat(cfg["fin_calibracion"])
    obs = load_metric_stream(PATHS.data_gold_real / f"{stream_id}.parquet")
    return [o for o in obs if o.timestamp <= corte]


def resumen_stream(stream_id: str) -> dict:
    """Lo que la pantalla de salud de modelos enseña de un stream.

    Todo sale de la config y de las tablas selladas; no se recalcula nada.
    """
    cfg = cargar_config(stream_id)
    mon = cfg["monitorizacion"]
    calib = cargar_tabla(f"calibracion_{stream_id}")
    alarmas = cargar_tabla(f"alarmas_{stream_id}")
    s = serie(stream_id)

    corte = pd.Timestamp(cfg["fin_calibracion"])
    vigilancia = s[s.index > corte]
    meses_vigilados = int(len(vigilancia))
    esperadas = meses_vigilados / float(mon["arl0_objetivo_meses"])

    filas = []
    for _, c in (calib.iterrows() if calib is not None else []):
        propias = alarmas[alarmas["detector"] == c["detector"]] if alarmas is not None else pd.DataFrame()
        filas.append(
            {
                "detector": c["detector"],
                "umbral": round(float(c["umbral"]), 3),
                "ARL0 alcanzable": round(float(c["arl0_alcanzable"]), 1),
                "ARL0 verificado": round(float(c["arl0_verificado"]), 1),
                "alarmas": int(len(propias)),
                "esperadas por azar": round(esperadas, 1),
                "última alarma": (str(propias["fecha"].max()) if len(propias) else "—"),
            }
        )

    huella = {}
    if calib is not None and len(calib):
        huella = {k: str(calib.iloc[0][k]) for k in ("config_hash", "hash_datos", "commit")}

    return {
        "stream_id": stream_id,
        "fuente": cfg.get("fuente", "—"),
        "metrica": cfg.get("metrica", "—"),
        "direction": cfg.get("direction", "—"),
        "frecuencia": cfg.get("frecuencia", "—"),
        "referencia": f"{s.index.min().date()} → {cfg['fin_calibracion']}",
        "vigilancia": (f"{vigilancia.index.min().date()} → {vigilancia.index.max().date()}"
                       if meses_vigilados else "—"),
        "meses_vigilados": meses_vigilados,
        "arl0_objetivo": float(mon["arl0_objetivo_meses"]),
        "esperadas_por_azar": esperadas,
        "detectores": pd.DataFrame(filas),
        "huella": huella,
    }


def umbrales_calibrados(stream_id: str) -> dict[str, float]:
    """detector → umbral, tal como quedó sellado en la tabla de calibración."""
    calib = cargar_tabla(f"calibracion_{stream_id}")
    if calib is None:
        return {}
    return {r["detector"]: float(r["umbral"]) for _, r in calib.iterrows()}


# ── Informe de tests (evidencia de validación) ───────────────────────

INFORME_TESTS = "tests_junit.xml"


def leer_informe_tests(ruta: Path | None = None) -> dict | None:
    """Lee el informe JUnit que escribe `pytest --junitxml=...`.

    Es el formato estándar de los sistemas de integración continua: no hay
    código propio que genere el informe, solo pytest. Devuelve el resumen
    (totales, duración, fecha, commit sellado por tests/conftest.py) y una
    fila por test con su capa, archivo, estado y motivo. None si no existe.
    """
    import xml.etree.ElementTree as ET

    ruta = Path(ruta) if ruta else PATHS.outputs_tables / INFORME_TESTS
    if not ruta.exists():
        return None
    raiz = ET.parse(ruta).getroot()
    suite = raiz if raiz.tag == "testsuite" else raiz.find("testsuite")
    propiedades = {p.get("name"): p.get("value") for p in suite.iter("property")}

    filas = []
    for caso in suite.iter("testcase"):
        clase, nombre = caso.get("classname", ""), caso.get("name", "")
        # "tests.unit.test_cusum" → capa "unit", archivo "test_cusum"; un skip a
        # nivel de módulo llega sin classname y con la ruta en el nombre.
        partes = (clase or nombre.replace("/", ".").replace("\\", ".")).split(".")
        capa = partes[1] if len(partes) > 1 and partes[0] == "tests" else "—"
        archivo = next((p for p in partes if p.startswith("test_")), clase or nombre)
        estado, motivo = "pasa", ""
        for etiqueta, valor in (("failure", "falla"), ("error", "error"), ("skipped", "fuera de alcance")):
            nodo = caso.find(etiqueta)
            if nodo is not None:
                estado, motivo = valor, (nodo.get("message") or "").strip()
                # Un skip a nivel de módulo trae message="collection skipped" y el
                # motivo real dentro del texto: "(ruta, línea, 'Skipped: …')".
                texto = nodo.text or ""
                if "Skipped: " in texto:
                    motivo = texto.split("Skipped: ", 1)[1].rstrip("')\"\n ")
        filas.append({"capa": capa, "archivo": archivo,
                      "test": nombre if clase else "(módulo completo)",
                      "estado": estado, "segundos": float(caso.get("time", 0) or 0), "motivo": motivo})

    tabla = pd.DataFrame(filas)
    cuenta = tabla["estado"].value_counts()
    return {
        "pasan": int(cuenta.get("pasa", 0)),
        "fallan": int(cuenta.get("falla", 0) + cuenta.get("error", 0)),
        "fuera_de_alcance": int(cuenta.get("fuera de alcance", 0)),
        "duracion_s": float(suite.get("time", 0) or 0),
        "fecha": suite.get("timestamp", "—"),
        "commit": propiedades.get("commit", "—"),
        "tabla": tabla,
    }
