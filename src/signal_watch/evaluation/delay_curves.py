"""
evaluation/delay_curves.py

El resultado central de la tesis: para cada tipo de métrica (AUC, PSI),
compara los detectores en el plano (ARL0, ARL1) — falsas alarmas vs
retardo de detección.

Metodología:
  1. CUSUM y Page-Hinkley (umbral ajustable) se CALIBRAN en el banco
     de CALIBRACIÓN para varios niveles objetivo de ARL0 (R4: semillas
     disjuntas de las de evaluación).
  2. UmbralFijo (PSI>0.25) y 3-sigma son folklore de la industria con
     umbral FIJO por definición — no se calibran, dan un punto único.
  3. Todas las mediciones de rendimiento se hacen sobre el banco de
     EVALUACIÓN.
  4. mu0 y sigma se estiman de los streams sin_cambio del banco de
     CALIBRACIÓN — nunca del de evaluación.

EL ARL1 SE MIDE POR ESTRATO (escenario × delta), NUNCA AGRUPADO:
  Un ARL1 que promedia los tres escenarios y las cinco magnitudes no
  mide el rendimiento de un detector, mide la composición del banco.
  CUSUM y 3-sigma tienen perfiles opuestos (CUSUM gana en derivas
  pequeñas; 3-sigma en saltos de 3 sigma y en cambio_varianza, donde
  CUSUM es ciego porque la media no se mueve), así que el promedio
  agrupado llega a INVERTIR el orden entre detectores. El ARL0, en
  cambio, SÍ es un número único por punto de operación: es una
  propiedad del detector bajo H0 y no depende del escenario.

Esta pieza SOLO calcula. No dibuja (eso es reporting/figures.py, R6/R9).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path

from signal_watch.detectors.baseline import TresSigma, UmbralFijo
from signal_watch.detectors.cusum import CUSUM
from signal_watch.detectors.page_hinkley import PageHinkley
from signal_watch.evaluation.arl import medir_arl0, medir_arl1
from signal_watch.evaluation.carga_banco import (
    cargar_banco,
    estratos_con_cambio,
    filtrar_por_metrica,
)


@dataclass(frozen=True)
class PuntoOperacion:
    """Una fila de resultados: un detector, en un punto de operación,
    medido sobre un estrato concreto (escenario, delta).

    Formato largo a propósito: el ARL0 se repite entre estratos del
    mismo punto de operación (es el mismo número — no depende del
    escenario), pero tener una fila por estrato hace que la tabla sea
    directamente analizable y graficable sin reestructurarla.

    Cada ARL lleva al lado sus dos formas de no-detección: censura
    (nunca alarmó) y, en ARL1, alarmas pre-tau (gritó antes de que
    hubiera nada que detectar).
    """

    detector: str
    parametro_umbral: float | None  # h o lambda_; None para folklore

    # ARL0 — propiedad del detector bajo H0, no depende del estrato
    arl0: float
    arl0_ic95: tuple[float, float]
    arl0_n_censurados: int
    arl0_n_streams: int

    # el estrato
    escenario: str
    delta_sigma: float

    # ARL1 — medido DENTRO del estrato
    arl1: float
    arl1_ic95: tuple[float, float]
    arl1_n_censurados: int
    arl1_n_streams: int
    arl1_n_excluidos: int


def estimar_baseline(streams_sin_cambio: list[list]) -> tuple[float, float]:
    """Estima mu0 y sigma agrupando todas las observaciones de todos los
    streams sin_cambio del banco de CALIBRACIÓN. Nunca llames a esto con
    el banco de evaluación."""
    valores = [obs.value for stream in streams_sin_cambio for obs in stream]
    return statistics.mean(valores), statistics.stdev(valores)


def _calibrar_umbral_biseccion(
    fabricar_detector,
    streams_calibracion,
    arl0_objetivo: float,
    umbral_min: float,
    umbral_max: float,
    tolerancia: float = 0.05,
    max_iter: int = 30,
) -> float:
    """Bisección: asume ARL0 monótono creciente en el umbral."""
    lo, hi = umbral_min, umbral_max
    mid = (lo + hi) / 2
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        resultado = medir_arl0(lambda: fabricar_detector(mid), streams_calibracion)
        if abs(resultado.arl - arl0_objetivo) / arl0_objetivo < tolerancia:
            return mid
        if resultado.arl < arl0_objetivo:
            lo = mid
        else:
            hi = mid
    return mid


def _medir_punto_en_todos_los_estratos(
    nombre: str,
    fabricar_detector,
    umbral: float | None,
    streams_sin_cambio_evaluacion,
    estratos,
) -> list[PuntoOperacion]:
    """Mide un punto de operación: UN ARL0 (no depende del escenario)
    y UN ARL1 por cada estrato (escenario, delta)."""
    r0 = medir_arl0(fabricar_detector, streams_sin_cambio_evaluacion)

    puntos = []
    for (escenario, delta), (streams, gts) in sorted(estratos.items()):
        r1 = medir_arl1(fabricar_detector, streams, gts)
        if r1.n_streams == 0:
            print(
                f"  [{nombre} | {escenario} d={delta}] AVISO: ningun stream "
                f"utilizable ({r1.n_excluidos_por_alarma_temprana} alarmaron antes de tau).",
                flush=True,
            )
        puntos.append(
            PuntoOperacion(
                detector=nombre,
                parametro_umbral=umbral,
                arl0=r0.arl,
                arl0_ic95=r0.intervalo_95,
                arl0_n_censurados=r0.n_censurados,
                arl0_n_streams=r0.n_streams,
                escenario=escenario,
                delta_sigma=delta,
                arl1=r1.arl,
                arl1_ic95=r1.intervalo_95,
                arl1_n_censurados=r1.n_censurados,
                arl1_n_streams=r1.n_streams,
                arl1_n_excluidos=r1.n_excluidos_por_alarma_temprana,
            )
        )
    return puntos


def curva_detector_calibrable(
    nombre: str,
    fabricar_detector,
    streams_sin_cambio_calibracion,
    streams_sin_cambio_evaluacion,
    estratos,
    umbral_min: float,
    umbral_max: float,
    niveles_arl0_objetivo: list[float],
) -> list[PuntoOperacion]:
    """Un detector con umbral ajustable: calibra en el banco de
    calibración para cada ARL0 objetivo, y mide en evaluación."""
    puntos = []

    for objetivo in niveles_arl0_objetivo:
        umbral = _calibrar_umbral_biseccion(
            fabricar_detector,
            streams_sin_cambio_calibracion,
            objetivo,
            umbral_min,
            umbral_max,
        )
        print(
            f"    {nombre}: ARL0 objetivo={objetivo} -> umbral={umbral:.4f}",
            flush=True,
        )
        puntos.extend(
            _medir_punto_en_todos_los_estratos(
                nombre,
                lambda: fabricar_detector(umbral),
                umbral,
                streams_sin_cambio_evaluacion,
                estratos,
            )
        )
    return puntos


def punto_detector_folclore(
    nombre: str,
    fabricar_detector,
    streams_sin_cambio_evaluacion,
    estratos,
) -> list[PuntoOperacion]:
    """Una regla de umbral FIJO (folclore): no se calibra, un solo
    punto de operación — pero medido igualmente en todos los estratos."""
    print(f"    {nombre}: umbral fijo (sin calibrar), midiendo...", flush=True)
    return _medir_punto_en_todos_los_estratos(
        nombre, fabricar_detector, None, streams_sin_cambio_evaluacion, estratos
    )


def construir_curvas_para_metrica(
    tipo_metrica: str,
    ruta_calibracion_obs: Path,
    ruta_calibracion_gt: Path,
    ruta_evaluacion_obs: Path,
    ruta_evaluacion_gt: Path,
    niveles_arl0_objetivo: list[float] = [20, 30, 50, 70, 90],
    delta_page_hinkley: float = 0.25,
) -> dict[str, list[PuntoOperacion]]:
    """Punto de entrada: construye todos los puntos para tipo_metrica
    ('auc' o 'psi') usando los bancos reales en disco.

    delta_page_hinkley se deja en 0.25, distinto del k=0.5 del CUSUM,
    a propósito: con delta = k los dos detectores son ALGEBRAICAMENTE
    IDÉNTICOS (verificado, 500/500 series con las mismas alarmas), así
    que usar el mismo valor daría dos curvas superpuestas. Con un delta
    distinto, Page-Hinkley explora otro punto del compromiso
    tolerancia/sensibilidad dentro de la misma familia de tests.
    """
    print(f"  cargando bancos ({tipo_metrica})...", flush=True)
    banco_calibracion = filtrar_por_metrica(
        cargar_banco(ruta_calibracion_obs, ruta_calibracion_gt), tipo_metrica
    )
    banco_evaluacion = filtrar_por_metrica(
        cargar_banco(ruta_evaluacion_obs, ruta_evaluacion_gt), tipo_metrica
    )

    mu0, sigma = estimar_baseline(banco_calibracion.streams_sin_cambio)
    direction = banco_evaluacion.streams_sin_cambio[0][0].direction
    estratos = estratos_con_cambio(banco_evaluacion)
    print(
        f"  mu0={mu0:.5f} sigma={sigma:.5f} | "
        f"{len(banco_calibracion.streams_sin_cambio)} streams sin_cambio (calib), "
        f"{len(estratos)} estratos con cambio (eval)",
        flush=True,
    )

    resultados: dict[str, list[PuntoOperacion]] = {}

    resultados["CUSUM"] = curva_detector_calibrable(
        "CUSUM",
        lambda h: CUSUM(mu0=mu0, sigma=sigma, k=0.5, h=h, direction=direction),
        banco_calibracion.streams_sin_cambio,
        banco_evaluacion.streams_sin_cambio,
        estratos,
        umbral_min=1.0,
        umbral_max=20.0,
        niveles_arl0_objetivo=niveles_arl0_objetivo,
    )

    # mismo rango de búsqueda que el h del CUSUM: ahora que Page-Hinkley
    # estandariza por sigma, lambda_ está en las mismas unidades que h.
    resultados["Page-Hinkley"] = curva_detector_calibrable(
        "Page-Hinkley",
        lambda lam: PageHinkley(
            mu0=mu0, sigma=sigma, delta=delta_page_hinkley,
            lambda_=lam, direction=direction,
        ),
        banco_calibracion.streams_sin_cambio,
        banco_evaluacion.streams_sin_cambio,
        estratos,
        umbral_min=1.0,
        umbral_max=20.0,
        niveles_arl0_objetivo=niveles_arl0_objetivo,
    )

    resultados["3-sigma"] = punto_detector_folclore(
        "3-sigma",
        lambda: TresSigma(mu0=mu0, sigma=sigma, direction=direction),
        banco_evaluacion.streams_sin_cambio,
        estratos,
    )

    if tipo_metrica == "psi":
        resultados["UmbralFijo (PSI>0.25)"] = punto_detector_folclore(
            "UmbralFijo (PSI>0.25)",
            lambda: UmbralFijo(umbral=0.25, direction=direction),
            banco_evaluacion.streams_sin_cambio,
            estratos,
        )

    return resultados

def seleccionar_punto_comparable(df, tipo_metrica: str, arl0_referencia: float | None = None):
    """Para cada detector, elige el punto de operación cuyo ARL0 medido
    esté más cerca de una referencia común.

    Por qué hace falta: 3-sigma y UmbralFijo tienen UN solo punto de
    operación (su umbral es fijo por definición), mientras CUSUM y
    Page-Hinkley tienen uno por cada nivel de ARL0 objetivo. Comparar el
    mejor retardo de CUSUM (el de su punto más agresivo) contra el único
    punto de 3-sigma sería hacer trampa: CUSUM estaría disparando muchas
    más falsas alarmas a cambio de esa velocidad. La única comparación
    con sentido es a tasa de falsas alarmas igualada.

    Por defecto la referencia es el ARL0 de 3-sigma, porque es el
    baseline contra el que se quiere medir.
    """
    import pandas as pd

    sub = df[df["tipo_metrica"] == tipo_metrica]
    if arl0_referencia is None:
        arl0_referencia = sub[sub["detector"] == "3-sigma"]["arl0"].iloc[0]

    filas = []
    for det in sub["detector"].unique():
        d = sub[sub["detector"] == det]
        if d["umbral"].notna().any():
            por_umbral = d.groupby("umbral")["arl0"].first()
            mejor = (por_umbral - arl0_referencia).abs().idxmin()
            filas.append(d[d["umbral"] == mejor])
        else:
            filas.append(d)  # folclore: umbral fijo, un solo punto
    return pd.concat(filas), arl0_referencia