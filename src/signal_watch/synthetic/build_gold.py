"""Construye el banco de pruebas completo: junta generator, scenarios
y metrics para producir cientos/miles de series sintéticas, cada una
con su ground truth, listas para guardar como capa gold.

Esta es la pieza que finalmente responde a la pregunta "genérame el
banco de pruebas" con una sola llamada, combinando:
  · generator.generar_ruido_ar1()      — el ruido con memoria
  · scenarios.aplicar_*()               — el tipo de cambio inyectado
  · metrics.generar_auc_realista() /
    metrics.generar_psi_desde_chi2()   — la semántica real de la métrica
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from signal_watch.gold.metric_stream import GroundTruth
from signal_watch.gold.schemas import Direction, MetricObservation
from signal_watch.synthetic.generator import generar_ruido_ar1
from signal_watch.synthetic.metrics import (
    clip_auc,
    generar_psi_desde_chi2,
    inyectar_cambio_psi,
    se_hanley_mcneil,
)
from signal_watch.synthetic.scenarios import (
    aplicar_cambio_varianza,
    aplicar_deriva,
    aplicar_salto,
    aplicar_sin_cambio,
)


@dataclass(frozen=True)
class EscenarioConfig:
    """Los parámetros de un escenario a generar. Una instancia de esto
    describe COMPLETAMENTE una serie: cuántos puntos, qué tipo de
    cambio, con qué magnitud, sobre qué métrica."""

    nombre: str  # nombre base del stream, p.ej. "sint_scorecard_auc"
    tipo_metrica: str  # "auc" o "psi"
    escenario: str  # "salto", "deriva", "cambio_varianza", "sin_cambio"
    n: int  # número de periodos
    tau: int | None  # instante del cambio (None si escenario="sin_cambio")
    delta_sigma: float  # magnitud del cambio, en unidades de sigma
    rho: float  # memoria del AR(1)
    n_obs_base: int  # tamaño de muestra típico de cada periodo
    seed: int  # semilla — misma semilla, misma serie SIEMPRE


def _generar_stream_auc(cfg: EscenarioConfig) -> tuple[list[MetricObservation], GroundTruth]:
    """Genera una serie sintética que se comporta como un AUC real."""
    rng = np.random.default_rng(cfg.seed)
    sigma = 0.05  # desviación típica razonable para un AUC (en escala 0-1)
    mu_base = 0.71

    ruido = generar_ruido_ar1(cfg.n, cfg.rho, sigma, rng)
    valores = mu_base + ruido

    if cfg.escenario == "salto" and cfg.tau is not None:
        valores = aplicar_salto(valores, cfg.tau, cfg.delta_sigma, sigma)
    elif cfg.escenario == "deriva" and cfg.tau is not None:
        valores = aplicar_deriva(valores, cfg.tau, cfg.delta_sigma, sigma)
    elif cfg.escenario == "cambio_varianza" and cfg.tau is not None:
        rng_var = np.random.default_rng(cfg.seed + 1)
        valores = aplicar_cambio_varianza(valores, cfg.tau, factor_varianza=4.0, rng=rng_var)
    elif cfg.escenario == "sin_cambio":
        valores = aplicar_sin_cambio(valores)
    else:
        raise ValueError(f"Combinación inválida: escenario={cfg.escenario}, tau={cfg.tau}")

    # dar semántica real de AUC: recortar al rango válido y calcular SE
    valores = clip_auc(valores)
    n_obs_serie = rng.integers(
        low=max(1, int(cfg.n_obs_base * 0.7)),
        high=int(cfg.n_obs_base * 1.3) + 1,
        size=cfg.n,
    )
    se_serie = se_hanley_mcneil(valores, n_obs_serie)

    fecha_inicio = date(2015, 1, 1)
    observaciones = [
        MetricObservation(
            stream_id=cfg.nombre,
            t=t,
            timestamp=fecha_inicio + timedelta(days=30 * t),
            value=float(valores[t]),
            value_se=float(se_serie[t]),
            n_obs=int(n_obs_serie[t]),
            direction=Direction.LOWER_IS_WORSE,
        )
        for t in range(cfg.n)
    ]
    ground_truth = GroundTruth(stream_id=cfg.nombre, tau=cfg.tau, escenario=cfg.escenario)
    return observaciones, ground_truth


def _generar_stream_psi(cfg: EscenarioConfig) -> tuple[list[MetricObservation], GroundTruth]:
    """Genera una serie sintética que se comporta como un PSI real
    (distribución nula chi-cuadrado, nunca negativo)."""
    rng = np.random.default_rng(cfg.seed)
    n_bins = 10

    n_obs_serie = rng.integers(
        low=max(1, int(cfg.n_obs_base * 0.7)),
        high=int(cfg.n_obs_base * 1.3) + 1,
        size=cfg.n,
    )
    # PSI bajo H0: usamos el n_obs medio de la serie para la escala
    valores = generar_psi_desde_chi2(
        n=cfg.n, n_bins=n_bins, n_obs=int(np.mean(n_obs_serie)), rng=rng
    )

    if cfg.escenario in ("salto", "deriva") and cfg.tau is not None:
        # para el PSI, "salto" y "deriva" se traducen en un incremento
        # sostenido a partir de tau (el PSI solo puede subir con deriva
        # real de la distribución, nunca "saltar hacia abajo")
        incremento = abs(cfg.delta_sigma) * 0.1
        valores = inyectar_cambio_psi(valores, cfg.tau, incremento)
    elif cfg.escenario == "sin_cambio":
        pass  # ya generado bajo H0, sin tocar
    else:
        raise ValueError(f"Escenario '{cfg.escenario}' no soportado para PSI")

    # el SE del PSI no tiene una fórmula tan estándar como Hanley-McNeil;
    # usamos una aproximación conservadora basada en el propio ruido chi2
    se_serie = np.full(cfg.n, valores.std() if cfg.n > 1 else 0.01)
    se_serie = np.clip(se_serie, 1e-4, None)

    fecha_inicio = date(2015, 1, 1)
    observaciones = [
        MetricObservation(
            stream_id=cfg.nombre,
            t=t,
            timestamp=fecha_inicio + timedelta(days=30 * t),
            value=float(valores[t]),
            value_se=float(se_serie[t]),
            n_obs=int(n_obs_serie[t]),
            direction=Direction.HIGHER_IS_WORSE,
        )
        for t in range(cfg.n)
    ]
    ground_truth = GroundTruth(stream_id=cfg.nombre, tau=cfg.tau, escenario=cfg.escenario)
    return observaciones, ground_truth


def generar_stream(cfg: EscenarioConfig) -> tuple[list[MetricObservation], GroundTruth]:
    """Punto de entrada único: genera una serie según su tipo de métrica.

    Despacha a _generar_stream_auc o _generar_stream_psi según
    cfg.tipo_metrica. Es la función que usarán los scripts de F2
    para construir el banco de pruebas completo.
    """
    if cfg.tipo_metrica == "auc":
        return _generar_stream_auc(cfg)
    elif cfg.tipo_metrica == "psi":
        return _generar_stream_psi(cfg)
    else:
        raise ValueError(f"tipo_metrica debe ser 'auc' o 'psi', recibido: {cfg.tipo_metrica}")


def generar_banco_completo(
    configs: list[EscenarioConfig],
) -> tuple[list[list[MetricObservation]], list[GroundTruth]]:
    """Genera todas las series de una lista de configuraciones.

    Devuelve dos listas paralelas: las observaciones de cada stream, y
    su ground truth correspondiente. El script de F2 (build_synthetic.py)
    las guardará en data/gold/synthetic/, con las observaciones y los
    ground truths en archivos SEPARADOS (la muralla, aplicada a escala).
    """
    todas_observaciones = []
    todos_ground_truths = []
    for cfg in configs:
        obs, gt = generar_stream(cfg)
        todas_observaciones.append(obs)
        todos_ground_truths.append(gt)
    return todas_observaciones, todos_ground_truths