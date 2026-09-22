"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

BOCPD es stretch, fuera del núcleo del proyecto: no existe detectors/bocpd.py que probar.
"""

import pytest

pytest.skip(
    "Fuera de alcance: BOCPD es stretch, fuera del núcleo del proyecto: no existe detectors/bocpd.py que probar.",
    allow_module_level=True,
)
