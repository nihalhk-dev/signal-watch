"""Page-Hinkley y la identidad de §9: con delta = k y lambda_ = h da
EXACTAMENTE las mismas alarmas que el CUSUM. No son dos detectores: son el
mismo test con otra parametrización."""

import numpy as np
import pytest

from signal_watch.detectors.cusum import CUSUM
from signal_watch.detectors.page_hinkley import PageHinkley
from signal_watch.gold.schemas import Direction


def _series(hacer_serie, n=300, semilla=3):
    rng = np.random.default_rng(semilla)
    out = []
    for i in range(n):
        x = 0.7 + 0.05 * rng.standard_normal(120)
        if i % 2:
            x[50:] -= 0.05 * rng.uniform(0.5, 2.0)  # la mitad, con una caída
        out.append(hacer_serie(x))
    return out


@pytest.mark.parametrize("k, h", [(0.5, 3.0), (0.25, 5.0), (1.0, 2.0)])
def test_identidad_con_cusum(hacer_serie, k, h):
    for s in _series(hacer_serie):
        a = CUSUM(0.7, 0.05, k, h).procesar_serie(s)
        b = PageHinkley(0.7, 0.05, k, h).procesar_serie(s)
        assert [x.t for x in a] == [x.t for x in b]
        if a:
            assert a[0].estadistico == pytest.approx(b[0].estadistico)


def test_con_delta_distinto_de_k_ya_no_coinciden(hacer_serie):
    """Control: la identidad viene de la igualdad de parámetros, no de un error de prueba."""
    distintas = sum(
        [x.t for x in CUSUM(0.7, 0.05, 0.5, 3.0).procesar_serie(s)]
        != [x.t for x in PageHinkley(0.7, 0.05, 0.25, 3.0).procesar_serie(s)]
        for s in _series(hacer_serie))
    assert distintas > 0


def test_estandariza_por_sigma(hacer_serie):
    """El bug de §8.3: sin dividir por sigma, delta significaba cosas distintas
    en AUC y en PSI. Escalar la métrica y su sigma a la vez no cambia nada."""
    s1 = hacer_serie([0.7] * 20 + [0.6] * 20)
    s2 = hacer_serie([7.0] * 20 + [6.0] * 20)
    a = PageHinkley(0.7, 0.05, 0.25, 4.0).procesar_serie(s1)
    b = PageHinkley(7.0, 0.5, 0.25, 4.0).procesar_serie(s2)
    assert [x.t for x in a] == [x.t for x in b] != []


def test_higher_is_worse(hacer_serie):
    d = PageHinkley(0.01, 0.005, 0.25, 3.0, direction=Direction.HIGHER_IS_WORSE)
    assert d.procesar_serie(hacer_serie([0.01] * 5 + [0.04] * 5, direction=Direction.HIGHER_IS_WORSE))
    assert not d.procesar_serie(hacer_serie([0.01] * 5 + [0.0] * 50, direction=Direction.HIGHER_IS_WORSE))


@pytest.mark.parametrize("kwargs", [dict(sigma=0), dict(delta=-1), dict(lambda_=0)])
def test_parametros_imposibles(kwargs):
    with pytest.raises(ValueError):
        PageHinkley(**{**dict(mu0=0.7, sigma=0.05, delta=0.25, lambda_=5.0), **kwargs})
