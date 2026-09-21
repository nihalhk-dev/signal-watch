"""Motor de monitorización: recorre un stream con un detector y emite alarmas.

Diferencia clave con el banco sintético:

    En `evaluation/` cada serie tiene UN cambio en un τ conocido, y el
    detector se para en la primera alarma (`Detector.procesar_serie`): lo
    que se mide es cuánto tardó en ver ESE cambio.

    En monitorización real la serie es larga, puede tener varios cambios de
    régimen, y nadie sabe dónde. Así que tras cada alarma el detector se
    REINICIA y sigue vigilando. Es la práctica estándar de control
    estadístico de procesos ("restart after signal"): en producción, una
    alarma se atiende, se revisa el modelo, y el monitor vuelve a empezar
    desde cero con la evidencia a cero.

    Consecuencia que hay que saber leer: si el régimen malo persiste, el
    detector volverá a alarmar al cabo de un tiempo. Varias alarmas seguidas
    no son varios cambios; son el mismo régimen confirmándose. Por eso cada
    evento lleva su número de orden, y la lectura se hace por ventanas.

Responsabilidad única: recorrer, actualizar, emitir. No calibra (eso es
`evaluation/error_analysis.py`), no decide un veredicto de negocio y no
explica causas.

Lo que hay aquí del manual y lo que no: el manual preveía un modo
incremental con estado persistido en base de datos. La base de datos está
fuera del alcance del proyecto, así que solo existe el modo batch.
"""

from __future__ import annotations

from signal_watch.detectors.base import Detector
from signal_watch.gold.metric_stream import to_detector_view
from signal_watch.gold.schemas import MetricObservation
from signal_watch.monitoring.alarms import AlarmEvent


def run_batch(
    observaciones: list[MetricObservation],
    detector: Detector,
    nombre_detector: str,
    umbral: float,
    huella: dict[str, str],
) -> list[AlarmEvent]:
    """Recorre el stream en orden y devuelve TODAS las alarmas.

    `huella` es la de `config.huella_ejecucion()`: se copia en cada evento
    para que cada alarma sea reproducible por sí sola.

    Todo entra por `to_detector_view()`, la puerta única de la muralla: el
    motor no le pasa al detector nada que no haya cruzado esa puerta.
    """
    vista = to_detector_view(observaciones)
    if not vista:
        return []
    stream_id = vista[0].stream_id

    detector.reset()
    eventos: list[AlarmEvent] = []

    for obs in vista:
        alarma = detector.update(obs)
        if alarma is None:
            continue
        # Se toman t, fecha y valor de la OBSERVACIÓN que disparó, no de
        # alarma.t: así el evento es correcto aunque un detector numerase
        # sus alarmas con un contador interno en vez de con obs.t.
        eventos.append(
            AlarmEvent(
                stream_id=stream_id,
                detector=nombre_detector,
                t=obs.t,
                fecha=obs.timestamp,
                valor=obs.value,
                estadistico=float(alarma.estadistico),
                umbral=float(umbral),
                n_alarma=len(eventos) + 1,
                config_hash=huella["config_hash"],
                commit=huella["commit"],
                hash_datos=huella["hash_datos"],
            )
        )
        detector.reset()  # restart after signal: la evidencia vuelve a cero

    return eventos