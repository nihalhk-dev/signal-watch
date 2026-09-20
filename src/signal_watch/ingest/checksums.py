"""Prueba documental de las descargas: qué fichero, de dónde, y con qué hash.

Por qué existe este módulo y no se hace dentro de cada `ingest/*`:
  Los datos reales NO se versionan en git (pesan, y en algunos casos la
  licencia no lo permite). Eso deja un agujero: dentro de seis meses,
  ¿cómo demuestras que los números de tu memoria salieron del fichero
  que dices y no de otro? El fichero no está en el repositorio.

  La respuesta es la misma que para el banco sintético (R7): no guardas
  los datos, guardas su HUELLA. `download_manifest.json` sí se versiona
  —es pequeño— y registra por cada descarga: URL exacta, nombre, tamaño,
  SHA-256, fecha y commit. Con eso, cualquiera puede rebajarse el fichero
  y comprobar que es byte a byte el mismo que usaste tú.

  Es exactamente el mismo argumento que `hash_datos` en el banco
  sintético, aplicado a datos que no controlas: no puedes regenerarlos
  con una semilla, así que sellas los que usaste.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_watch.config import hash_archivo, obtener_commit
from signal_watch.paths import PATHS


def ruta_manifiesto() -> Path:
    """Dónde vive el manifiesto de descargas."""
    return PATHS.data_raw / "_metadata" / "download_manifest.json"


def leer_manifiesto() -> dict[str, Any]:
    """Devuelve el manifiesto actual, o un diccionario vacío si aún no existe."""
    ruta = ruta_manifiesto()
    if not ruta.exists():
        return {}
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def registrar_descarga(
    ruta_fichero: Path | str,
    url: str,
    fuente: str,
) -> dict[str, Any]:
    """Anota (o reanota) una descarga en el manifiesto y devuelve su entrada.

    La clave del manifiesto es el nombre del fichero, así que volver a
    descargar el mismo recurso SOBRESCRIBE su entrada en vez de acumular
    duplicados. Eso es deliberado: el manifiesto describe el estado actual
    de `data/raw/`, no un histórico de descargas.

    `fuente` es una etiqueta corta y legible ("kenneth_french") para poder
    agrupar por origen sin tener que parsear la URL.
    """
    ruta_fichero = Path(ruta_fichero)
    if not ruta_fichero.exists():
        raise FileNotFoundError(
            f"No puedo registrar una descarga que no existe: {ruta_fichero}"
        )

    entrada = {
        "fuente": fuente,
        "url": url,
        "bytes": ruta_fichero.stat().st_size,
        "sha256_12": hash_archivo(ruta_fichero),
        "descargado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": obtener_commit(),
    }

    manifiesto = leer_manifiesto()
    manifiesto[ruta_fichero.name] = entrada

    destino = ruta_manifiesto()
    PATHS.ensure(destino.parent)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(manifiesto, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    return entrada


def verificar_descarga(ruta_fichero: Path | str) -> bool:
    """¿El fichero en disco sigue siendo el que se registró?

    Devuelve False si el fichero no está registrado o si su hash ha
    cambiado. No lanza: quien llama decide si eso es un aviso o un error.
    """
    ruta_fichero = Path(ruta_fichero)
    entrada = leer_manifiesto().get(ruta_fichero.name)
    if entrada is None or not ruta_fichero.exists():
        return False
    return entrada["sha256_12"] == hash_archivo(ruta_fichero)