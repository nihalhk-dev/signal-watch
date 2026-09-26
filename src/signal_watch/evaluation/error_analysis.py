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

Retardo fuera de muestra
────────────────────────
Para medir el RETARDO sobre ruido real hay que inyectar un cambio en series
de ruido. Si ese ruido sale de los mismos meses con los que se calibró el
umbral, el detector juega en casa. Por eso el experimento de retardo parte
la referencia en años alternos: una mitad calibra, la otra pone el ruido,
y luego al revés. Ver medir_retardo_fuera_de_muestra.

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

Tramo = tuple[int, int]  # [inicio, fin) en índices de la referencia


def particion_intercalada(n: int, tramo: int, minimo: int) -> tuple[list[Tramo], list[Tramo]]:
    """Parte los n meses de la referencia en tramos de `tramo` meses y los
    reparte alternando: pares -> mitad A (calibra), impares -> mitad B
    (ruido para inyectar).

    Por qué intercalada y no "primera mitad / segunda mitad": 1963-1976 y
    1977-1990 no tienen el mismo Sharpe. Partir por la mitad mezclaría la
    separación con un cambio de régimen; alternando años, las dos mitades
    ven las mismas épocas.

    Un último tramo más corto que `minimo` (el bloque del bootstrap) se
    descarta de las dos mitades: no cabe un bloque entero dentro de él.
    """
    if tramo < minimo:
        raise ValueError(f"Tramos de {tramo} meses no caben bloques de {minimo}.")
    a: list[Tramo] = []
    b: list[Tramo] = []
    for i, inicio in enumerate(range(0, n, tramo)):
        fin = min(inicio + tramo, n)
        if fin - inicio < minimo:
            continue
        (a if i % 2 == 0 else b).append((inicio, fin))
    return a, b


def indices_de(tramos: list[Tramo]) -> np.ndarray:
    """Todos los índices de la referencia que caen dentro de `tramos`."""
    return np.concatenate([np.arange(s, e) for s, e in tramos])


def subconjunto(obs: list[MetricObservation], tramos: list[Tramo] | None) -> list[MetricObservation]:
    """Las observaciones de `tramos` (todas, si no hay tramos)."""
    return obs if tramos is None else [obs[i] for i in indices_de(tramos)]


def bloques_candidatos(tramos: list[Tramo], bloque: int) -> np.ndarray:
    """Todos los bloques que el bootstrap puede sortear dentro de `tramos`,
    uno por fila.

    Bootstrap CIRCULAR dentro de cada tramo (Politis y Romano, 1992): un
    bloque que llega al final de su tramo sigue por el principio del mismo
    tramo, nunca salta al siguiente (que es de la otra mitad). Con bloques
    móviles normales, los meses del borde de cada tramo saldrían mucho menos
    que los del centro; con el circular, cada mes sale exactamente en
    `bloque` de los candidatos. Así el ruido fabricado es el de la mitad,
    sin meses que pesen más que otros por dónde caen dentro del tramo.
    """
    filas = []
    for s, e in tramos:
        largo = e - s
        if bloque > largo:
            raise ValueError(f"Bloque de {bloque} meses en un tramo de {largo}.")
        for off in range(largo):
            filas.append(s + (off + np.arange(bloque)) % largo)
    return np.array(filas)


