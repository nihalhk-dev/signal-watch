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
     Primero DENTRO de muestra: el ruido sale de los mismos meses que
     calibraron; es la comparación a igual tasa de falsas alarmas.
     Si la config trae `inyeccion.particion_tramo_meses`, lo repite FUERA DE
     MUESTRA: calibra con años alternos (mitad A) e inyecta sobre los otros
     (mitad B), y luego al revés. Ahí la pregunta es otra: ¿la tasa de
     falsas alarmas prometida aguanta en años que el umbral no ha visto?
  6. Guarda las tablas selladas con la huella R7:
       outputs/tables/calibracion_<stream>.csv
       outputs/tables/alarmas_<stream>.csv
       outputs/tables/retardo_ruido_real_<stream>.csv      (dentro de muestra)
       outputs/tables/retardo_fuera_muestra_<stream>.csv   (si hay partición)
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
    indices_de,
    medir_retardo_con_inyeccion,
    medir_retardo_fuera_de_muestra,
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
# Opcional: si está, el retardo se mide fuera de muestra (ver docstring).
CLAVE_PARTICION = "particion_tramo_meses"


def _fila_retardo(stream_id: str, p) -> dict:
    """Una fila de tabla de retardo. Mismas columnas que antes de añadir la
    prueba fuera de muestra, para que la app y la figura no cambien."""
    return {
        "stream_id": stream_id, "detector": p.detector, "escenario": p.escenario,
        "delta_sigma": p.delta_sigma, "delta_sharpe": p.delta_sharpe,
        "arl1_meses": p.arl1, "arl1_ic_low": p.arl1_ic95[0],
        "arl1_ic_high": p.arl1_ic95[1], "n_streams": p.n_streams,
        "n_censurados": p.n_censurados, "n_excluidos_pre_tau": p.n_excluidos_pre_tau,
        "n_series": p.n_series,
    }


def _imprimir_retardo(tabla, detectores, escenarios, n_series, sigma) -> None:
    for escenario in escenarios:
        sub = tabla[tabla["escenario"] == escenario]
        piv = sub.pivot(index="detector", columns="delta_sigma", values="arl1_meses")
        piv = piv.reindex(detectores)
        piv.columns = [f"{d:g}σ ({d * sigma:.2f} SR)" for d in piv.columns]
        print(f"\n{escenario} — retardo medio en MESES desde el cambio:")
        print(piv.round(1).to_string())
        cens = sub.pivot(index="detector", columns="delta_sigma", values="n_censurados")
        excl = sub.pivot(index="detector", columns="delta_sigma", values="n_excluidos_pre_tau")
        print(f"  censuradas por celda (de {n_series}): "
              + ", ".join(f"{d}: {int(cens.loc[d].max())}" for d in detectores)
              + " (máximo entre magnitudes)")
        print("  excluidas por falsa alarma antes de τ: "
              + ", ".join(f"{d}: {int(excl.loc[d].min())}-{int(excl.loc[d].max())}"
                          for d in detectores))


