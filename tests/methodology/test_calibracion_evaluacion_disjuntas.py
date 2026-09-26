"""R4 — los datos que ajustan un detector no son los que lo evalúan.

Banco sintético: cuatro rangos de semillas (AUC y PSI × calibración y
evaluación), disjuntos dos a dos. Rama real: en cada stream, calibración,
verificación e inyección usan semillas distintas, y ninguna cae dentro de
los rangos del banco sintético. Y en HML, el retardo se mide con
calibración e inyección en meses distintos de la referencia.
"""

import importlib.util
from itertools import combinations

import numpy as np
import pytest
import yaml

from signal_watch.evaluation.error_analysis import (
    bloques_candidatos,
    indices_bootstrap,
    indices_de,
    particion_intercalada,
)
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


# ── Retardo fuera de muestra: calibración e inyección en meses disjuntos ──
#
# Las semillas distintas no bastan: dos semillas que remuestrean los mismos
# 330 meses siguen viendo el mismo ruido. Estos tests comprueban la
# separación por DATOS, a nivel de índice (qué meses de la referencia entran
# en cada serie fabricada).

N_REF, TRAMO, BLOQUE = 330, 12, 6  # los de factor_hml_sharpe


def test_particion_disjunta_y_sin_huecos():
    a, b = particion_intercalada(N_REF, TRAMO, BLOQUE)
    ia, ib = set(indices_de(a)), set(indices_de(b))
    assert not ia & ib, "un mes cae en las dos mitades"
    assert ia | ib == set(range(N_REF)), "se ha perdido algún mes de la referencia"


def test_el_bootstrap_de_una_mitad_no_toca_la_otra():
    a, b = particion_intercalada(N_REF, TRAMO, BLOQUE)
    ia = set(indices_de(a))
    for tramos, propios in ((a, ia), (b, set(indices_de(b)))):
        usados = set(np.concatenate(indices_bootstrap(N_REF, 200, 600, BLOQUE, 7, tramos)))
        assert usados <= propios, "el bootstrap ha sacado meses de la otra mitad"


def test_cobertura_uniforme_dentro_de_la_mitad():
    """Cada mes aparece en exactamente BLOQUE bloques candidatos. Sin esto,
    los meses del borde de cada tramo pesarían menos que los del centro y el
    ruido fabricado no sería el de la mitad."""
    a, _ = particion_intercalada(N_REF, TRAMO, BLOQUE)
    cuenta = np.bincount(bloques_candidatos(a, BLOQUE).ravel(), minlength=N_REF)
    assert set(cuenta[indices_de(a)]) == {BLOQUE}


def test_sin_tramos_el_bootstrap_de_produccion_no_cambia():
    """La calibración de producción (330 meses) debe salir idéntica a antes
    de añadir la partición: mismo algoritmo, mismas llamadas al generador."""
    rng = np.random.default_rng(9000000)
    antes = [
        np.concatenate([np.arange(s, s + BLOQUE)
                        for s in rng.integers(0, N_REF - BLOQUE + 1, size=100)])[:600]
        for _ in range(5)
    ]
    ahora = indices_bootstrap(N_REF, 5, 600, BLOQUE, 9000000)
    assert all(np.array_equal(x, y) for x, y in zip(antes, ahora))


def test_hml_mide_el_retardo_fuera_de_muestra():
    cfg = yaml.safe_load((PATHS.configs / "streams" / "factor_hml_sharpe.yaml")
                         .read_text(encoding="utf-8"))
    tramo = cfg["inyeccion"].get("particion_tramo_meses")
    assert tramo is not None, "HML ha vuelto a medir el retardo dentro de muestra"
    assert tramo >= cfg["monitorizacion"]["bootstrap_bloque_meses"]


def test_calibrar_con_la_misma_semilla_que_verificar_falla():
    from signal_watch.evaluation.error_analysis import calibrar_en_ruido_real
    with pytest.raises(ValueError):
        calibrar_en_ruido_real([], arl0_objetivo=120, k_cusum=0.5, delta_page_hinkley=0.25,
                               bootstrap_bloque=6, bootstrap_longitud=600, bootstrap_n_series=10,
                               semilla_calibracion=1, semilla_verificacion=1)
