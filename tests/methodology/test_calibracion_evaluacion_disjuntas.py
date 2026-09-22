"""R4 — los datos que ajustan un detector no son los que lo evalúan.

Banco sintético: cuatro rangos de semillas (AUC y PSI × calibración y
evaluación), disjuntos dos a dos. Rama real: en cada stream, calibración,
verificación e inyección usan semillas distintas, y ninguna cae dentro de
los rangos del banco sintético.
"""

import importlib.util
from itertools import combinations

import pytest
import yaml

from signal_watch.paths import PATHS


@pytest.fixture(scope="module")
def build_synthetic():
    ruta = PATHS.root / "scripts" / "build_synthetic.py"
    spec = importlib.util.spec_from_file_location("build_synthetic", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def rangos(build_synthetic):
    b = build_synthetic
    return {
        "auc_calib": {c.seed for c in b._construir_configs("auc", b.SEMILLA_BASE_CALIBRACION, "x")},
        "psi_calib": {c.seed for c in b._construir_configs("psi", b.SEMILLA_BASE_CALIBRACION + 500_000, "x")},
        "auc_eval": {c.seed for c in b._construir_configs("auc", b.SEMILLA_BASE_EVALUACION, "x")},
        "psi_eval": {c.seed for c in b._construir_configs("psi", b.SEMILLA_BASE_EVALUACION + 500_000, "x")},
    }


def test_los_cuatro_rangos_son_disjuntos_dos_a_dos(rangos):
    for a, b in combinations(rangos, 2):
        assert not (rangos[a] & rangos[b]), f"R4 violada: {a} y {b} comparten semillas"


def test_cada_serie_tiene_su_semilla(rangos, build_synthetic):
    b = build_synthetic
    esperado = (len(b.ESCENARIOS) - 1) * len(b.DELTAS_SIGMA) * b.N_REPLICAS + b.N_REPLICAS
    assert all(len(s) == esperado for s in rangos.values())


def _streams_reales():
    for ruta in sorted((PATHS.configs / "streams").glob("*.yaml")):
        cfg = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        if "monitorizacion" in cfg and "inyeccion" in cfg:
            yield ruta.stem, cfg


def test_rama_real_semillas_distintas_y_fuera_del_banco(rangos):
    todas = set().union(*rangos.values())
    vistas = {}
    streams = list(_streams_reales())
    assert streams, "no hay ningún stream real con bloque de monitorización"
    for nombre, cfg in streams:
        semillas = [cfg["monitorizacion"]["semilla_calibracion"],
                    cfg["monitorizacion"]["semilla_verificacion"], cfg["inyeccion"]["semilla"]]
        assert len(set(semillas)) == 3, f"{nombre}: calibración, verificación e inyección comparten semilla"
        assert not set(semillas) & todas, f"{nombre}: una semilla cae dentro del banco sintético"
        for s in semillas:
            assert s not in vistas, f"{nombre} reutiliza la semilla {s} de {vistas.get(s)}"
            vistas[s] = nombre


def test_calibrar_con_la_misma_semilla_que_verificar_falla():
    from signal_watch.evaluation.error_analysis import calibrar_en_ruido_real
    with pytest.raises(ValueError):
        calibrar_en_ruido_real([], arl0_objetivo=120, k_cusum=0.5, delta_page_hinkley=0.25,
                               bootstrap_bloque=6, bootstrap_longitud=600, bootstrap_n_series=10,
                               semilla_calibracion=1, semilla_verificacion=1)