def indices_bootstrap(
    n: int,
    n_series: int,
    longitud: int,
    bloque: int,
    semilla: int,
    tramos: list[Tramo] | None = None,
) -> list[np.ndarray]:
    """Índices de la referencia que forman cada serie fabricada.

    Sin `tramos`: bloques móviles sobre toda la referencia. Es el código de
    siempre, con las mismas llamadas al generador, así que la calibración
    de producción sale idéntica bit a bit (lo comprueba un test).

    Con `tramos`: solo bloques de dentro de esos tramos (ver
    bloques_candidatos). Así una mitad nunca ve un mes de la otra.
    """
    if bloque >= n:
        raise ValueError(f"Bloque de {bloque} meses con solo {n} meses de referencia.")
    rng = np.random.default_rng(semilla)
    n_bloques = -(-longitud // bloque)  # techo de la división

    if tramos is None:
        inicios_posibles = n - bloque + 1
        salida = []
        for _ in range(n_series):
            inicios = rng.integers(0, inicios_posibles, size=n_bloques)
            salida.append(np.concatenate([np.arange(s, s + bloque) for s in inicios])[:longitud])
        return salida

    candidatos = bloques_candidatos(tramos, bloque)
    return [
        candidatos[rng.integers(0, len(candidatos), size=n_bloques)].ravel()[:longitud]
        for _ in range(n_series)
    ]


def series_nulas_bootstrap(
    obs: list[MetricObservation],
    n_series: int,
    longitud: int,
    bloque: int,
    semilla: int,
    tramos: list[Tramo] | None = None,
) -> list[list[MetricObservation]]:
    """Bootstrap por bloques sobre la ventana de referencia (o sobre una de
    sus mitades, si se pasan `tramos`).

    Cada serie fabricada reindexa `t` desde 0: `medir_arl0` cuenta el
    tiempo hasta la alarma a partir de `t`, igual que en el banco sintético.
    """
    series = []
    for i, indices in enumerate(
        indices_bootstrap(len(obs), n_series, longitud, bloque, semilla, tramos)
    ):
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


def _umbral_shewhart_escalon(
    obs: list[MetricObservation],
    mu0: float,
    sigma: float,
    direction: Direction,
    j: int,
) -> float:
    """Umbral de Shewhart que deja exactamente j valores de la referencia
    por el lado malo: a medio camino entre el j-ésimo más extremo y el
    siguiente.

    Por qué Shewhart NO se calibra por bisección. Shewhart mira cada
    observación por separado: alarma si UN valor pasa del umbral. Sobre
    series fabricadas remuestreando n valores reales, mover el umbral solo
    cambia algo cuando cruza uno de esos n valores. El ARL0 va a saltos, uno
    por cada j = 1, 2, 3...: **un ARL0 de 120 exacto no existe.** La
    bisección salta entre dos escalones según el ruido del conjunto de
    calibración, y en verificación cae en el otro (lo vimos: umbral
    calibrado a "120", verificado a 153).

    Cuánto vale cada escalón NO se supone: se mide (ver calibrar_en_ruido_real).
    La cuenta de manual, ARL0 = n/j, solo vale si los j meses extremos están
    separados. Si dos son vecinos, un bloque del bootstrap que trae uno trae
    también el otro: las alarmas llegan en racimos y el ARL0 sube. Pasó en la
    mitad A de HML: n/j = 168/2 = 84 sobre el papel, 107 medido.

    La lección de fondo, que es un argumento a favor del CUSUM: la tasa de
    falsas alarmas de una regla de una sola observación la deciden los
    tres o cuatro meses más extremos de 27 años de historia (y hasta si son
    vecinos o no). El CUSUM acumula muchas observaciones moderadas, y su
    tasa depende del grueso de la distribución, no de su cola más fina, que
    es justo la parte peor estimada.
    """
    x = np.array([o.value for o in obs], dtype=float)
    z = (x - mu0) / sigma
    malo = -z if direction == Direction.LOWER_IS_WORSE else z
    ordenado = np.sort(malo)[::-1]  # más extremo primero
    return float((ordenado[j - 1] + ordenado[j]) / 2)


@dataclass(frozen=True)
class Calibracion:
    """Resultado de calibrar un detector sobre ruido real."""

    detector: str
    umbral: float
    arl0_alcanzable: float   # = objetivo salvo en Shewhart (ver _umbral_shewhart_escalon)
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
    tramos: list[Tramo] | None = None,
) -> tuple[dict[str, Calibracion], dict, float]:
    """Calibra CUSUM, Page-Hinkley y Shewhart al MISMO ARL0 sobre ruido real.

    Devuelve (calibraciones, config_efectiva, arl0_tres_sigma_clasico).

    Con `tramos`, todo (mu0, sigma, el cuantil de Shewhart y los dos
    bootstraps) sale SOLO de esos meses de la referencia. Es lo que usa el
    experimento de retardo fuera de muestra: calibrar con la mitad A.

    Los tres al mismo ARL0 porque comparar detectores con tasas de falsa
    alarma distintas no significa nada (MEMORIA §8.6). Shewhart incluido:
    su k se calibra como cualquier otro umbral y deja de ser 3.

    El `3σ` clásico sin calibrar se mide aparte y se devuelve como dato
    informativo: dice cuánto se aleja la regla de manual de la tasa de falsas
    alarmas que un banco elegiría a propósito.
    """
    if semilla_calibracion == semilla_verificacion:
        raise ValueError("Calibración y verificación necesitan semillas distintas (R4).")

    propios = subconjunto(obs_referencia, tramos)
    ruido = ruido_empirico(propios)
    mu0, sigma = ruido["mu0"], ruido["sigma"]
    direction = obs_referencia[0].direction

    nulas_calib = series_nulas_bootstrap(
        obs_referencia, bootstrap_n_series, bootstrap_longitud,
        bootstrap_bloque, semilla_calibracion, tramos,
    )
    nulas_verif = series_nulas_bootstrap(
        obs_referencia, bootstrap_n_series, bootstrap_longitud,
        bootstrap_bloque, semilla_verificacion, tramos,
    )

    def fabrica(nombre):
        return lambda u: fabricar_detector(
            nombre, u, mu0, sigma, direction, k_cusum, delta_page_hinkley
        )

    calibraciones: dict[str, Calibracion] = {}
    arl0_alcanzable: dict[str, float] = {}
    for nombre, (u_min, u_max) in RANGOS_UMBRAL.items():
        if nombre == "Shewhart":
            # El primer escalón que NO es más estricto que el objetivo, con su
            # ARL0 MEDIDO en las series de calibración. "No más estricto" y no
            # "el más cercano": si Shewhart quedara con menos falsas alarmas
            # que los otros, también detectaría más tarde y la comparación le
            # perjudicaría. Así, si pierde, pierde con la ventaja a su favor.
            for j in range(1, len(propios)):
                umbral = _umbral_shewhart_escalon(propios, mu0, sigma, direction, j)
                alcanzable = float(medir_arl0(lambda: fabrica(nombre)(umbral), nulas_calib).arl)
                if alcanzable <= arl0_objetivo:
                    break
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
    # Solo si hay tramos: sin ellos la config (y su hash) queda como siempre.
    if tramos is not None:
        config_efectiva["tramos"] = [list(t) for t in tramos]
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
# Primera versión: calibrar e inyectar remuestreaban los MISMOS 330 meses.
# El umbral se había ajustado a ese ruido y luego se medía sobre él: no era
# una prueba fuera de muestra (lo señaló el tutor). Ahora, con
# `particion_tramo_meses` en la config, medir_retardo_fuera_de_muestra parte
# la referencia en años alternos: una mitad calibra, la otra pone el ruido
# donde se inyecta, y luego al revés. Ningún mes está en las dos. La tabla
# dentro de muestra se conserva: es la comparación a igual tasa de falsas
# alarmas; fuera de muestra esa igualdad se pierde (ver la función).
#
# Limitación que sigue en pie: A y B son dos mitades de UNA historia
# (1963-1990). Es fuera de muestra respecto a la calibración, no respecto a
# otra época ni a otro mercado.


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
    tramos_ruido: list[Tramo] | None = None,
    parametros_detector: tuple[float, float] | None = None,
    sigma_inyeccion: float | None = None,
) -> list[PuntoRetardo]:
    """Mide el retardo de cada detector calibrado ante caídas inyectadas.

    Números aleatorios comunes: TODAS las celdas (escenario × delta) usan el
    mismo ruido de fondo. Así la diferencia entre dos magnitudes es solo el
    tamaño del cambio, no la suerte de haber sacado otro ruido.

    Sin argumentos opcionales, todo sale de la referencia entera (la versión
    dentro de muestra). Para la versión fuera de muestra:
      · tramos_ruido: de qué meses sale el ruido donde se inyecta (mitad B);
      · parametros_detector: (mu0, sigma) con los que se calibró (mitad A):
        el detector no sabe nada de B;
      · sigma_inyeccion: la escala del cambio. Se deja en la sigma de la
        referencia entera para que "0,15σ" siga siendo "el factor pasa a
        Sharpe cero" y las tablas se puedan comparar. El tamaño del cambio
        es la pregunta del experimento, no algo que el detector conozca.
    """
    ruido = ruido_empirico(obs_referencia)
    mu0, sigma = parametros_detector or (ruido["mu0"], ruido["sigma"])
    escala = sigma_inyeccion if sigma_inyeccion is not None else sigma
    direction = obs_referencia[0].direction
    # la caída va en la dirección MALA de la métrica (lección del Bloque 2, §8.1)
    signo = -1.0 if direction == Direction.LOWER_IS_WORSE else 1.0

    base = series_nulas_bootstrap(
        obs_referencia, n_series, tau + horizonte, bootstrap_bloque, semilla, tramos_ruido
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
                nuevos = inyectar(valores.copy(), tau, signo * d, escala)
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
                        delta_sharpe=float(d * escala),
                        arl1=float(r.arl),
                        arl1_ic95=tuple(float(v) for v in r.intervalo_95),
                        n_streams=int(r.n_streams),
                        n_censurados=int(r.n_censurados),
                        n_excluidos_pre_tau=int(r.n_excluidos_por_alarma_temprana),
                        n_series=n_series,
                    )
                )
    return puntos


