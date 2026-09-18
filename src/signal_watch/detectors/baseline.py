"""Los detectores de referencia: TresSigma y UmbralFijo.

TresSigma es el baseline estadístico simple: alarma si el valor se
aleja demasiado de mu0, sin acumular evidencia entre instantes (a
diferencia del CUSUM). Es lo que cualquiera construiría "a ojo" sin
saber nada de detección secuencial.

UmbralFijo es la pieza conceptualmente más importante del proyecto,
aunque sea la más simple de código: convierte el FOLCLORE de la
industria ("si el PSI supera 0.25, hay alarma") en un detector de
pleno derecho, con la MISMA interfaz que el CUSUM. Esto es lo que
permite, por primera vez, medirle su ARL0 real y compararlo en la
misma curva retardo-vs-falsas-alarmas que los detectores serios. El
titular del proyecto ("nadie ha medido nunca la tasa de falsas
alarmas del umbral 0.25") solo es posible porque esta clase existe.
"""

from __future__ import annotations

from signal_watch.detectors.base import Alarma, Detector
from signal_watch.gold.schemas import Direction, MetricObservation


class TresSigma(Detector):
    """Alarma si el valor se aleja más de k desviaciones estándar de mu0,
    EN UN SOLO INSTANTE (no acumula evidencia entre observaciones).

    Es la referencia mínima honesta: un detector que "mira" cada punto
    aislado. Sirve para demostrar cuánto gana el CUSUM por acumular
    evidencia en vez de mirar instante a instante.
    """

    def __init__(
        self,
        mu0: float,
        sigma: float,
        k: float = 3.0,
        direction: Direction = Direction.LOWER_IS_WORSE,
    ) -> None:
        if sigma <= 0:
            raise ValueError(f"sigma debe ser positivo, recibido: {sigma}")
        if k <= 0:
            raise ValueError(f"k debe ser positivo, recibido: {k}")
        self.mu0 = mu0
        self.sigma = sigma
        self.k = k
        self.direction = direction
        super().__init__()

    def reset(self) -> None:
        pass  # no hay estado entre instantes: cada observación se evalúa sola

    def update(self, obs: MetricObservation) -> Alarma | None:
        distancia = (obs.value - self.mu0) / self.sigma
        if self.direction == Direction.HIGHER_IS_WORSE:
            distancia = -distancia
        # distancia negativa y grande en magnitud = degradación
        if -distancia > self.k:
            return Alarma(t=obs.t, estadistico=-distancia)
        return None


class UmbralFijo(Detector):
    """El folclore de la industria, como detector medible: alarma si el
    valor cruza un umbral absoluto fijo — sin calibrar, sin conocer su
    ARL0, tal y como se usa hoy en la práctica.

    El caso de uso central: UmbralFijo(umbral=0.25, direction=HIGHER_IS_WORSE)
    reproduce EXACTAMENTE la regla "si PSI > 0.25, alarma" que usa media
    industria. Al darle la misma interfaz que el CUSUM, evaluation/delay_curves.py
    puede medirle su retardo y su ARL0 en el banco de pruebas sintético,
    sin trato especial — es lo que permite el resultado central del
    proyecto: caracterizar por primera vez esta regla, en vez de darla
    por buena porque "así se ha hecho siempre".
    """

    def __init__(
        self,
        umbral: float,
        direction: Direction = Direction.HIGHER_IS_WORSE,
    ) -> None:
        """
        Args:
            umbral: el valor absoluto que dispara la alarma. Para el
                    folclore del PSI, esto es 0.25.
            direction: por defecto higher_is_worse, porque el caso de
                       uso principal ES el PSI. Para un umbral fijo
                       sobre una métrica lower_is_worse (menos común
                       en la práctica, pero soportado por completitud),
                       se pasa LOWER_IS_WORSE.
        """
        self.umbral = umbral
        self.direction = direction
        super().__init__()

    def reset(self) -> None:
        pass  # tampoco tiene estado: cada punto se compara solo contra el umbral

    def update(self, obs: MetricObservation) -> Alarma | None:
        if self.direction == Direction.HIGHER_IS_WORSE:
            if obs.value > self.umbral:
                return Alarma(t=obs.t, estadistico=obs.value)
        else:
            if obs.value < self.umbral:
                return Alarma(t=obs.t, estadistico=obs.value)
        return None