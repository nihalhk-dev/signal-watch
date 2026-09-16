"""Rutas del proyecto, resueltas por MARCADOR, nunca por el directorio actual.

La regla de oro: la raíz del repo es "la carpeta que contiene pyproject.toml",
encontrada subiendo desde este fichero. NO es os.getcwd().

Por qué importa (y por qué un revisor lo mira):
  · si la raíz se resolviera por getcwd(), el código funcionaría lanzado desde
    la raíz y se ROMPERÍA lanzado desde notebooks/ o scripts/ — el clásico
    "en mi máquina funciona".
  · anclando a __file__, da igual desde dónde se ejecute: un notebook, un test,
    el CLI o Streamlit Cloud resuelven SIEMPRE la misma raíz.
  · todas las rutas del proyecto salen de aquí. Ningún otro módulo construye
    rutas a mano con strings: piden PATHS.data_raw, PATHS.configs, etc. Un solo
    sitio que cambiar si la estructura se mueve.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_MARCADOR = "pyproject.toml"


def _encontrar_raiz(desde: Path) -> Path:
    """Sube desde `desde` hasta encontrar la carpeta que contiene pyproject.toml.

    Lanza RuntimeError si llega a la raíz del sistema sin encontrarlo — eso
    significaría que el paquete se está ejecutando fuera del repo, y es mejor
    fallar claro que devolver una ruta silenciosamente equivocada.
    """
    actual = desde.resolve()
    for candidata in (actual, *actual.parents):
        if (candidata / _MARCADOR).is_file():
            return candidata
    raise RuntimeError(
        f"No encuentro '{_MARCADOR}' subiendo desde {desde}. "
        "¿Se está ejecutando signal_watch fuera del repositorio?"
    )


# Raíz calculada UNA vez, al importar. Este fichero vive en src/signal_watch/,
# así que subiendo encuentra el pyproject.toml en la raíz del repo.
ROOT: Path = _encontrar_raiz(Path(__file__))


@dataclass(frozen=True)
class _Paths:
    """Contenedor inmutable de las rutas del proyecto.

    Frozen: nadie puede reasignar PATHS.data_raw = otra_cosa en caliente.
    Las rutas se derivan de ROOT, no se hardcodean.
    """

    root: Path

    # ── capas de datos (raw → processed → gold) ──────────────────────
    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def data_raw(self) -> Path:
        return self.data / "raw"

    @property
    def data_processed(self) -> Path:
        return self.data / "processed"

    @property
    def data_gold(self) -> Path:
        return self.data / "gold"

    @property
    def data_gold_real(self) -> Path:
        return self.data_gold / "real"

    @property
    def data_gold_synthetic(self) -> Path:
        return self.data_gold / "synthetic"

    # ── configuración ────────────────────────────────────────────────
    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def configs_frozen(self) -> Path:
        return self.configs / "detectors" / "frozen"

    # ── salidas (evidencia versionada + artefactos ignorados) ────────
    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def outputs_tables(self) -> Path:
        return self.outputs / "tables"

    @property
    def outputs_figures(self) -> Path:
        return self.outputs / "figures"

    @property
    def outputs_audit(self) -> Path:
        return self.outputs / "audit"

    # ── figuras de la memoria (todas desde reporting/figures.py, R9) ──
    @property
    def memoria_figuras(self) -> Path:
        return self.root / "docs" / "memoria" / "figuras"

    def ensure(self, path: Path) -> Path:
        """Crea el directorio (y sus padres) si no existe, y lo devuelve.
        Para usar justo antes de escribir un artefacto generado."""
        path.mkdir(parents=True, exist_ok=True)
        return path


# La instancia única que importa todo el proyecto:  from signal_watch.paths import PATHS
PATHS = _Paths(root=ROOT)