def main(stream_id: str = "factor_hml_sharpe") -> None:
    cfg = cargar_config(stream_id)
    if "monitorizacion" not in cfg:
        raise KeyError(f"configs/streams/{stream_id}.yaml no tiene bloque 'monitorizacion'")
    mon = cfg["monitorizacion"]
    validate_keys(mon, CLAVES_MONITORIZACION, name=f"{stream_id}.yaml:monitorizacion")
    if "inyeccion" not in cfg:
        raise KeyError(f"configs/streams/{stream_id}.yaml no tiene bloque 'inyeccion'")
    iny = cfg["inyeccion"]
    validate_keys({k: v for k, v in iny.items() if k != CLAVE_PARTICION},
                  CLAVES_INYECCION, name=f"{stream_id}.yaml:inyeccion")
    fuera_de_muestra = CLAVE_PARTICION in iny
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
                       "inyeccion": {k: iny[k] for k in sorted(iny)}}

    archivos_datos = [ruta, carpeta_french() / NOMBRE_ZIP]
    huella = huella_ejecucion(config_efectiva, archivos_datos)

    print("\nUmbrales calibrados (ARL0 medido en series de VERIFICACIÓN, no en las de calibrar):")
    print(f"  {'detector':<14}{'umbral':>9}{'alcanzable':>12}{'ARL0 verif.':>13}{'IC95':>16}"
          f"{'censuradas':>12}")
    for c in calib.values():
        ic = f"({c.arl0_ic95[0]:.0f}, {c.arl0_ic95[1]:.0f})"
        print(f"  {c.detector:<14}{c.umbral:>9.3f}{c.arl0_alcanzable:>12.1f}"
              f"{c.arl0_verificado:>13.1f}{ic:>16}{c.n_censurados:>7}/{c.n_series}")
    print("  'alcanzable' = objetivo, salvo en Shewhart: una regla de UNA observación sobre")
    print(f"  {len(referencia)} valores reales tiene el ARL0 a saltos; se toma el primer escalón que")
    print("  no es más estricto que el objetivo, medido en calibración (ver error_analysis.py).")
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
    comunes = dict(
        k_cusum=float(mon["k_cusum"]),
        delta_page_hinkley=float(mon["delta_page_hinkley"]),
        escenarios=list(iny["escenarios"]),
        deltas_sigma=[float(d) for d in iny["deltas_sigma"]],
        tau=int(iny["tau_meses"]),
        horizonte=int(iny["horizonte_meses"]),
        n_series=int(iny["n_series"]),
        semilla=int(iny["semilla"]),
    )
    print(f"τ = mes {iny['tau_meses']}, horizonte {iny['horizonte_meses']} meses, "
          f"{iny['n_series']} series por celda. Umbrales: los calibrados arriba.", flush=True)
    print(f"DENTRO DE MUESTRA: el ruido de inyección sale de los mismos {len(referencia)} meses")
    print("que calibraron. Es la comparación a IGUAL tasa de falsas alarmas.")
    puntos = medir_retardo_con_inyeccion(
        referencia, calib,
        bootstrap_bloque=int(mon["bootstrap_bloque_meses"]),
        **comunes,
    )
    tabla_retardo = pd.DataFrame([{**_fila_retardo(stream_id, p), **huella} for p in puntos])
    _imprimir_retardo(tabla_retardo, list(calib), iny["escenarios"], iny["n_series"], r["sigma"])

    tabla_fdm = None
    if fuera_de_muestra:
        print("\n" + "-" * 72)
        print("RETARDO FUERA DE MUESTRA (calibrar con unos años, inyectar en otros)")
        print("-" * 72)
        filas = []
        for invertir in (False, True):
            fdm = medir_retardo_fuera_de_muestra(
                referencia,
                arl0_objetivo=float(mon["arl0_objetivo_meses"]),
                bootstrap_bloque=int(mon["bootstrap_bloque_meses"]),
                bootstrap_longitud=int(mon["bootstrap_longitud_meses"]),
                bootstrap_n_series=int(mon["bootstrap_n_series"]),
                semilla_calibracion=int(mon["semilla_calibracion"]),
                semilla_verificacion=int(mon["semilla_verificacion"]),
                tramo_meses=int(iny[CLAVE_PARTICION]),
                invertir=invertir,
                **comunes,
            )
            n_c, n_i = len(indices_de(fdm.tramos_calibra)), len(indices_de(fdm.tramos_inyecta))
            print(f"\n{fdm.direccion}: calibra con {n_c} meses, inyecta sobre otros {n_i}; "
                  "ningún mes en los dos.")
            print(f"  mu0 {fdm.mu0_calibra:.3f} · sigma {fdm.sigma_calibra:.3f} en la mitad que "
                  f"calibra (referencia entera: {r['mu0']:.3f} · {r['sigma']:.3f})")
            print(f"  {'detector':<14}{'umbral':>9}{'ARL0 calibra':>14}{'ARL0 inyecta':>14}")
            for n, c in fdm.calibraciones.items():
                print(f"  {n:<14}{c.umbral:>9.3f}{c.arl0_verificado:>14.1f}"
                      f"{fdm.arl0_ruido_inyeccion[n]:>14.1f}")
            sub = pd.DataFrame([_fila_retardo(stream_id, p) for p in fdm.puntos])
            _imprimir_retardo(sub, list(calib), iny["escenarios"], iny["n_series"], r["sigma"])
            for p in fdm.puntos:
                c = fdm.calibraciones[p.detector]
                filas.append({
                    **_fila_retardo(stream_id, p),
                    "direccion": fdm.direccion,
                    "umbral": c.umbral,
                    "arl0_calibra": c.arl0_verificado,
                    "arl0_ruido_inyeccion": fdm.arl0_ruido_inyeccion[p.detector],
                    **huella,
                })
        tabla_fdm = pd.DataFrame(filas)
        print("\n  CÓMO LEER ESTO: fuera de muestra los detectores dejan de tener la misma")
        print("  tasa de falsas alarmas ('ARL0 inyecta'). Sus retardos ya NO se comparan")
        print("  como una carrera: el que salta a menudo 'detecta' pronto aunque no haya")
        print("  nada (mira sus excluidas antes de τ). Lo que responde esta prueba es la")
        print("  columna 'ARL0 inyecta': ¿la tasa prometida aguanta en años no vistos?")
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
    ruta_fdm = destino / f"retardo_fuera_muestra_{stream_id}.csv"
    tabla_calib.to_csv(ruta_calib, index=False)
    a_dataframe(eventos).to_csv(ruta_alarmas, index=False)
    tabla_retardo.to_csv(ruta_retardo, index=False)
    if tabla_fdm is not None:
        tabla_fdm.to_csv(ruta_fdm, index=False)

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
    if tabla_fdm is not None:
        print(f"Guardado: {ruta_fdm}")
    print(f"Guardado: {ruta_figura}")
    print(f"Huella:   config_hash={huella['config_hash']}  hash_datos={huella['hash_datos']}  "
          f"commit={huella['commit']}")
    print("\nRecordatorio: sin τ, ninguna de estas fechas es 'una detección'. Se leen")
    print("como 'la alarma cae en la ventana donde la literatura sitúa X'.")
    print("=" * 72)


if __name__ == "__main__":
    main(*sys.argv[1:])
