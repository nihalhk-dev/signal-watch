"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

monitoring/verdict.py no existe: las reglas de veredicto de negocio no se han definido (por eso la app no tiene semáforo).
"""

import pytest

pytest.skip(
    "Fuera de alcance: monitoring/verdict.py no existe: las reglas de veredicto de negocio no se han definido (por eso la app no tiene semáforo).",
    allow_module_level=True,
)
