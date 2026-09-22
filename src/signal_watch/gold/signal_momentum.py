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
  · Dos listones, con los mismos costes: estar siempre largo (= HML) y la
    regla de una línea "largo si HML subió en los últimos 12 meses". Si la
    regla hace lo mismo que la logística, el ML no aporta nada.
  · ¿Es bueno? PSR (Mertens) de los retornos mensuales netos frente a 0 y,
    sobre todo, de la DIFERENCIA ML − listón: ¿le gana de verdad o por
    suerte? ¿Es estable? El modelo se entrena en dos tramos disjuntos
    (antes y después de fin_calibracion): si los signos de los pesos no
    coinciden, lo que aprende es ruido.

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
from signal_watch.evaluation.deflated_sharpe import momentos, psr
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


def _mensual(r_diario: pd.Series) -> pd.Series:
    """Retorno mensual compuesto desde los diarios (como en deflated_sharpe)."""
    return (1 + r_diario).groupby(r_diario.index.to_period("M").to_timestamp("M")).prod() - 1


def _psr_vs_0(r_mensual: pd.Series) -> float:
    m = momentos(r_mensual)
    return psr(m["sr"], 0.0, m["T"], m["asimetria"], m["curtosis"])


def posiciones_listones(pred: pd.DataFrame, tabla: pd.DataFrame) -> dict[str, pd.Series]:
    """Los dos listones, con las mismas fechas que el ML.

    La regla de momentum usa hml_12m al cierre del mes de la predicción:
    exactamente la información que tenía el modelo, ni un dato más.
    """
    mom = tabla.loc[pred["fecha_prediccion"], "hml_12m"].to_numpy()
    return {
        "Siempre largo (baseline)": pd.Series(1, index=pred.index),
        "Regla momentum 12m (baseline)": pd.Series(np.where(mom > 0, 1, -1), index=pred.index),
    }


def resumen(pred: pd.DataFrame, tabla: pd.DataFrame, df_diario: pd.DataFrame, coste_pb: float,
            fin_calibracion: str) -> pd.DataFrame:
    """ML frente a los dos listones, por tramo, con su significancia.

    Filas de modelo: acierto, Sharpe bruto y neto, rotación y PSR del retorno
    mensual neto frente a 0. Filas "ML − listón": la DIFERENCIA de retornos
    mensuales netos; su Sharpe es un ratio de información y su PSR contesta
    "¿le gana de verdad?". El PSR usa N = 1: con más configuraciones probadas
    solo podría bajar.

    Solo meses con resultado conocido: la última predicción (el mes en curso)
    se guarda en la tabla de predicciones, pero todavía no se puede evaluar.
    """
    pred = pred[pred["objetivo"].notna()]
    corte = pd.Timestamp(fin_calibracion)
    tramos = (("referencia", pred.index <= corte), ("vigilancia", pred.index > corte),
              ("total", np.ones(len(pred), dtype=bool)))
    estrategias = {"ML (logística)": pred["posicion"], **posiciones_listones(pred, tabla)}
    netos_mensuales, aciertos, filas = {}, {}, []
    for nombre, pos in estrategias.items():
        bruto = retornos_estrategia(df_diario, pos, 0.0)
        neto = retornos_estrategia(df_diario, pos, coste_pb)
        netos_mensuales[nombre] = _mensual(neto)
        aciertos[nombre] = ((pos > 0).astype(float) == pred["objetivo"])
        for tramo, sel in tramos:
            meses = pred.index[sel]
            dias = bruto.index.to_period("M").to_timestamp("M").isin(meses)
            filas.append({
                "modelo": nombre, "tramo": tramo,
                "desde": str(meses.min().date()), "hasta": str(meses.max().date()),
                "meses": int(len(meses)),
                "acierto": round(float(aciertos[nombre][sel].mean()), 4),
                "sharpe_anual_bruto": round(_sharpe_anual(bruto[dias]), 4),
                "sharpe_anual_neto": round(_sharpe_anual(neto[dias]), 4),
                "cambios_por_ano": round(float((pos[sel].diff().abs() > 0).sum() / (len(meses) / 12)), 2),
                "psr_neto_vs_0": round(_psr_vs_0(netos_mensuales[nombre].loc[meses]), 4),
            })
    ml = "ML (logística)"
    for liston in list(estrategias)[1:]:
        dif = netos_mensuales[ml] - netos_mensuales[liston]
        for tramo, sel in tramos:
            meses = pred.index[sel]
            m = momentos(dif.loc[meses])
            filas.append({
                "modelo": f"ML − {liston.split(' (')[0]}", "tramo": tramo,
                "desde": str(meses.min().date()), "hasta": str(meses.max().date()),
                "meses": int(len(meses)),
                "acierto": round(float(aciertos[ml][sel].mean() - aciertos[liston][sel].mean()), 4),
                "sharpe_anual_bruto": np.nan,
                "sharpe_anual_neto": round(m["sr"] * np.sqrt(12), 4),
                "cambios_por_ano": np.nan,
                "psr_neto_vs_0": round(psr(m["sr"], 0.0, m["T"], m["asimetria"], m["curtosis"]), 4),
            })
    return pd.DataFrame(filas)


