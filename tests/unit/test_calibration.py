"""detectors/calibration.py: calibración por simulación con ruido AR(1) propio.

Recordatorio (MEMORIA §14.22): este camino NO produce ninguno de los números
del trabajo (salen de delay_curves.py y error_analysis.py). Se prueba igual
porque existe y está en el repositorio: código sin probar es una afirmación
sin demostrar.
"""

import pytest

from signal_watch.detectors.base import Alarma, Detector
from signal_watch.detectors.calibration import calibrar_umbral, medir_arl0
from signal_watch.detectors.cusum import CUSUM


class AlarmaEn(Detector):
    def __init__(self, indice):
        self.indice = indice
        super().__init__()

    def reset(self):
        pass

    def update(self, obs):
        return Alarma(t=obs.t, estadistico=1.0) if obs.t == self.indice else None


RUIDO = dict(mu0=0.0, sigma=1.0, rho=0.0, n_periodos_max=100, n_simulaciones=5, seed=0)


def test_la_racha_cuenta_observaciones_consumidas():
    """Mismo convenio que evaluation/arl.py (§8.5d): alarma en el índice 9 = racha de 10."""
    assert medir_arl0(lambda: AlarmaEn(9), **RUIDO) == 10


def test_sin_alarma_se_censura_en_el_maximo():
    assert medir_arl0(lambda: AlarmaEn(None), **RUIDO) == 100


def test_misma_semilla_mismo_resultado():
    f = lambda: CUSUM(0.0, 1.0, 0.5, 3.0)  # noqa: E731
    kw = dict(mu0=0.0, sigma=1.0, rho=0.5, n_periodos_max=500, n_simulaciones=50)
    assert medir_arl0(f, seed=7, **kw) == medir_arl0(f, seed=7, **kw)


def test_la_biseccion_converge_al_objetivo():
    r = calibrar_umbral(lambda h: CUSUM(0.0, 1.0, 0.5, h), arl0_objetivo=60, mu0=0.0, sigma=1.0,
                        rho=0.0, h_min=0.5, h_max=10.0, n_periodos_max=1000, n_simulaciones=300,
                        tolerancia_relativa=0.1, seed=1)
    assert r.convergio and abs(r.arl0_medido - 60) / 60 <= 0.1


def test_rango_imposible():
    with pytest.raises(ValueError):
        calibrar_umbral(lambda h: CUSUM(0.0, 1.0, 0.5, h), arl0_objetivo=60, mu0=0.0, sigma=1.0,
                        rho=0.0, h_min=5.0, h_max=5.0)
