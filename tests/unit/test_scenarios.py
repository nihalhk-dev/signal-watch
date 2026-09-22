"""Los escenarios de cambio, y el bug más grave de §8.1: el SIGNO.

scenarios.py desplaza por la cantidad CON SIGNO que recibe; quien conoce la
dirección (build_gold) pone el signo. El bug era inyectar +δ en el AUC, es
decir, una MEJORA del modelo mientras el CUSUM vigilaba caídas.
"""

import numpy as np
import pytest

from signal_watch.synthetic.build_gold import EscenarioConfig, generar_stream
from signal_watch.synthetic.scenarios import (
    aplicar_cambio_varianza,
    aplicar_deriva,
    aplicar_salto,
    aplicar_sin_cambio,
)

BASE = np.zeros(100)


def test_salto():
    r = aplicar_salto(BASE, tau=40, delta_sigma=-2.0, sigma=0.05)
    assert np.all(r[:40] == 0) and np.allclose(r[40:], -0.1)
    assert np.all(BASE == 0), "no modifica la entrada"


def test_deriva_es_una_rampa_hasta_el_salto_completo():
    r = aplicar_deriva(BASE, tau=40, delta_sigma=1.0, sigma=1.0, duracion=20)
    assert np.all(r[:40] == 0)
    assert r[40] == 0 and np.all(np.diff(r[40:60]) > 0)
    assert np.allclose(r[60:], 1.0)


def test_cambio_de_varianza_no_mueve_la_media():
    base = np.random.default_rng(0).standard_normal(200_000)
    r = aplicar_cambio_varianza(base, tau=100_000, factor_varianza=4.0, rng=np.random.default_rng(1))
    assert np.array_equal(r[:100_000], base[:100_000])
    assert r[100_000:].mean() == pytest.approx(0, abs=0.02)
    assert r[100_000:].var() / base[:100_000].var() == pytest.approx(4.0, rel=0.05)


def test_sin_cambio_es_una_copia():
    r = aplicar_sin_cambio(BASE)
    assert np.array_equal(r, BASE) and r is not BASE


def _media_antes_despues(tipo, escenario, n_semillas=30):
    antes, despues = [], []
    for s in range(n_semillas):
        obs, _ = generar_stream(EscenarioConfig(nombre="t", tipo_metrica=tipo, escenario=escenario,
                                                n=100, tau=40, delta_sigma=1.0, rho=0.5,
                                                n_obs_base=800, seed=10_000 + s))
        v = np.array([o.value for o in obs])
        antes.append(v[:40].mean())
        despues.append(v[60:].mean())
    return np.mean(antes), np.mean(despues)


@pytest.mark.parametrize("escenario", ["salto", "deriva"])
def test_degradar_el_auc_lo_hace_bajar(escenario):
    antes, despues = _media_antes_despues("auc", escenario)
    assert despues < antes


@pytest.mark.parametrize("escenario", ["salto", "deriva"])
def test_degradar_el_psi_lo_hace_subir(escenario):
    antes, despues = _media_antes_despues("psi", escenario)
    assert despues > antes
