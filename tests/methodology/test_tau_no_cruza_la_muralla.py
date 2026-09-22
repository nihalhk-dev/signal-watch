"""R2 — el instante de cambio real (τ) nunca llega a un detector.

Tres capas de la muralla, cada una con su test:
  1. Por TIPO: MetricObservation no tiene campo `tau`, y si alguien se lo
     pasa al construirla, no se queda dentro.
  2. En DISCO: un Parquet de observaciones con columna `tau` no se carga.
  3. En la PUERTA: to_detector_view() rechaza cualquier objeto con `tau`,
     y el motor de monitorización pasa siempre por esa puerta.
"""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from signal_watch.exceptions import TauLeakageError
from signal_watch.gold import metric_stream
from signal_watch.gold.metric_stream import (
    GroundTruth,
    load_metric_stream,
    observations_to_dataframe,
    save_ground_truth,
    save_metric_stream,
    to_detector_view,
)
from signal_watch.gold.schemas import MetricObservation


def test_el_contrato_no_tiene_campo_tau():
    assert "tau" not in MetricObservation.model_fields


def test_un_tau_colado_al_construir_no_se_queda_dentro(hacer_serie):
    datos = hacer_serie([0.7])[0].model_dump()
    obs = MetricObservation(**datos, tau=40)
    assert not hasattr(obs, "tau")


def test_un_parquet_con_columna_tau_no_se_carga(tmp_path, hacer_serie):
    df = observations_to_dataframe(hacer_serie([0.7, 0.69, 0.71])).assign(tau=1)
    ruta = tmp_path / "con_tau.parquet"
    df.to_parquet(ruta, index=False)
    with pytest.raises(TauLeakageError):
        load_metric_stream(ruta)


def test_observaciones_y_verdad_viven_en_archivos_separados(tmp_path, hacer_serie):
    obs = hacer_serie([0.7, 0.6])
    save_metric_stream(obs, tmp_path / "obs.parquet")
    save_ground_truth([GroundTruth(stream_id="test", tau=1, escenario="salto")], tmp_path / "gt.parquet")
    columnas = set(pd.read_parquet(tmp_path / "obs.parquet").columns)
    assert "tau" not in columnas
    assert load_metric_stream(tmp_path / "obs.parquet") == obs


def test_la_puerta_rechaza_cualquier_objeto_con_tau(hacer_serie):
    colado = SimpleNamespace(**hacer_serie([0.7])[0].model_dump(), tau=5)
    with pytest.raises(TauLeakageError):
        to_detector_view(hacer_serie([0.7, 0.7]) + [colado])


def test_la_puerta_deja_pasar_observaciones_limpias_sin_tocarlas(hacer_serie):
    obs = hacer_serie([0.7, 0.6, 0.5])
    assert to_detector_view(obs) == obs


def test_el_motor_pasa_siempre_por_la_puerta(monkeypatch, hacer_serie):
    from signal_watch.detectors.cusum import CUSUM
    from signal_watch.monitoring import engine

    llamadas = []

    def espia(obs):
        llamadas.append(len(obs))
        return metric_stream.to_detector_view(obs)

    monkeypatch.setattr(engine, "to_detector_view", espia)
    huella = {"config_hash": "x", "commit": "y", "hash_datos": "z"}
    engine.run_batch(hacer_serie([0.7] * 10), CUSUM(0.7, 0.05, 0.5, 4.0), "CUSUM", 4.0, huella)
    assert llamadas == [10]
