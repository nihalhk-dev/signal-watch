"""Catálogo de detectores: mapea un nombre (string, el que aparece en
configs/detectors/*.yaml) a la clase que lo implementa.

Por qué existe: sin esto, cada script que quiere "el detector llamado
en tal config.yaml" tendría que tener un if/elif con los 4 nombres
repetido en cada sitio. Con el registro, basta con
`obtener_clase_detector("cusum")` y el resto del código no necesita
saber que existen 4 clases distintas — solo pide por nombre.
"""

from __future__ import annotations

from signal_watch.detectors.base import Detector
from signal_watch.detectors.baseline import TresSigma, UmbralFijo
from signal_watch.detectors.cusum import CUSUM
from signal_watch.detectors.page_hinkley import PageHinkley

REGISTRO_DETECTORES: dict[str, type[Detector]] = {
    "cusum": CUSUM,
    "page_hinkley": PageHinkley,
    "tres_sigma": TresSigma,
    "umbral_fijo": UmbralFijo,
}


def obtener_clase_detector(nombre: str) -> type[Detector]:
    """Devuelve la CLASE del detector registrado bajo `nombre` (no una
    instancia — cada quien la instancia con sus propios parámetros,
    que salen de configs/detectors/{nombre}.yaml).

    Lanza KeyError con un mensaje útil (lista los nombres válidos) si
    el nombre no está registrado — mejor eso que un KeyError críptico
    de diccionario.
    """
    if nombre not in REGISTRO_DETECTORES:
        disponibles = sorted(REGISTRO_DETECTORES.keys())
        raise KeyError(
            f"No hay ningún detector registrado con el nombre '{nombre}'. "
            f"Detectores disponibles: {disponibles}"
        )
    return REGISTRO_DETECTORES[nombre]


def nombres_disponibles() -> list[str]:
    """Lista los nombres de todos los detectores registrados."""
    return sorted(REGISTRO_DETECTORES.keys())