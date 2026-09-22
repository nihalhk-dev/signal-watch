"""Utilidades compartidas por los tests.

`hacer_serie` fabrica una lista de MetricObservation a partir de valores:
es la forma más corta de darle a un detector una serie cuyo comportamiento
correcto se conoce de antemano (un salto en un instante elegido, una
constante, etc.).
"""

from datetime import date, timedelta

import pytest

from signal_watch.gold.schemas import Direction, MetricObservation


def serie(valores, direction=Direction.LOWER_IS_WORSE, stream_id="test", se=0.01, n_obs=100):
    inicio = date(2000, 1, 31)
    return [
        MetricObservation(stream_id=stream_id, t=t, timestamp=inicio + timedelta(days=30 * t),
                          value=float(v), value_se=se, n_obs=n_obs, direction=direction)
        for t, v in enumerate(valores)
    ]


@pytest.fixture
def hacer_serie():
    return serie
