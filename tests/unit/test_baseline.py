"""Los detectores de referencia: el folclore (UmbralFijo) y 3-sigma."""

import pytest

from signal_watch.detectors.baseline import TresSigma, UmbralFijo
from signal_watch.gold.schemas import Direction

ALTO = Direction.HIGHER_IS_WORSE


def test_psi_mayor_que_025_es_estricto(hacer_serie):
    d = UmbralFijo(0.25)
    assert d.procesar_serie(hacer_serie([0.25] * 10, direction=ALTO)) == []
    assert d.procesar_serie(hacer_serie([0.10, 0.26], direction=ALTO))[0].t == 1


def test_umbral_fijo_lower_is_worse(hacer_serie):
    d = UmbralFijo(0.6, direction=Direction.LOWER_IS_WORSE)
    assert d.procesar_serie(hacer_serie([0.7, 0.65, 0.59]))[0].t == 2


def test_tres_sigma_es_estricto_y_de_un_solo_instante(hacer_serie):
    d = TresSigma(0.0, 1.0, k=3.0)  # μ0 = 0, σ = 1: distancias exactas, sin coma flotante en el borde
    assert d.procesar_serie(hacer_serie([-3.0] * 10)) == []  # exactamente 3σ: no
    assert d.procesar_serie(hacer_serie([0.0, -3.01]))[0].t == 1
    # no acumula: muchas caídas de 2,9σ seguidas nunca alarman
    assert d.procesar_serie(hacer_serie([-2.9] * 500)) == []


def test_tres_sigma_no_alarma_si_mejora(hacer_serie):
    assert TresSigma(0.7, 0.05).procesar_serie(hacer_serie([0.95] * 10)) == []
    assert TresSigma(0.01, 0.005, direction=ALTO).procesar_serie(hacer_serie([0.0] * 10, direction=ALTO)) == []


@pytest.mark.parametrize("kwargs", [dict(sigma=0), dict(k=0)])
def test_tres_sigma_parametros_imposibles(kwargs):
    with pytest.raises(ValueError):
        TresSigma(**{**dict(mu0=0.7, sigma=0.05, k=3.0), **kwargs})
