"""El detector CUSUM — acumula evidencia de cambio, instante a instante.

Implementación directa de la fórmula derivada desde la razón de
verosimilitud (ver docs/arquitectura/decisiones/, o MEMORIA_PROYECTO.md
para el razonamiento completo, paso a paso, de cómo se llega aquí):

    S[t] = max(0, S[t-1] + (x[t] - mu0)/sigma - k)

    donde k = delta_minimo / 2  (en unidades de sigma: la mitad de la
    distancia mínima que queremos poder detectar entre "todo va bien"
    y "ya cambió")

Dispara alarma cuando S[t] > h (el umbral, calibrado en detectors/calibration.py
para lograr un ARL0 objetivo).

Por qué max(0, ...) y no dejar que S derive libremente: sin el recorte,
un cambio que llega tras una racha larga de "todo normal" tendría que
"pagar" primero toda la evidencia negativa acumulada antes de que S
empezara a subir de verdad — retrasando la detección sin necesidad. Con
el recorte, el detector siempre parte del mejor punto posible para notar
el cambio (esto se razonó y se confirmó con la autora antes de escribir
este código, no es un detalle arbitrario de implementación).

Esta implementación detecta DESCENSOS (mu1 < mu0), que es el caso de
interés del proyecto: un AUC o un Sharpe que CAE representa degradación.
Para higher_is_worse (el PSI) se usa la variante simétrica, ver más abajo.
"""

from __future__ import annotations

from signal_watch.detectors.base import Alarma, Detector
from signal_watch.gold.schemas import Direction, MetricObservation


class CUSUM(Detector):
    """CUSUM unilateral: detecta que la métrica ha EMPEORADO.

    Qué significa "empeorado" depende de `direction`:
      · lower_is_worse (AUC, Sharpe): vigila caídas por debajo de mu0.
      · higher_is_worse (PSI): vigila subidas por encima de mu0.
    En ambos casos, el acumulador crece cuando la evidencia apunta a
    degradación, y se recorta a 0 cuando apunta a normalidad.
    """

    def __init__(
        self,
        mu0: float,
        sigma: float,
        k: float,
        h: float,
        direction: Direction = Direction.LOWER_IS_WORSE,
    ) -> None:
        """
        Args:
            mu0: valor esperado de la métrica cuando todo va bien
                 (el nivel de referencia — normalmente el promedio del
                 periodo de calibración/entrenamiento).
            sigma: desviación estándar de la métrica bajo mu0 (el ruido
                   de fondo esperado). Nota: en la práctica cada
                   observación trae su propio value_se (ver update()),
                   que es más preciso que un sigma fijo — pero el CUSUM
                   clásico se define con un sigma de referencia único
                   para mantener el umbral h comparable entre periodos.
            k: la mitad de la magnitud mínima de cambio (en unidades de
               sigma) que queremos poder detectar. Cuanto más pequeño,
               más sensible a cambios sutiles, pero más falsas alarmas
               para el mismo h.
            h: el umbral de alarma. Se calibra (detectors/calibration.py)
               para lograr un ARL0 objetivo — NO se elige a ojo.
            direction: si la degradación es una caída o una subida.
        """
        if sigma <= 0:
            raise ValueError(f"sigma debe ser positivo, recibido: {sigma}")
        if k < 0:
            raise ValueError(f"k no puede ser negativo, recibido: {k}")
        if h <= 0:
            raise ValueError(f"h debe ser positivo, recibido: {h}")

        self.mu0 = mu0
        self.sigma = sigma
        self.k = k
        self.h = h
        self.direction = direction
        super().__init__()

    def reset(self) -> None:
        self.s = 0.0  # el acumulador, arranca en 0
        self.t_actual = -1

    def update(self, obs: MetricObservation) -> Alarma | None:
        self.t_actual = obs.t

        # Estandarizar: cuántas sigmas se aleja el valor observado de mu0.
        # Si direction=higher_is_worse (PSI), invertimos el signo, así
        # el resto de la fórmula es IDÉNTICA en ambos casos — "evidencia
        # positiva" siempre significa "evidencia de degradación",
        # nunca hay que acordarse de invertir nada más adelante.
        z = (obs.value - self.mu0) / self.sigma
        if self.direction == Direction.HIGHER_IS_WORSE:
            z = -z

        # La fórmula derivada: acumula evidencia de degradación,
        # recorta a 0 cuando la evidencia apunta a normalidad.
        self.s = max(0.0, self.s - z - self.k)
        # (nota de signo: para lower_is_worse, degradación = valor BAJA,
        #  z se vuelve NEGATIVO, así que -z es POSITIVO -> el acumulador
        #  sube. Si direction=higher_is_worse ya invertimos z arriba,
        #  así que la misma línea sirve para los dos casos.)

        if self.s > self.h:
            return Alarma(t=obs.t, estadistico=self.s)
        return None
