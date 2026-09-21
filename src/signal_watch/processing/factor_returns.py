"""De retornos diarios de factores a una métrica de rendimiento por periodo.

Qué produce: para cada mes, el **Sharpe anualizado** del factor, con su
error estándar y el número de días hábiles con que se calculó.

Es el análogo exacto de lo que hace la rama de crédito con el AUC:

    | rama     | value              | value_se            | n_obs           |
    |----------|--------------------|---------------------|-----------------|
    | crédito  | AUC de la cosecha  | Hanley-McNeil       | préstamos       |
    | mercado  | Sharpe del mes     | Lo (2002)           | días hábiles    |

Mismo contrato (`MetricObservation`), dos dominios que no se parecen en
nada. Esa simetría es el argumento de que el sistema es agnóstico al
modelo: el detector no sabe ni le importa de dónde viene el número.

────────────────────────────────────────────────────────────────────────
LAS CUATRO DECISIONES DE DISEÑO, Y POR QUÉ
────────────────────────────────────────────────────────────────────────

1. **Ventanas mensuales SIN SOLAPE, no un Sharpe móvil de 252 días.**
   Un Sharpe móvil calculado cada día comparte 251 de sus 252 datos con
   el punto anterior: ρ(lag 1) = +0,996. Un umbral calibrado sobre ruido
   con ρ=0,5 da, sobre esa serie, un ARL0 real de 213 cuando se pidió
   100 — y por tanto también detecta el doble de lento sin avisar.
   Con meses sin solape, dos puntos consecutivos no comparten ni un dato.

2. **Arranque en julio de 1963.** La NYSE cotizaba los sábados hasta
   1952: los meses anteriores tienen ~24-25 días hábiles y los actuales
   ~21. Como la métrica se calcula con los días de cada mes, eso metería
   una no-estacionariedad en el tamaño muestral. Además, 1963-07 es la
   muestra canónica de la literatura de factores. La decisión se toma
   ANTES de calibrar nada.

3. **A HML no se le resta la tasa libre de riesgo.** HML es una cartera
   larga-corta de inversión neta cero: ya es un retorno de exceso por
   construcción. Restarle `rf` sería contarlo dos veces. A `mkt_rf`
   tampoco: el nombre lo dice, ya viene neto. Este es el tipo de detalle
   que un jefe de riesgos pregunta para ver si entiendes lo que estás
   midiendo o si solo has llamado a una función.

4. **Mensual y no trimestral o anual: da igual, y eso se puede demostrar.**
   La pregunta obvia es si agregar más (trimestres, años) reduciría el
   ruido lo bastante como para detectar antes. Simulado, con un cambio
   de régimen realista de HML (Sharpe ~0,9 en los 80 → ~−0,3 en los
   2010, es decir 1,2) y **la misma tasa de falsa alarma en tiempo real**
   (una cada 10 años):

       cadencia     SE del Sharpe   cambio en σ   detección
       mensual          ±3,46          0,35σ       2,0 años
       trimestral       ±2,00          0,60σ       2,0 años
       anual            ±1,00          1,20σ       2,1 años

   Las tres tardan **lo mismo**. Agregar sube la relación señal-ruido de
   cada observación y baja el número de observaciones, y las dos cosas se
   cancelan: la información llega al ritmo que marca el dato, no al que
   marca cómo lo trocees. Elegimos mensual por tener más puntos para
   calibrar y mejor resolución temporal, no porque detecte antes.

   **Y de paso, el resultado honesto que hay que decir en la defensa:**
   confirmar una decadencia real de este tamaño cuesta ~2 años. No es una
   limitación del detector — es el límite de información del problema.
   Cualquiera que prometa detectarlo en un trimestre está prometiendo
   falsas alarmas, no velocidad.

5. **Meses con menos de 15 días hábiles se descartan.** Hay unos pocos
   (cierres por emergencia, la crisis administrativa de la NYSE en 1968,
   septiembre de 2001). Un Sharpe estimado con 6 observaciones no es una
   medición, es ruido con formato de número.

────────────────────────────────────────────────────────────────────────
EL ERROR ESTÁNDAR DEL SHARPE — Lo (2002)
────────────────────────────────────────────────────────────────────────

Para retornos independientes, la varianza del Sharpe estimado es

        Var(SR) ≈ (1 + SR²/2) / T

donde SR está en las unidades del periodo (aquí, diario) y T es el número
de observaciones. Anualizar multiplica ambos, SR y su error, por √252.

La intuición, que es la misma que en Hanley-McNeil: el ruido baja con
√T —cuatro veces más datos, la mitad de error— y el término `SR²/2`
recoge que estimar el denominador (la volatilidad) también cuesta
precisión, y cuesta más cuanto mayor es el Sharpe.

**Aviso honesto sobre la magnitud:** con ~21 días por mes, el error
estándar del Sharpe anualizado ronda **±3,4**. Es enorme comparado con un
Sharpe típico de 0,5. Cada observación mensual, por sí sola, no dice
nada. Eso no invalida el método: es precisamente la situación para la que
existe el CUSUM — acumular evidencia débil hasta que sea concluyente. Pero
hay que decirlo en voz alta antes de que lo pregunten, y explica por qué
un umbral de "una observación fuera de 3σ" (el baseline) funciona mal
aquí.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signal_watch.ingest.french import cargar_factores_diarios

# ── Parámetros de la ventana, fijados por las razones del encabezado ──

INICIO_MUESTRA = "1963-07-01"   # muestra canónica; evita los sábados de la NYSE
FIN_CALIBRACION = "1990-12-31"  # anterior a Fama-French (1992): nadie arbitraba aún
DIAS_HABILES_ANO = 252
MIN_DIAS_POR_MES = 15

# Factores que YA son retornos de exceso y a los que NUNCA se resta rf.
# senal_ml_hml: posición ±1 sobre HML (gold/signal_momentum.py). Una cartera
# larga-corta por un escalar sigue siendo un retorno de exceso.
FACTORES_EXCESO = ("mkt_rf", "smb", "hml", "senal_ml_hml")


def recortar_muestra(
    df_diario: pd.DataFrame,
    inicio: str = INICIO_MUESTRA,
) -> pd.DataFrame:
    """Recorta la serie diaria al periodo de estudio."""
    recortado = df_diario.loc[inicio:].copy()
    if recortado.empty:
        raise ValueError(f"No quedan datos después de recortar en {inicio}")
    return recortado


def sharpe_mensual(df_diario: pd.DataFrame, factor: str = "hml") -> pd.DataFrame:
    """Sharpe anualizado por mes, sin solape, con su error estándar.

    Devuelve un DataFrame indexado por fin de mes con:
        sharpe        Sharpe anualizado del mes
        sharpe_se     error estándar de esa estimación (Lo, 2002)
        n_obs         días hábiles usados
        retorno_anual media diaria anualizada (para interpretar)
        vol_anual     volatilidad diaria anualizada (para interpretar)
    """
    if factor not in df_diario.columns:
        raise ValueError(
            f"No tengo la columna '{factor}'. Disponibles: {list(df_diario.columns)}"
        )
    if factor not in FACTORES_EXCESO:
        raise ValueError(
            f"'{factor}' no está declarado como retorno de exceso. Antes de "
            "usarlo hay que decidir explícitamente si se le resta rf."
        )

    serie = df_diario[factor].dropna()
    por_mes = serie.groupby(pd.Grouper(freq="ME"))

    filas = []
    for fecha, r in por_mes:
        n = len(r)
        if n < MIN_DIAS_POR_MES:
            continue
        media = r.mean()
        # ddof=1: estimamos la volatilidad a partir de la muestra, no la conocemos
        vol = r.std(ddof=1)
        if vol == 0 or not np.isfinite(vol):
            continue

        sr_diario = media / vol
        # Lo (2002), caso independiente
        se_diario = np.sqrt((1.0 + 0.5 * sr_diario**2) / n)

        raiz = np.sqrt(DIAS_HABILES_ANO)
        filas.append(
            {
                "fecha": fecha,
                "sharpe": sr_diario * raiz,
                "sharpe_se": se_diario * raiz,
                "n_obs": n,
                "retorno_anual": media * DIAS_HABILES_ANO,
                "vol_anual": vol * raiz,
            }
        )

    if not filas:
        raise ValueError(
            f"No he podido construir ni un mes válido para '{factor}'. "
            f"¿Hay al menos {MIN_DIAS_POR_MES} días hábiles por mes?"
        )

    out = pd.DataFrame(filas).set_index("fecha").sort_index()
    out.index.name = "fecha"
    return out


def construir_metrica_factor(
    factor: str = "hml",
    inicio: str = INICIO_MUESTRA,
) -> pd.DataFrame:
    """Punto de entrada: de los datos crudos de French a la métrica mensual."""
    return sharpe_mensual(recortar_muestra(cargar_factores_diarios(), inicio), factor)


def parametros_calibracion(
    metrica: pd.DataFrame,
    fin_calibracion: str = FIN_CALIBRACION,
) -> dict[str, float]:
    """mu0 y sigma de la ventana de referencia, para calibrar el detector.

    Por qué NO se calibra sobre la serie completa: estimar un ARL0 exige
    un tramo donde no pase nada, y la serie completa está llena de cambios
    de régimen. El sigma saldría inflado por los propios cambios que
    queremos detectar, y el detector quedaría sordo.

    1963-1990 es el periodo anterior a que Fama y French publicaran el
    factor (1992): nadie lo estaba arbitrando todavía. Es la misma
    disciplina que el tutor exigió para la referencia del PSI — se congela
    ANTES del periodo monitorizado, no después de verlo.
    """
    calib = metrica.loc[:fin_calibracion]
    if len(calib) < 60:
        raise ValueError(
            f"Solo {len(calib)} meses en la ventana de calibración; hacen falta "
            "bastantes más para estimar mu0 y sigma con sentido."
        )
    return {
        "mu0": float(calib["sharpe"].mean()),
        "sigma": float(calib["sharpe"].std(ddof=1)),
        "n_meses_calibracion": int(len(calib)),
        "inicio_calibracion": str(calib.index.min().date()),
        "fin_calibracion": str(calib.index.max().date()),
    }


# ── Diagnóstico ──────────────────────────────────────────────────────

def main(factor: str = "hml") -> None:
    """Comprueba que la métrica es lo que dijimos que sería."""
    m = construir_metrica_factor(factor)

    print("=" * 70)
    print(f"MÉTRICA MENSUAL SIN SOLAPE — {factor.upper()}")
    print("=" * 70)
    print(f"Meses: {len(m)}")
    print(f"Rango: {m.index.min().date()} -> {m.index.max().date()}")
    print(
        f"Días por mes: min {m['n_obs'].min()} · mediana "
        f"{int(m['n_obs'].median())} · max {m['n_obs'].max()}"
    )

    print("\n--- LA COMPROBACIÓN QUE JUSTIFICA TODO EL DISEÑO ---")
    rho = m["sharpe"].autocorr(lag=1)
    print(f"Autocorrelación de la métrica, lag 1: {rho:+.3f}")
    print(
        "  Tiene que estar cerca de 0. Si saliera por encima de 0,5, las\n"
        "  ventanas se estarían solapando y el umbral calibrado no valdría."
    )

    print("\n--- VENTANA DE CALIBRACIÓN (1963-07 a 1990-12) ---")
    p = parametros_calibracion(m)
    for k, v in p.items():
        print(f"  {k:22} {v}")
    print(
        "\n  mu0 y sigma salen SOLO de aquí. El resto de la serie es lo que\n"
        "  se vigila, y no participa en fijar el umbral."
    )

    print("\n--- SHARPE POR DÉCADA (reconstruido desde la métrica mensual) ---")
    por_decada = m.groupby(m.index.year // 10 * 10).agg(
        sharpe_medio=("sharpe", "mean"),
        meses=("sharpe", "size"),
        retorno_anual=("retorno_anual", "mean"),
        vol_anual=("vol_anual", "mean"),
    )
    print(por_decada.round(3).to_string())

    print("\n--- EL RUIDO DE UNA SOLA OBSERVACIÓN ---")
    print(f"  error estándar mediano del Sharpe mensual: ±{m['sharpe_se'].median():.2f}")
    print(f"  desviación típica de la serie (calibración): {p['sigma']:.2f}")
    print(
        "\n  Un solo mes no dice nada: el error de medición es del orden de la\n"
        "  propia señal. Por eso hace falta acumular evidencia (CUSUM) en vez\n"
        "  de mirar observaciones sueltas (3-sigma)."
    )

    print("\n--- MESES MÁS EXTREMOS ---")
    print("\nPeores 5:")
    print(m.nsmallest(5, "sharpe")[["sharpe", "n_obs", "vol_anual"]].round(2).to_string())
    print("\nMejores 5:")
    print(m.nlargest(5, "sharpe")[["sharpe", "n_obs", "vol_anual"]].round(2).to_string())
    print("=" * 70)


if __name__ == "__main__":
    main()
