"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

Rama de crédito, fuera de alcance: no hay scorecard con variables de concesión que vigilar.
"""

import pytest

pytest.skip(
    "Fuera de alcance: Rama de crédito, fuera de alcance: no hay scorecard con variables de concesión que vigilar.",
    allow_module_level=True,
)
