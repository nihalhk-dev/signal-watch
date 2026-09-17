"""El generador del banco de pruebas: series con ruido AR(1) y un
cambio inyectado en un instante tau que TÚ eliges.

Por qué AR(1) y no ruido puro (independiente):
  Las métricas financieras reales (un AUC mes a mes, un Sharpe móvil)
  no saltan al azar de un punto a otro — se mueven con inercia, cada
  valor se parece al anterior más un poco de ruido nuevo. Un detector
  calibrado sobre ruido puro (sin memoria) estaría calibrado para un
  mundo que no se parece al real, y los resultados no transferirían.

La ecuación del ruido AR(1):
    x[t] = rho * x[t-1] + epsilon[t]
donde epsilon[t] ~ Normal(0, sigma) es ruido nuevo en cada instante,
y rho in [0, 1) controla cuánta "memoria" tiene la serie.

El cambio se inyecta como un desplazamiento de la media a partir de tau:
    valor[t] = mu_base                        si t < tau
    valor[t] = mu_base + delta_sigma * sigma   si t >= tau
(delta_sigma se expresa en unidades de sigma, no en unidades absolutas
 — así "un cambio de 1.5 sigma" significa lo mismo en una serie de AUC
 que en una de Sharpe, que es justo la portabilidad que buscamos con
 value_se en el contrato).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from signal_watch.gold.metric_stream import GroundTruth
from signal_watch.gold.schemas import Direction, MetricObservation


def generar_ruido_ar1(
    n: int,
    rho: float,
    sigma: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Genera n puntos de ruido AR(1) centrado en 0.

    x[0] se inicializa desde la distribución estacionaria del proceso
    (varianza sigma^2 / (1 - rho^2)), para que la serie no "empiece
    fría" — si empezara en 0 siempre, los primeros puntos tendrían
    menos varianza que el resto, sesgando cualquier cosa que mida
    ruido cerca del principio de la serie.
    """
    if not (0 <= rho < 1):
        raise ValueError(f"rho debe estar en [0, 1), recibido: {rho}")
    if sigma < 0:
        raise ValueError(f"sigma no puede ser negativo, recibido: {sigma}")

    x = np.empty(n)
    sigma_estacionaria = sigma / np.sqrt(1 - rho**2)
    x[0] = rng.normal(0, sigma_estacionaria)
    for t in range(1, n):
        x[t] = rho * x[t - 1] + rng.normal(0, sigma)
    return x


def generar_serie(
    stream_id: str,
    n: int,
    mu_base: float,
    sigma: float,
    rho: float,
    tau: int | None,
    delta_sigma: float,
    n_obs_base: int,
    direction: Direction,
    fecha_inicio: date,
    seed: int,
    escenario: str = "salto",
) -> tuple[list[MetricObservation], GroundTruth]:
    """Genera una serie sintética completa: las observaciones (lo que
    ve el detector) Y su ground truth (guardado aparte, nunca junto).

    Args:
        stream_id: nombre del flujo, p.ej. 'sint_scorecard_auc_001'
        n: número de periodos a generar
        mu_base: valor medio de la serie ANTES del cambio
        sigma: desviación estándar del ruido
        rho: memoria del AR(1), en [0, 1)
        tau: instante donde empieza el cambio (None = sin cambio)
        delta_sigma: magnitud del cambio, en unidades de sigma
        n_obs_base: n_obs "típico" para esta serie (con algo de variación)
        direction: lower_is_worse o higher_is_worse
        fecha_inicio: fecha del primer punto (t=0)
        seed: semilla del generador aleatorio — MISMA semilla, MISMA serie
        escenario: nombre del escenario, para el ground truth

    Returns:
        (observaciones, ground_truth) — SIEMPRE juntos como tupla en
        memoria, pero se guardan en archivos SEPARADOS (ver metric_stream.py).
        Que viajen juntos en el retorno de esta función no viola la
        muralla: la muralla protege el momento en que el dato SE GUARDA
        y SE LE PASA AL DETECTOR, no la generación en sí.
    """
    rng = np.random.default_rng(seed)

    ruido = generar_ruido_ar1(n, rho, sigma, rng)
    valores = np.full(n, mu_base) + ruido

    if tau is not None:
        if not (0 <= tau < n):
            raise ValueError(f"tau={tau} debe estar dentro de [0, {n})")
        valores[tau:] += delta_sigma * sigma

    # n_obs varía un poco alrededor de n_obs_base (como en la vida real,
    # no todas las cosechas tienen exactamente el mismo tamaño)
    n_obs_serie = rng.integers(
        low=max(1, int(n_obs_base * 0.7)),
        high=int(n_obs_base * 1.3) + 1,
        size=n,
    )

    # value_se: cuanto mayor n_obs, menor el ruido de la métrica.
    # Aproximación simple pero razonable: se_se ~ sigma / sqrt(n_obs).
    # (La fórmula exacta para AUC, Hanley-McNeil, llega en metrics.py;
    # aquí usamos una aproximación genérica válida para cualquier métrica.)
    value_se_serie = sigma / np.sqrt(n_obs_serie)

    observaciones = [
        MetricObservation(
            stream_id=stream_id,
            t=t,
            timestamp=fecha_inicio + timedelta(days=30 * t),  # aprox. mensual
            value=float(valores[t]),
            value_se=float(value_se_serie[t]),
            n_obs=int(n_obs_serie[t]),
            direction=direction,
        )
        for t in range(n)
    ]

    ground_truth = GroundTruth(stream_id=stream_id, tau=tau, escenario=escenario)

    return observaciones, ground_truth
