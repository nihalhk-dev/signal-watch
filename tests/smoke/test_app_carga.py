"""La app arranca y cada página se pinta sin excepciones.

Usa el banco de pruebas oficial de Streamlit (streamlit.testing.v1.AppTest),
que ejecuta el script como lo haría `streamlit run`, sin navegador. Necesita
las tablas selladas de outputs/tables/: si no están (un clon recién hecho
sin ejecutar el pipeline), el test se salta en vez de fallar.
"""

import sys

import pytest

from signal_watch.paths import PATHS

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = PATHS.root / "app"
PAGINAS = ["Home.py", "pages/1_Salud_de_modelos.py", "pages/3_Factores_de_mercado.py",
           "pages/4_Banco_de_pruebas.py"]


@pytest.fixture(autouse=True)
def _requisitos(monkeypatch):
    if not (PATHS.outputs_tables / "alarmas_factor_hml_sharpe.csv").exists():
        pytest.skip("Faltan las tablas selladas: ejecuta el pipeline antes (run_monitoring.py).")
    # Streamlit pone en sys.path la carpeta del script principal (app/); al
    # probar una página suelta hay que hacerlo a mano para `from components import …`.
    monkeypatch.setattr(sys, "path", [str(APP), *sys.path])


@pytest.mark.parametrize("pagina", PAGINAS)
def test_la_pagina_carga_sin_excepciones(pagina):
    at = AppTest.from_file(str(APP / pagina), default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
