"""El test de Page-Hinkley — la misma acumulación de evidencia que el
CUSUM, expresada de otra forma.

  · CUSUM: el acumulador se recorta a 0 cada vez que baja de 0, y se
    compara contra un umbral FIJO h.
  · Page-Hinkley: el acumulador NUNCA se recorta. Lo que se vigila es
    la distancia entre el acumulador actual y su PROPIO MÍNIMO
    HISTÓRICO. Si esa distancia supera lambda_, hay alarma.

IDENTIDAD (verificada empíricamente, 500/500 series):
    S_t = max(0, S_{t-1} + u_t)  ==  m_t - min_{j<=t} m_j
Es decir: con delta = k y lambda_ = h, Page-Hinkley y CUSUM producen
EXACTAMENTE las mismas alarmas. No son dos detectores distintos: son
el mismo test bajo un cambio de parametrización (la formulación
original de Page de 1954 es precisamente la distancia al mínimo).
Se mantienen los dos en el proyecto porque con delta != k sí exploran
puntos de operación distintos —el efecto del parámetro de tolerancia—
y porque poder DEMOSTRAR la identidad vale más que asumirla.

Fórmula:
    z[t] = (x[t] - mu0) / sigma                (estandarizado, como CUSUM)
    m[t] = m[t-1] - z[t] - delta               (acumulador, sin recortar)
    M[t] = min(M[t-1], m[t])                   (el minimo historico)
    PH[t] = m[t] - M[t]                        (la distancia que se vigila)
    alarma si PH[t] > lambda_
"""

from __future__ import annotations

from signal_watch.detectors.base import Alarma, Detector
from signal_watch.gold.schemas import Direction, MetricObservation


class PageHinkley(Detector):
    """Detector de Page-Hinkley: vigila la distancia entre el acumulador
    (sin recortar) y su mínimo histórico.
    """

    def __init__(
        self,
        mu0: float,
        sigma: float,
        delta: float,
        lambda_: float,
        direction: Direction = Direction.LOWER_IS_WORSE,
    ) -> None:
        """
        Args:
            mu0: valor esperado cuando todo va bien (igual que en CUSUM).
            sigma: desviación estándar de la métrica bajo mu0. ESTE
                   PARÁMETRO ES IMPRESCINDIBLE: sin él, `delta` y
                   `lambda_` estarían en unidades absolutas de la
                   métrica, y el mismo valor significaría cosas
                   distintas para un AUC (sigma~0.05) que para un PSI
                   (sigma~0.005). Con la estandarización, ambos
                   parámetros están en unidades de sigma y son
                   portables entre métricas — exactamente igual que
                   el h del CUSUM.
            delta: tolerancia de deriva permitida por paso, EN SIGMAS.
                   Es el análogo exacto del `k` del CUSUM: con
                   delta = k los dos detectores son idénticos.
            lambda_: el umbral de alarma, EN SIGMAS (nombre con guion
                     bajo porque `lambda` es palabra reservada).
                     Análogo del `h` del CUSUM, y se calibra igual.
            direction: igual que en CUSUM y baseline.
        """
        if sigma <= 0:
            raise ValueError(f"sigma debe ser positivo, recibido: {sigma}")
        if delta < 0:
            raise ValueError(f"delta no puede ser negativo, recibido: {delta}")
        if lambda_ <= 0:
            raise ValueError(f"lambda_ debe ser positivo, recibido: {lambda_}")

        self.mu0 = mu0
        self.sigma = sigma
        self.delta = delta
        self.lambda_ = lambda_
        self.direction = direction
        super().__init__()

    def reset(self) -> None:
        self.m = 0.0  # acumulador, SIN recorte
        self.m_min = 0.0  # su mínimo histórico

    def update(self, obs: MetricObservation) -> Alarma | None:
        # Estandarizar por sigma y normalizar el signo: "positivo"
        # siempre significa "evidencia de degradación", sea cual sea
        # la direction. Idéntico al criterio del CUSUM.
        z = (obs.value - self.mu0) / self.sigma
        if self.direction == Direction.HIGHER_IS_WORSE:
            z = -z

        # acumulador SIN recorte (a diferencia del CUSUM)
        self.m = self.m - z - self.delta
        # actualizar el minimo historico
        self.m_min = min(self.m_min, self.m)

        # la distancia entre el acumulador y su mejor momento pasado
        ph = self.m - self.m_min

        if ph > self.lambda_:
            return Alarma(t=obs.t, estadistico=ph)
        return None