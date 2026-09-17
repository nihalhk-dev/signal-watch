"""Configuración de logging para Signal Watch.

Configura los mensajes que el programa escribe mientras trabaja, para
que puedas ver qué está pasando en cada momento. Un solo punto de
configuración para todo el proyecto: en vez de poner print() por
todas partes, usamos logging, que permite:
  · ver mensajes con distintos niveles (DEBUG, INFO, WARNING, ERROR)
  · activar/desactivar el detalle sin tocar código
  · añadir fecha y hora a cada mensaje automáticamente
  · redirigir la salida a un archivo si hace falta

Uso en cualquier módulo del proyecto:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Cargados %d préstamos", n)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from signal_watch.paths import PATHS

# El formato de cada mensaje: fecha · nivel · módulo · el mensaje
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
) -> None:
    """Configura el logging de todo el proyecto.

    Se llama UNA vez, al arrancar (en cli.py). Después, cada módulo
    hace `logger = logging.getLogger(__name__)` y ya funciona.

    Args:
        level: nivel mínimo de mensajes a mostrar.
               "DEBUG" = todo, "INFO" = normal, "WARNING" = solo avisos.
        log_file: si se pasa una ruta, los mensajes también se escriben
                  a ese archivo (además de a la pantalla).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Handler para la pantalla (stderr)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    handlers: list[logging.Handler] = [console]

    # Handler para archivo, si se pide
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
        handlers.append(file_handler)

    # Configurar el logger raíz de signal_watch
    root_logger = logging.getLogger("signal_watch")
    root_logger.setLevel(numeric_level)

    # Limpiar handlers previos (por si se llama más de una vez, ej. en tests)
    root_logger.handlers.clear()
    for h in handlers:
        root_logger.addHandler(h)

    # Silenciar librerías ruidosas
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
