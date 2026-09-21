"""Señal de ML sobre HML: un modelo real cuya métrica vigila el monitor.

Para qué existe: demostrar que el monitor no depende del modelo. Aquí el
"modelo" es un clasificador de ML (regresión logística) que decide cada mes
si estar largo o corto en HML. Su rendimiento mensual —el Sharpe de la
estrategia, NETO de costes— es un stream más del contrato metric_stream, y
entra por el mismo scripts/run_monitoring.py que el propio HML, sin tocar
ni una línea del monitor.

Lo que NO pretende: ser una buena estrategia. El timing de factores es
notoriamente difícil; lo esperable es un acierto apenas por encima del de
"estar siempre largo". Si no le gana al baseline, se dice. Lo que se
demuestra es la vigilancia, no el alfa (y si alguien pregunta por el alfa,
lo contesta el Deflated Sharpe, no los detectores).

Diseño, cada decisión por una razón:

  · Frecuencia MENSUAL. Al cierre del mes t se calculan las características
    con datos hasta t, y se predice el signo del retorno de HML en t+1. La
    posición se mantiene todo el mes t+1: rotación baja, costes acotados.
  · Características (todas conocidas al cierre de t): momentum de HML a 1,
    3 y 12 meses, su volatilidad realizada a 3 meses, y el estado del
    mercado (retorno a 12 meses y volatilidad a 3 meses).
  · Validación HACIA DELANTE con ventana creciente. El modelo se reentrena
    cada diciembre con TODOS los meses cuyo objetivo ya se conoce, y nada
    más. Una aserción en el bucle comprueba, mes a mes, que el último dato
    de entrenamiento es anterior al mes que se predice: si alguna vez se
    cuela el futuro, el script se para (R2 llevado al ML).
  · Posición +1 / −1 (largo o corto), no largo / fuera: un mes "fuera" tiene
    retorno constante 0 y su Sharpe no está definido, lo que rompería la
    serie mensual.
  · Costes: cada cambio de posición paga coste_pb por unidad de rotación
    (pasar de +1 a −1 es rotación 2). El stream vigilado es el NETO.
  · Baseline ingenuo: estar siempre largo (= HML). Con los mismos costes.

Todos los parámetros salen de configs/streams/senal_ml_hml_sharpe.yaml.

Desviación documentada respecto al árbol: el árbol reserva este archivo
(gold/signal_momentum.py) y configs/streams/senal_mom_ic.yaml para "la
señal". El módulo se queda con su nombre —las características son momentum
de series temporales—, pero el YAML se llama por lo que mide: el Sharpe
neto de la señal, no un IC. Un IC necesita una sección cruzada de activos
y aquí hay uno solo.

Uso:
    python -m signal_watch.gold.signal_momentum
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from signal_watch.config import config_hash, huella_ejecucion, validate_keys
from signal_watch.gold.factor_metrics import (
    cargar_config,
    metrica_a_observaciones,
    ruta_stream,
)
from signal_watch.gold.metric_stream import load_metric_stream, save_metric_stream
from signal_watch.gold.schemas import Direction
from signal_watch.ingest.french import NOMBRE_ZIP, cargar_factores_diarios, carpeta_french
from signal_watch.paths import PATHS
from signal_watch.processing import factor_returns

STREAM_POR_DEFECTO = "senal_ml_hml_sharpe"
COLUMNA_SENAL = "senal_ml_hml"  # declarada en factor_returns.FACTORES_EXCESO

CLAVES_SENAL = {
    "caracteristicas",
    "C",
    "meses_min_entrenamiento",
    "mes_reentreno",
    "umbral_probabilidad",
    "coste_pb",
}

# Cada característica, con cómo se calcula. Solo usa datos hasta el cierre
# del mes t: por construcción no puede mirar el futuro.
CARACTERISTICAS_DISPONIBLES = {
    "hml_1m": "retorno de HML en el mes t",
    "hml_3m": "retorno acumulado de HML en t-2..t",
    "hml_12m": "retorno acumulado de HML en t-11..t",
    "hml_vol_3m": "volatilidad diaria anualizada de HML en t-2..t",
    "mkt_12m": "retorno acumulado del mercado (Mkt-RF) en t-11..t",
    "mkt_vol_3m": "volatilidad diaria anualizada del mercado en t-2..t",
}


# ── 1. Características y objetivo ────────────────────────────────────

def tabla_mensual(df_diario: pd.DataFrame) -> pd.DataFrame:
    """Características al cierre de cada mes y el objetivo del mes siguiente.

    Retornos acumulados en logaritmos (se suman), para que 3 y 12 meses
    sean composiciones exactas. `objetivo` es 1 si HML sube en t+1: es lo
    ÚNICO de la fila que pertenece al futuro, y por eso la última fila no
    lo tiene.
    """
    log_hml = np.log1p(df_diario["hml"])
    log_mkt = np.log1p(df_diario["mkt_rf"])
    mes = pd.Grouper(freq="ME")

    r_hml = log_hml.groupby(mes).sum()
    r_mkt = log_mkt.groupby(mes).sum()
    # suma de cuadrados y número de días por mes → volatilidad a 3 meses
    ss_hml = (df_diario["hml"] ** 2).groupby(mes).sum()
    ss_mkt = (df_diario["mkt_rf"] ** 2).groupby(mes).sum()
    n_dias = df_diario["hml"].groupby(mes).size()

    t = pd.DataFrame(index=r_hml.index)
    t["hml_1m"] = np.expm1(r_hml)
    t["hml_3m"] = np.expm1(r_hml.rolling(3).sum())
    t["hml_12m"] = np.expm1(r_hml.rolling(12).sum())
    t["hml_vol_3m"] = np.sqrt(ss_hml.rolling(3).sum() / n_dias.rolling(3).sum() * 252)
    t["mkt_12m"] = np.expm1(r_mkt.rolling(12).sum())
    t["mkt_vol_3m"] = np.sqrt(ss_mkt.rolling(3).sum() / n_dias.rolling(3).sum() * 252)

    retorno_siguiente = np.expm1(r_hml).shift(-1)
    t["retorno_hml_siguiente"] = retorno_siguiente
    t["objetivo"] = (retorno_siguiente > 0).astype(float).where(retorno_siguiente.notna())
    t.index.name = "fecha"
    return t


# ── 2. Validación hacia delante ──────────────────────────────────────

def _modelo(C: float):
    # Escalado dentro del pipeline: la media y la desviación se aprenden
    # SOLO con los datos de entrenamiento de cada reentreno.
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=1000))


def predecir_hacia_delante(tabla: pd.DataFrame, caracteristicas: list[str], C: float,
                           meses_min_entrenamiento: int, mes_reentreno: int,
                           umbral_probabilidad: float) -> pd.DataFrame:
    """Una predicción por mes, cada una hecha solo con el pasado.

    En el cierre del mes t, el modelo vigente (entrenado en el último
    reentreno) predice P(HML sube en t+1). Se reentrena en cada `mes_reentreno`
    con todas las filas s < t (su objetivo, el mes s+1 ≤ t, ya se conoce al
    cierre de t). El primer modelo se ajusta en cuanto hay
    `meses_min_entrenamiento` filas.
    """
    datos = tabla.dropna(subset=caracteristicas)
    modelo, fin_entreno, n_entreno = None, None, 0
    filas = []
    for t in datos.index:
        pasado = datos.loc[datos.index < t].dropna(subset=["objetivo"])
        toca = modelo is None or t.month == mes_reentreno
        if toca and len(pasado) >= meses_min_entrenamiento:
            modelo = _modelo(C).fit(pasado[caracteristicas].to_numpy(),
                                    pasado["objetivo"].to_numpy().astype(int))
            fin_entreno, n_entreno = pasado.index.max(), len(pasado)
        if modelo is None:
            continue
        # La muralla del ML: el último objetivo usado para entrenar es el del
        # mes fin_entreno+1, que tiene que ser ≤ t. Si no, se ha colado el futuro.
        if not fin_entreno < t:
            raise AssertionError(f"Fuga temporal: entrenado hasta {fin_entreno}, predice en {t}")
        p = float(modelo.predict_proba(datos.loc[[t], caracteristicas].to_numpy())[0, 1])
        filas.append({
            "fecha_prediccion": t,
            "mes_objetivo": t + pd.offsets.MonthEnd(1),
            "probabilidad_sube": p,
            "posicion": 1 if p > umbral_probabilidad else -1,
            "objetivo": datos.at[t, "objetivo"],
            "fin_entrenamiento": fin_entreno,
            "n_entrenamiento": n_entreno,
        })
    pred = pd.DataFrame(filas).set_index("mes_objetivo")
    pred["acierto"] = ((pred["posicion"] > 0).astype(float) == pred["objetivo"]).where(
        pred["objetivo"].notna())
    return pred


# ── 3. De las posiciones a retornos diarios, con costes ──────────────

def retornos_estrategia(df_diario: pd.DataFrame, posicion_mensual: pd.Series,
                        coste_pb: float) -> pd.Series:
    """Retorno diario de mantener `posicion_mensual` durante cada mes.

    El coste se cobra el primer día del mes en que cambia la posición:
    |posición nueva − posición anterior| × coste_pb / 10.000. Entrar desde
    fuera cuesta rotación 1; darle la vuelta de +1 a −1, rotación 2.
    """
    hml = df_diario["hml"].dropna()
    meses = hml.index.to_period("M").to_timestamp("M")
    pos = posicion_mensual.copy()
    pos.index = pd.DatetimeIndex(pos.index).to_period("M").to_timestamp("M")
    dentro = meses.isin(pos.index)
    hml, meses = hml[dentro], meses[dentro]

    pos_diaria = pd.Series(pos.reindex(meses).to_numpy(), index=hml.index)
    retorno = pos_diaria * hml

    rotacion = pos.diff().abs().fillna(abs(pos.iloc[0]))
    primer_dia = hml.groupby(meses).apply(lambda s: s.index.min())
    coste = pd.Series(0.0, index=hml.index)
    coste.loc[primer_dia.to_numpy()] = rotacion.reindex(primer_dia.index).to_numpy() * coste_pb / 1e4
    return retorno - coste


# ── 4. Resumen honesto: ML frente al baseline ────────────────────────

def _sharpe_anual(r: pd.Series) -> float:
    return float(r.mean() / r.std(ddof=1) * np.sqrt(252))


def resumen(pred: pd.DataFrame, df_diario: pd.DataFrame, coste_pb: float,
            fin_calibracion: str) -> pd.DataFrame:
    """Acierto, Sharpe bruto y neto, y rotación: ML y siempre largo, por tramo.

    Solo meses con resultado conocido: la última predicción (el mes en curso)
    se guarda en la tabla de predicciones, pero todavía no se puede evaluar.
    """
    pred = pred[pred["objetivo"].notna()]
    siempre_largo = pd.Series(1, index=pred.index)
    corte = pd.Timestamp(fin_calibracion)
    filas = []
    for nombre, pos in (("ML (logística)", pred["posicion"]), ("Siempre largo (baseline)", siempre_largo)):
        bruto = retornos_estrategia(df_diario, pos, 0.0)
        neto = retornos_estrategia(df_diario, pos, coste_pb)
        acierto = ((pos > 0).astype(float) == pred["objetivo"]).where(pred["objetivo"].notna())
        for tramo, sel in (("referencia", pred.index <= corte), ("vigilancia", pred.index > corte),
                           ("total", np.ones(len(pred), dtype=bool))):
            meses = pred.index[sel]
            dias = bruto.index.to_period("M").to_timestamp("M").isin(meses)
            n_anos = len(meses) / 12
            filas.append({
                "modelo": nombre, "tramo": tramo,
                "desde": str(meses.min().date()), "hasta": str(meses.max().date()),
                "meses": int(len(meses)),
                "acierto": round(float(acierto[sel].mean()), 4),
                "sharpe_anual_bruto": round(_sharpe_anual(bruto[dias]), 4),
                "sharpe_anual_neto": round(_sharpe_anual(neto[dias]), 4),
                "cambios_por_ano": round(float((pos[sel].diff().abs() > 0).sum() / n_anos), 2),
            })
    return pd.DataFrame(filas)


# ── 5. El stream ─────────────────────────────────────────────────────

def cargar_config_senal(stream_id: str = STREAM_POR_DEFECTO) -> dict[str, Any]:
    cfg = cargar_config(stream_id)  # mismas comprobaciones que el stream de HML
    if "senal" not in cfg:
        raise KeyError(f"configs/streams/{stream_id}.yaml no tiene bloque 'senal'")
    validate_keys(cfg["senal"], CLAVES_SENAL, name=f"{stream_id}.yaml:senal")
    desconocidas = set(cfg["senal"]["caracteristicas"]) - set(CARACTERISTICAS_DISPONIBLES)
    if desconocidas:
        raise ValueError(f"Características desconocidas: {sorted(desconocidas)}")
    return cfg


def construir_senal(stream_id: str = STREAM_POR_DEFECTO):
    """Devuelve (observaciones, config, predicciones, resumen)."""
    cfg = cargar_config_senal(stream_id)
    s = cfg["senal"]
    df = factor_returns.recortar_muestra(cargar_factores_diarios(), cfg["inicio_muestra"])
    pred = predecir_hacia_delante(tabla_mensual(df), list(s["caracteristicas"]), float(s["C"]),
                                  int(s["meses_min_entrenamiento"]), int(s["mes_reentreno"]),
                                  float(s["umbral_probabilidad"]))
    neto = retornos_estrategia(df, pred["posicion"], float(s["coste_pb"]))
    metrica = factor_returns.sharpe_mensual(neto.to_frame(COLUMNA_SENAL), factor=COLUMNA_SENAL)
    obs = metrica_a_observaciones(metrica, stream_id, Direction(cfg["direction"]))
    return obs, cfg, pred, resumen(pred, df, float(s["coste_pb"]), cfg["fin_calibracion"])


def main(stream_id: str = STREAM_POR_DEFECTO) -> None:
    obs, cfg, pred, res = construir_senal(stream_id)
    destino = ruta_stream(stream_id)
    save_metric_stream(obs, destino)
    if load_metric_stream(destino) != obs:
        raise RuntimeError("El stream releído no coincide con el guardado.")

    huella = huella_ejecucion(cfg, [carpeta_french() / NOMBRE_ZIP])
    tablas = PATHS.ensure(PATHS.outputs_tables)
    res.assign(**huella).to_csv(tablas / f"resumen_{stream_id}.csv", index=False)
    pred.reset_index().assign(**huella).to_csv(tablas / f"predicciones_{stream_id}.csv", index=False)

    print("=" * 72)
    print(f"SEÑAL DE ML — {stream_id}")
    print("=" * 72)
    print(f"Predicciones:  {len(pred)}  ({pred.index.min().date()} -> {pred.index.max().date()})")
    print(f"Primer modelo entrenado con {int(pred['n_entrenamiento'].iloc[0])} meses; "
          f"reentrenos: {pred['fin_entrenamiento'].nunique()}")
    print(f"Stream gold:   {destino}  ({len(obs)} meses, ida y vuelta OK)")
    print(f"config_hash:   {config_hash(cfg)}")
    print("\nML frente a estar siempre largo (mismos meses, mismos costes):\n")
    print(res.to_string(index=False))
    print("\nLectura: 'acierto' del baseline = fracción de meses en que HML sube.")
    print("Si el ML no la supera con claridad, el modelo no tiene habilidad: se dice.")
    print("=" * 72)


if __name__ == "__main__":
    main()
