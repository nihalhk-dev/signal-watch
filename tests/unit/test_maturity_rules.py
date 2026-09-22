"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

processing/maturity_rules.py es de la rama de crédito, fuera de alcance. La regla de madurez está decidida con datos (MEMORIA §4), no implementada.
"""

import pytest

pytest.skip(
    "Fuera de alcance: processing/maturity_rules.py es de la rama de crédito, fuera de alcance. La regla de madurez está decidida con datos (MEMORIA §4), no implementada.",
    allow_module_level=True,
)
