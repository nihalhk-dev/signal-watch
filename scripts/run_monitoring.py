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
  5. Mide el RETARDO sobre ruido real: inyecta una caída de tamaño conocido
     en un τ fijado sobre el bootstrap de la referencia (la única forma de
     medir retardo en una rama sin τ; ver evaluation/error_analysis.py).
  6. Guarda tres tablas selladas con la huella R7:
       outputs/tables/calibracion_<stream>.csv
       outputs/tables/alarmas_<stream>.csv
       outputs/tables/retardo_ruido_real_<stream>.csv
     y la figura oficial de la rama real (reporting/figures.py, R9):
       outputs/figures/rama_real_<stream>.png

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
    medir_retardo_con_inyeccion,
    ruido_empirico,
)
from signal_watch.gold.factor_metrics import cargar_config, ruta_stream
from signal_watch.gold.metric_stream import load_metric_stream
from signal_watch.ingest.french import NOMBRE_ZIP, carpeta_french
from signal_watch.monitoring.alarms import a_dataframe
from signal_watch.monitoring.engine import run_batch
from signal_watch.paths import PATHS
from signal_watch.reporting.figures import fig_rama_real

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
CLAVES_INYECCION = {
    "escenarios", "deltas_sigma", "tau_meses", "horizonte_meses", "n_series", "semilla",
}


