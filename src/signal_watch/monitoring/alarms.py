"""La alarma como objeto de dominio: todo lo necesario para auditarla después.

Un detector devuelve una `Alarma` mínima (instante y estadístico): es lo
que le basta al banco sintético para medir retardos. En monitorización eso
no alcanza. Un validador que lea la alarma dentro de un año tiene que poder
responder, sin preguntar a nadie:

    · ¿qué serie, qué fecha y qué valor la dispararon?
    · ¿qué detector, con qué umbral, y calibrado cómo?
    · ¿con qué código y sobre qué datos exactos?

Las tres últimas preguntas son R7 aplicada a cada alarma individual: los
mismos `config_hash`, `commit` y `hash_datos` que sellan las tablas del
banco sintético. Dos ejecuciones con la misma huella producen exactamente
las mismas alarmas; si alguien discute una, se puede reproducir.

Deliberadamente fuera (el manual los preveía para la fase con base de
datos, que está fuera de alcance): `id`, `severity`, `created_at` y la
estimación del instante de inicio del cambio (`t_hat`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class AlarmEvent:
    """Una alarma de monitorización, lista para una tabla de auditoría."""

    stream_id: str
    detector: str
    t: int                 # índice ordinal dentro del stream completo
    fecha: date            # periodo real que disparó la alarma
    valor: float           # la métrica en ese periodo (p. ej. el Sharpe del mes)
    estadistico: float     # estado interno del detector al disparar
    umbral: float          # h, lambda o k con el que estaba calibrado
    n_alarma: int          # 1ª, 2ª, 3ª... alarma de este detector en esta ejecución

    # trazabilidad (R7): idénticos para todas las alarmas de una ejecución
    config_hash: str
    commit: str
    hash_datos: str


def a_dataframe(eventos: list[AlarmEvent]) -> pd.DataFrame:
    """Lista de eventos → tabla. Una lista vacía da una tabla vacía CON
    columnas: "ninguna alarma" es un resultado, y tiene que poder
    guardarse y leerse igual que cualquier otro."""
    columnas = list(AlarmEvent.__dataclass_fields__)
    if not eventos:
        return pd.DataFrame(columns=columnas)
    return pd.DataFrame([asdict(e) for e in eventos], columns=columnas)