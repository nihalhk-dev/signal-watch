"""El contrato metric_stream: la forma común de TODAS las series del proyecto.

Este es el documento más importante del diseño, convertido en código.
Tanto las series sintéticas como las reales (crédito, mercado) se
materializan con este mismo esquema. Es lo que hace que el sistema
sea agnóstico al origen del dato: un detector que sabe procesar un
`MetricObservation` no necesita saber si viene de un scorecard de
crédito o de un factor de mercado.

Dos clases:
  · MetricObservation — UNA fila del contrato (un punto en el tiempo)
  · Direction — el enum de las dos direcciones posibles

El campo `tau` (el instante real del cambio) NO está aquí a propósito.
Vive en un esquema aparte (ver la nota al final). Esa separación es
la "muralla" que impide que el detector vea la verdad-terreno.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Direction(str, Enum):
    """Hacia dónde es "peor" que se mueva la métrica.

    lower_is_worse: como el AUC — un valor más bajo es peor (el modelo
        discrimina menos). La mayoría de las métricas del proyecto.
    higher_is_worse: como el PSI — un valor más alto es peor (más
        deriva de la distribución). Es la EXCEPCIÓN del proyecto, y
        por eso el contrato la declara de forma explícita en vez de
        asumir siempre "más alto es mejor".
    """

    LOWER_IS_WORSE = "lower_is_worse"
    HIGHER_IS_WORSE = "higher_is_worse"


class MetricObservation(BaseModel):
    """Una fila del contrato: un punto en el tiempo de una serie.

    Pydantic valida automáticamente cada campo al crear el objeto.
    Si algo no cumple (un n_obs negativo, un value_se negativo...),
    lanza un error INMEDIATAMENTE — no se cuela un dato corrupto para
    fallar silenciosamente tres pasos después.
    """

    stream_id: str = Field(
        ...,
        min_length=1,
        description="Identificador del flujo, p.ej. 'credito_lc_auc_36m'",
    )
    t: int = Field(
        ...,
        ge=0,
        description="Índice temporal ordinal (0, 1, 2, ...) dentro del stream",
    )
    timestamp: date = Field(
        ...,
        description="Fecha real del periodo (cosecha mensual o día de mercado)",
    )
    value: float = Field(
        ...,
        description="Valor de la métrica en este periodo",
    )
    value_se: float = Field(
        ...,
        ge=0,
        description="Error estándar de la métrica (mide el ruido de este punto)",
    )
    n_obs: int = Field(
        ...,
        gt=0,
        description="Número de observaciones que sostienen la métrica "
        "(préstamos en la cosecha, días en la ventana)",
    )
    direction: Direction = Field(
        ...,
        description="Si un valor más bajo o más alto es peor",
    )

    @field_validator("value_se")
    @classmethod
    def _se_no_puede_ser_negativa(cls, v: float) -> float:
        # Redundante con ge=0 de arriba, pero deja un mensaje más claro
        # si alguna vez se relaja el Field — nunca queremos un error
        # estándar negativo, no tiene sentido físico.
        if v < 0:
            raise ValueError(
                f"value_se no puede ser negativo (recibido: {v}). "
                "Un error estándar negativo no tiene sentido."
            )
        return v

    class Config:
        # Permite comparar por valor (dos observaciones con los mismos
        # campos son "iguales"), útil en los tests.
        frozen = True


# ── Nota sobre tau (el instante de cambio real) ──────────────────────
#
# A propósito, NO hay un campo `tau` en MetricObservation. El instante
# de cambio real vive en un esquema SEPARADO (que se define en
# synthetic/generator.py, cuando construyamos el banco de pruebas).
#
# Esta separación física entre "lo que ve el detector" (MetricObservation)
# y "la verdad que solo existe para poder medir" (tau) es la salvaguarda
# de R2. Si algún día alguien intenta meter tau en este esquema, o pasar
# un tau al detector, el sistema debe lanzar TauLeakageError — eso se
# implementa en gold/metric_stream.py, la siguiente pieza.