"""Da a las series sintéticas la semántica REAL de las métricas que imitan.

Sin este módulo, tu generador produce "ruido con un salto" — números
sueltos sin ninguna propiedad matemática particular. Con este módulo,
una serie "de AUC" se comporta como un AUC de verdad (acotada entre
0.5 y 1, con su error estándar dependiente de n vía Hanley-McNeil), y
una serie "de PSI" se comporta como un PSI de verdad (siempre >= 0,
con su distribución nula chi-cuadrado, NO gaussiana).

Esto es crítico para el resultado más importante del proyecto: si el
PSI sintético usa ruido gaussiano, el ARL0 medido para el umbral
"PSI > 0.25" es FALSO, y ese es precisamente el número que se presenta
como titular (ADR-0008).
"""

from __future__ import annotations

import numpy as np
from scipy import stats


# ── AUC: acotado en (0.5, 1), con SE de Hanley-McNeil ──────────────────

def clip_auc(valores: np.ndarray, minimo: float = 0.5, maximo: float = 0.999) -> np.ndarray:
    """Recorta valores para que se comporten como un AUC real: nunca
    por debajo de 0.5 (adivinar al azar) ni por encima de 1.

    El máximo se deja en 0.999, no 1.0, porque un AUC exactamente 1.0
    (discriminación perfecta) es un caso degenerado que rompe fórmulas
    que dividen por (1 - AUC), como la propia Hanley-McNeil.
    """
    return np.clip(valores, minimo, maximo)


def se_hanley_mcneil(auc: float | np.ndarray, n_obs: int | np.ndarray) -> float | np.ndarray:
    """Error estándar de un AUC estimado sobre n_obs ejemplos, según
    la fórmula de Hanley y McNeil (1982).

    Es una aproximación que asume una proporción de positivos del 50%
    aproximadamente (razonable como aproximación genérica para el
    banco de pruebas; la fórmula exacta usa n_positivos y n_negativos
    por separado, que en el banco sintético no distinguimos).

    Fórmula (forma simplificada, asumiendo Q1 y Q2 estándar):
        SE(AUC) = sqrt( AUC*(1-AUC) * (1 + (n/2 - 1)*(...)) / n )

    Usamos aquí la forma clásica de Hanley-McNeil con las aproximaciones
    Q1 = AUC / (2 - AUC) y Q2 = 2*AUC^2 / (1 + AUC):
        SE(AUC)^2 = [ AUC(1-AUC) + (n_pos-1)(Q1-AUC^2) + (n_neg-1)(Q2-AUC^2) ] / (n_pos * n_neg)

    Simplificamos asumiendo n_pos = n_neg = n_obs/2 (clases balanceadas),
    que es razonable para un banco de pruebas sintético de propósito
    general.
    """
    auc = np.asarray(auc, dtype=float)
    n_obs = np.asarray(n_obs, dtype=float)

    n_pos = n_obs / 2
    n_neg = n_obs / 2

    q1 = auc / (2 - auc)
    q2 = (2 * auc**2) / (1 + auc)

    numerador = (
        auc * (1 - auc)
        + (n_pos - 1) * (q1 - auc**2)
        + (n_neg - 1) * (q2 - auc**2)
    )
    varianza = numerador / (n_pos * n_neg)
    varianza = np.clip(varianza, 1e-10, None)  # nunca negativa por redondeo

    return np.sqrt(varianza)


def generar_auc_realista(
    valores_base: np.ndarray,
    n_obs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Convierte una serie de ruido genérico en una serie de AUC realista.

    Pasos:
      1. Recorta los valores al rango válido (0.5, 0.999).
      2. Calcula el error estándar de CADA punto con Hanley-McNeil,
         usando su propio n_obs (así una cosecha grande tiene menos
         ruido reportado que una pequeña, como en la vida real).

    Devuelve (valores_recortados, errores_estandar).
    """
    auc = clip_auc(valores_base)
    se = se_hanley_mcneil(auc, n_obs)
    return auc, se


# ── PSI: siempre >= 0, con distribución nula chi-cuadrado ──────────────

def clip_psi(valores: np.ndarray) -> np.ndarray:
    """El PSI nunca puede ser negativo (es una suma de términos al
    cuadrado). Recorta cualquier valor negativo a 0."""
    return np.clip(valores, 0.0, None)


def generar_psi_desde_chi2(
    n: int,
    n_bins: int,
    n_obs: int,
    rng: np.random.Generator,
    escala: float = 1.0,
) -> np.ndarray:
    """Genera una serie de PSI bajo la hipótesis nula (SIN cambio real),
    muestreando de su distribución REAL: chi-cuadrado, no gaussiana.

    Por qué chi-cuadrado y no una campana de Gauss:
      El PSI compara dos histogramas (la distribución de referencia y
      la actual) sumando, por cada bin, (observado-esperado)^2/esperado.
      Esa suma de términos al cuadrado es, por construcción, una
      variable chi-cuadrado — asimétrica, siempre positiva, con una
      cola larga hacia la derecha. Generar el PSI sintético con ruido
      gaussiano centrado en 0 y recortado a positivo NO reproduce esa
      forma: subestima la cola derecha, y por tanto subestima cuántas
      veces el PSI cruza un umbral alto por puro azar. El ARL0 que
      midieras sobre ese PSI mal simulado sería FALSO (ADR-0008).

    Bajo H0, el estadístico PSI se comporta aproximadamente como
    chi2(df) / n_obs, donde df = n_bins - 1 (grados de libertad: el
    número de categorías menos una, porque las proporciones deben
    sumar 1). Aquí generamos exactamente eso.

    Args:
        n: número de puntos de la serie
        n_bins: número de categorías (bins) usadas para calcular el PSI
        n_obs: tamaño de muestra de cada cosecha (a mayor n_obs, menor
               el PSI esperado por azar — más observaciones, histogramas
               más parecidos a la referencia)
        rng: generador aleatorio (para reproducibilidad con semilla)
        escala: factor multiplicativo extra, por si se necesita ajustar
                el nivel del ruido sin cambiar n_obs
    """
    df = max(n_bins - 1, 1)
    muestras_chi2 = rng.chisquare(df=df, size=n)
    # normalizamos por n_obs: con más observaciones, el PSI "de ruido"
    # esperado bajo H0 es menor (histogramas se parecen más al azar)
    psi = escala * muestras_chi2 / n_obs * 100  # *100 para escalar a rango típico ~0-0.3
    return psi


def inyectar_cambio_psi(
    psi_base: np.ndarray,
    tau: int,
    incremento: float,
) -> np.ndarray:
    """Añade un incremento de PSI a partir de tau (simulando deriva
    real de la distribución de covariables). El incremento se SUMA
    porque el PSI mide distancia entre distribuciones, así que un
    cambio real solo puede aumentarlo, nunca reducirlo por debajo del
    ruido de fondo."""
    resultado = psi_base.copy()
    resultado[tau:] += incremento
    return clip_psi(resultado)
