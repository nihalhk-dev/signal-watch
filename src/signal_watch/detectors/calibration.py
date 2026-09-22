"""Calibración: encuentra el umbral h que produce el ARL0 deseado.

No existe una fórmula cerrada simple para "qué h da un ARL0 de 200"
(depende de k, del ruido, de la distribución de la métrica). Así que
se calibra por SIMULACIÓN: para un h candidato, se generan muchas
series SIN cambio real (bajo H0), se mide cada cuánto dispara el
detector en promedio (eso ES el ARL0 medido), y se ajusta h con
bisección hasta acercarse al objetivo.

Por qué bisección y no prueba y error a ojo:
  El ARL0 es una función MONÓTONA de h — subir h siempre alarga el
  ARL0 medio (un umbral más alto tarda más en cruzarse, sea cual sea
  la fuente del ruido). Esa monotonía es justo lo que hace que la
  bisección funcione: si el ARL0 medido es menor que el objetivo, h
  es demasiado bajo, se sube; si es mayor, se baja. Se repite hasta
  converger dentro de una tolerancia.

Esta pieza es la que separa "elegí h=5 porque sí" de "elegí h para
que el detector tenga una falsa alarma cada 200 periodos en promedio,
medido sobre miles de simulaciones". Sin calibración, cualquier
resultado del proyecto es arbitrario.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from signal_watch.detectors.base import Detector
from signal_watch.gold.schemas import Direction, MetricObservation
from signal_watch.synthetic.generator import generar_ruido_ar1


@dataclass(frozen=True)
class ResultadoCalibracion:
    """El resultado de calibrar un detector: el h encontrado, y la
    evidencia de que funciona (para poder auditarlo, no solo confiar)."""

    h_calibrado: float
    arl0_medido: float
    arl0_objetivo: float
    n_simulaciones: int
    convergio: bool


def medir_arl0(
    fabricar_detector: callable,
    mu0: float,
    sigma: float,
    rho: float,
    n_periodos_max: int,
    n_simulaciones: int,
    seed: int,
) -> float:
    """Mide el ARL0 real de un detector: genera n_simulaciones series
    SIN cambio real (bajo H0, puro ruido AR(1) centrado en mu0), corre
    el detector sobre cada una, y devuelve el promedio de "cuánto tardó
    en dispararse" (o n_periodos_max, censurado, si nunca se disparó
    dentro de la simulación).

    fabricar_detector: una función sin argumentos que devuelve una
    instancia NUEVA del detector a medir (necesitamos una instancia
    limpia por simulación, no reutilizar estado entre series).
    """
    rng_maestro = np.random.default_rng(seed)
    tiempos_hasta_alarma = []

    for _ in range(n_simulaciones):
        semilla_serie = int(rng_maestro.integers(0, 2**31 - 1))
        rng_serie = np.random.default_rng(semilla_serie)
        ruido = generar_ruido_ar1(n_periodos_max, rho, sigma, rng_serie)
        valores = mu0 + ruido

        detector = fabricar_detector()
        disparo = None
        for t in range(n_periodos_max):
            obs = MetricObservation(
                stream_id="calib",
                t=t,
                timestamp=__import__("datetime").date(2020, 1, 1),
                value=float(valores[t]),
                value_se=sigma,
                n_obs=500,
                direction=Direction.LOWER_IS_WORSE,
            )
            alarma = detector.update(obs)
            if alarma is not None:
                # Observaciones CONSUMIDAS, no el índice: una alarma en t=0
                # es una racha de 1. Mismo convenio que evaluation/arl.py
                # (el off-by-one de MEMORIA §8.5d, que aquí seguía vivo).
                disparo = t + 1
                break

        # si nunca se disparó, se censura al máximo simulado (subestima
        # el ARL0 real, pero es la convención estándar y conservadora:
        # mejor subestimar cuánto "aguanta" un detector que sobreestimarlo)
        tiempos_hasta_alarma.append(disparo if disparo is not None else n_periodos_max)

    return float(np.mean(tiempos_hasta_alarma))


def calibrar_umbral(
    fabricar_detector_con_h: callable,
    arl0_objetivo: float,
    mu0: float,
    sigma: float,
    rho: float,
    h_min: float = 0.5,
    h_max: float = 50.0,
    n_periodos_max: int = 2000,
    n_simulaciones: int = 200,
    tolerancia_relativa: float = 0.1,
    max_iteraciones: int = 20,
    seed: int = 0,
) -> ResultadoCalibracion:
    """Encuentra, por bisección, el h que da un ARL0 lo más cercano
    posible a arl0_objetivo.

    fabricar_detector_con_h: función que recibe un h y devuelve una
    instancia NUEVA del detector con ese h (p.ej.
    lambda h: CUSUM(mu0=mu0, sigma=sigma, k=k, h=h)).

    La búsqueda converge cuando el ARL0 medido está dentro de
    tolerancia_relativa del objetivo (por defecto, 10%), o se agota
    max_iteraciones — en cuyo caso se devuelve el mejor h encontrado,
    con convergio=False, para que quien lo use SEPA que el resultado
    es aproximado y no lo dé por bueno sin más.
    """
    if h_min >= h_max:
        raise ValueError(f"h_min ({h_min}) debe ser menor que h_max ({h_max})")

    lo, hi = h_min, h_max
    mejor_h = h_max
    mejor_arl0 = None
    convergio = False

    for iteracion in range(max_iteraciones):
        h_candidato = (lo + hi) / 2
        arl0_medido = medir_arl0(
            fabricar_detector=lambda: fabricar_detector_con_h(h_candidato),
            mu0=mu0,
            sigma=sigma,
            rho=rho,
            n_periodos_max=n_periodos_max,
            n_simulaciones=n_simulaciones,
            seed=seed + iteracion,  # semilla distinta cada iteración
        )

        mejor_h = h_candidato
        mejor_arl0 = arl0_medido

        error_relativo = abs(arl0_medido - arl0_objetivo) / arl0_objetivo
        if error_relativo <= tolerancia_relativa:
            convergio = True
            break

        # monotonía: ARL0 más bajo de lo que queremos -> el detector
        # dispara demasiado pronto -> h es demasiado bajo -> subir h
        if arl0_medido < arl0_objetivo:
            lo = h_candidato
        else:
            hi = h_candidato

    return ResultadoCalibracion(
        h_calibrado=mejor_h,
        arl0_medido=mejor_arl0,
        arl0_objetivo=arl0_objetivo,
        n_simulaciones=n_simulaciones,
        convergio=convergio,
    )