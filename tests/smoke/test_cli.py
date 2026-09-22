"""El comando `signal-watch` responde (pyproject → signal_watch.cli:app)."""

from typer.testing import CliRunner

from signal_watch import __version__
from signal_watch.cli import app


def test_version():
    r = CliRunner().invoke(app, ["version"])
    assert r.exit_code == 0
    assert r.stdout.startswith(f"signal-watch {__version__} (commit: ")


def test_sin_subcomando_muestra_la_ayuda():
    """El bug de F0: con un solo subcomando, Typer colapsaba la estructura y
    `signal-watch version` fallaba. El callback lo evita."""
    r = CliRunner().invoke(app, [])
    assert r.exit_code == 0 and "version" in r.stdout
