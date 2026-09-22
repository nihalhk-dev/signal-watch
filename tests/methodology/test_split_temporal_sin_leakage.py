"""La señal de ML no puede mirar el futuro — y si lo mirara, se notaría.

Es R2 (la muralla de τ) llevada al modelo de ML. Cinco comprobaciones:

  1. El objetivo de la fila t es el mes t+1, y solo él.
  2. Las características de t no cambian si se altera el futuro.
  3. Cada predicción se hace con un modelo entrenado solo con el pasado.
  4. PLACEBO: sobre ruido puro, el acierto no supera al de la moneda
     sesgada (la fracción de meses que sube). Un modelo sin fuga no puede
     ganar sobre ruido.
  5. FUGA PLANTADA: si se le da al modelo una característica del futuro, el
     acierto se dispara. Demuestra que el montaje SÍ notaría una fuga: una
     prueba que no puede fallar no prueba nada.

Todo sobre datos sintéticos con semilla fija: no depende de French ni de disco.
"""

import numpy as np
import pandas as pd
import pytest

from signal_watch.gold.signal_momentum import (
    predecir_hacia_delante,
    retornos_estrategia,
    tabla_mensual,
)

CARACTERISTICAS = ["hml_1m", "hml_3m", "hml_12m", "hml_vol_3m", "mkt_12m", "mkt_vol_3m"]
PARAMS = dict(C=1.0, meses_min_entrenamiento=120, mes_reentreno=12, umbral_probabilidad=0.5)


def _diario_ruido(semilla: int = 7, inicio: str = "1960-01-01", fin: str = "2004-12-31") -> pd.DataFrame:
    """Retornos diarios independientes: aquí no hay nada que predecir."""
    rng = np.random.default_rng(semilla)
    fechas = pd.bdate_range(inicio, fin)
    return pd.DataFrame({"hml": rng.normal(0.0001, 0.006, len(fechas)),
                         "mkt_rf": rng.normal(0.0003, 0.01, len(fechas))}, index=fechas)


@pytest.fixture(scope="module")
def diario():
    return _diario_ruido()


@pytest.fixture(scope="module")
def tabla(diario):
    return tabla_mensual(diario)


def test_objetivo_es_el_mes_siguiente(diario, tabla):
    mensual = (1 + diario["hml"]).groupby(pd.Grouper(freq="ME")).prod() - 1
    esperado = (mensual.shift(-1) > 0).astype(float)
    comun = tabla["objetivo"].dropna().index
    assert (tabla.loc[comun, "objetivo"] == esperado.loc[comun]).all()
    assert np.isnan(tabla["objetivo"].iloc[-1]), "el último mes no puede tener objetivo"


def test_caracteristicas_no_cambian_si_se_altera_el_futuro(diario, tabla):
    corte = pd.Timestamp("1985-06-30")
    alterado = diario.copy()
    alterado.loc[alterado.index > corte, ["hml", "mkt_rf"]] *= -5.0
    t2 = tabla_mensual(alterado)
    antes = tabla.index <= corte
    pd.testing.assert_frame_equal(tabla.loc[antes, CARACTERISTICAS], t2.loc[antes, CARACTERISTICAS])


@pytest.fixture(scope="module")
def pred(tabla):
    return predecir_hacia_delante(tabla, CARACTERISTICAS, **PARAMS)


def test_cada_prediccion_se_entrena_solo_con_el_pasado(pred):
    assert (pred["fin_entrenamiento"] < pred["fecha_prediccion"]).all()
    assert (pred.index > pred["fecha_prediccion"]).all(), "el mes objetivo es posterior al de la predicción"
    assert pred["n_entrenamiento"].iloc[0] >= PARAMS["meses_min_entrenamiento"]


def test_placebo_sobre_ruido_no_gana_a_la_moneda(pred):
    evaluable = pred.dropna(subset=["objetivo"])
    base = max(evaluable["objetivo"].mean(), 1 - evaluable["objetivo"].mean())
    se = np.sqrt(0.25 / len(evaluable))
    assert evaluable["acierto"].mean() < base + 3 * se, (
        f"acierto {evaluable['acierto'].mean():.3f} frente a {base:.3f}: sobre ruido no debería ganar")


def test_fuga_plantada_se_nota(tabla):
    """Si el modelo viera el futuro, acertaría casi siempre."""
    trampa = tabla.assign(trampa=tabla["retorno_hml_siguiente"])
    pred_trampa = predecir_hacia_delante(trampa, CARACTERISTICAS + ["trampa"], **PARAMS)
    acierto = pred_trampa["acierto"].dropna().mean()
    assert acierto > 0.9, f"con el futuro dentro debería acertar casi siempre (acierto {acierto:.3f})"


def test_la_posicion_se_aplica_al_mes_objetivo_y_paga_la_rotacion():
    fechas = pd.bdate_range("2000-01-03", "2000-03-31")
    diario = pd.DataFrame({"hml": 0.001, "mkt_rf": 0.0}, index=fechas)
    pos = pd.Series([1, -1, -1], index=pd.to_datetime(["2000-01-31", "2000-02-29", "2000-03-31"]))
    r = retornos_estrategia(diario, pos, coste_pb=10)
    enero, febrero = r["2000-01"], r["2000-02"]
    assert enero.iloc[0] == pytest.approx(0.001 - 1 * 10 / 1e4)   # entrar: rotación 1
    assert enero.iloc[1:].to_numpy() == pytest.approx(0.001)
    assert febrero.iloc[0] == pytest.approx(-0.001 - 2 * 10 / 1e4)  # darle la vuelta: rotación 2
    assert r["2000-03"].to_numpy() == pytest.approx(-0.001)         # sin cambio, sin coste
