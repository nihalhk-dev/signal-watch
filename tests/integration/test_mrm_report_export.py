"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

reporting/mrm_report.py está en el roadmap (informe MRM). La tabla de alarmas con su huella sí existe y se prueba en test_monitoring_engine.py.
"""

import pytest

pytest.skip(
    "Fuera de alcance: reporting/mrm_report.py está en el roadmap (informe MRM). La tabla de alarmas con su huella sí existe y se prueba en test_monitoring_engine.py.",
    allow_module_level=True,
)
