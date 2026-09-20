"""scripts/run_evaluation.py

Corre la evaluación completa sobre el banco sintético real y produce:
  · outputs/tables/curvas_retardo.csv  — tabla larga, una fila por
    (metrica, detector, punto de operacion, escenario, delta), SELLADA
    con la huella de reproducibilidad (R7)
  · outputs/figures/retardo_vs_magnitud_{auc,psi}.png — la figura central

Las figuras se generan a ARL0 IGUALADO: para cada detector se elige el
punto de operación cuyo ARL0 medido está más cerca del de 3-sigma. Sin
eso, el detector al que se le permiten más falsas alarmas siempre parece
el más rápido, y la comparación no significa nada.

Cada fila del CSV lleva cuatro columnas de trazabilidad (R7):
  · config_hash  — los parámetros del análisis, tomados de la config
    EFECTIVA que devuelve construir_curvas_para_metrica (no de un
    diccionario escrito aquí, que podría desincronizarse en silencio).
  · hash_datos   — el contenido real de los cuatro Parquet de entrada.
    Captura de una vez réplicas, semillas y cualquier cambio en el
    generador, sin tener que enumerarlos.
  · commit       — el commit de git que produjo la tabla.
  · generado_en  — cuándo (UTC).

Con ese par de hashes, la tabla es reproducible: mismos dos hashes =
misma tabla, necesariamente.
"""

from pathlib import Path

import pandas as pd

from signal_watch.config import huella_ejecucion
from signal_watch.evaluation.delay_curves import (
    construir_curvas_para_metrica,
    seleccionar_punto_comparable,
)
from signal_watch.paths import PATHS
from signal_watch.reporting.figures import fig_retardo_vs_magnitud

RUTAS = {
    "calib_obs": PATHS.data_gold_synthetic / "calibracion.parquet",
    "calib_gt": PATHS.data_gold_synthetic / "calibracion_ground_truth.parquet",
    "eval_obs": PATHS.data_gold_synthetic / "evaluacion.parquet",
    "eval_gt": PATHS.data_gold_synthetic / "evaluacion_ground_truth.parquet",
}

filas_csv = []

for tipo in ["auc", "psi"]:
    print(f"\n{'='*70}\n{tipo.upper()}\n{'='*70}")
    puntos, config_efectiva = construir_curvas_para_metrica(
        tipo_metrica=tipo,
        ruta_calibracion_obs=RUTAS["calib_obs"],
        ruta_calibracion_gt=RUTAS["calib_gt"],
        ruta_evaluacion_obs=RUTAS["eval_obs"],
        ruta_evaluacion_gt=RUTAS["eval_gt"],
        niveles_arl0_objetivo=[20, 30, 50, 70, 90],
    )

    huella = huella_ejecucion(config_efectiva, list(RUTAS.values()))
    print(
        f"  huella R7: config={huella['config_hash']} "
        f"datos={huella['hash_datos']} commit={huella['commit']}",
        flush=True,
    )

    for nombre, lista in puntos.items():
        for p in lista:
            filas_csv.append({
                "tipo_metrica": tipo,
                "detector": nombre,
                "umbral": p.parametro_umbral,
                "escenario": p.escenario,
                "delta_sigma": p.delta_sigma,
                "arl0": p.arl0,
                "arl0_ic_low": p.arl0_ic95[0], "arl0_ic_high": p.arl0_ic95[1],
                "arl0_censurados": p.arl0_n_censurados,
                "arl0_n_streams": p.arl0_n_streams,
                "arl1": p.arl1,
                "arl1_ic_low": p.arl1_ic95[0], "arl1_ic_high": p.arl1_ic95[1],
                "arl1_censurados": p.arl1_n_censurados,
                "arl1_n_streams": p.arl1_n_streams,
                "arl1_excluidos_pre_tau": p.arl1_n_excluidos,
                **huella,  # config_hash, commit, hash_datos, generado_en
            })

df = pd.DataFrame(filas_csv)
out_csv = Path("outputs/tables/curvas_retardo.csv")
out_csv.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out_csv, index=False)

# ── Resumen legible, a ARL0 igualado ─────────────────────────────────
for tipo in ["auc", "psi"]:
    d_punto, ref = seleccionar_punto_comparable(df, tipo)
    print(f"\n{'='*78}")
    print(f"RESUMEN {tipo.upper()} — retardo (ARL1) a ARL0 igualado ≈ {ref:.0f}")
    print(f"{'='*78}")
    for escenario in ["salto", "deriva", "cambio_varianza"]:
        e = d_punto[d_punto["escenario"] == escenario]
        if e.empty:
            continue
        print(f"\n  escenario: {escenario}")
        pivot = e.pivot_table(
            index="delta_sigma", columns="detector", values="arl1", aggfunc="first"
        )
        print(pivot.to_string(float_format=lambda x: f"{x:7.1f}"))

# ── Figuras ──────────────────────────────────────────────────────────
print(f"\n{'='*78}\nFIGURAS\n{'='*78}")
for tipo in ["auc", "psi"]:
    d_punto, ref = seleccionar_punto_comparable(df, tipo)
    # en AUC, cambio_varianza ignora delta_sigma (usa factor_varianza fijo),
    # asi que las cinco columnas de delta son replicas de la misma condicion
    notas = ({"cambio_varianza": "δ no aplica: la media no se mueve"}
             if tipo == "auc" else None)
    fig = fig_retardo_vs_magnitud(d_punto, tipo, ref, notas=notas)
    out_fig = Path("outputs/figures") / f"retardo_vs_magnitud_{tipo}.png"
    out_fig.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_fig, dpi=150, metadata={"Date": None}, bbox_inches="tight")
    print(f"  {out_fig}  (ARL0 referencia = {ref:.1f})")

print(f"\nOK: tabla larga en {out_csv} ({len(df)} filas)")
print(f"    trazabilidad: {df['config_hash'].nunique()} config_hash distintos "
      f"(uno por metrica), hash_datos={df['hash_datos'].iloc[0]}")