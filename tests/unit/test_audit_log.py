"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

monitoring/audit_log.py está en el roadmap. La trazabilidad de cada alarma (huella R7) se prueba en test_monitoring_engine.py.
"""

import pytest

pytest.skip(
    "Fuera de alcance: monitoring/audit_log.py está en el roadmap. La trazabilidad de cada alarma (huella R7) se prueba en test_monitoring_engine.py.",
    allow_module_level=True,
)
