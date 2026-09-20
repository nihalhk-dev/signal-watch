"""Configuración del proyecto: carga, validación y huella digital.

Este módulo hace cuatro cosas:
  1. Carga archivos YAML de configs/ en diccionarios Python.
  2. Valida que no falten campos obligatorios.
  3. Genera una HUELLA DIGITAL (config_hash) de cada configuración,
     de forma que:
       - misma config → mismo hash, SIEMPRE (independiente del orden
         de las claves o de los comentarios del YAML)
       - config distinta → hash distinto
     Esto es lo que permite R5 (no evaluar sin config congelada) y
     R7 (cada resultado lleva el hash de la config que lo produjo).
  4. Sella un resultado con su huella de reproducibilidad completa
     (huella_ejecucion): config, datos de entrada, commit y fecha.

El truco clave es la NORMALIZACIÓN: antes de hashear, se convierte
la config a JSON con las claves ordenadas (sort_keys=True). Así
dos YAMLs con las mismas claves en distinto orden dan el mismo hash.
Sin esto, el test de reproducibilidad daría falsas alarmas cada vez
que alguien reordena un YAML sin cambiar ningún valor.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from signal_watch.exceptions import ConfigError, ConfigNotFrozenError
from signal_watch.paths import PATHS


# ── Carga de YAML ───────────────────────────────────────────────────

def load_yaml(path: Path | str) -> dict[str, Any]:
    """Carga un archivo YAML y devuelve su contenido como diccionario.

    Lanza ConfigError si el archivo no existe, no se puede leer,
    o no contiene un diccionario en el nivel superior.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"No encuentro el archivo de configuración: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Error al parsear {path}: {e}") from e

    if data is None:
        # Archivo vacío: YAML válido pero sin contenido
        return {}

    if not isinstance(data, dict):
        raise ConfigError(
            f"{path} no contiene un diccionario en el nivel superior "
            f"(contiene {type(data).__name__})"
        )

    return data


def load_stream_config(stream_id: str) -> dict[str, Any]:
    """Carga la configuración de un stream por su nombre.

    Busca en configs/streams/{stream_id}.yaml.
    """
    path = PATHS.configs / "streams" / f"{stream_id}.yaml"
    return load_yaml(path)


def load_detector_config(detector_name: str) -> dict[str, Any]:
    """Carga la configuración de un detector por su nombre.

    Busca en configs/detectors/{detector_name}.yaml.
    """
    path = PATHS.configs / "detectors" / f"{detector_name}.yaml"
    return load_yaml(path)


# ── Huella digital (config_hash) ─────────────────────────────────────

def config_hash(config: dict[str, Any]) -> str:
    """Genera una huella de 12 caracteres hex de una configuración.

    La huella es CANÓNICA: el mismo conjunto de claves y valores
    produce siempre el mismo hash, sin importar el orden en que
    estuvieran escritas en el YAML.

    Cómo lo consigue:
      1. Convierte el diccionario a texto JSON con las claves ORDENADAS
         alfabéticamente (sort_keys=True) y sin espacios extra.
      2. Hashea ese texto con SHA-256.
      3. Devuelve los primeros 12 caracteres del hash (suficiente para
         identificar sin ambigüedad en un proyecto de este tamaño).

    Por qué 12 caracteres: 12 hex = 48 bits = 281 billones de valores
    posibles. Para un proyecto con decenas de configs, la probabilidad
    de colisión es despreciable. Y 12 caracteres caben bien en una
    columna de CSV o en un nombre de archivo.
    """
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


# ── Validación de configs ────────────────────────────────────────────

def validate_keys(
    config: dict[str, Any],
    required: set[str],
    name: str = "config",
) -> None:
    """Comprueba que todas las claves obligatorias están presentes.

    Lanza ConfigError si falta alguna, indicando cuáles faltan.
    """
    missing = required - set(config.keys())
    if missing:
        raise ConfigError(
            f"Faltan claves obligatorias en {name}: {sorted(missing)}"
        )


# ── Congelación de configs (R5) ──────────────────────────────────────