def main(stream_id: str = "factor_hml_sharpe") -> None:
    cfg = cargar_config(stream_id)
    if "monitorizacion" not in cfg:
        raise KeyError(f"configs/streams/{stream_id}.yaml no tiene bloque 'monitorizacion'")
    mon = cfg["monitorizacion"]
    validate_keys(mon, CLAVES_MONITORIZACION, name=f"{stream_id}.yaml:monitorizacion")
    if "inyeccion" not in cfg:
        raise KeyError(f"configs/streams/{stream_id}.yaml no tiene bloque 'inyeccion'")
    iny = cfg["inyeccion"]
    validate_keys(iny, CLAVES_INYECCION, name=f"{stream_id}.yaml:inyeccion")
    semillas = {mon["semilla_calibracion"], mon["semilla_verificacion"], iny["semilla"]}
    if len(semillas) != 3:
        raise ValueError("Calibración, verificación e inyección necesitan semillas distintas (R4).")

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
                       **config_efectiva,
                       "inyeccion": {k: iny[k] for k in sorted(CLAVES_INYECCION)}}

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
    n_ref = len(referencia)
    print(f"  sobre {n_ref} valores reales solo puede tener ARL0 = {n_ref}/j (ver error_analysis.py).")
    for c in calib.values():
        desvio = (c.arl0_verificado - c.arl0_alcanzable) / c.arl0_alcanzable
        if abs(desvio) > 0.10:
            print(f"  AVISO {c.detector}: ARL0 verificado {c.arl0_verificado:.1f} frente a "
                  f"{c.arl0_alcanzable:.1f} ({desvio:+.0%}). Con una referencia finita el ARL0 va a")
            print("  saltos en el umbral y la bisección puede caer en el borde de uno. Se declara.")
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

    print("-" * 72)
    print("RETARDO SOBRE RUIDO REAL (caída inyectada en un τ conocido)")
    print("-" * 72)
    print(f"τ = mes {iny['tau_meses']}, horizonte {iny['horizonte_meses']} meses, "
          f"{iny['n_series']} series por celda. Umbrales: los calibrados arriba.", flush=True)
    puntos = medir_retardo_con_inyeccion(
        referencia, calib,
        k_cusum=float(mon["k_cusum"]),
        delta_page_hinkley=float(mon["delta_page_hinkley"]),
        escenarios=list(iny["escenarios"]),
        deltas_sigma=[float(d) for d in iny["deltas_sigma"]],
        tau=int(iny["tau_meses"]),
        horizonte=int(iny["horizonte_meses"]),
        n_series=int(iny["n_series"]),
        bootstrap_bloque=int(mon["bootstrap_bloque_meses"]),
        semilla=int(iny["semilla"]),
    )
    tabla_retardo = pd.DataFrame(
        [
            {
                "stream_id": stream_id, "detector": p.detector, "escenario": p.escenario,
                "delta_sigma": p.delta_sigma, "delta_sharpe": p.delta_sharpe,
                "arl1_meses": p.arl1, "arl1_ic_low": p.arl1_ic95[0],
                "arl1_ic_high": p.arl1_ic95[1], "n_streams": p.n_streams,
                "n_censurados": p.n_censurados, "n_excluidos_pre_tau": p.n_excluidos_pre_tau,
                "n_series": p.n_series, **huella,
            }
            for p in puntos
        ]
    )
    for escenario in iny["escenarios"]:
        sub = tabla_retardo[tabla_retardo["escenario"] == escenario]
        tabla = sub.pivot(index="detector", columns="delta_sigma", values="arl1_meses")
        tabla = tabla.reindex(list(calib))
        tabla.columns = [f"{d:g}σ ({d * r['sigma']:.2f} SR)" for d in tabla.columns]
        print(f"\n{escenario} — retardo medio en MESES desde el cambio:")
        print(tabla.round(1).to_string())
        cens = sub.pivot(index="detector", columns="delta_sigma", values="n_censurados")
        excl = sub.pivot(index="detector", columns="delta_sigma", values="n_excluidos_pre_tau")
        print(f"  censuradas por celda (de {iny['n_series']}): "
              + ", ".join(f"{d}: {int(cens.loc[d].max())}" for d in calib)
              + " (máximo entre magnitudes)")
        print(f"  excluidas por falsa alarma antes de τ: "
              + ", ".join(f"{d}: {int(excl.loc[d].min())}-{int(excl.loc[d].max())}" for d in calib))
    print("\n  'SR' = el tamaño del cambio en Sharpe anualizado.")
    if stream_id == "factor_hml_sharpe":
        print("  0,15σ ≈ el factor pasa a Sharpe cero; 0,25σ ≈ la caída media de los 2010.")
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
    ruta_retardo = destino / f"retardo_ruido_real_{stream_id}.csv"
    tabla_calib.to_csv(ruta_calib, index=False)
    a_dataframe(eventos).to_csv(ruta_alarmas, index=False)
    tabla_retardo.to_csv(ruta_retardo, index=False)

    # La figura oficial de la rama real: la dibuja reporting/figures.py (R9),
    # la guarda el script. Se construye desde las MISMAS tablas que se acaban
    # de guardar, así que figura y CSV no pueden contar cosas distintas.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    serie = pd.DataFrame(
        {"sharpe": [o.value for o in obs]},
        index=pd.to_datetime([o.timestamp for o in obs]),
    )
    fig = fig_rama_real(
        serie, a_dataframe(eventos), tabla_retardo,
        fin_calibracion=cfg["fin_calibracion"],
        arl0_objetivo=float(mon["arl0_objetivo_meses"]),
        esperadas_por_azar=esperadas,
        titulo=cfg.get("titulo_figura"),
    )
    ruta_figura = PATHS.ensure(PATHS.outputs_figures) / f"rama_real_{stream_id}.png"
    fig.savefig(ruta_figura, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print("-" * 72)
    print(f"Guardado: {ruta_calib}")
    print(f"Guardado: {ruta_alarmas}")
    print(f"Guardado: {ruta_retardo}")
    print(f"Guardado: {ruta_figura}")
    print(f"Huella:   config_hash={huella['config_hash']}  hash_datos={huella['hash_datos']}  "
          f"commit={huella['commit']}")
    print("\nRecordatorio: sin τ, ninguna de estas fechas es 'una detección'. Se leen")
    print("como 'la alarma cae en la ventana donde la literatura sitúa X'.")
    print("=" * 72)


if __name__ == "__main__":
    main(*sys.argv[1:])
