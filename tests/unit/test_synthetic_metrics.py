"""AUC y PSI sintéticos: forma y ESCALA.

Protege los bugs de §8.5b (el ×100 que ponía el 99% del PSI sano por encima
de 0,25) y §8.5c (un incremento de PSI sin relación con su propio ruido).
"""

import numpy as np
import pytest
from scipy.stats import skew

from signal_watch.synthetic.build_gold import EscenarioConfig, generar_stream
from signal_watch.synthetic.metrics import (
    clip_auc,
    clip_psi,
    generar_psi_desde_chi2,
    inyectar_cambio_psi,
    se_hanley_mcneil,
)


def test_psi_sano_tiene_la_escala_de_chi2_entre_n():
    psi = generar_psi_desde_chi2(n=200_000, n_bins=10, n_obs=800, rng=np.random.default_rng(0))
    assert psi.mean() == pytest.approx(9 / 800, rel=0.02)
    assert (psi > 0.25).mean() == 0.0  # un PSI sano no cruza el umbral del folclore


def test_psi_tiene_cola_derecha_no_es_gaussiano():
    psi = generar_psi_desde_chi2(n=200_000, n_bins=10, n_obs=800, rng=np.random.default_rng(0))
    assert skew(psi) == pytest.approx(np.sqrt(8 / 9), rel=0.05)  # asimetría de chi2(9)


def test_el_incremento_del_psi_se_mide_en_su_propio_ruido():
    antes, despues = [], []
    for s in range(200):
        obs, _ = generar_stream(EscenarioConfig(nombre="t", tipo_metrica="psi", escenario="salto", n=100,
                                                tau=40, delta_sigma=1.0, rho=0.5, n_obs_base=800, seed=s))
        v = np.array([o.value for o in obs])
        antes.append(v[:40].mean()); despues.append(v[40:].mean())
    sigma_psi = np.sqrt(2 * 9) / 800
    assert np.mean(despues) - np.mean(antes) == pytest.approx(sigma_psi, rel=0.1)


def test_hanley_mcneil_baja_con_la_muestra():
    se = [float(se_hanley_mcneil(0.7, n)) for n in (100, 1000, 10_000)]
    assert se[0] > se[1] > se[2] > 0
    assert se[0] / se[2] == pytest.approx(10, rel=0.1)  # ~ 1/√n


def test_recortes():
    assert clip_auc(np.array([0.3, 0.7, 1.2])).tolist() == [0.5, 0.7, 0.999]
    assert clip_psi(np.array([-0.1, 0.2])).tolist() == [0.0, 0.2]


def test_inyectar_cambio_psi_solo_desde_tau():
    r = inyectar_cambio_psi(np.full(10, 0.01), tau=4, incremento=0.02)
    assert np.allclose(r[:4], 0.01) and np.allclose(r[4:], 0.03)
