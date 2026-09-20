"""Carga, guarda y valida metric_streams. Y la MURALLA que separa la
verdad-terreno (tau) de lo que el detector puede ver.

Esta es la pieza de diseño más importante del proyecto (R2). La idea:

  · MetricObservation (schemas.py) — lo que el detector SÍ puede ver.
  · GroundTruth (aquí) — el instante real del cambio (tau). Solo existe
    para el banco sintético, donde TÚ lo inyectaste y por tanto lo conoces.
    Vive en un objeto y un archivo COMPLETAMENTE SEPARADOS.

La función to_detector_view() es la muralla física: toma un stream
completo (con su ground truth al lado) y devuelve SOLO las observaciones,
nunca el tau. Un detector que reciba el resultado de esta función es
FÍSICAMENTE incapaz de ver dónde está el cambio — no es una promesa de
buen comportamiento, es que el dato no está en el objeto.

Si en algún punto del código alguien intenta pasarle tau a un detector,
o mezclar GroundTruth dentro de un MetricObservation, debe saltar
TauLeakageError. Aquí es donde se monta esa defensa.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from signal_watch.exceptions import SchemaViolationError, TauLeakageError
from signal_watch.gold.schemas import Direction, MetricObservation


class GroundTruth(BaseModel):
    """El instante real del cambio, SOLO para series sintéticas.

    Vive completamente separado de MetricObservation. Nunca se guarda
    en el mismo archivo que las observaciones, y nunca se le pasa a
    un detector.
    """

    stream_id: str = Field(..., min_length=1)
    tau: int | None = Field(
        ...,
        description="Índice t en el que ocurre el cambio real. "
        "None si el escenario es 'sin_cambio' (no hay cambio que detectar).",
    )
    escenario: str = Field(
        ...,
        description="Nombre del escenario sintético: salto, deriva, "
        "cambio_varianza, sin_cambio, etc.",
    )

    class Config:
        frozen = True


# ── Guardar y cargar observaciones ────────────────────────────────────

def observations_to_dataframe(observations: list[MetricObservation]) -> pd.DataFrame:
    """Convierte una lista de observaciones a un DataFrame de pandas,
    listo para guardar como Parquet."""
    if not observations:
        raise SchemaViolationError("No se puede guardar una lista vacía de observaciones")

    rows = [obs.model_dump() for obs in observations]
    df = pd.DataFrame(rows)
    # Direction es un Enum: al volcarlo a dict queda como el Enum mismo
    # o como string según la versión de pydantic. Normalizamos a string
    # para que el Parquet sea legible fuera de Python también.
    df["direction"] = df["direction"].apply(
        lambda d: d.value if isinstance(d, Direction) else d
    )
    return df


def save_metric_stream(observations: list[MetricObservation], path: Path | str) -> None:
    """Guarda una lista de observaciones como Parquet.

    IMPORTANTE: esta función solo acepta MetricObservation, nunca
    GroundTruth. Si necesitas guardar la verdad-terreno de un escenario
    sintético, usa save_ground_truth() — a propósito son funciones
    distintas, para que sea imposible mezclarlas por error de tipeo.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = observations_to_dataframe(observations)
    df.to_parquet(path, index=False)


def load_metric_stream(path: Path | str) -> list[MetricObservation]:
    """Carga un metric_stream desde Parquet y valida cada fila contra
    el contrato (MetricObservation). Si una fila no cumple, falla aquí
    y no más adelante en el pipeline."""
    path = Path(path)
    if not path.exists():
        raise SchemaViolationError(f"No encuentro el metric_stream: {path}")

    df = pd.read_parquet(path)

    required_cols = {"stream_id", "t", "timestamp", "value", "value_se", "n_obs", "direction"}
    missing = required_cols - set(df.columns)
    if missing:
        raise SchemaViolationError(
            f"{path} no cumple el contrato metric_stream. Faltan columnas: {sorted(missing)}"
        )

    # GUARDIA DE LA MURALLA: si alguien coló una columna 'tau' en el
    # mismo archivo que las observaciones, es una fuga de verdad-terreno.
    if "tau" in df.columns:
        raise TauLeakageError(
            f"{path} contiene una columna 'tau' junto a las observaciones. "
            "El instante de cambio real NUNCA debe vivir en el mismo archivo "
            "que lo que ve el detector. Guarda el ground truth por separado "
            "con save_ground_truth()."
        )

    observations = []
    for _, row in df.iterrows():
        observations.append(
            MetricObservation(
                stream_id=row["stream_id"],
                t=int(row["t"]),
                timestamp=row["timestamp"],
                value=float(row["value"]),
                value_se=float(row["value_se"]),
                n_obs=int(row["n_obs"]),
                direction=Direction(row["direction"]),
            )
        )
    return observations


# ── Guardar y cargar la verdad-terreno (SOLO sintético) ────────────────

def save_ground_truth(truths: list[GroundTruth], path: Path | str) -> None:
    """Guarda la verdad-terreno (tau) en un archivo SEPARADO de las
    observaciones. Este archivo nunca se lee en el camino que va hacia
    un detector — solo lo lee evaluation/delay_curves.py, después de
    que el detector ya haya dado su alarma, para medir el retardo."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([t.model_dump() for t in truths])
    df.to_parquet(path, index=False)


def load_ground_truth(path: Path | str) -> list[GroundTruth]:
    """Carga la verdad-terreno. Usar SOLO en evaluation/, nunca en
    el camino que construye la entrada de un detector."""
    path = Path(path)
    if not path.exists():
        raise SchemaViolationError(f"No encuentro el ground truth: {path}")
    df = pd.read_parquet(path)
    return [
        GroundTruth(
            stream_id=row["stream_id"],
            tau=None if pd.isna(row["tau"]) else int(row["tau"]),
            escenario=row["escenario"],
        )
        for _, row in df.iterrows()
    ]

# ── LA MURALLA ─────────────────────────────────────────────────────────

def to_detector_view(observations: list[MetricObservation]) -> list[MetricObservation]:
    """Devuelve la vista que un detector puede consumir.

    Ahora mismo esto parece trivial (devuelve la lista tal cual), porque
    MetricObservation ya no tiene tau por diseño (ver schemas.py). Pero
    esta función existe como el PUNTO ÚNICO por el que cualquier dato
    pasa antes de llegar a un detector. Si en el futuro alguien añade
    un campo sensible a MetricObservation, este es el sitio donde se
    filtra — no cada detector individualmente.

    Es la puerta de la muralla: todo lo que entra a un detector, entra
    por aquí.
    """
    for obs in observations:
        # Defensa en profundidad: si por lo que sea un objeto que no es
        # un MetricObservation válido se coló hasta aquí (p.ej. alguien
        # construyó un dict con 'tau' dentro a mano), lo cazamos.
        if hasattr(obs, "tau"):
            raise TauLeakageError(
                "Se ha intentado pasar un objeto con atributo 'tau' a la "
                "vista del detector. El instante de cambio real NUNCA "
                "puede llegar a un detector."
            )
    return list(observations)