"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

processing/privacy.py es de la rama de crédito, fuera de alcance: los datos de mercado no contienen datos personales.
"""

import pytest

pytest.skip(
    "Fuera de alcance: processing/privacy.py es de la rama de crédito, fuera de alcance: los datos de mercado no contienen datos personales.",
    allow_module_level=True,
)
