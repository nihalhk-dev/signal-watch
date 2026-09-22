"""El ruido AR(1) del banco sintético y la serie completa."""

from datetime import date

import numpy as np
import pytest

from signal_watch.gold.schemas import Direction
from signal_watch.synthetic.generator import generar_ruido_ar1, generar_serie


def _autocorr(x):
    return np.corrcoef(x[:-1], x[1:])[0, 1]


@pytest.mark.parametrize("rho", [0.0, 0.5, 0.9])
def test_se_recupera_rho(rho):
    x = generar_ruido_ar1(200_000, rho, 1.0, np.random.default_rng(1))
    assert _autocorr(x) == pytest.approx(rho, abs=0.01)


def test_arranca_desde_la_varianza_estacionaria():
    rho, sigma = 0.9, 1.0
    primeros = [generar_ruido_ar1(2, rho, sigma, np.random.default_rng(s))[0] for s in range(20_000)]
    assert np.var(primeros) == pytest.approx(sigma**2 / (1 - rho**2), rel=0.05)


def test_misma_semilla_misma_serie():
    a = generar_ruido_ar1(100, 0.5, 1.0, np.random.default_rng(42))
    b = generar_ruido_ar1(100, 0.5, 1.0, np.random.default_rng(42))
    c = generar_ruido_ar1(100, 0.5, 1.0, np.random.default_rng(43))
    assert np.array_equal(a, b) and not np.array_equal(a, c)


@pytest.mark.parametrize("rho, sigma", [(1.0, 1.0), (-0.1, 1.0), (0.5, -1.0)])
def test_parametros_imposibles(rho, sigma):
    with pytest.raises(ValueError):
        generar_ruido_ar1(10, rho, sigma, np.random.default_rng(0))


def _serie(tau=40, **kw):
    base = dict(stream_id="s", n=100, mu_base=0.7, sigma=0.05, rho=0.5, tau=tau, delta_sigma=-2.0,
                n_obs_base=800, direction=Direction.LOWER_IS_WORSE, fecha_inicio=date(2015, 1, 1), seed=7)
    return generar_serie(**{**base, **kw})


def test_la_serie_y_su_verdad_viajan_separadas():
    obs, gt = _serie()
    assert len(obs) == 100 and [o.t for o in obs] == list(range(100))
    assert gt.tau == 40 and all(not hasattr(o, "tau") for o in obs)
    assert all(o.value_se > 0 and o.n_obs > 0 for o in obs)


def test_el_cambio_empieza_en_tau():
    con, _ = _serie()
    sin, _ = _serie(tau=None)
    dif = np.array([a.value - b.value for a, b in zip(con, sin)])
    assert np.allclose(dif[:40], 0) and np.allclose(dif[40:], -2.0 * 0.05)


def test_tau_fuera_de_rango():
    with pytest.raises(ValueError):
        _serie(tau=100)
