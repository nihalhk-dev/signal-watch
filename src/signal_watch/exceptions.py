"""Jerarquía de excepciones de Signal Watch.

Módulo hoja: NO importa nada del propio paquete (ni pandas, ni pydantic).
Todo el resto de signal_watch puede importar de aquí sin riesgo de ciclos.

Por qué una jerarquía propia y no ValueError sueltos:
  · quien USA el paquete puede capturar `SignalWatchError` y saber que el
    fallo es "culpa nuestra" (un contrato violado, una config mala), no un
    bug de numpy ni un fichero que no existe.
  · cada capa tiene su excepción → el traceback dice DÓNDE falló el pipeline
    (ingesta, contrato, detector) sin leer el mensaje.
  · los tests hacen `pytest.raises(SchemaViolationError)` — específico y
    legible — en vez de `pytest.raises(ValueError)`, que atraparía cualquier
    cosa, incluido un error que NO era el que queríamos probar.
"""

from __future__ import annotations


class SignalWatchError(Exception):
    """Raíz de todos los errores del proyecto. Captura esto para atrapar
    cualquier fallo previsto por Signal Watch (y solo esos)."""


# ── Configuración y entorno ──────────────────────────────────────────
class ConfigError(SignalWatchError):
    """Una configuración es inválida, incoherente o falta."""


class ConfigNotFrozenError(ConfigError):
    """Se intenta evaluar con una config que no está en configs/detectors/frozen/.
    Salvaguarda de R5: no se producen resultados con parámetros sin congelar."""


# ── Contrato metric_stream (la muralla de τ) ─────────────────────────
class ContractError(SignalWatchError):
    """Raíz de las violaciones del contrato metric_stream."""


class SchemaViolationError(ContractError):
    """Un metric_stream no cumple el esquema: falta una columna, un tipo no
    encaja, un valor está fuera de rango, o el orden temporal está roto."""


class TauLeakageError(ContractError):
    """Salvaguarda de R2: el instante de cambio real (τ) intentó cruzar hacia
    la vista que ve el detector. Un detector JAMÁS puede ver τ. Si esto salta,
    hay una fuga de verdad-terreno y todo resultado posterior es inválido."""


# ── Datos e ingesta ──────────────────────────────────────────────────
class DataError(SignalWatchError):
    """Raíz de los problemas con datos de entrada."""


class ChecksumMismatchError(DataError):
    """El sha256 de un fichero descargado no coincide con configs/sources/checksums.yaml.
    O la fuente cambió, o la descarga se corrompió: en ambos casos, para."""


class InsufficientDataError(DataError):
    """No hay observaciones suficientes para una operación (p. ej. una cosecha
    con n < n_min, o una ventana móvil más corta que su tamaño)."""


# ── Detectores y evaluación ──────────────────────────────────────────
class DetectorError(SignalWatchError):
    """Raíz de los fallos de detectores."""


class CalibrationError(DetectorError):
    """La calibración no converge al ARL₀ objetivo (p. ej. la bisección sobre h
    no encuentra solución en el rango dado)."""


class NotCalibratedError(DetectorError):
    """Se llama a un detector que necesita calibración previa sin haberla hecho."""
