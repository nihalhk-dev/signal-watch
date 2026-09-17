"""Los escenarios de cambio del banco de pruebas.

Cada escenario es una función que, dado un array de valores base (ya
con ruido AR(1) aplicado) y un instante tau, devuelve los valores
CON el cambio aplicado. Todos comparten la misma firma, así que el
generador puede tratarlos de forma intercambiable.

Por qué varios escenarios y no solo "salto":
  Un detector que solo se ha visto las caras con un salto brusco puede
  fallar estrepitosamente ante una deriva lenta (que es más realista:
  un modelo raramente se rompe de un día para otro) o ante un cambio
  de varianza (que muchos detectores, calibrados para vigilar la media,
  ni siquiera ven). Probar contra los cuatro es lo que te permite decir
  con honestidad "mi detector funciona bien AQUÍ y flojea ALLÁ", en vez
  de una afirmación general sin matices.

"sin_cambio" es el escenario de control: aquí NO hay tau real (tau=None),
y es el que usas para medir el ARL0 — cuánto tarda el detector en
disparar una falsa alarma cuando no hay absolutamente nada que detectar.
"""

from __future__ import annotations

import numpy as np


def aplicar_salto(
    valores: np.ndarray,
    tau: int,
    delta_sigma: float,
    sigma: float,
) -> np.ndarray:
    """Cambio brusco: la media se desplaza de golpe en tau y se queda ahí.

    Es el escenario "fácil" — el cambio es máximo desde el primer
    instante después de tau. Cualquier detector razonable debería
    encontrarlo, tarde o temprano.
    """
    resultado = valores.copy()
    resultado[tau:] += delta_sigma * sigma
    return resultado


def aplicar_deriva(
    valores: np.ndarray,
    tau: int,
    delta_sigma: float,
    sigma: float,
    duracion: int = 20,
) -> np.ndarray:
    """Cambio gradual: el desplazamiento crece poco a poco en rampa,
    desde 0 en tau hasta el valor completo tras `duracion` pasos.

    Es el escenario realista: un modelo que se degrada porque la
    población de solicitantes cambia poco a poco, no de un día para
    otro. Es más difícil de detectar que el salto porque en cada
    instante individual el cambio es pequeño — el detector tiene que
    acumular evidencia durante más tiempo.
    """
    resultado = valores.copy()
    n = len(valores)
    fin_rampa = min(tau + duracion, n)

    # de tau a fin_rampa: el desplazamiento crece linealmente de 0 a 1
    rampa = np.linspace(0, 1, fin_rampa - tau)
    resultado[tau:fin_rampa] += rampa * delta_sigma * sigma

    # después de la rampa: desplazamiento completo, como el salto
    if fin_rampa < n:
        resultado[fin_rampa:] += delta_sigma * sigma

    return resultado


def aplicar_cambio_varianza(
    valores: np.ndarray,
    tau: int,
    factor_varianza: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Cambio de varianza: la media NO se mueve, pero el ruido a partir
    de tau se multiplica por `factor_varianza` (>1 = más ruidoso).

    Es el escenario trampa: un detector calibrado para vigilar
    desplazamientos de la MEDIA (como un CUSUM clásico) puede no
    reaccionar aquí en absoluto, porque el promedio de la serie sigue
    siendo el mismo — lo que cambió es cuánto se dispersa alrededor
    de ese promedio. Sirve para caracterizar honestamente ESE límite
    del método, no para ocultarlo.
    """
    resultado = valores.copy()
    n = len(valores)
    # Le añadimos ruido EXTRA a partir de tau, calibrado para que la
    # varianza total se multiplique por factor_varianza.
    # var_extra = var_original * (factor_varianza - 1)
    varianza_original = np.var(valores[:tau]) if tau > 0 else np.var(valores)
    sigma_extra = np.sqrt(max(varianza_original * (factor_varianza - 1), 0))
    ruido_extra = rng.normal(0, sigma_extra, size=n - tau)
    resultado[tau:] += ruido_extra
    return resultado


def aplicar_sin_cambio(valores: np.ndarray) -> np.ndarray:
    """Sin cambio: devuelve la serie tal cual, sin tocar nada.

    Este es el escenario de CONTROL. No hay tau real — se usa para
    medir el ARL0 (cuánto tarda un detector en dar una falsa alarma
    cuando no hay absolutamente nada que detectar). Un buen detector
    debe quedarse callado aquí la mayor parte del tiempo.
    """
    return valores.copy()


# Catálogo de escenarios disponibles, para que build_gold.py pueda
# iterar sobre todos ellos por nombre sin un if/elif gigante.
ESCENARIOS_DISPONIBLES = (
    "salto",
    "deriva",
    "cambio_varianza",
    "sin_cambio",
)