@dataclass(frozen=True)
class FueraDeMuestra:
    """Todo lo que produce el experimento de retardo fuera de muestra, en
    UNA dirección (calibrar con una mitad, inyectar en la otra)."""

    direccion: str                            # "A->B" o "B->A"
    puntos: list[PuntoRetardo]
    calibraciones: dict[str, Calibracion]     # umbrales ajustados SOLO con la mitad que calibra
    arl0_ruido_inyeccion: dict[str, float]    # esos umbrales, sobre ruido de la otra mitad
    tramos_calibra: list[Tramo]
    tramos_inyecta: list[Tramo]
    mu0_calibra: float
    sigma_calibra: float


def medir_retardo_fuera_de_muestra(
    obs_referencia: list[MetricObservation],
    arl0_objetivo: float,
    k_cusum: float,
    delta_page_hinkley: float,
    bootstrap_bloque: int,
    bootstrap_longitud: int,
    bootstrap_n_series: int,
    semilla_calibracion: int,
    semilla_verificacion: int,
    escenarios: list[str],
    deltas_sigma: list[float],
    tau: int,
    horizonte: int,
    n_series: int,
    semilla: int,
    tramo_meses: int,
    invertir: bool = False,
) -> FueraDeMuestra:
    """Retardo con calibración e inyección en meses DISJUNTOS.

    1. Parte la referencia en tramos alternos de `tramo_meses`: A y B.
       Sin invertir, A calibra y B pone el ruido; invirtiendo, al revés.
       Se corren las dos direcciones: con una sola partición, cualquier
       conclusión podría ser suerte de cómo cayeron los años.
    2. Calibra los tres detectores al mismo ARL0 usando SOLO la mitad que
       calibra (mu0, sigma, bisección, verificación, escalón de Shewhart).
    3. Mide qué ARL0 tienen esos umbrales sobre ruido de la otra mitad, sin
       cambio. Es la pregunta de un validador: ¿la tasa de falsas alarmas
       prometida aguanta en datos que el umbral no ha visto?
    4. Inyecta las caídas sobre ruido de la otra mitad y mide el retardo.

    OJO al leer el retardo: fuera de muestra los detectores dejan de tener
    la misma tasa de falsas alarmas (paso 3), así que sus retardos ya no se
    comparan como una carrera. Un detector que salta a menudo "detecta"
    pronto aunque no haya nada. El retardo se lee SIEMPRE junto a su ARL0
    en el ruido de inyección y a las series excluidas antes de τ.

    Los umbrales de producción (calibracion_<stream>.csv, 330 meses) NO
    cambian: lo que se valida aquí es el procedimiento de calibración.
    """
    tramos_a, tramos_b = particion_intercalada(len(obs_referencia), tramo_meses, bootstrap_bloque)
    calibra, inyecta = (tramos_b, tramos_a) if invertir else (tramos_a, tramos_b)
    calib, _, _ = calibrar_en_ruido_real(
        obs_referencia, arl0_objetivo, k_cusum, delta_page_hinkley,
        bootstrap_bloque, bootstrap_longitud, bootstrap_n_series,
        semilla_calibracion, semilla_verificacion, tramos=calibra,
    )
    ruido_c = ruido_empirico(subconjunto(obs_referencia, calibra))
    mu0_c, sigma_c = ruido_c["mu0"], ruido_c["sigma"]
    direction = obs_referencia[0].direction

    # semilla + 1: otra extracción, distinta de la del ruido de inyección
    nulas = series_nulas_bootstrap(
        obs_referencia, bootstrap_n_series, bootstrap_longitud,
        bootstrap_bloque, semilla + 1, inyecta,
    )
    arl0_iny = {
        nombre: float(
            medir_arl0(
                lambda c=c, nombre=nombre: fabricar_detector(
                    nombre, c.umbral, mu0_c, sigma_c, direction, k_cusum, delta_page_hinkley
                ),
                nulas,
            ).arl
        )
        for nombre, c in calib.items()
    }

    puntos = medir_retardo_con_inyeccion(
        obs_referencia, calib, k_cusum, delta_page_hinkley, escenarios, deltas_sigma,
        tau, horizonte, n_series, bootstrap_bloque, semilla,
        tramos_ruido=inyecta,
        parametros_detector=(mu0_c, sigma_c),
        sigma_inyeccion=ruido_empirico(obs_referencia)["sigma"],
    )
    return FueraDeMuestra(
        "B->A" if invertir else "A->B", puntos, calib, arl0_iny,
        calibra, inyecta, mu0_c, sigma_c,
    )


