"""Monitoriza un stream real: calibra sobre la referencia y vigila el resto.

    python scripts/run_monitoring.py                      # factor_hml_sharpe
    python scripts/run_monitoring.py otro_stream_id

Qué hace, en orden:
  1. Carga la config del stream y el stream gold ya construido.
  2. Parte la serie en REFERENCIA (hasta `fin_calibracion`) y VIGILANCIA
     (todo lo posterior). La referencia solo sirve para calibrar; nunca se
     vigila. Es R4 llevada a una serie única.
  3. Calibra CUSUM, Page-Hinkley y Shewhart al mismo ARL0, por bootstrap
     de bloques de la referencia (ver evaluation/error_analysis.py).
  4. Recorre la vigilancia con cada detector (monitoring/engine.py).
  5. Guarda dos tablas selladas con la huella R7:
       outputs/tables/calibracion_<stream>.csv
       outputs/tables/alarmas_<stream>.csv

LEER ANTES DE INTERPRETAR LA SALIDA
    En datos reales no hay τ. Una alarma NO es "el sistema detectó X".
    La única frase permitida es: "la alarma cae en la ventana donde la
    literatura sitúa X". El retardo solo se mide en el experimento de
    inyección, donde τ lo fija quien inyecta.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date

import pandas as pd

from signal_watch.config import huella_ejecucion, validate_keys
from signal_watch.evaluation.error_analysis import (
    calibrar_en_ruido_real,
    fabricar_detector,
    ruido_empirico,
)
from signal_watch.gold.factor_metrics import cargar_config, ruta_stream
from signal_watch.gold.metric_stream import load_metric_stream
from signal_watch.ingest.french import NOMBRE_ZIP, carpeta_french
from signal_watch.monitoring.alarms import a_dataframe
from signal_watch.monitoring.engine import run_batch
from signal_watch.paths import PATHS

CLAVES_MONITORIZACION = {
    "arl0_objetivo_meses",
    "k_cusum",
    "delta_page_hinkley",
    "bootstrap_bloque_meses",
    "bootstrap_longitud_meses",
    "bootstrap_n_series",
    "semilla_calibracion",
    "semilla_verificacion",
}


def main(stream_id: str = "factor_hml_sharpe") -> None:
    cfg = cargar_config(stream_id)
    if "monitorizacion" not in cfg:
        raise KeyError(f"configs/streams/{stream_id}.yaml no tiene bloque 'monitorizacion'")
    mon = cfg["monitorizacion"]
    validate_keys(mon, CLAVES_MONITORIZACION, name=f"{stream_id}.yaml:monitorizacion")

    ruta = ruta_stream(stream_id)
    obs = load_metric_stream(ruta)

    corte = date.fromisoformat(cfg["fin_calibracion"])
    referencia = [o for o in obs if o.timestamp <= corte]
    vigilancia = [o for o in obs if o.timestamp > corte]
    if not referencia or not vigilancia:
        raise ValueError("La partición referencia/vigilancia ha dejado un lado vacío.")

    print("=" * 72)
    print(f"MONITORIZACIÓN — {stream_id}")
    print("=" * 72)
    print(f"Referencia: {referencia[0].timestamp} -> {referencia[-1].timestamp}  "
          f"({len(referencia)} meses)  — solo calibra, NO se vigila")
    print(f"Vigilancia: {vigilancia[0].timestamp} -> {vigilancia[-1].timestamp}  "
          f"({len(vigilancia)} meses)")

    r = ruido_empirico(referencia)
    print("\nRuido de la referencia (lo que el bootstrap reproduce):")
    print(f"  mu0 {r['mu0']:.3f} · sigma {r['sigma']:.3f} · rho(1) {r['rho_lag1']:+.3f} · "
          f"asimetría {r['asimetria']:+.2f} · curtosis de exceso {r['curtosis_exceso']:+.2f}")
    if r["curtosis_exceso"] > 0.5:
        print("  (colas más gordas que una normal: una calibración gaussiana dispararía")
        print("   más de lo prometido; el bootstrap las conserva)")
    else:
        print("  (colas parecidas a las de una normal en esta métrica: el bootstrap no")
        print("   supone nada sobre la forma, así que sirve igual; conserva además la")
        print("   autocorrelación dentro de cada bloque)")

    print(f"\nCalibrando al ARL0 objetivo = {mon['arl0_objetivo_meses']} meses "
          f"({mon['bootstrap_n_series']} series x {mon['bootstrap_longitud_meses']} meses, "
          "x2 conjuntos)... puede tardar un par de minutos.", flush=True)
    calib, config_efectiva, arl0_3sigma = calibrar_en_ruido_real(
        referencia,
        arl0_objetivo=float(mon["arl0_objetivo_meses"]),
        k_cusum=float(mon["k_cusum"]),
        delta_page_hinkley=float(mon["delta_page_hinkley"]),
        bootstrap_bloque=int(mon["bootstrap_bloque_meses"]),
        bootstrap_longitud=int(mon["bootstrap_longitud_meses"]),
        bootstrap_n_series=int(mon["bootstrap_n_series"]),
        semilla_calibracion=int(mon["semilla_calibracion"]),
        semilla_verificacion=int(mon["semilla_verificacion"]),
    )
    config_efectiva = {"stream_id": stream_id, "fin_calibracion": cfg["fin_calibracion"],
                       **config_efectiva}

    archivos_datos = [ruta, carpeta_french() / NOMBRE_ZIP]
    huella = huella_ejecucion(config_efectiva, archivos_datos)

    print("\nUmbrales calibrados (ARL0 medido en series de VERIFICACIÓN, no en las de calibrar):")
    print(f"  {'detector':<14}{'umbral':>9}{'alcanzable':>12}{'ARL0 verif.':>13}{'IC95':>16}"
          f"{'censuradas':>12}")
    for c in calib.values():
        ic = f"({c.arl0_ic95[0]:.0f}, {c.arl0_ic95[1]:.0f})"
        print(f"  {c.detector:<14}{c.umbral:>9.3f}{c.arl0_alcanzable:>12.1f}"
              f"{c.arl0_verificado:>13.1f}{ic:>16}{c.n_censurados:>7}/{c.n_series}")
    print("  'alcanzable' = objetivo, salvo en Shewhart: una regla de UNA observación")
    print("  sobre 330 valores reales solo puede tener ARL0 = 330/j (ver error_analysis.py).")
    print(f"\n  Dato informativo — el 3σ de manual SIN calibrar tendría ARL0 ≈ "
          f"{arl0_3sigma:.0f} meses sobre este mismo ruido.")

    # Los MISMOS mu0 y sigma con los que se calibró (ruido_empirico hace el
    # mismo cálculo dentro de calibrar_en_ruido_real). Los de config_efectiva
    # están redondeados para el hash: sirven para identificar, no para operar.
    mu0, sigma = r["mu0"], r["sigma"]
    direction = referencia[0].direction
    eventos = []
    for nombre, c in calib.items():
        det = fabricar_detector(nombre, c.umbral, mu0, sigma, direction,
                                float(mon["k_cusum"]), float(mon["delta_page_hinkley"]))
        eventos.extend(run_batch(vigilancia, det, nombre, c.umbral, huella))

    print("\n" + "-" * 72)
    print("ALARMAS EN LA VIGILANCIA")
    print("-" * 72)
    esperadas = len(vigilancia) / mon["arl0_objetivo_meses"]
    print(f"Si no hubiera NINGÚN cambio real, cada detector daría de media ~{esperadas:.1f} "
          f"falsas alarmas en {len(vigilancia)} meses.\n")
    for nombre in calib:
        propios = [e for e in eventos if e.detector == nombre]
        print(f"{nombre}: {len(propios)} alarmas")
        for e in propios:
            print(f"   #{e.n_alarma:<2} {e.fecha}  Sharpe del mes {e.valor:+7.2f}  "
                  f"estadístico {e.estadistico:7.2f}")
        por_decada = Counter((e.fecha.year // 10) * 10 for e in propios)
        if por_decada:
            print("   por década: " + ", ".join(f"{d}s: {n}" for d, n in sorted(por_decada.items())))
        print()

    tabla_calib = pd.DataFrame(
        [
            {
                "stream_id": stream_id, "detector": c.detector, "umbral": c.umbral,
                "arl0_objetivo": mon["arl0_objetivo_meses"],
                "arl0_alcanzable": c.arl0_alcanzable,
                "arl0_verificado": c.arl0_verificado,
                "arl0_ic_low": c.arl0_ic95[0], "arl0_ic_high": c.arl0_ic95[1],
                "n_censurados": c.n_censurados, "n_series": c.n_series,
                "arl0_3sigma_clasico": arl0_3sigma, **huella,
            }
            for c in calib.values()
        ]
    )
    destino = PATHS.ensure(PATHS.outputs_tables)
    ruta_calib = destino / f"calibracion_{stream_id}.csv"
    ruta_alarmas = destino / f"alarmas_{stream_id}.csv"
    tabla_calib.to_csv(ruta_calib, index=False)
    a_dataframe(eventos).to_csv(ruta_alarmas, index=False)

    print("-" * 72)
    print(f"Guardado: {ruta_calib}")
    print(f"Guardado: {ruta_alarmas}")
    print(f"Huella:   config_hash={huella['config_hash']}  hash_datos={huella['hash_datos']}  "
          f"commit={huella['commit']}")
    print("\nRecordatorio: sin τ, ninguna de estas fechas es 'una detección'. Se leen")
    print("como 'la alarma cae en la ventana donde la literatura sitúa X'.")
    print("=" * 72)


if __name__ == "__main__":
    main(*sys.argv[1:])
