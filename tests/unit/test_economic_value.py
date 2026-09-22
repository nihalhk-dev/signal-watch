"""Fuera de alcance — se declara en vez de dejar el archivo vacío.

evaluation/economic_value.py no se construyó por calendario (roadmap). Los costes de la señal de ML se prueban en test_split_temporal_sin_leakage.py.
"""

import pytest

pytest.skip(
    "Fuera de alcance: evaluation/economic_value.py no se construyó por calendario (roadmap). Los costes de la señal de ML se prueban en test_split_temporal_sin_leakage.py.",
    allow_module_level=True,
)
