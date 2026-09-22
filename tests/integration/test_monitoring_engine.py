"""El motor de monitorización: reinicia tras cada alarma y sella cada una."""

from signal_watch.detectors.cusum import CUSUM
from signal_watch.monitoring.engine import run_batch

HUELLA = {"config_hash": "abc123", "commit": "f00ba12", "hash_datos": "d4t05"}


def test_reinicia_tras_cada_alarma(hacer_serie):
    # dos caídas separadas por un tramo normal: dos alarmas, numeradas
    valores = [0.7] * 20 + [0.55] * 5 + [0.7] * 20 + [0.55] * 5
    eventos = run_batch(hacer_serie(valores), CUSUM(0.7, 0.05, 0.5, 4.0), "CUSUM", 4.0, HUELLA)
    assert [e.n_alarma for e in eventos] == list(range(1, len(eventos) + 1))
    assert len(eventos) >= 2
    assert eventos[0].t < 25 <= 45 <= eventos[-1].t


def test_regimen_malo_persistente_da_alarmas_repetidas(hacer_serie):
    eventos = run_batch(hacer_serie([0.55] * 30), CUSUM(0.7, 0.05, 0.5, 4.0), "CUSUM", 4.0, HUELLA)
    # 3σ por paso, k = 0,5: cada 2 pasos la evidencia vuelve a cruzar h = 4
    assert [e.t for e in eventos][:3] == [1, 3, 5]


def test_cada_alarma_lleva_la_huella_y_la_observacion_que_la_disparo(hacer_serie):
    serie = hacer_serie([0.7] * 10 + [0.5] * 3, stream_id="factor_x")
    e = run_batch(serie, CUSUM(0.7, 0.05, 0.5, 4.0), "CUSUM", 4.0, HUELLA)[0]
    assert (e.config_hash, e.commit, e.hash_datos) == ("abc123", "f00ba12", "d4t05")
    assert e.stream_id == "factor_x" and e.detector == "CUSUM" and e.umbral == 4.0
    assert e.valor == serie[e.t].value and e.fecha == serie[e.t].timestamp


def test_sin_cambio_no_hay_alarmas(hacer_serie):
    assert run_batch(hacer_serie([0.7] * 200), CUSUM(0.7, 0.05, 0.5, 4.0), "CUSUM", 4.0, HUELLA) == []


def test_serie_vacia():
    assert run_batch([], CUSUM(0.7, 0.05, 0.5, 4.0), "CUSUM", 4.0, HUELLA) == []
