"""De los datos crudos de French al stream gold, sobre un zip fabricado con
la MISMA forma que el real (cabecera de cortesía, línea en blanco, fila de
columnas, códigos de faltante, copyright al final).

Protege las tres trampas del fichero (MEMORIA §7): no es un CSV limpio, los
valores vienen en PORCENTAJE (el mismo tipo de error que el ×100 del PSI), y
los faltantes se marcan con -99.99 / -999.
"""

import zipfile

import numpy as np
import pandas as pd
import pytest

from signal_watch.gold.factor_metrics import metrica_a_observaciones
from signal_watch.gold.metric_stream import load_metric_stream, save_metric_stream
from signal_watch.gold.schemas import Direction
from signal_watch.ingest.french import parsear_factores_diarios
from signal_watch.processing.factor_returns import sharpe_mensual


@pytest.fixture(scope="module")
def zip_french(tmp_path_factory):
    fechas = pd.bdate_range("1926-07-01", "2024-12-31")
    rng = np.random.default_rng(3)
    lineas = ["This file was created by CMPT_ME_BEYME_RETS using the 202412 CRSP database.",
              "The 1-month TBill return is from Ibbotson and Associates, Inc.", "",
              ",Mkt-RF,SMB,HML,RF"]
    for i, f in enumerate(fechas):
        if i == 10:
            fila = "-99.99,-99.99,-99.99,-99.99"
        elif i == 11:
            fila = "-999,-999,-999,-999"
        elif i == 12:
            fila = "0.53,0.10,-0.25,0.013"     # valores conocidos, en PORCENTAJE
        else:
            fila = ",".join(f"{v:.2f}" for v in rng.normal(0.03, 1.0, 3)) + ",0.013"
        lineas.append(f"{f:%Y%m%d},{fila}")
    lineas += ["", "Copyright 2025 Kenneth R. French"]
    ruta = tmp_path_factory.mktemp("french") / "F-F_Research_Data_Factors_daily_CSV.zip"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("F-F_Research_Data_Factors_daily.CSV", "\n".join(lineas))
    return ruta, fechas


def test_el_parser_ignora_cabecera_y_copyright(zip_french):
    ruta, fechas = zip_french
    df = parsear_factores_diarios(ruta)
    assert list(df.columns) == ["mkt_rf", "smb", "hml", "rf"]
    assert len(df) == len(fechas) and df.index.is_monotonic_increasing


def test_porcentaje_a_decimal_una_sola_vez(zip_french):
    ruta, fechas = zip_french
    fila = parsear_factores_diarios(ruta).loc[fechas[12]]
    assert fila.tolist() == pytest.approx([0.0053, 0.0010, -0.0025, 0.00013])


def test_codigos_de_faltante_son_nan(zip_french):
    ruta, fechas = zip_french
    df = parsear_factores_diarios(ruta)
    assert df.loc[fechas[10]].isna().all() and df.loc[fechas[11]].isna().all()
    assert df.drop(index=fechas[[10, 11]]).notna().all().all()


def test_de_crudo_a_gold_ida_y_vuelta(zip_french, tmp_path):
    ruta, _ = zip_french
    metrica = sharpe_mensual(parsear_factores_diarios(ruta).loc["1963-07-01":], factor="hml")
    assert (metrica["n_obs"] >= 15).all() and (metrica["sharpe_se"] > 0).all()
    obs = metrica_a_observaciones(metrica, "factor_hml_sharpe", Direction.LOWER_IS_WORSE)
    assert [o.t for o in obs] == list(range(len(obs)))
    save_metric_stream(obs, tmp_path / "gold.parquet")
    assert load_metric_stream(tmp_path / "gold.parquet") == obs


def test_no_se_resta_rf_a_un_factor_no_declarado(zip_french):
    ruta, _ = zip_french
    with pytest.raises(ValueError):
        sharpe_mensual(parsear_factores_diarios(ruta), factor="rf")
