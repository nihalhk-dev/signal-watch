"""R5 — no se evalúa con una config sin congelar.

Lo que se prueba es el MECANISMO (config.load_frozen / verify_frozen), que
existe y funciona. Lo que NO se afirma: que el pipeline de evaluación lo
use. Ese es un límite declarado (MEMORIA §3): delay_curves.py barre muchos
umbrales a propósito y no despliega uno solo, y la congelación queda para
cuando un umbral se despliegue de verdad.
"""

import pytest
import yaml

from signal_watch import config
from signal_watch.config import load_frozen, verify_frozen
from signal_watch.exceptions import ConfigNotFrozenError


def test_sin_config_congelada_no_se_evalua():
    with pytest.raises(ConfigNotFrozenError):
        load_frozen("v9.9.9-no-existe")


@pytest.fixture
def congelada(tmp_path, monkeypatch):
    ruta = tmp_path / "v1.0.0.yaml"
    ruta.write_text(yaml.safe_dump({"k": 0.5, "h": 3.586, "arl0": 120}), encoding="utf-8")
    monkeypatch.setattr(config, "get_frozen_path", lambda version: tmp_path / f"{version}.yaml")
    return "v1.0.0"


def test_la_misma_config_verifica_aunque_cambie_el_orden(congelada):
    assert verify_frozen({"arl0": 120, "h": 3.586, "k": 0.5}, congelada)


def test_un_cambio_real_de_valor_no_verifica(congelada):
    assert not verify_frozen({"k": 0.7, "h": 3.586, "arl0": 120}, congelada)