# ── Una sola serie, para el laboratorio de la app ────────────────────
#
# La app (app/pages/3_Factores_de_mercado.py) deja al usuario inyectar una
# caída sobre ruido real y ver cuándo salta cada detector. La lógica vive
# aquí y no en la app (R6): la app solo llama y dibuja. Usa exactamente las
# mismas piezas que la medición seria (bootstrap de la referencia, las
# funciones de inyección del Bloque 2, los detectores con sus umbrales ya
# calibrados), así que lo que se ve en pantalla es un caso concreto de lo
# que las tablas promedian sobre 1000 series.
#
# El laboratorio sigue remuestreando la referencia entera con los umbrales
# de producción: es una ilustración de un caso, no una medición. Los números
# que se defienden son los de retardo_ruido_real_<stream>.csv.


def demo_inyeccion(
    obs_referencia: list[MetricObservation],
    umbrales: dict[str, float],
    k_cusum: float,
    delta_page_hinkley: float,
    escenario: str,
    delta_sigma: float,
    tau: int,
    horizonte: int,
    bootstrap_bloque: int,
    semilla: int,
) -> dict:
    """Fabrica UNA serie de ruido real con una caída en τ y la pasa por cada
    detector. Devuelve los valores y, por detector, el mes de su primera
    alarma y cómo leerla.

    Convenio de tiempo, el mismo que evaluation/arl.py: el instante de una
    alarma es `alarma.t + 1` (observaciones consumidas). Si es ≤ τ, la alarma
    llegó antes del cambio: es una falsa alarma, no una detección.
    """
    if escenario not in INYECTORES:
        raise ValueError(f"Escenario de inyección desconocido: {escenario}")
    ruido = ruido_empirico(obs_referencia)
    mu0, sigma = ruido["mu0"], ruido["sigma"]
    direction = obs_referencia[0].direction
    signo = -1.0 if direction == Direction.LOWER_IS_WORSE else 1.0

    serie = series_nulas_bootstrap(obs_referencia, 1, tau + horizonte, bootstrap_bloque, semilla)[0]
    valores = np.array([o.value for o in serie], dtype=float)
    nuevos = INYECTORES[escenario](valores.copy(), tau, signo * delta_sigma, sigma)
    obs = [o.model_copy(update={"value": float(v), "stream_id": "demo"}) for o, v in zip(serie, nuevos)]

    # El nivel "verdadero" que se ha inyectado (sin ruido), para dibujarlo:
    # se obtiene aplicando la misma inyección a una serie constante en mu0.
    nivel = INYECTORES[escenario](np.full(len(valores), mu0), tau, signo * delta_sigma, sigma)
    resultado = {"valores": [float(v) for v in nuevos], "nivel": [float(v) for v in nivel],
                 "tau": tau, "mu0": mu0, "sigma": sigma, "detectores": {}}
    for nombre, umbral in umbrales.items():
        det = fabricar_detector(nombre, umbral, mu0, sigma, direction, k_cusum, delta_page_hinkley)
        alarmas = det.procesar_serie(obs)
        if not alarmas:
            resultado["detectores"][nombre] = {"instante": None, "retardo": None,
                                               "lectura": "no alarma en todo el horizonte"}
            continue
        instante = alarmas[0].t + 1
        if instante <= tau:
            resultado["detectores"][nombre] = {"instante": instante, "retardo": None,
                                               "lectura": "falsa alarma ANTES del cambio"}
        else:
            resultado["detectores"][nombre] = {"instante": instante, "retardo": instante - tau,
                                               "lectura": f"detecta {instante - tau} meses después del cambio"}
    return resultado


