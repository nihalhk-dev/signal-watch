"""Calibración sobre ruido REAL: cómo fijar un umbral cuando solo hay una serie.

El problema
───────────
En el banco sintético el ARL0 se mide sobre miles de series sin cambio que
fabricamos nosotros. En datos reales hay UNA serie. Los 330 meses de la
ventana de referencia (1963-1990) con un ARL0 objetivo de 120 darían, con
suerte, dos o tres falsas alarmas: imposible estimar un ARL0 con eso.

Dos salidas, y por qué se elige la segunda
──────────────────────────────────────────
1. Simular ruido gaussiano AR(1) con la media, la sigma y el ρ estimados.
   Es lo que hace `detectors/calibration.py`. Problema: los retornos reales
   tienen colas gordas, y una gaussiana las borra. Un umbral calibrado sobre
   colas finas dispara más de lo prometido cuando llega la cola de verdad.
   Es la primera pregunta que haría un validador de riesgos.

2. **Bootstrap por bloques de la propia ventana de referencia.** Se trocea
   la serie real 1963-1990 en bloques de meses consecutivos, se sortean
   bloques con reemplazo y se concatenan hasta tener series largas. Cada
   serie fabricada así:
     · tiene EXACTAMENTE la distribución de los valores reales, colas
       incluidas (no hay ningún valor que no haya ocurrido);
     · conserva la autocorrelación de corto plazo, porque dentro de cada
       bloque los meses siguen en su orden original;
     · y no contiene ningún cambio de régimen nuevo, porque todo sale de un
       tramo que tomamos como referencia.
   Se elige esta. El umbral se calibra sobre el ruido que de verdad tiene
   la serie, no sobre uno que nos inventamos.

   Dato medido, para no vender de más: en el Sharpe MENSUAL de HML la
   curtosis de exceso de la referencia es ≈ 0 (+0,01). Los retornos DIARIOS
   sí tienen colas gordas, pero dividir por la volatilidad del propio mes
   las doma. Así que aquí el bootstrap y una gaussiana darían umbrales
   parecidos. Se mantiene el bootstrap porque no necesita suponerlo — y
   porque la próxima métrica que se enchufe puede no tener esa suerte.

Longitud del bloque: la autocorrelación medida es ρ ≈ 0,2 a un mes y cae
rápido. Bloques de 6 meses la cubren de sobra sin trocear tan grueso que
las series fabricadas se parezcan demasiado entre sí.

Dos conjuntos disjuntos (R4, aplicada a la serie real)
──────────────────────────────────────────────────────
Se fabrican DOS conjuntos de series nulas con semillas distintas: con el
primero se calibra el umbral por bisección; con el segundo se mide el ARL0
que ese umbral consigue de verdad. Es la misma separación calibración /
evaluación del Bloque 4. Si se midiera sobre las mismas series con las que
se calibró, el ARL0 saldría clavado al objetivo por construcción y no
demostraría nada.

La bisección no es nueva
────────────────────────
Se reutiliza `_calibrar_umbral_biseccion` de `evaluation/delay_curves.py`
tal cual —el mismo código que produjo los resultados del Bloque 4—, en vez
de escribir una segunda bisección que pudiera divergir de la primera.

Limitación declarada
────────────────────
El bootstrap supone que 1963-1990 es un tramo sin cambios. No lo es del
todo (el Sharpe de los 60 y el de los 70 no son iguales). Si hubo cambios
dentro de la referencia, la sigma sale algo inflada y el detector algo más
conservador de lo que dice su ARL0. Se declara; no se corrige.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from signal_watch.detectors.baseline import TresSigma
from signal_watch.detectors.cusum import CUSUM
from signal_watch.detectors.page_hinkley import PageHinkley
from signal_watch.evaluation.arl import medir_arl0, medir_arl1
from signal_watch.evaluation.delay_curves import _calibrar_umbral_biseccion
from signal_watch.gold.metric_stream import GroundTruth
from signal_watch.gold.schemas import Direction, MetricObservation
from signal_watch.synthetic.scenarios import aplicar_deriva, aplicar_salto

# Las MISMAS funciones de inyección del banco sintético (Bloque 2): el
# método no cambia, lo que cambia es el ruido sobre el que se inyecta.
INYECTORES = {"salto": aplicar_salto, "deriva": aplicar_deriva}

# Rango de búsqueda de cada umbral, en unidades de sigma.
RANGOS_UMBRAL = {
    "CUSUM": (0.5, 40.0),          # h
    "Page-Hinkley": (0.5, 80.0),   # lambda (delta pequeño -> umbral mayor)
    "Shewhart": (1.0, 6.0),        # k: nº de sigmas de una sola observación
}
TOLERANCIA_BISECCION = 0.05


# ── Ruido empírico ───────────────────────────────────────────────────

def ruido_empirico(obs: list[MetricObservation]) -> dict[str, float]:
    """Describe el ruido de la ventana de referencia: lo que el bootstrap
    va a reproducir, y lo que hay que declarar."""
    x = np.array([o.value for o in obs], dtype=float)
    centrado = x - x.mean()
    sd = x.std(ddof=1)
    return {
        "n": int(len(x)),
        "mu0": float(x.mean()),
        "sigma": float(sd),
        "rho_lag1": float(np.corrcoef(x[:-1], x[1:])[0, 1]),
        "asimetria": float((centrado**3).mean() / sd**3),
        # exceso de curtosis: 0 en una normal, >0 con colas gordas
        "curtosis_exceso": float((centrado**4).mean() / sd**4 - 3.0),
    }


# ── Series nulas por bootstrap ───────────────────────────────────────

def series_nulas_bootstrap(
    obs: list[MetricObservation],
    n_series: int,
    longitud: int,
    bloque: int,
    semilla: int,
) -> list[list[MetricObservation]]:
    """Bootstrap de bloques móviles sobre la ventana de referencia.

    Cada serie fabricada reindexa `t` desde 0: `medir_arl0` cuenta el
    tiempo hasta la alarma a partir de `t`, igual que en el banco sintético.
    """
    n = len(obs)
    if bloque >= n:
        raise ValueError(f"Bloque de {bloque} meses con solo {n} meses de referencia.")
    rng = np.random.default_rng(semilla)
    n_bloques = -(-longitud // bloque)  # techo de la división
    inicios_posibles = n - bloque + 1

    series = []
    for i in range(n_series):
        inicios = rng.integers(0, inicios_posibles, size=n_bloques)
        indices = np.concatenate([np.arange(s, s + bloque) for s in inicios])[:longitud]
        series.append(
            [
                obs[j].model_copy(update={"t": t, "stream_id": f"bootstrap_{i:04d}"})
                for t, j in enumerate(indices)
            ]
        )
    return series


# ── Detectores ───────────────────────────────────────────────────────

def fabricar_detector(
    nombre: str,
    umbral: float,
    mu0: float,
    sigma: float,
    direction: Direction,
    k_cusum: float,
    delta_page_hinkley: float,
):
    """Construye el detector `nombre` con su umbral. Un solo sitio donde se
    decide cómo se instancia cada uno, para calibración y para monitorizar."""
    if nombre == "CUSUM":
        return CUSUM(mu0=mu0, sigma=sigma, k=k_cusum, h=umbral, direction=direction)
    if nombre == "Page-Hinkley":
        return PageHinkley(
            mu0=mu0, sigma=sigma, delta=delta_page_hinkley,
            lambda_=umbral, direction=direction,
        )
    if nombre == "Shewhart":
        return TresSigma(mu0=mu0, sigma=sigma, k=umbral, direction=direction)
    raise ValueError(f"Detector desconocido: {nombre}")


def _umbral_shewhart_por_cuantil(
    obs: list[MetricObservation],
    mu0: float,
    sigma: float,
    direction: Direction,
    arl0_objetivo: float,
) -> tuple[float, float]:
    """El umbral de Shewhart NO se puede calibrar por bisección aquí. Por qué:

    Shewhart mira cada observación por separado: alarma si UN valor pasa del
    umbral. Sobre series fabricadas remuestreando n = 330 valores reales, la
    probabilidad de alarma en cada paso es exactamente j/n, donde j es
    cuántos de esos 330 valores quedan más allá del umbral. El ARL0 solo
    puede valer n/j: 330, 165, 110, 82,5... **Un ARL0 de 120 no existe.**
    La bisección salta entre 110 y 165 según el ruido del conjunto de
    calibración, y en verificación cae en el otro escalón (lo vimos: umbral
    calibrado a "120", verificado a 153).

    Así que se elige el escalón alcanzable más cercano al objetivo
    (j = round(n / objetivo)) y se pone el umbral a medio camino entre el
    j-ésimo valor más extremo y el siguiente. Y se declara el ARL0
    ALCANZABLE, no el objetivo.

    La lección de fondo, que es un argumento a favor del CUSUM: la tasa de
    falsas alarmas de una regla de una sola observación la deciden los
    tres o cuatro meses más extremos de 27 años de historia. El CUSUM
    acumula muchas observaciones moderadas, y su tasa depende del grueso
    de la distribución, no de su cola más fina, que es justo la parte peor
    estimada.
    """
    x = np.array([o.value for o in obs], dtype=float)
    z = (x - mu0) / sigma
    malo = -z if direction == Direction.LOWER_IS_WORSE else z
    ordenado = np.sort(malo)[::-1]  # más extremo primero
    n = len(ordenado)
    j = int(np.clip(round(n / arl0_objetivo), 1, n - 1))
    umbral = float((ordenado[j - 1] + ordenado[j]) / 2)
    return umbral, n / j


@dataclass(frozen=True)
class Calibracion:
    """Resultado de calibrar un detector sobre ruido real."""

    detector: str
    umbral: float
    arl0_alcanzable: float   # = objetivo salvo en Shewhart (ver _umbral_shewhart_por_cuantil)
    arl0_verificado: float
    arl0_ic95: tuple[float, float]
    n_censurados: int
    n_series: int


def calibrar_en_ruido_real(
    obs_referencia: list[MetricObservation],
    arl0_objetivo: float,
    k_cusum: float,
    delta_page_hinkley: float,
    bootstrap_bloque: int,
    bootstrap_longitud: int,
    bootstrap_n_series: int,
    semilla_calibracion: int,
    semilla_verificacion: int,
) -> tuple[dict[str, Calibracion], dict, float]:
    """Calibra CUSUM, Page-Hinkley y Shewhart al MISMO ARL0 sobre ruido real.

    Devuelve (calibraciones, config_efectiva, arl0_tres_sigma_clasico).

    Los tres al mismo ARL0 porque comparar detectores con tasas de falsa
    alarma distintas no significa nada (MEMORIA §8.6). Shewhart incluido:
    su k se calibra como cualquier otro umbral y deja de ser 3.

    El `3σ` clásico sin calibrar se mide aparte y se devuelve como dato
    informativo: dice cuánto se aleja la regla de manual de la tasa de falsas
    alarmas que un banco elegiría a propósito.
    """
    if semilla_calibracion == semilla_verificacion:
        raise ValueError("Calibración y verificación necesitan semillas distintas (R4).")

    ruido = ruido_empirico(obs_referencia)
    mu0, sigma = ruido["mu0"], ruido["sigma"]
    direction = obs_referencia[0].direction

    nulas_calib = series_nulas_bootstrap(
        obs_referencia, bootstrap_n_series, bootstrap_longitud,
        bootstrap_bloque, semilla_calibracion,
    )
    nulas_verif = series_nulas_bootstrap(
        obs_referencia, bootstrap_n_series, bootstrap_longitud,
        bootstrap_bloque, semilla_verificacion,
    )

    def fabrica(nombre):
        return lambda u: fabricar_detector(
            nombre, u, mu0, sigma, direction, k_cusum, delta_page_hinkley
        )

    calibraciones: dict[str, Calibracion] = {}
    arl0_alcanzable: dict[str, float] = {}
    for nombre, (u_min, u_max) in RANGOS_UMBRAL.items():
        if nombre == "Shewhart":
            umbral, alcanzable = _umbral_shewhart_por_cuantil(
                obs_referencia, mu0, sigma, direction, arl0_objetivo
            )
        else:
            umbral = _calibrar_umbral_biseccion(
                fabrica(nombre), nulas_calib, arl0_objetivo, u_min, u_max,
            )
            alcanzable = arl0_objetivo
        arl0_alcanzable[nombre] = alcanzable
        r = medir_arl0(lambda: fabrica(nombre)(umbral), nulas_verif)
        # Fallar alto si la bisección se quedó pegada a un extremo del rango:
        # devolvería un umbral que NO cumple el objetivo sin avisar.
        if abs(r.arl - alcanzable) / alcanzable > 0.20:
            raise RuntimeError(
                f"{nombre}: el umbral {umbral:.3f} da ARL0 {r.arl:.1f} en las series de "
                f"verificación, lejos de {alcanzable:.1f}. ¿El rango "
                f"{RANGOS_UMBRAL[nombre]} no contiene la solución?"
            )
        calibraciones[nombre] = Calibracion(
            detector=nombre,
            umbral=float(umbral),
            arl0_alcanzable=float(alcanzable),
            arl0_verificado=float(r.arl),
            arl0_ic95=tuple(float(v) for v in r.intervalo_95),
            n_censurados=int(r.n_censurados),
            n_series=int(r.n_streams),
        )

    clasico = medir_arl0(
        lambda: fabricar_detector("Shewhart", 3.0, mu0, sigma, direction,
                                  k_cusum, delta_page_hinkley),
        nulas_verif,
    )

    config_efectiva = {
        "metodo_calibracion": "bootstrap_bloques_moviles",
        "arl0_objetivo": arl0_objetivo,
        "k_cusum": k_cusum,
        "delta_page_hinkley": delta_page_hinkley,
        "bootstrap_bloque": bootstrap_bloque,
        "bootstrap_longitud": bootstrap_longitud,
        "bootstrap_n_series": bootstrap_n_series,
        "semilla_calibracion": semilla_calibracion,
        "semilla_verificacion": semilla_verificacion,
        "rangos_umbral": {k: list(v) for k, v in RANGOS_UMBRAL.items()},
        "biseccion_tolerancia": TOLERANCIA_BISECCION,
        "n_referencia": ruido["n"],
        "mu0_estimado": round(mu0, 8),
        "sigma_estimado": round(sigma, 8),
        "umbrales": {k: round(c.umbral, 8) for k, c in calibraciones.items()},
        "arl0_alcanzable": {k: round(v, 4) for k, v in arl0_alcanzable.items()},
    }
    return calibraciones, config_efectiva, float(clasico.arl)


# ── Retardo sobre ruido real: inyección de un cambio conocido ────────
#
# Sobre la serie cruda no hay τ, así que no se puede medir un retardo.
# Aquí se fabrica: se toma ruido real (el mismo bootstrap de la referencia),
# se inyecta una caída de tamaño conocido en un τ elegido, y se mide cuánto
# tarda cada detector —con los umbrales YA calibrados, sin reajustar nada—.
#
# Es el cierre metodológico que pedía el manual para la fase de validación
# real: "tus curvas de retardo valen sobre tu ruido de juguete; ¿valen sobre
# ruido real?". Esta es la respuesta.
#
# Limitación declarada: el ruido sale de remuestrear UNA historia (330
# meses). Mide el rendimiento sobre el ruido de esa historia, no sobre ruido
# fuera de muestra.


@dataclass(frozen=True)
class PuntoRetardo:
    """Retardo de un detector ante un cambio inyectado de tamaño conocido."""

    detector: str
    escenario: str
    delta_sigma: float        # tamaño del cambio en unidades de sigma de la serie
    delta_sharpe: float       # el mismo cambio en Sharpe anualizado (interpretable)
    arl1: float               # retardo medio desde τ, en meses
    arl1_ic95: tuple[float, float]
    n_streams: int            # series que entran en la media del retardo
    n_censurados: int         # no alarmaron dentro del horizonte
    n_excluidos_pre_tau: int  # alarmaron ANTES del cambio (falsa alarma, se cuenta)
    n_series: int             # series fabricadas por celda


def medir_retardo_con_inyeccion(
    obs_referencia: list[MetricObservation],
    calibraciones: dict[str, "Calibracion"],
    k_cusum: float,
    delta_page_hinkley: float,
    escenarios: list[str],
    deltas_sigma: list[float],
    tau: int,
    horizonte: int,
    n_series: int,
    bootstrap_bloque: int,
    semilla: int,
) -> list[PuntoRetardo]:
    """Mide el retardo de cada detector calibrado ante caídas inyectadas.

    Números aleatorios comunes: TODAS las celdas (escenario × delta) usan el
    mismo ruido de fondo. Así la diferencia entre dos magnitudes es solo el
    tamaño del cambio, no la suerte de haber sacado otro ruido.
    """
    ruido = ruido_empirico(obs_referencia)
    mu0, sigma = ruido["mu0"], ruido["sigma"]
    direction = obs_referencia[0].direction
    # la caída va en la dirección MALA de la métrica (lección del Bloque 2, §8.1)
    signo = -1.0 if direction == Direction.LOWER_IS_WORSE else 1.0

    base = series_nulas_bootstrap(
        obs_referencia, n_series, tau + horizonte, bootstrap_bloque, semilla
    )

    puntos: list[PuntoRetardo] = []
    for escenario in escenarios:
        if escenario not in INYECTORES:
            raise ValueError(f"Escenario de inyección desconocido: {escenario}")
        inyectar = INYECTORES[escenario]
        for d in deltas_sigma:
            streams, verdades = [], []
            for i, serie in enumerate(base):
                valores = np.array([o.value for o in serie], dtype=float)
                nuevos = inyectar(valores.copy(), tau, signo * d, sigma)
                sid = f"iny_{escenario}_d{d:.2f}_r{i:04d}"
                streams.append(
                    [
                        o.model_copy(update={"value": float(v), "stream_id": sid})
                        for o, v in zip(serie, nuevos)
                    ]
                )
                verdades.append(GroundTruth(stream_id=sid, tau=tau, escenario=escenario))

            for nombre, c in calibraciones.items():
                r = medir_arl1(
                    lambda: fabricar_detector(
                        nombre, c.umbral, mu0, sigma, direction, k_cusum, delta_page_hinkley
                    ),
                    streams,
                    verdades,
                )
                puntos.append(
                    PuntoRetardo(
                        detector=nombre,
                        escenario=escenario,
                        delta_sigma=float(d),
                        delta_sharpe=float(d * sigma),
                        arl1=float(r.arl),
                        arl1_ic95=tuple(float(v) for v in r.intervalo_95),
                        n_streams=int(r.n_streams),
                        n_censurados=int(r.n_censurados),
                        n_excluidos_pre_tau=int(r.n_excluidos_por_alarma_temprana),
                        n_series=n_series,
                    )
                )
    return puntos
