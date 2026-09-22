"""El contrato en disco: ida y vuelta sin pérdida, y fallos altos y claros."""

import pandas as pd
import pytest

from signal_watch.exceptions import SchemaViolationError
from signal_watch.gold.metric_stream import (
    GroundTruth,
    load_ground_truth,
    load_metric_stream,
    observations_to_dataframe,
    save_ground_truth,
    save_metric_stream,
)
from signal_watch.gold.schemas import Direction


def test_ida_y_vuelta_sin_perdida(tmp_path, hacer_serie):
    obs = hacer_serie([0.71, 0.70, 0.69], direction=Direction.HIGHER_IS_WORSE)
    save_metric_stream(obs, tmp_path / "s.parquet")
    assert load_metric_stream(tmp_path / "s.parquet") == obs


def test_falta_una_columna(tmp_path, hacer_serie):
    df = observations_to_dataframe(hacer_serie([0.7])).drop(columns=["value_se"])
    df.to_parquet(tmp_path / "roto.parquet", index=False)
    with pytest.raises(SchemaViolationError):
        load_metric_stream(tmp_path / "roto.parquet")


def test_no_se_guarda_una_lista_vacia(tmp_path):
    with pytest.raises(SchemaViolationError):
        save_metric_stream([], tmp_path / "vacio.parquet")


def test_archivo_inexistente(tmp_path):
    with pytest.raises(SchemaViolationError):
        load_metric_stream(tmp_path / "no_existe.parquet")


def test_tau_none_sobrevive_al_parquet(tmp_path):
    """El bug de §8.5a: mezclar tau=None con tau entero hace que pandas suba la
    columna a float y convierta None en NaN; al recargar, Pydantic lo rechazaba."""
    verdad = [GroundTruth(stream_id="a", tau=None, escenario="sin_cambio"),
              GroundTruth(stream_id="b", tau=40, escenario="salto")]
    save_ground_truth(verdad, tmp_path / "gt.parquet")
    assert pd.read_parquet(tmp_path / "gt.parquet")["tau"].dtype.kind == "f"  # la trampa existe
    assert load_ground_truth(tmp_path / "gt.parquet") == verdad                 # y se sortea
