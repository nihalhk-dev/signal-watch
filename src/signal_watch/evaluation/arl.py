"""Mide el Average Run Length (ARL) de un detector: cuánto tarda en
disparar, en promedio, en dos regímenes distintos:

  · ARL0 — bajo H0 (streams "sin_cambio"): cuánto tarda en dar una
    FALSA alarma. Cuanto más alto, mejor (el detector es más "tranquilo").
  · ARL1 — bajo H1 (streams con cambio real): cuánto tarda en detectar
    el cambio DESDE que ocurre tau. Cuanto más bajo, mejor (detecta rápido).

Esta es la pieza que, aplicada sobre el banco de pruebas real, produce
el número que se compara en la curva de retardo vs. falsas alarmas
(delay_curves.py) — el resultado central del proyecto.

CONVENIO DE LONGITUD DE RACHA:
  El "tiempo hasta la alarma" es el número de observaciones CONSUMIDAS,
  no el índice de la observación. Una alarma en la primera observación
  (índice 0) es una racha de longitud 1, no 0. Esto lo hace consistente
  con el caso censurado, que siempre valió len(observaciones). Sin esta
  consistencia, el ARL0 quedaba subestimado en exactamente 1 unidad.

DOS FORMAS DE "NO DETECTAR", Y POR QUÉ SE CUENTAN APARTE:
  · Censura: el detector nunca alarmó dentro de la serie. No se descarta
    —descartarla sesgaría el ARL hacia abajo, porque justo las rachas
    más largas son las que se censuran—. Se cuenta como "al menos tantos
    pasos como duró la serie".
  · Alarma pre-tau (solo en ARL1): el detector alarmó ANTES de que el
    cambio ocurriera. No es una detección del cambio, así que no puede
    entrar en la media del retardo. PERO tampoco es gratis: es una falsa
    alarma, y su frecuencia es un COSTE real del punto de operación.
    Por eso se cuenta y se devuelve (n_excluidos_por_alarma_temprana)
    en vez de descartarse en silencio: sin ese número, cada punto de la
    curva estaría calculado sobre una submuestra distinta, seleccionada
    por el propio detector, y los retardos no serían comparables entre sí.
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
         la serie, si nunca alarmó — censurado). nan si no quedó ningún
         stream utilizable.
    error_estandar: el error estándar de esa media, para poder reportar
                     un intervalo de confianza, no solo un número suelto.
    n_streams: cuántos streams entraron realmente en la media.
    n_censurados: cuántos de ellos NUNCA dispararon dentro de su longitud
                   (el ARL real podría ser aún mayor de lo medido).
    n_excluidos_por_alarma_temprana: solo en ARL1 — cuántos streams se
                   quedaron FUERA de la media porque el detector alarmó
                   antes de tau. Es la tasa de falsa alarma pre-cambio,
                   y hay que reportarla junto al retardo SIEMPRE.
    """

    arl: float
    error_estandar: float
    n_streams: int
    n_censurados: int
    n_excluidos_por_alarma_temprana: int = 0

    @property
    def intervalo_95(self) -> tuple[float, float]:
        """Intervalo de confianza aproximado al 95% (± 1.96 SE)."""
        margen = 1.96 * self.error_estandar
        return (self.arl - margen, self.arl + margen)


def _tiempo_hasta_alarma(
    detector: Detector,
    observaciones: list[MetricObservation],
) -> tuple[int, bool]:
    """Corre un detector sobre una serie y devuelve (racha, censurado).

    racha: número de observaciones CONSUMIDAS hasta la alarma incluida
           (una alarma en el índice 0 da racha 1), o len(observaciones)
           si nunca alarmó.
    censurado: True si nunca alarmó dentro de la serie.
    """
    detector.reset()
    for obs in observaciones:
        alarma = detector.update(obs)
        if alarma is not None:
            return alarma.t + 1, False
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

    if not tiempos:
        return ResultadoARL(float("nan"), float("nan"), 0, 0)

    tiempos_arr = np.array(tiempos, dtype=float)
    error = (
        float(tiempos_arr.std(ddof=1) / np.sqrt(len(tiempos_arr)))
        if len(tiempos_arr) > 1
        else 0.0
    )
    return ResultadoARL(
        arl=float(tiempos_arr.mean()),
        error_estandar=error,
        n_streams=len(tiempos),
        n_censurados=n_censurados,
    )


def medir_arl1(
    fabricar_detector: callable,
    streams_con_cambio: list[list[MetricObservation]],
    ground_truths: list[GroundTruth],
) -> ResultadoARL:
    """Mide el ARL1: RETARDO de detección, es decir, observaciones
    consumidas DESDE tau hasta la alarma — no el tiempo absoluto.

    Requiere que ground_truths[i] corresponda a streams_con_cambio[i]
    (misma posición) y que tau no sea None en ninguno (si lo es, ese
    stream no pertenece aquí — es un "sin_cambio" y va a medir_arl0).

    Los streams donde el detector alarma ANTES de tau NO entran en la
    media (no son detecciones del cambio), pero se CUENTAN y se devuelven
    en n_excluidos_por_alarma_temprana. Ese número es tan importante como
    el retardo: mide cuántas veces el detector gritó antes de que hubiera
    nada que detectar, y sin él los retardos de distintos puntos de
    operación no son comparables entre sí.

    Si no queda ningún stream utilizable, devuelve arl=nan con n_streams=0
    (no lanza excepción): un detector que siempre alarma antes de tau es
    un resultado informativo, no un error de programa.
    """
    if len(streams_con_cambio) != len(ground_truths):
        raise ValueError(
            f"streams_con_cambio ({len(streams_con_cambio)}) y ground_truths "
            f"({len(ground_truths)}) deben tener la misma longitud"
        )

    retardos = []
    n_censurados = 0
    n_excluidos = 0

    for obs, gt in zip(streams_con_cambio, ground_truths):
        if gt.tau is None:
            raise ValueError(
                f"stream '{gt.stream_id}' tiene tau=None — pertenece a "
                "medir_arl0(), no a medir_arl1()"
            )
        detector = fabricar_detector()
        t, censurado = _tiempo_hasta_alarma(detector, obs)

        # t es un CONTEO de observaciones consumidas, así que una alarma
        # en el último instante ANTES del cambio (índice tau-1) da t=tau.
        # Por eso la comparación es <= y no <.
        if not censurado and t <= gt.tau:
            n_excluidos += 1
            continue

        if censurado:
            # nunca alarmó: el retardo es "al menos" lo que quedaba de
            # serie desde tau
            retardo = len(obs) - gt.tau
            n_censurados += 1
        else:
            retardo = t - gt.tau

        retardos.append(retardo)

    if not retardos:
        return ResultadoARL(
            arl=float("nan"),
            error_estandar=float("nan"),
            n_streams=0,
            n_censurados=0,
            n_excluidos_por_alarma_temprana=n_excluidos,
        )

    retardos_arr = np.array(retardos, dtype=float)
    error = (
        float(retardos_arr.std(ddof=1) / np.sqrt(len(retardos_arr)))
        if len(retardos_arr) > 1
        else 0.0
    )
    return ResultadoARL(
        arl=float(retardos_arr.mean()),
        error_estandar=error,
        n_streams=len(retardos),
        n_censurados=n_censurados,
        n_excluidos_por_alarma_temprana=n_excluidos,
    )