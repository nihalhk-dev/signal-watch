"""La interfaz común de todos los detectores.

Cualquier detector (CUSUM, Page-Hinkley, el folclore PSI, el control
3-sigma) hereda de Detector e implementa update(). Esto es lo que
permite que evaluation/delay_curves.py los trate a todos por igual,
sin saber ni importarle qué hay dentro de cada uno.

La firma de update() es la muralla aplicada a nivel de TIPO: solo
acepta un MetricObservation (que nunca tiene tau, por diseño de
schemas.py). No hay forma de pasarle a un detector el instante de
cambio real ni por accidente — el tipo del parámetro lo impide.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from signal_watch.gold.schemas import MetricObservation


@dataclass(frozen=True)
class Alarma:
    """Lo que un detector devuelve cuando decide que ha habido un cambio.

    t: el instante (índice temporal) en el que el detector dispara —
       esto es t_alarma, lo que se compara contra tau (el cambio real)
       para medir el retardo. El propio detector NUNCA ve tau; quien
       compara alarma.t contra tau es evaluation/delay_curves.py,
       DESPUÉS de que el detector ya haya hablado.
    estadistico: el valor interno del detector en el momento de la
       alarma (p.ej. el acumulador del CUSUM). Sirve para interpretar
       cuán fuerte fue la señal, y para depurar/explicar la alarma.
    """

    t: int
    estadistico: float


class Detector(ABC):
    """Clase base de todos los detectores del proyecto.

    Contrato:
      · update(obs) se llama UNA VEZ por cada observación nueva, EN ORDEN.
      · Devuelve una Alarma si el detector decide disparar en ESE instante,
        o None si sigue vigilando sin alarmar.
      · El detector mantiene su propio estado interno entre llamadas
        (por eso no es una función pura) — cada subclase decide qué
        estado necesita (acumuladores, medias móviles, etc.).
      · reset() vuelve al detector a su estado inicial, para poder
        reutilizar la misma instancia en una serie nueva sin crear un
        objeto desde cero.
    """

    def __init__(self) -> None:
        self.reset()

    @abstractmethod
    def update(self, obs: MetricObservation) -> Alarma | None:
        """Procesa una observación nueva y decide si dispara una alarma.

        IMPORTANTE: obs es un MetricObservation, que por diseño (ver
        schemas.py) NUNCA tiene un campo tau. Un detector es, por tipo,
        incapaz de recibir la verdad-terreno.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reinicia el estado interno del detector a sus valores iniciales."""
        raise NotImplementedError

    def procesar_serie(self, observaciones: list[MetricObservation]) -> list[Alarma]:
        """Conveniencia: procesa una serie completa de observaciones EN
        ORDEN y devuelve todas las alarmas que se disparen.

        Nota de diseño: un detector real de monitorización solo dispara
        UNA alarma y luego un humano decide qué hacer (no sigue
        alarmando cada instante indefinidamente). Por eso, tras la
        primera alarma, procesar_serie() deja de llamar a update() —
        igual que pasaría en producción, donde alguien atiende la
        primera alarma antes de que tenga sentido seguir vigilando esa
        misma racha de cambio.
        """
        self.reset()
        alarmas: list[Alarma] = []
        for obs in observaciones:
            alarma = self.update(obs)
            if alarma is not None:
                alarmas.append(alarma)
                break  # una alarma detiene el procesamiento de esta serie
        return alarmas