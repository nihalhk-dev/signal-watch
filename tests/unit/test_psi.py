"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

scorecard/psi.py es de la rama de crédito, fuera de alcance. El PSI sintético del banco se prueba en test_synthetic_metrics.py.
"""

import pytest

pytest.skip(
    "Fuera de alcance: scorecard/psi.py es de la rama de crédito, fuera de alcance. El PSI sintético del banco se prueba en test_synthetic_metrics.py.",
    allow_module_level=True,
)
