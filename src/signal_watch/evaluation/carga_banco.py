"""Carga el banco de pruebas REAL desde disco y lo reagrupa en streams
individuales, listos para evaluation/delay_curves.py.

data/gold/synthetic/evaluacion.parquet tiene TODAS las observaciones
de TODOS los streams en una tabla plana (una fila por observación).
Este módulo las reagrupa por stream_id, y separa los streams en dos
grupos según su ground truth:

  · streams_sin_cambio: los del escenario "sin_cambio" (tau=None) ->
    van a evaluation.arl.medir_arl0()
  · streams_con_cambio: el resto (tau conocido) -> van a
    evaluation.arl.medir_arl1()

Esta separación NO es una elección arbitraria: es exactamente la
distinción que necesitan medir_arl0/medir_arl1 (ver arl.py), y que
existe porque el banco de pruebas sintético fue diseñado desde el
principio (build_synthetic.py) para tener ambos tipos de streams.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from signal_watch.gold.metric_stream import load_ground_truth, load_metric_stream
from signal_watch.gold.schemas import MetricObservation


@dataclass(frozen=True)
class BancoDePruebas:
    """El banco de pruebas ya cargado y organizado, listo para evaluar.

    streams_sin_cambio: lista de streams (cada uno, una lista de
        MetricObservation) del escenario "sin_cambio".
    streams_con_cambio: lista de streams con cambio real.
    ground_truths_con_cambio: el GroundTruth de cada stream en
        streams_con_cambio, EN EL MISMO ORDEN (índice a índice) —
        así medir_arl1() puede emparejarlos directamente.
    """

    streams_sin_cambio: list[list[MetricObservation]]
    streams_con_cambio: list[list[MetricObservation]]
    ground_truths_con_cambio: list

    @property
    def n_streams_total(self) -> int:
        return len(self.streams_sin_cambio) + len(self.streams_con_cambio)


def cargar_banco(
    ruta_observaciones: Path | str,
    ruta_ground_truth: Path | str,
) -> BancoDePruebas:
    """Carga y reagrupa el banco de pruebas real desde dos archivos
    Parquet (observaciones planas + ground truth planas), producidos
    por scripts/build_synthetic.py.

    Devuelve un BancoDePruebas ya separado en los dos grupos que
    necesita evaluation/arl.py — no hace falta que quien llame a esto
    sepa nada sobre cómo se organizaba la tabla plana original.
    """
    observaciones = load_metric_stream(ruta_observaciones)
    ground_truths = load_ground_truth(ruta_ground_truth)

    # indexar los ground truths por stream_id, para emparejar rápido
    gt_por_stream = {gt.stream_id: gt for gt in ground_truths}

    # reagrupar las observaciones planas por stream_id, PRESERVANDO
    # el orden temporal dentro de cada stream (los Parquet no garantizan
    # el orden de filas, así que se ordena explícitamente por t)
    obs_por_stream: dict[str, list[MetricObservation]] = {}
    for obs in observaciones:
        obs_por_stream.setdefault(obs.stream_id, []).append(obs)

    for stream_id in obs_por_stream:
        obs_por_stream[stream_id].sort(key=lambda o: o.t)

    # verificar que todo stream tiene su ground truth (si no, algo se
    # desincronizó entre los dos archivos, y es mejor fallar aquí, alto
    # y claro, que silenciosamente ignorar streams huérfanos)
    stream_ids_obs = set(obs_por_stream.keys())
    stream_ids_gt = set(gt_por_stream.keys())
    faltantes_en_gt = stream_ids_obs - stream_ids_gt
    if faltantes_en_gt:
        raise ValueError(
            f"{len(faltantes_en_gt)} streams tienen observaciones pero no "
            f"ground truth (ejemplo: {sorted(faltantes_en_gt)[:3]}). "
            "Los archivos de observaciones y ground truth no están sincronizados."
        )

    streams_sin_cambio: list[list[MetricObservation]] = []
    streams_con_cambio: list[list[MetricObservation]] = []
    ground_truths_con_cambio: list = []

    for stream_id, obs_lista in obs_por_stream.items():
        gt = gt_por_stream[stream_id]
        if gt.tau is None:
            streams_sin_cambio.append(obs_lista)
        else:
            streams_con_cambio.append(obs_lista)
            ground_truths_con_cambio.append(gt)

    return BancoDePruebas(
        streams_sin_cambio=streams_sin_cambio,
        streams_con_cambio=streams_con_cambio,
        ground_truths_con_cambio=ground_truths_con_cambio,
    )


def filtrar_por_metrica(banco: BancoDePruebas, tipo_metrica: str) -> BancoDePruebas:
    """Filtra un banco para quedarse solo con los streams de un tipo
    de métrica ("auc" o "psi"), identificado por el prefijo del
    stream_id (p.ej. "sint_eval_auc_..." vs "sint_eval_psi_...").

    Útil porque AUC y PSI usan direcciones distintas (lower_is_worse
    vs higher_is_worse) y normalmente se evalúan por separado.
    """
    marcador = f"_{tipo_metrica}_"

    sin_cambio_filtrado = [
        s for s in banco.streams_sin_cambio if marcador in s[0].stream_id
    ]

    con_cambio_filtrado = []
    gt_filtrado = []
    for stream, gt in zip(banco.streams_con_cambio, banco.ground_truths_con_cambio):
        if marcador in stream[0].stream_id:
            con_cambio_filtrado.append(stream)
            gt_filtrado.append(gt)

    return BancoDePruebas(
        streams_sin_cambio=sin_cambio_filtrado,
        streams_con_cambio=con_cambio_filtrado,
        ground_truths_con_cambio=gt_filtrado,
    )
    
import re

# El stream_id lo construye build_synthetic.py como
#   f"{prefijo}_{tipo_metrica}_{escenario}_d{delta:.1f}_r{replica:03d}"
# p.ej. "sint_eval_auc_cambio_varianza_d1.5_r007".
# Se extrae delta con expresión regular y NO partiendo por "_", porque
# el nombre del escenario puede llevar guion bajo dentro
# ("cambio_varianza") y partir por "_" daría un resultado equivocado.
_PATRON_DELTA = re.compile(r"_d(\d+\.\d+)_r")


def extraer_delta(stream_id: str) -> float | None:
    """Saca la magnitud delta_sigma del nombre del stream, o None si
    el nombre no sigue el patrón esperado."""
    m = _PATRON_DELTA.search(stream_id)
    return float(m.group(1)) if m else None


def estratos_con_cambio(
    banco: BancoDePruebas,
) -> dict[tuple[str, float], tuple[list, list]]:
    """Parte los streams CON cambio en estratos (escenario, delta_sigma).

    Por qué esto es necesario y no un lujo: un ARL1 que promedia los
    tres escenarios y las cinco magnitudes en un solo número no mide
    el rendimiento de un detector — mide la MEZCLA concreta de
    escenarios del banco. Como CUSUM y 3-sigma tienen perfiles opuestos
    (CUSUM gana en derivas pequeñas, 3-sigma en saltos grandes y en
    cambios de varianza donde CUSUM es ciego por construcción), el
    promedio agrupado puede invertir el orden real entre detectores.
    Estratificar es lo que permite decir "funciona bien AQUÍ y flojea
    ALLÁ" en vez de una media que no describe ningún caso.

    Devuelve {(escenario, delta): (streams, ground_truths)}.
    """
    grupos: dict[tuple[str, float], tuple[list, list]] = {}
    for stream, gt in zip(banco.streams_con_cambio, banco.ground_truths_con_cambio):
        delta = extraer_delta(stream[0].stream_id)
        clave = (gt.escenario, delta if delta is not None else float("nan"))
        if clave not in grupos:
            grupos[clave] = ([], [])
        grupos[clave][0].append(stream)
        grupos[clave][1].append(gt)
    return grupos