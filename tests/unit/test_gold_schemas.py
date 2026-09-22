"""El contrato MetricObservation: rechaza lo imposible en el momento de crearlo."""

from datetime import date

import pydantic
import pytest

from signal_watch.gold.schemas import Direction, MetricObservation

VALIDO = dict(stream_id="s", t=0, timestamp=date(2020, 1, 31), value=0.7, value_se=0.01,
              n_obs=500, direction=Direction.LOWER_IS_WORSE)


def test_una_observacion_valida_se_acepta():
    obs = MetricObservation(**VALIDO)
    assert obs.value == 0.7 and obs.direction is Direction.LOWER_IS_WORSE


@pytest.mark.parametrize("campo, valor", [
    ("t", -1), ("value_se", -0.001), ("n_obs", 0), ("stream_id", ""),
])
def test_valores_imposibles_se_rechazan(campo, valor):
    with pytest.raises(pydantic.ValidationError):
        MetricObservation(**{**VALIDO, campo: valor})


def test_es_inmutable():
    obs = MetricObservation(**VALIDO)
    with pytest.raises(pydantic.ValidationError):
        obs.value = 0.1


def test_dos_observaciones_iguales_son_iguales():
    assert MetricObservation(**VALIDO) == MetricObservation(**VALIDO)


def test_direction_solo_admite_los_dos_valores():
    assert {d.value for d in Direction} == {"lower_is_worse", "higher_is_worse"}
    with pytest.raises(pydantic.ValidationError):
        MetricObservation(**{**VALIDO, "direction": "da_igual"})
