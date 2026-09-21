"""RQ2 — ¿Era HML alfa de verdad, o un Sharpe inflado por suerte o por búsqueda?

ESTE MÓDULO CONTESTA UNA PREGUNTA DISTINTA DE LA DE LOS DETECTORES
    · PSR / DSR (aquí):   "¿era alfa?"      — sobre los RETORNOS de la estrategia
    · CUSUM y compañía:   "¿se murió?"      — sobre la MÉTRICA que se vigila
    No se mezclan. Un factor que nunca fue alfa no tiene nada que "morir";
    uno que lo fue puede morir después. Son dos ejes, dos resultados.

PASO 1 — PSR (Bailey y López de Prado, 2012)
    Un Sharpe medido tiene error. Para retornos no normales (Mertens, 2002):

        SE(SR) = sqrt( (1 − γ3·SR + (γ4 − 1)/4 · SR²) / (T − 1) )

    con γ3 = asimetría y γ4 = curtosis (NO de exceso), SR en unidades del
    periodo. Con retornos normales (γ3 = 0, γ4 = 3) queda (1 + SR²/2)/(T−1):
    la fórmula de Lo que ya usa processing/factor_returns.py. Y:

        PSR(SR*) = Φ( (SR − SR*) / SE )

    "Probabilidad de que el Sharpe verdadero supere SR*, dado lo medido."

PASO 2 — DSR (Bailey y López de Prado, 2014)
    Si se prueban N estrategias de puro ruido y se elige la mejor, esa
    mejor tiene Sharpe positivo por selección. Su valor esperado es

        SR0 = sqrt(V) · [ (1 − γe)·Φ⁻¹(1 − 1/N) + γe·Φ⁻¹(1 − 1/(N·e)) ]

    con γe ≈ 0,5772 (Euler-Mascheroni) y V ≈ 1/(T − 1), la varianza de un
    Sharpe estimado cuando el verdadero es 0. El DSR es el PSR con SR0 como
    listón en lugar de 0.

EL PROBLEMA HONESTO: NADIE SABE N
    Se da un rango, no un número: 1 (una sola idea), 10, 100 y 316, los
    factores publicados que contaron Harvey, Liu y Zhu (2016). Matiz: HML
    (1992) es de los PRIMEROS; los 316 no estaban probados cuando se
    descubrió, así que N = 316 castiga de más. Si lo supera, es robusto.

EL CASTIGO SOLO SE APLICA A LA MUESTRA DE DESCUBRIMIENTO
    El DSR corrige la BÚSQUEDA, y la búsqueda ocurrió antes de publicar. De
    1991 en adelante HML es un factor fijo que nadie volvió a elegir: es
    una muestra FUERA DE MUESTRA, y ahí N = 1 (PSR frente a 0). Aplicarle el
    castigo de 316 pruebas a la muestra posterior sería contar una búsqueda
    que no ocurrió en ese periodo.

POR QUÉ RETORNOS MENSUALES
    El DSR se aplica a la estrategia (sus retornos), no a la métrica que
    vigilan los detectores. Mensuales, compuestos desde los diarios, porque
    es la frecuencia de la literatura y evita la microestructura diaria.

Uso:
    python -m signal_watch.evaluation.deflated_sharpe
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from signal_watch.config import huella_ejecucion
from signal_watch.ingest.french import NOMBRE_ZIP, cargar_factores_diarios, carpeta_french
from signal_watch.paths import PATHS

EULER_MASCHERONI = 0.5772156649015329
NS_PRUEBAS = (1, 10, 100, 316)  # 316 = Harvey, Liu y Zhu (2016)
# (inicio, fin, ¿es la muestra donde se DESCUBRIÓ el factor?)
VENTANAS = {
    # ≈ la muestra original de Fama y French (1993), que llegaba a 1991
    "1963-1990 (descubrimiento)": ("1963-07-01", "1990-12-31", True),
    # fuera de muestra: sin búsqueda, N = 1
    "1991-2026 (fuera de muestra)": ("1991-01-01", "2026-12-31", False),
}
MIN_DIAS_POR_MES = 15


def retornos_mensuales(df_diario: pd.DataFrame, factor: str = "hml") -> pd.Series:
    """Retorno mensual compuesto: prod(1 + r_diario) − 1.

    HML ya es un retorno de exceso (cartera larga-corta de inversión neta
    cero): no se le resta rf. Meses con menos de 15 días se descartan, con
    el mismo criterio que la métrica mensual.
    """
    r = df_diario[factor].dropna()
    grupos = r.groupby(pd.Grouper(freq="ME"))
    compuesto = grupos.apply(lambda x: float(np.prod(1.0 + x.to_numpy()) - 1.0))
    n = grupos.size()
    return compuesto[n >= MIN_DIAS_POR_MES]


def momentos(r: pd.Series) -> dict[str, float]:
    """Sharpe por periodo, asimetría y curtosis (NO de exceso) de una serie."""
    x = r.to_numpy(dtype=float)
    t = len(x)
    media, sd = x.mean(), x.std(ddof=1)
    c = x - media
    m2 = (c**2).mean()
    return {
        "T": t,
        "sr": float(media / sd),
        "asimetria": float((c**3).mean() / m2**1.5),
        "curtosis": float((c**4).mean() / m2**2),  # 3 en una normal
    }


def error_estandar_sharpe(sr: float, t: int, asimetria: float, curtosis: float) -> float:
    """SE del Sharpe estimado, corregido por no normalidad (Mertens, 2002)."""
    varianza = (1.0 - asimetria * sr + (curtosis - 1.0) / 4.0 * sr**2) / (t - 1)
    return math.sqrt(varianza)


def psr(sr: float, sr_ref: float, t: int, asimetria: float, curtosis: float) -> float:
    """Probabilistic Sharpe Ratio: P(SR verdadero > sr_ref | lo medido)."""
    return float(norm.cdf((sr - sr_ref) / error_estandar_sharpe(sr, t, asimetria, curtosis)))


def sr0_maximo_esperado(n_pruebas: int, t: int) -> float:
    """Sharpe esperado de la MEJOR de n estrategias de puro ruido.

    Con n = 1 no hay selección y el listón es 0.
    """
    if n_pruebas <= 1:
        return 0.0
    v = 1.0 / (t - 1)
    return math.sqrt(v) * (
        (1 - EULER_MASCHERONI) * norm.ppf(1 - 1 / n_pruebas)
        + EULER_MASCHERONI * norm.ppf(1 - 1 / (n_pruebas * math.e))
    )


def tabla_rq2(factor: str = "hml") -> pd.DataFrame:
    """Una fila por (ventana, N): Sharpe, momentos, listón SR0, PSR y DSR."""
    mensuales = retornos_mensuales(cargar_factores_diarios(), factor)
    filas = []
    for nombre, (ini, fin, descubrimiento) in VENTANAS.items():
        r = mensuales.loc[ini:fin]
        m = momentos(r)
        psr0 = psr(m["sr"], 0.0, m["T"], m["asimetria"], m["curtosis"])
        for n in (NS_PRUEBAS if descubrimiento else (1,)):
            sr0 = sr0_maximo_esperado(n, m["T"])
            filas.append(
                {
                    "factor": factor,
                    "ventana": nombre,
                    "muestra_descubrimiento": descubrimiento,
                    "inicio": str(r.index.min().date()),
                    "fin": str(r.index.max().date()),
                    "T_meses": m["T"],
                    "sharpe_anual": m["sr"] * math.sqrt(12),
                    "asimetria": m["asimetria"],
                    "curtosis": m["curtosis"],
                    "psr_vs_0": psr0,
                    "n_pruebas": n,
                    "sr0_anual": sr0 * math.sqrt(12),
                    "dsr": psr(m["sr"], sr0, m["T"], m["asimetria"], m["curtosis"]),
                }
            )
    return pd.DataFrame(filas)


def main(factor: str = "hml") -> None:
    tabla = tabla_rq2(factor)

    config = {
        "factor": factor,
        "frecuencia": "mensual_compuesta",
        "min_dias_por_mes": MIN_DIAS_POR_MES,
        "ventanas": {k: [v[0], v[1], v[2]] for k, v in VENTANAS.items()},
        "n_pruebas": list(NS_PRUEBAS),
        "formula_se": "mertens_2002",
        "varianza_sr_bajo_h0": "1/(T-1)",
    }
    huella = huella_ejecucion(config, [carpeta_french() / NOMBRE_ZIP])
    for k, v in huella.items():
        tabla[k] = v

    print("=" * 74)
    print(f"RQ2 — ¿ERA {factor.upper()} ALFA DE VERDAD?  (PSR / DSR sobre retornos mensuales)")
    print("=" * 74)
    for nombre, sub in tabla.groupby("ventana", sort=False):
        f = sub.iloc[0]
        print(f"\n{nombre}:  {f['inicio']} → {f['fin']}  ({f['T_meses']} meses)")
        print(f"  Sharpe anualizado {f['sharpe_anual']:+.2f} · asimetría {f['asimetria']:+.2f} · "
              f"curtosis {f['curtosis']:.2f} (una normal tendría 3)")
        print(f"  PSR frente a 0: {f['psr_vs_0']:.4f}   ← P(el Sharpe verdadero es > 0)")
        if not f["muestra_descubrimiento"]:
            print("  Fuera de muestra: no hubo búsqueda en este periodo, así que N = 1")
            print("  y el DSR coincide con el PSR frente a 0.")
            continue
        print(f"  {'N pruebas':>10}{'listón SR0 (anual)':>22}{'DSR':>10}")
        for _, fila in sub.iterrows():
            print(f"  {fila['n_pruebas']:>10}{fila['sr0_anual']:>22.3f}{fila['dsr']:>10.4f}")

    print("\nLectura: DSR ≥ 0,95 = supera, con 95% de confianza, lo que habría sacado")
    print("la MEJOR de N estrategias de puro ruido. N = 316 (Harvey-Liu-Zhu) castiga de")
    print("más a HML, que es anterior a casi todos esos factores.")
    print("Recordatorio: esto contesta '¿era alfa?'. '¿Se murió?' lo contestan los detectores.")

    destino = PATHS.ensure(PATHS.outputs_tables) / f"deflated_sharpe_{factor}.csv"
    tabla.to_csv(destino, index=False)
    print(f"\nGuardado: {destino}")
    print(f"Huella:   config_hash={huella['config_hash']}  hash_datos={huella['hash_datos']}  "
          f"commit={huella['commit']}")
    print("=" * 74)


if __name__ == "__main__":
    main()