def distribucion_retardos(
    obs_referencia: list[MetricObservation],
    umbrales: dict[str, float],
    k_cusum: float,
    delta_page_hinkley: float,
    escenario: str,
    delta_sigma: float,
    tau: int,
    horizonte: int,
    bootstrap_bloque: int,
    n_series: int,
    semilla_base: int,
) -> list[dict]:
    """Monte Carlo pequeño para el laboratorio: la DISTRIBUCIÓN del retardo,
    no solo su media.

    Repite demo_inyeccion con n_series semillas consecutivas y devuelve una
    fila por (serie, detector) con el retardo o con qué pasó si no hubo
    detección. Las tablas selladas dan la media sobre 1000 series; esto
    enseña la dispersión, que es lo que hace entender por qué un solo caso
    no prueba nada.
    """
    filas = []
    for i in range(n_series):
        r = demo_inyeccion(
            obs_referencia, umbrales, k_cusum, delta_page_hinkley, escenario,
            delta_sigma, tau, horizonte, bootstrap_bloque, semilla_base + i,
        )
        for nombre, info in r["detectores"].items():
            if info["instante"] is None:
                resultado = "no detecta"
            elif info["retardo"] is None:
                resultado = "falsa alarma antes de τ"
            else:
                resultado = "detecta"
            filas.append({"serie": i, "detector": nombre, "resultado": resultado,
                          "retardo_meses": info["retardo"]})
    return filas
