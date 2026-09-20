"""Mide el Average Run Length (ARL) de un detector: cuánto tarda en
disparar, en promedio, en dos regímenes distintos:

  · ARL0 — bajo H0 (streams "sin_cambio"): cuánto tarda en dar una
    FALSA alarma. Cuanto más alto, mejor (el detector es más "tranquilo").
  · ARL1 — bajo H1 (streams con cambio real): cuánto tarda en detectar
    el cambio DESDE que ocurre tau. Cuanto más bajo, mejor (detecta rápido).

Esta es la pieza que, aplicada sobre el banco de pruebas real (320.000
observaciones, calibration.py ya usó una versión simplificada de esto
para calibrar h), produce el número que se compara en la curva de
retardo vs. falsas alarmas (delay_curves.py) — el resultado central
del proyecto.

Nota sobre censura: no todo stream produce una alarma dentro de su
longitud. Un run "censurado" (el detector nunca disparó) no se descarta
—descartarlo sesgaría el ARL0 hacia abajo, porque justo los runs más
tranquilos (los que MÁS tardan) son los que se censuran—. Se cuenta como
"al menos tantos pasos como duró la serie", siguiendo la misma convención
conservadora que ya se usó en calibration.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from signal_watch.detectors.base import Detector
from signal_watch.gold.metric_stream import GroundTruth
from signal_watch.gold.schemas import MetricObservation


@dataclass(frozen=True)
class ResultadoARL:
    """El resultado de medir un ARL (0 o 1) sobre un conjunto de streams.

    arl: la media de los tiempos hasta la alarma (o hasta el final de
         la serie, si nunca alarmó — censurado).
    error_estandar: el error estándar de esa media, para poder reportar
                     un intervalo de confianza, no solo un número suelto.
    n_streams: cuántos streams se usaron para la medición.
    n_censurados: cuántos de ellos NUNCA dispararon dentro de su longitud
                   (el ARL real podría ser aún mayor de lo medido).
    """

    arl: float
    error_estandar: float
    n_streams: int
    n_censurados: int

    @property
    def intervalo_95(self) -> tuple[float, float]:
        """Intervalo de confianza aproximado al 95% (± 1.96 SE)."""
        margen = 1.96 * self.error_estandar
        return (self.arl - margen, self.arl + margen)


def _tiempo_hasta_alarma(
    detector: Detector,
    observaciones: list[MetricObservation],
) -> tuple[int, bool]:
    """Corre un detector sobre una serie y devuelve (tiempo, censurado).

    tiempo: el t de la primera alarma, o len(observaciones) si nunca
            alarmó (censurado).
    censurado: True si nunca alarmó dentro de la serie.
    """
    detector.reset()
    for obs in observaciones:
        alarma = detector.update(obs)
        if alarma is not None:
            return alarma.t, False
    return len(observaciones), True


def medir_arl0(
    fabricar_detector: callable,
    streams_sin_cambio: list[list[MetricObservation]],
) -> ResultadoARL:
    """Mide el ARL0: tiempo hasta la falsa alarma, sobre streams donde
    NO hay cambio real (escenario "sin_cambio", ground_truth.tau=None).

    fabricar_detector: función sin argumentos que devuelve una instancia
    NUEVA del detector (se necesita una instancia limpia por stream).
    """
    tiempos = []
    n_censurados = 0
    for obs in streams_sin_cambio:
        detector = fabricar_detector()
        t, censurado = _tiempo_hasta_alarma(detector, obs)
        tiempos.append(t)
        if censurado:
            n_censurados += 1

    tiempos_arr = np.array(tiempos, dtype=float)
    return ResultadoARL(
        arl=float(tiempos_arr.mean()),
        error_estandar=float(tiempos_arr.std(ddof=1) / np.sqrt(len(tiempos_arr))),
        n_streams=len(tiempos),
        n_censurados=n_censurados,
    )


def medir_arl1(
    fabricar_detector: callable,
    streams_con_cambio: list[list[MetricObservation]],
    ground_truths: list[GroundTruth],
) -> ResultadoARL:
    """Mide el ARL1: RETARDO de detección, es decir, tiempo hasta la
    alarma MENOS tau (el instante real del cambio) — no el tiempo
    absoluto de la alarma.

    Requiere que ground_truths[i] corresponda a streams_con_cambio[i]
    (misma posición) y que tau no sea None en ninguno (si lo es, ese
    stream no pertenece aquí — es un "sin_cambio" y va a medir_arl0).

    Streams donde el detector alarma ANTES de tau se excluyen de la
    media de retardo con un aviso: eso sería, en el mejor de los casos,
    una alarma "por casualidad" en la parte de la serie sin cambio
    real, no una detección genuina del cambio — mezclar esos casos en
    el ARL1 subestimaría el retardo real de forma artificial y optimista.
    """
    if len(streams_con_cambio) != len(ground_truths):
        raise ValueError(
            f"streams_con_cambio ({len(streams_con_cambio)}) y ground_truths "
            f"({len(ground_truths)}) deben tener la misma longitud"
        )

    retardos = []
    n_censurados = 0
    n_excluidos_por_alarma_temprana = 0

    for obs, gt in zip(streams_con_cambio, ground_truths):
        if gt.tau is None:
            raise ValueError(
                f"stream '{gt.stream_id}' tiene tau=None — pertenece a "
                "medir_arl0(), no a medir_arl1()"
            )
        detector = fabricar_detector()
        t, censurado = _tiempo_hasta_alarma(detector, obs)

        if not censurado and t < gt.tau:
            # alarma antes de que ocurriera el cambio real: no es una
            # detección genuina, se excluye para no sesgar el retardo
            n_excluidos_por_alarma_temprana += 1
            continue

        if censurado:
            # nunca alarmó: el retardo es "al menos" la longitud restante
            # de la serie desde tau
            retardo = len(obs) - gt.tau
            n_censurados += 1
        else:
            retardo = t - gt.tau

        retardos.append(retardo)

    if not retardos:
        raise ValueError(
            "Ningún stream produjo un retardo válido — revisa si el detector "
            "está calibrado razonablemente para este banco de pruebas."
        )

    retardos_arr = np.array(retardos, dtype=float)
    return ResultadoARL(
        arl=float(retardos_arr.mean()),
        error_estandar=float(retardos_arr.std(ddof=1) / np.sqrt(len(retardos_arr))),
        n_streams=len(retardos),
        n_censurados=n_censurados,
    )