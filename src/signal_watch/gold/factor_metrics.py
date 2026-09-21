"""Capa gold de la rama de mercado: del Sharpe mensual al contrato metric_stream.

Qué hace: lee la config del stream (`configs/streams/<stream_id>.yaml`),
construye la métrica con `processing/factor_returns.py` usando EXACTAMENTE
esos parámetros, convierte cada mes en un `MetricObservation` y lo guarda en
`data/gold/real/<stream_id>.parquet`.

A partir de aquí, la serie real es indistinguible —para el detector— de una
serie sintética o de una serie de AUC de un scorecard. Ese es el punto del
contrato.

Lo que este módulo NO produce, a propósito: un `GroundTruth`.
    En datos reales no existe un τ conocido (HML cambia de régimen varias
    veces; ver MEMORIA §9), así que no hay nada que guardar al otro lado de
    la muralla. El ground truth solo aparecerá en el experimento de
    inyección sobre ruido real, donde τ lo fija quien inyecta. Es la
    diferencia entre "ilustro" y "mido" llevada al código: si no hay
    GroundTruth, ningún módulo de evaluation/ puede calcular un retardo
    sobre esta serie, ni por error.

Uso:
    python -m signal_watch.gold.factor_metrics
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from signal_watch.config import config_hash, load_stream_config, validate_keys
from signal_watch.gold.metric_stream import load_metric_stream, save_metric_stream
from signal_watch.gold.schemas import Direction, MetricObservation
from signal_watch.paths import PATHS
from signal_watch.processing import factor_returns

STREAM_POR_DEFECTO = "factor_hml_sharpe"

CLAVES_OBLIGATORIAS = {
    "stream_id",
    "fuente",
    "factor",
    "metrica",
    "direction",
    "frecuencia",
    "inicio_muestra",
    "fin_calibracion",
    "min_dias_por_mes",
}


# ── Config ───────────────────────────────────────────────────────────

def cargar_config(stream_id: str = STREAM_POR_DEFECTO) -> dict[str, Any]:
    """Carga y valida la config del stream. Falla alto si algo no cuadra."""
    cfg = load_stream_config(stream_id)
    validate_keys(cfg, CLAVES_OBLIGATORIAS, name=f"configs/streams/{stream_id}.yaml")

    if cfg["stream_id"] != stream_id:
        raise ValueError(
            f"El YAML se llama {stream_id}.yaml pero declara "
            f"stream_id={cfg['stream_id']!r}. Tienen que coincidir."
        )

    # Direction(...) lanza si el texto no es un valor válido del enum:
    # mejor aquí, con el nombre del archivo, que en mitad del pipeline.
    Direction(cfg["direction"])

    # min_dias_por_mes vive como constante en factor_returns.py. En vez de
    # tener dos fuentes que pueden divergir en silencio, se exige que
    # coincidan: si alguien cambia una y no la otra, esto salta.
    if int(cfg["min_dias_por_mes"]) != factor_returns.MIN_DIAS_POR_MES:
        raise ValueError(
            f"min_dias_por_mes={cfg['min_dias_por_mes']} en el YAML, pero "
            f"factor_returns.MIN_DIAS_POR_MES={factor_returns.MIN_DIAS_POR_MES}. "
            "Tienen que coincidir: si no, el config_hash describiría un "
            "parámetro que no es el que se usó."
        )

    return cfg


def ruta_stream(stream_id: str = STREAM_POR_DEFECTO) -> Path:
    """`data/gold/real/<stream_id>.parquet`."""
    return PATHS.data_gold_real / f"{stream_id}.parquet"


# ── Conversión al contrato ───────────────────────────────────────────

def metrica_a_observaciones(
    metrica: pd.DataFrame,
    stream_id: str,
    direction: Direction,
) -> list[MetricObservation]:
    """Cada fila mensual → un MetricObservation.

    `t` es el índice ordinal 0, 1, 2... dentro del stream, igual que en el
    banco sintético: el detector razona en pasos, no en fechas. La fecha
    real viaja en `timestamp` para poder dibujar y para el informe.
    """
    observaciones = []
    for t, (fecha, fila) in enumerate(metrica.iterrows()):
        observaciones.append(
            MetricObservation(
                stream_id=stream_id,
                t=t,
                timestamp=fecha.date(),
                value=float(fila["sharpe"]),
                value_se=float(fila["sharpe_se"]),
                n_obs=int(fila["n_obs"]),
                direction=direction,
            )
        )
    return observaciones


def construir_stream(
    stream_id: str = STREAM_POR_DEFECTO,
) -> tuple[list[MetricObservation], dict[str, Any]]:
    """Construye el stream real y devuelve (observaciones, config usada)."""
    cfg = cargar_config(stream_id)
    metrica = factor_returns.construir_metrica_factor(
        factor=cfg["factor"],
        inicio=cfg["inicio_muestra"],
    )
    obs = metrica_a_observaciones(metrica, stream_id, Direction(cfg["direction"]))
    return obs, cfg


# ── Script ───────────────────────────────────────────────────────────

def main(stream_id: str = STREAM_POR_DEFECTO) -> None:
    obs, cfg = construir_stream(stream_id)
    destino = ruta_stream(stream_id)
    save_metric_stream(obs, destino)

    # Ida y vuelta: se relee con el cargador oficial, que revalida CADA
    # fila contra el contrato y comprueba que no se ha colado un 'tau'.
    # Si esto pasa, el archivo es consumible por cualquier detector.
    releidas = load_metric_stream(destino)
    if releidas != obs:
        raise RuntimeError(
            "Lo que se ha releído del Parquet no coincide con lo que se "
            "guardó. Algo se pierde en la conversión (tipos, fechas)."
        )

    # Los parámetros de calibración se calculan desde el stream YA GUARDADO,
    # no desde el DataFrame intermedio: así se comprueba que el contrato
    # conserva todo lo necesario para calibrar.
    serie = pd.DataFrame(
        {"sharpe": [o.value for o in releidas]},
        index=pd.to_datetime([o.timestamp for o in releidas]),
    )
    calib = factor_returns.parametros_calibracion(serie, cfg["fin_calibracion"])

    print("=" * 68)
    print(f"STREAM GOLD — {stream_id}")
    print("=" * 68)
    print(f"Guardado:      {destino}")
    print(f"Observaciones: {len(releidas)}  (t = 0 .. {releidas[-1].t})")
    print(f"Rango:         {releidas[0].timestamp} -> {releidas[-1].timestamp}")
    print(f"Direction:     {releidas[0].direction.value}")
    print(f"config_hash:   {config_hash(cfg)}")
    print("\nIda y vuelta por el cargador oficial: OK (contrato validado fila")
    print("a fila, sin columna 'tau').")

    print("\nPrimera y última observación:")
    for o in (releidas[0], releidas[-1]):
        print(
            f"  t={o.t:>3}  {o.timestamp}  value={o.value:+8.3f}  "
            f"se={o.value_se:.3f}  n_obs={o.n_obs}"
        )

    print("\nParámetros de calibración (recalculados desde el stream guardado):")
    for k, v in calib.items():
        print(f"  {k:22} {v}")
    print(
        "\n  Tienen que ser IDÉNTICOS a los de factor_returns (mu0 0.8598...,\n"
        "  sigma 5.7123...). Si difieren, el contrato está perdiendo precisión."
    )
    print("=" * 68)


if __name__ == "__main__":
    main()