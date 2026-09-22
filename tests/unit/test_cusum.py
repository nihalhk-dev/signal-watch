"""CUSUM: S[t] = max(0, S[t-1] − z[t] − k) con z = (x − μ0)/σ; alarma si S > h."""

import numpy as np
import pytest

from signal_watch.detectors.cusum import CUSUM
from signal_watch.gold.schemas import Direction


@pytest.mark.parametrize("kwargs", [dict(sigma=0), dict(k=-0.1), dict(h=0)])
def test_parametros_imposibles(kwargs):
    with pytest.raises(ValueError):
        CUSUM(**{**dict(mu0=0.7, sigma=0.05, k=0.5, h=5.0), **kwargs})


def test_en_el_nivel_de_referencia_no_acumula(hacer_serie):
    d = CUSUM(0.7, 0.05, 0.5, 5.0)
    assert d.procesar_serie(hacer_serie([0.7] * 500)) == []
    assert d.s == 0.0


def test_caida_de_3_sigma_se_detecta_al_tercer_paso(hacer_serie):
    # μ0 = 0 y σ = 1 para que z sea exacto (con 0,7 − 0,15 la coma flotante
    # da z = −3,0000000000000004 y el borde "5,0 no es > 5" deja de serlo).
    # Cada paso suma 3 − 0,5 = 2,5: 2,5 → 5,0 (no > 5) → 7,5 > 5
    valores = [0.0] * 30 + [-3.0] * 10
    alarmas = CUSUM(0.0, 1.0, 0.5, 5.0).procesar_serie(hacer_serie(valores))
    assert alarmas[0].t == 32
    assert alarmas[0].estadistico == pytest.approx(7.5)


def test_lower_is_worse_no_alarma_si_la_metrica_mejora(hacer_serie):
    assert CUSUM(0.7, 0.05, 0.5, 2.0).procesar_serie(hacer_serie([0.9] * 100)) == []


def test_higher_is_worse_vigila_subidas_y_no_bajadas(hacer_serie):
    sube = hacer_serie([0.01] * 5 + [0.05] * 5, direction=Direction.HIGHER_IS_WORSE)
    baja = hacer_serie([0.01] * 5 + [0.0] * 50, direction=Direction.HIGHER_IS_WORSE)
    d = CUSUM(0.01, 0.005, 0.5, 4.0, direction=Direction.HIGHER_IS_WORSE)
    assert d.procesar_serie(sube) != []
    assert d.procesar_serie(baja) == []


def test_el_recorte_a_cero_no_hace_pagar_la_buena_racha(hacer_serie):
    """Por qué max(0, …): tras 200 periodos muy buenos, el cambio se detecta
    igual de rápido que partiendo de cero."""
    cambio = [0.7 - 2 * 0.05] * 20
    fresco = CUSUM(0.7, 0.05, 0.5, 4.0).procesar_serie(hacer_serie(cambio))[0].t
    tras_racha = CUSUM(0.7, 0.05, 0.5, 4.0).procesar_serie(hacer_serie([0.8] * 200 + cambio))[0].t - 200
    assert tras_racha == fresco


def test_reset_vuelve_a_cero(hacer_serie):
    d = CUSUM(0.7, 0.05, 0.5, 100.0)
    for obs in hacer_serie([0.6] * 5):
        d.update(obs)
    assert d.s > 0
    d.reset()
    assert d.s == 0.0


def test_un_umbral_mayor_tarda_mas_en_dar_falsas_alarmas(hacer_serie):
    rng = np.random.default_rng(0)
    series = [hacer_serie(0.7 + 0.05 * rng.standard_normal(400)) for _ in range(200)]

    def arl0(h):
        tiempos = []
        for s in series:
            a = CUSUM(0.7, 0.05, 0.5, h).procesar_serie(s)
            tiempos.append(a[0].t + 1 if a else len(s))
        return np.mean(tiempos)

    assert arl0(2.0) < arl0(3.0) < arl0(4.0)