def estabilidad_pesos(tabla: pd.DataFrame, caracteristicas: list[str], C: float,
                      fin_calibracion: str) -> pd.DataFrame:
    """Pesos del modelo entrenado en dos tramos que NO se solapan.

    Por qué no basta con mirar los reentrenos: con ventana creciente, cada
    reentreno comparte más del 90% de sus datos con el anterior, así que sus
    pesos casi no pueden cambiar de signo AUNQUE el modelo ajuste ruido
    (comprobado sobre ruido puro: "mismo signo" 0,85-1,0). La prueba que sí
    discrimina es entrenar con datos disjuntos: si una característica tiene
    un efecto real, su signo coincide en los dos tramos; si es ruido, es una
    moneda al aire.
    """
    datos = tabla.dropna(subset=[*caracteristicas, "objetivo"])
    corte = pd.Timestamp(fin_calibracion)
    pesos = {}
    for tramo, sel in (("hasta_" + fin_calibracion[:4], datos.index <= corte),
                       ("desde_" + str(corte.year + 1), datos.index > corte)):
        d = datos[sel]
        pesos[tramo] = _modelo(C).fit(d[caracteristicas].to_numpy(),
                                      d["objetivo"].to_numpy().astype(int))[-1].coef_[0]
    a, b = pesos.values()
    return pd.DataFrame({"caracteristica": caracteristicas,
                         **{f"peso_{k}": np.round(v, 4) for k, v in pesos.items()},
                         "mismo_signo": np.sign(a) == np.sign(b)})


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
    """Devuelve (observaciones, config, predicciones, resumen, estabilidad)."""
    cfg = cargar_config_senal(stream_id)
    s = cfg["senal"]
    df = factor_returns.recortar_muestra(cargar_factores_diarios(), cfg["inicio_muestra"])
    tabla = tabla_mensual(df)
    pred = predecir_hacia_delante(tabla, list(s["caracteristicas"]), float(s["C"]),
                                  int(s["meses_min_entrenamiento"]), int(s["mes_reentreno"]),
                                  float(s["umbral_probabilidad"]))
    neto = retornos_estrategia(df, pred["posicion"], float(s["coste_pb"]))
    metrica = factor_returns.sharpe_mensual(neto.to_frame(COLUMNA_SENAL), factor=COLUMNA_SENAL)
    obs = metrica_a_observaciones(metrica, stream_id, Direction(cfg["direction"]))
    res = resumen(pred, tabla, df, float(s["coste_pb"]), cfg["fin_calibracion"])
    estab = estabilidad_pesos(tabla, list(s["caracteristicas"]), float(s["C"]), cfg["fin_calibracion"])
    return obs, cfg, pred, res, estab


def main(stream_id: str = STREAM_POR_DEFECTO) -> None:
    obs, cfg, pred, res, estab = construir_senal(stream_id)
    destino = ruta_stream(stream_id)
    save_metric_stream(obs, destino)
    if load_metric_stream(destino) != obs:
        raise RuntimeError("El stream releído no coincide con el guardado.")

    huella = huella_ejecucion(cfg, [carpeta_french() / NOMBRE_ZIP])
    tablas = PATHS.ensure(PATHS.outputs_tables)
    res.assign(**huella).to_csv(tablas / f"resumen_{stream_id}.csv", index=False)
    pred.reset_index().assign(**huella).to_csv(tablas / f"predicciones_{stream_id}.csv", index=False)
    estab.assign(**huella).to_csv(tablas / f"estabilidad_pesos_{stream_id}.csv", index=False)

    print("=" * 72)
    print(f"SEÑAL DE ML — {stream_id}")
    print("=" * 72)
    print(f"Predicciones:  {len(pred)}  ({pred.index.min().date()} -> {pred.index.max().date()})")
    print(f"Primer modelo entrenado con {int(pred['n_entrenamiento'].iloc[0])} meses; "
          f"reentrenos: {pred['fin_entrenamiento'].nunique()}")
    print(f"Stream gold:   {destino}  ({len(obs)} meses, ida y vuelta OK)")
    print(f"config_hash:   {config_hash(cfg)}")
    with pd.option_context("display.width", 200):
        print("\nML frente a los dos listones (mismos meses, mismos costes):\n")
        print(res.to_string(index=False))
        print("\nEstabilidad: pesos (características estandarizadas) entrenando en dos "
              "tramos disjuntos:\n")
        print(estab.to_string(index=False))
    print("\nLectura:")
    print("  · 'acierto' de 'Siempre largo' = fracción de meses en que HML sube.")
    print("  · Filas 'ML − …': diferencia de retornos netos. Su PSR ≥ 0,95 querría decir")
    print("    que el ML le gana de verdad; por debajo, la ventaja no se distingue de la suerte.")
    print("  · 'mismo_signo': si una característica tiene efecto real, su peso tiene el mismo")
    print("    signo en los dos tramos. Con 6 características, ~3 coincidencias es lo del azar.")
    print("=" * 72)


if __name__ == "__main__":
    main()
