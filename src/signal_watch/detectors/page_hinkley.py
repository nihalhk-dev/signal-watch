"""El test de Page-Hinkley — variante secuencial adaptada a deriva de media.

Comparte la misma base conceptual que el CUSUM (acumula evidencia de
desviación respecto a mu0, instante a instante), pero con una diferencia
de mecanismo:

  · CUSUM: el acumulador se recorta a 0 cada vez que baja de 0, y se
    compara contra un umbral FIJO h.
  · Page-Hinkley: el acumulador NUNCA se recorta — crece o decrece
    libremente. Lo que se vigila es la distancia entre el acumulador
    actual y su PROPIO MÍNIMO HISTÓRICO hasta ese momento. Si esa
    distancia supera un umbral lambda, hay alarma.

La intuición: mientras todo va bien, el acumulador (con una pequeña
resta de tolerancia delta en cada paso) tiende a la baja, así que su
mínimo histórico se va actualizando constantemente, pegado al valor
actual. En cuanto hay una degradación real, el acumulador empieza a
subir y se ALEJA de ese mínimo — la distancia creciente es la señal.
Es una forma distinta de mirar la misma acumulación de evidencia que
el CUSUM, mecánicamente distinta pero con el mismo espíritu.

Fórmula:
    m[t] = m[t-1] + (x[t] - mu0 - delta)      (acumulador, sin recortar)
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
        delta: float,
        lambda_: float,
        direction: Direction = Direction.LOWER_IS_WORSE,
    ) -> None:
        """
        Args:
            mu0: valor esperado cuando todo va bien (igual que en CUSUM).
            delta: tolerancia de deriva permitida por paso — evita que
                   el acumulador reaccione a fluctuaciones minúsculas de
                   ruido. Análogo en espíritu al `k` del CUSUM, aunque
                   se usa de forma distinta en la fórmula.
            lambda_: el umbral de alarma (nombre con guion bajo porque
                     `lambda` es palabra reservada en Python). Se calibra
                     igual que el h del CUSUM (detectors/calibration.py
                     funciona con cualquier detector que exponga un
                     parámetro de umbral vía fabricar_detector_con_h).
            direction: igual que en CUSUM y baseline.
        """
        if delta < 0:
            raise ValueError(f"delta no puede ser negativo, recibido: {delta}")
        if lambda_ <= 0:
            raise ValueError(f"lambda_ debe ser positivo, recibido: {lambda_}")

        self.mu0 = mu0
        self.delta = delta
        self.lambda_ = lambda_
        self.direction = direction
        super().__init__()

    def reset(self) -> None:
        self.m = 0.0  # acumulador, SIN recorte
        self.m_min = 0.0  # su mínimo histórico

    def update(self, obs: MetricObservation) -> Alarma | None:
        # misma normalización de signo que en CUSUM: "positivo" siempre
        # significa "evidencia de degradación", sea cual sea direction
        z = obs.value - self.mu0
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