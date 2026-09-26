"""El expediente de monitorización se genera en PDF, sin calcular ni leer nada.

Tres cosas que tienen que ser verdad:
  1. Con las tablas selladas, sale un PDF válido.
  2. Si falta alguna tabla, el expediente se genera igual y lo dice: la
     ausencia de evidencia no puede tumbar la descarga ni rellenarse sola.
  3. R6: la función no toca el disco. Recibe los datos ya leídos; si
     intentara leer una tabla por su cuenta, este test lo pararía.
"""

import pandas as pd
import pytest

from signal_watch.reporting.mrm_report import expediente_pdf

HUELLA = {"config_hash": "abc123", "hash_datos": "def456", "commit": "0000000", "generado_en": "x"}
CONFIG = {"metrica": "sharpe_mensual_anualizado", "direction": "lower_is_worse",
          "frecuencia": "mensual", "fuente": "prueba", "monitorizacion": {"arl0_objetivo_meses": 120}}
RESUMEN = {"referencia": "1963-07-31 → 1990-12-31", "vigilancia": "1991-01-31 → 2026-07-31",
           "meses_vigilados": 427, "esperadas_por_azar": 3.56}


@pytest.fixture
def tablas():
    calib = pd.DataFrame([{"detector": "CUSUM", "umbral": 3.586, "arl0_alcanzable": 120.0,
                           "arl0_verificado": 116.7, "arl0_ic_low": 110.0, "arl0_ic_high": 124.0, **HUELLA}])
    alarmas = pd.DataFrame([{"detector": "CUSUM", "fecha": "2007-07-31", "valor": -15.58,
                             "estadistico": 4.11, "umbral": 3.586, "n_alarma": 1, **HUELLA}])
    retardo = pd.DataFrame([{"detector": "CUSUM", "escenario": "salto", "delta_sigma": d, "arl1_meses": m}
                            for d, m in ((0.25, 37.7), (1.0, 7.2))])
    fuera = pd.DataFrame([{"direccion": dr, "detector": "CUSUM", "arl0_ruido_inyeccion": v}
                          for dr, v in (("A->B", 190.9), ("B->A", 67.3))])
    return calib, alarmas, retardo, fuera


def _es_pdf(b: bytes) -> bool:
    return b.startswith(b"%PDF-") and b.rstrip().endswith(b"%%EOF") and len(b) > 5_000


def test_con_todas_las_tablas_sale_un_pdf(tablas):
    calib, alarmas, retardo, fuera = tablas
    informe = {"pasan": 126, "fallan": 0, "fuera_de_alcance": 10, "commit": "0000000", "fecha": "hoy"}
    assert _es_pdf(expediente_pdf("s", CONFIG, RESUMEN, calib, alarmas, retardo, fuera, informe))


def test_sin_tablas_se_genera_igual():
    assert _es_pdf(expediente_pdf("s", CONFIG, RESUMEN, None, None))
    assert _es_pdf(expediente_pdf("s", {}, {}, None, None))


def test_sin_alarmas_se_genera_igual(tablas):
    calib, alarmas, _, _ = tablas
    assert _es_pdf(expediente_pdf("s", CONFIG, RESUMEN, calib, alarmas.iloc[0:0]))


def test_no_lee_nada_del_disco(tablas, monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("expediente_pdf ha intentado leer una tabla por su cuenta (R6)")
    monkeypatch.setattr(pd, "read_csv", prohibido)
    monkeypatch.setattr(pd, "read_parquet", prohibido)
    calib, alarmas, retardo, fuera = tablas
    assert _es_pdf(expediente_pdf("s", CONFIG, RESUMEN, calib, alarmas, retardo, fuera))