def get_frozen_path(version: str) -> Path:
    """Devuelve la ruta de una config congelada por su versión.

    Ejemplo: get_frozen_path("v1.0.0") → configs/detectors/frozen/v1.0.0.yaml
    """
    return PATHS.configs_frozen / f"{version}.yaml"


def load_frozen(version: str) -> dict[str, Any]:
    """Carga una config congelada. Lanza ConfigNotFrozenError si no existe.

    ¿Por qué ConfigNotFrozenError y no ConfigError? Porque "la config
    congelada no existe" es un fallo METODOLÓGICO (estás intentando
    evaluar sin haber congelado), no un fallo técnico. El nombre del
    error comunica el problema.
    """
    path = get_frozen_path(version)
    if not path.exists():
        raise ConfigNotFrozenError(
            f"No existe la config congelada {version} en {PATHS.configs_frozen}. "
            "¿Has corrido 'signal-watch freeze-config' antes de evaluar? (R5)"
        )
    return load_yaml(path)


def verify_frozen(config: dict[str, Any], version: str) -> bool:
    """Comprueba que una config coincide con su versión congelada.

    Compara los hashes canónicos. Devuelve True si coinciden.
    Lanza ConfigNotFrozenError si la versión congelada no existe.

    Uso típico: antes de producir resultados, el pipeline comprueba
    que la config actual es la misma que se congeló — si alguien la
    tocó (aunque sea el orden de las claves), el hash cambia y lo
    detectamos. Bueno, en realidad no: gracias a la normalización,
    el orden de las claves NO cambia el hash. Solo cambios reales
    en los valores lo cambian. Ese es el punto.
    """
    frozen = load_frozen(version)
    return config_hash(config) == config_hash(frozen)


# ── Trazabilidad de resultados (R7) ──────────────────────────────────

def obtener_commit() -> str:
    """Hash corto del commit actual de git.

    Devuelve 'sin-git' si no estamos en un repo o git no está
    disponible. NUNCA lanza: es información de trazabilidad, y que
    falte no debe tumbar una ejecución de análisis de 40 minutos.
    """
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "sin-git"


def hash_archivo(path: Path | str, bloque: int = 1 << 20) -> str:
    """SHA-256 (12 hex) del contenido de un archivo.

    Se lee por bloques de 1 MB en vez de de una vez, porque los Parquet
    del banco de pruebas pesan cientos de megas y no tiene sentido
    cargarlos enteros en memoria solo para hashearlos.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while trozo := f.read(bloque):
            h.update(trozo)
    return h.hexdigest()[:12]


def huella_ejecucion(
    config: dict[str, Any],
    archivos_datos: list[Path | str],
) -> dict[str, str]:
    """La huella que hace reproducible un resultado (R7).

    Son DOS hashes complementarios, a propósito:

      · config_hash — los parámetros del análisis (niveles de ARL0
        objetivo, k, delta, rangos de búsqueda de umbral). Responde a
        "¿con qué ajustes se produjo esta tabla?".

      · hash_datos — el contenido REAL de los archivos de entrada.
        Responde a "¿sobre qué datos?". Captura de una vez el número de
        réplicas, las semillas y cualquier cambio en el generador, sin
        tener que enumerarlos uno a uno — y detecta un solo byte
        distinto.

    Juntos fijan el resultado por completo: mismo par de hashes = misma
    tabla, necesariamente. Uno solo de los dos no bastaría: los mismos
    parámetros sobre otro banco dan otros números, y el mismo banco con
    otros parámetros también.

    IMPORTANTE sobre de dónde sale `config`: tiene que ser la config
    EFECTIVA que devolvió la función que hizo el cálculo, no un
    diccionario escrito a mano en el script que llama. Si los parámetros
    viven dentro de la función de cálculo y el hash se construye fuera,
    cambiar un parámetro no cambiaría el hash: dos ejecuciones distintas
    tendrían la misma huella, y R7 quedaría incumplida en silencio —
    que es peor que no tener huella, porque da falsa confianza.
    """
    return {
        "config_hash": config_hash(config),
        "commit": obtener_commit(),
        "hash_datos": config_hash(
            {Path(p).name: hash_archivo(p) for p in archivos_datos}
        ),
        "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }