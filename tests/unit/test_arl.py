"""La estadística de tiempos de parada, con un detector de juguete que
alarma en un instante conocido: así cada número esperado se sabe a mano.

Protege dos fallos reales de §8: el off-by-one de la racha (una alarma en
el índice 0 es una racha de 1, no de 0) y la exclusión silenciosa de las
alarmas antes de τ (ahora se cuentan y se devuelven).
"""

import math

import pytest

from signal_watch.detectors.base import Alarma, Detector
from signal_watch.evaluation.arl import _tiempo_hasta_alarma, medir_arl0, medir_arl1
from signal_watch.gold.metric_stream import GroundTruth


class AlarmaEn(Detector):
    """Dispara exactamente en el índice `indice` (None = nunca)."""

    def __init__(self, indice):
        self.indice = indice
        super().__init__()

    def reset(self):
        pass

    def update(self, obs):
        return Alarma(t=obs.t, estadistico=1.0) if obs.t == self.indice else None


def gt(tau):
    return GroundTruth(stream_id="s", tau=tau, escenario="salto")


def test_alarma_en_el_indice_cero_es_racha_uno(hacer_serie):
    assert _tiempo_hasta_alarma(AlarmaEn(0), hacer_serie([0] * 10)) == (1, False)


def test_sin_alarma_la_racha_es_la_longitud_y_esta_censurada(hacer_serie):
    assert _tiempo_hasta_alarma(AlarmaEn(None), hacer_serie([0] * 10)) == (10, True)


def test_arl0_media_y_censura(hacer_serie):
    series = [hacer_serie([0] * 50) for _ in range(3)]
    detectores = iter([AlarmaEn(9), AlarmaEn(19), AlarmaEn(None)])
    r = medir_arl0(lambda: next(detectores), series)
    assert r.arl == pytest.approx((10 + 20 + 50) / 3)
    assert (r.n_streams, r.n_censurados) == (3, 1)


def test_arl1_mide_el_retardo_desde_tau(hacer_serie):
    r = medir_arl1(lambda: AlarmaEn(44), [hacer_serie([0] * 100)], [gt(40)])
    assert r.arl == 5  # racha 45 − τ 40


def test_alarma_antes_de_tau_se_excluye_pero_se_cuenta(hacer_serie):
    series = [hacer_serie([0] * 100) for _ in range(3)]
    detectores = iter([AlarmaEn(10), AlarmaEn(39), AlarmaEn(40)])
    r = medir_arl1(lambda: next(detectores), series, [gt(40)] * 3)
    # índice 39 → racha 40 = τ: alarma en el último instante ANTES del cambio → excluida
    assert r.n_excluidos_por_alarma_temprana == 2
    assert (r.n_streams, r.arl) == (1, 1)


def test_retardo_censurado_cuenta_hasta_el_final(hacer_serie):
    r = medir_arl1(lambda: AlarmaEn(None), [hacer_serie([0] * 100)], [gt(40)])
    assert (r.arl, r.n_censurados) == (60, 1)


def test_si_todo_se_excluye_devuelve_nan_sin_romper(hacer_serie):
    r = medir_arl1(lambda: AlarmaEn(0), [hacer_serie([0] * 100)] * 2, [gt(40)] * 2)
    assert math.isnan(r.arl) and r.n_streams == 0 and r.n_excluidos_por_alarma_temprana == 2


def test_errores_de_uso(hacer_serie):
    with pytest.raises(ValueError):
        medir_arl1(lambda: AlarmaEn(None), [hacer_serie([0] * 10)], [])
    with pytest.raises(ValueError):
        medir_arl1(lambda: AlarmaEn(None), [hacer_serie([0] * 10)], [gt(None)])


def test_intervalo_95():
    from signal_watch.evaluation.arl import ResultadoARL
    assert ResultadoARL(100, 5, 50, 0).intervalo_95 == pytest.approx((90.2, 109.8))
