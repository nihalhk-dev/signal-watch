"""PSR y DSR: las fórmulas de la RQ2, contra lo que tienen que dar.

  · Con retornos normales, el error estándar de Mertens se reduce a Lo (2002).
  · PSR = 0,5 cuando lo medido es exactamente el listón.
  · El listón SR0 es 0 con una sola prueba y crece con N.
  · SR0 coincide con el máximo simulado de N estrategias de puro ruido.
"""

import math

import numpy as np
import pandas as pd
import pytest

from signal_watch.evaluation.deflated_sharpe import (
    error_estandar_sharpe,
    momentos,
    psr,
    sr0_maximo_esperado,
)


def test_con_normalidad_mertens_se_reduce_a_lo():
    sr, t = 0.18, 330
    assert error_estandar_sharpe(sr, t, asimetria=0.0, curtosis=3.0) == pytest.approx(
        math.sqrt((1 + sr**2 / 2) / (t - 1)))


def test_colas_gordas_agrandan_el_error():
    assert error_estandar_sharpe(0.2, 300, 0.0, 6.0) > error_estandar_sharpe(0.2, 300, 0.0, 3.0)


def test_psr_es_medio_en_el_liston():
    assert psr(0.15, 0.15, 400, 0.0, 3.0) == pytest.approx(0.5)


def test_psr_crece_con_el_sharpe_y_con_la_muestra():
    assert psr(0.20, 0.0, 300, 0, 3) > psr(0.10, 0.0, 300, 0, 3)
    assert psr(0.10, 0.0, 600, 0, 3) > psr(0.10, 0.0, 300, 0, 3)


def test_sr0_es_cero_sin_busqueda_y_crece_con_n():
    t = 330
    valores = [sr0_maximo_esperado(n, t) for n in (1, 10, 100, 316)]
    assert valores[0] == 0.0
    assert all(a < b for a, b in zip(valores, valores[1:]))


def test_sr0_coincide_con_el_maximo_simulado_de_ruido():
    n, t, reps = 100, 330, 1500
    rng = np.random.default_rng(0)
    maximos = [ (lambda x: (x.mean(0) / x.std(0, ddof=1)).max())(rng.standard_normal((t, n)))
                for _ in range(reps)]
    assert sr0_maximo_esperado(n, t) == pytest.approx(np.mean(maximos), rel=0.03)


def test_momentos_de_una_normal():
    x = pd.Series(np.random.default_rng(1).normal(0.01, 0.05, 200_000))
    m = momentos(x)
    assert m["sr"] == pytest.approx(0.2, abs=0.01)
    assert m["asimetria"] == pytest.approx(0.0, abs=0.03)
    assert m["curtosis"] == pytest.approx(3.0, abs=0.05)
