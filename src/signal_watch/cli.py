"""Línea de comandos de Signal Watch.

Este módulo hace que al escribir `signal-watch` en la terminal, el
programa responda. Usa Typer, que convierte funciones de Python en
subcomandos de la terminal automáticamente.

Cada fase del proyecto añade su subcomando aquí:
  · F0: version (este archivo)
  · F2: build-synthetic
  · F3: calibrate, freeze-config
  · F4: evaluate
  · F5: download-data, build-processed
  · F7: build-gold, train-scorecard
  · F9: monitor
  · F10: report

Uso:
    signal-watch version          → muestra la versión y el commit
    signal-watch --help           → lista todos los subcomandos disponibles
"""

from __future__ import annotations

import subprocess

import typer

from signal_watch import __version__
from signal_watch.logging_conf import setup_logging

# La app de Typer — el pyproject.toml apunta aquí ([project.scripts])
app = typer.Typer(
    name="signal-watch",
    help="Detección secuencial de degradación de rendimiento en modelos financieros.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Punto de entrada principal. Sin subcomando, muestra la ayuda."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _get_commit() -> str:
    """Intenta obtener el hash corto del commit actual de git.

    Si no estamos en un repo git (o git no está instalado), devuelve
    'sin-git'. No falla: es solo informativo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "sin-git"


@app.command()
def version() -> None:
    """Muestra la versión del paquete y el commit de git."""
    commit = _get_commit()
    typer.echo(f"signal-watch {__version__} (commit: {commit})")


# ── Aquí irán los subcomandos de cada fase ──────────────────────────
# Se añaden conforme se construye cada bloque. Ejemplo (F2):
#
# @app.command()
# def build_synthetic(config: str = "calibracion") -> None:
#     """Genera el banco de pruebas sintético."""
#     ...
