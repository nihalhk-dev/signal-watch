"""Factores de mercado: la rama real, para explorar.

Filtros en la barra lateral (periodo, detectores, vista mensual/anual,
suavizado) que recalculan gráficos y cifras. Cuatro pestañas:
  1. Serie y alarmas            — la serie interactiva con las alarmas encima
  2. Retardo sobre ruido real   — la MEDICIÓN: caídas inyectadas de tamaño conocido
  3. ¿Era alfa? (RQ2)           — DSR en vivo según el número de pruebas
  4. Laboratorio                — el usuario inyecta una caída; una serie o 200

Todo número sale de tablas selladas o de funciones de src/ (R6). El
laboratorio usa las mismas piezas que la medición seria: lo que se ve es un
caso concreto de lo que las tablas promedian sobre 1000 series.
"""

import pandas as pd
import streamlit as st

from components import CONFIG_PLOTLY, cabecera, seccion
from components.delay_curve_plot import grafico_demo, grafico_distribucion, grafico_retardo_real
from components.metric_chart import grafico_dsr, grafico_serie
from components.sidebar_filters import filtros_serie
from signal_watch.evaluation.error_analysis import demo_inyeccion, distribucion_retardos
from state.session import (
    cargar_config,
    cargar_tabla,
    observaciones_referencia,
    serie,
    streams_monitorizados,
    umbrales_calibrados,
)

factores = [s for s in streams_monitorizados() if s.startswith("factor_")]
if not factores:
    st.markdown(cabecera("Validación · rama real", "Factores de mercado",
                         "Sin streams de factores todavía."), unsafe_allow_html=True)
    st.info("No hay ningún stream de factores monitorizado. Ejecuta `python scripts/run_monitoring.py`.")
    st.stop()

stream_id = st.sidebar.selectbox("Stream", factores) if len(factores) > 1 else factores[0]
cfg = cargar_config(stream_id)
mon, iny = cfg["monitorizacion"], cfg["inyeccion"]


@st.cache_data
def _serie(sid: str) -> pd.DataFrame:
    return serie(sid)


@st.cache_data
def _tabla(nombre: str):
    return cargar_tabla(nombre)


@st.cache_resource
def _referencia(sid: str):
    return observaciones_referencia(sid)


s = _serie(stream_id)
alarmas = _tabla(f"alarmas_{stream_id}")
retardo = _tabla(f"retardo_ruido_real_{stream_id}")
dsr = _tabla(f"deflated_sharpe_{cfg['factor']}")
f = filtros_serie(int(s.index.min().year), int(s.index.max().year), clave=stream_id)

corte = pd.Timestamp(cfg["fin_calibracion"])
mu0 = float(s.loc[:corte, "value"].mean())
ini, fin = pd.Timestamp(f"{f['periodo'][0]}-01-01"), pd.Timestamp(f"{f['periodo'][1]}-12-31")
en_periodo = s.loc[ini:fin]
vigilados = int((en_periodo.index > corte).sum())
esperadas = vigilados / float(mon["arl0_objetivo_meses"])
alarmas_periodo = alarmas[pd.to_datetime(alarmas["fecha"]).between(ini, fin)
                          & alarmas["detector"].isin(f["detectores"])]

st.markdown(cabecera(
    "Validación · rama real",
    f"Factores de mercado · {cfg['factor'].upper()}",
    "El mismo monitor, sobre la métrica de un modelo real: el Sharpe mensual del factor value "
    "(Kenneth French). Aquí no hay verdad conocida; el retardo se mide inyectando caídas sobre "
    "su ruido real.",
    [stream_id, cfg["metrica"], f"referencia hasta {cfg['fin_calibracion']}",
     f"ARL0 ≈ {mon['arl0_objetivo_meses']} meses"],
), unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Meses en el periodo", len(en_periodo), help=f"De ellos, {vigilados} en vigilancia.")
k2.metric("Sharpe medio del periodo", f"{en_periodo['value'].mean():.2f}",
          delta=f"{en_periodo['value'].mean() - mu0:+.2f} frente a μ0", delta_color="normal",
          help="Media de los Sharpes mensuales del periodo elegido.")
k3.metric("Alarmas en el periodo", len(alarmas_periodo),
          help="Suma de los detectores seleccionados.")
k4.metric("Esperadas por azar, por detector", f"{esperadas:.1f}",
          help="Meses vigilados del periodo / ARL0. Si las alarmas no la superan con claridad, "
               "no se distinguen del ruido.")

t1, t2, t3, t4 = st.tabs([":material/show_chart: Serie y alarmas",
                          ":material/timer: Retardo sobre ruido real",
                          ":material/verified: ¿Era alfa? (RQ2)",
                          ":material/science: Laboratorio"])

# ── 1. Serie y alarmas ───────────────────────────────────────────────
with t1:
    with st.container(border=True, key="card_serie"):
        st.plotly_chart(
            grafico_serie(s, cfg["fin_calibracion"], alarmas, f["detectores"], f["periodo"],
                          f["suavizado"], f["vista"], mu0), config=CONFIG_PLOTLY,
        )
    st.caption("Pasa el ratón por un punto para ver su error estándar y sus días de negociación; "
               "por una alarma, para ver su estadístico y su umbral. Usa 5A / 10A / 20A o arrastra "
               "el deslizador inferior para acercarte.")
    izq, der = st.columns([3, 2])
    with izq:
        st.markdown(seccion("Alarmas del periodo"), unsafe_allow_html=True)
        if alarmas_periodo.empty:
            st.info("Ninguna alarma de los detectores seleccionados en este periodo.")
        else:
            st.dataframe(
                alarmas_periodo[["detector", "fecha", "valor", "estadistico", "umbral", "n_alarma"]]
                .rename(columns={"valor": "Sharpe del mes", "estadistico": "estadístico",
                                 "n_alarma": "nº"}).round(2),
                hide_index=True,
            )
            st.download_button("Descargar alarmas (CSV, con huella R7)",
                               alarmas_periodo.to_csv(index=False).encode("utf-8"),
                               file_name=f"alarmas_{stream_id}_{f['periodo'][0]}-{f['periodo'][1]}.csv",
                               mime="text/csv")
    with der:
        st.markdown(seccion("Cómo leerlo"), unsafe_allow_html=True)
        st.markdown(
            f"- Por puro azar se esperan **~{esperadas:.1f} alarmas por detector** en este periodo.\n"
            "- Sobre la serie cruda no se distingue señal de ruido: una caída de este tamaño "
            "tarda años en confirmarse, y los regímenes de HML se interrumpen antes.\n"
            "- Las fechas se leen como «caen en la ventana donde la literatura sitúa X» "
            "(burbuja tecnológica, *quant quake* de 2007, caída del value 2018-2020).\n"
            "- Ojo con la circularidad: los meses más extremos son los que hacen famosos los episodios."
        )

# ── 2. Retardo sobre ruido real ──────────────────────────────────────
with t2:
    st.markdown(
        "**La medición de la rama real.** Ruido real de la referencia + una caída de tamaño "
        f"conocido en el mes {iny['tau_meses']}; cada detector con sus umbrales ya calibrados. "
        f"{iny['n_series']} series por punto."
    )
    a, b = st.columns([2, 1])
    esc = a.radio("Escenario", iny["escenarios"], horizontal=True, key="esc_retardo",
                  format_func=lambda e: {"salto": "Salto brusco", "deriva": "Deriva gradual"}.get(e, e))
    unidad = b.radio("Unidad", ["Años", "Meses"], horizontal=True, key="unidad_retardo")
    with st.container(border=True, key="card_retardo"):
        st.plotly_chart(grafico_retardo_real(retardo, esc, f["detectores"], en_anos=(unidad == "Años")),
                        config=CONFIG_PLOTLY)

    d_sel = st.select_slider("Comparar en una caída concreta", options=iny["deltas_sigma"], value=0.25,
                             format_func=lambda d: f"{d:g}σ")
    fila = retardo[(retardo["escenario"] == esc) & (retardo["delta_sigma"] == d_sel)].set_index("detector")
    cols = st.columns(len(f["detectores"]))
    for col, det in zip(cols, f["detectores"]):
        meses = float(fila.loc[det, "arl1_meses"])
        dif = meses - float(fila.loc["Shewhart", "arl1_meses"])
        col.metric(det, f"{meses:.1f} meses",
                   delta=(f"{dif:+.1f} meses frente a Shewhart" if det != "Shewhart" else None),
                   delta_color="inverse")  # menos meses = mejor: verde si es negativo
    st.caption("0,15σ ≈ el factor pasa a Sharpe cero; 0,25σ ≈ la caída media de los 2010. Marcador "
               "hueco: >20% de series sin detectar (cota inferior). Las barras son el IC95.")

# ── 3. RQ2 ───────────────────────────────────────────────────────────
with t3:
    st.markdown("**¿Era alfa de verdad, o un Sharpe inflado por suerte o por búsqueda?** No lo "
                "contestan los detectores: lo contesta el Deflated Sharpe.")
    if dsr is None:
        st.info("Falta la tabla. Ejecuta `python -m signal_watch.evaluation.deflated_sharpe`.")
    else:
        desc = dsr[dsr["muestra_descubrimiento"]].iloc[0]
        fuera = dsr[~dsr["muestra_descubrimiento"]].iloc[0]
        n = st.slider("N: estrategias probadas antes de quedarse con HML (muestra 1963-1990)",
                      min_value=1, max_value=1000, value=10)
        fig, dsr_n, n_corte = grafico_dsr(float(desc["sharpe_anual"]), int(desc["T_meses"]),
                                         float(desc["asimetria"]), float(desc["curtosis"]), n)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Sharpe 1963-1990", f"{desc['sharpe_anual']:.2f}")
        m2.metric(f"DSR con N = {n}", f"{dsr_n:.3f}",
                  delta="supera 0,95" if dsr_n >= 0.95 else "no supera 0,95",
                  delta_color="normal" if dsr_n >= 0.95 else "inverse")
        m3.metric("Aguanta hasta", f"N ≈ {n_corte}" if n_corte else "—",
                  help="Mayor N con DSR ≥ 0,95.")
        m4.metric("Fuera de muestra (1991-2026)", f"Sharpe {fuera['sharpe_anual']:.2f}",
                  delta=f"PSR {fuera['psr_vs_0']:.3f}", delta_color="off")
        with st.container(border=True, key="card_dsr"):
            st.plotly_chart(fig, config=CONFIG_PLOTLY)
        st.caption("La curva es el DSR: la probabilidad de que el Sharpe verdadero supere al mejor "
                   "de N estrategias de puro ruido. Por encima de la línea de 0,95 se puede afirmar "
                   "que era alfa. El castigo por búsqueda solo se aplica a la muestra de descubrimiento: después "
                   "de 1991 nadie volvió a elegir el factor (N = 1). Harvey, Liu y Zhu (2016) "
                   "contaron 316 factores publicados, casi todos posteriores a HML: N = 316 castiga de más.")

# ── 4. Laboratorio ───────────────────────────────────────────────────
with t4:
    st.markdown("**Inyecta una caída sobre ruido real de HML y mira cuándo salta cada detector.**")
    c1, c2, c3 = st.columns(3)
    esc_l = c1.radio("Escenario", iny["escenarios"], horizontal=True, key="esc_lab",
                     format_func=lambda e: {"salto": "Salto", "deriva": "Deriva"}.get(e, e))
    delta = c2.select_slider("Tamaño de la caída", options=iny["deltas_sigma"], value=0.25,
                             format_func=lambda d: f"{d:g}σ", key="delta_lab")
    semilla = int(c3.number_input("Semilla (cambia la serie)", min_value=0, max_value=10_000,
                                  value=1, step=1))
    params = dict(k_cusum=float(mon["k_cusum"]), delta_page_hinkley=float(mon["delta_page_hinkley"]),
                  escenario=esc_l, delta_sigma=float(delta), tau=int(iny["tau_meses"]),
                  horizonte=int(iny["horizonte_meses"]),
                  bootstrap_bloque=int(mon["bootstrap_bloque_meses"]))
    ref = _referencia(stream_id)
    umbrales = umbrales_calibrados(stream_id)

    r = demo_inyeccion(ref, umbrales, semilla=semilla, **params)
    with st.container(border=True, key="card_demo"):
        st.plotly_chart(grafico_demo(r, f["detectores"]), config=CONFIG_PLOTLY)
    cols = st.columns(len(f["detectores"]))
    for col, det in zip(cols, f["detectores"]):
        info = r["detectores"][det]
        col.metric(det, f"{info['retardo']} meses" if info["retardo"] else "—", help=info["lectura"])
        col.caption(info["lectura"])

    st.markdown(seccion("Una serie no prueba nada. ¿Y en 200?",
                        "Misma caída, 200 series de ruido distintas: la distribución del retardo."),
                unsafe_allow_html=True)
    clave = (stream_id, esc_l, float(delta), semilla)
    if st.button("Simular 200 series con estos parámetros", type="primary", icon=":material/play_arrow:"):
        with st.spinner("Simulando..."):
            filas = pd.DataFrame(distribucion_retardos(ref, umbrales, n_series=200,
                                                       semilla_base=10_000 + semilla, **params))
        st.session_state["lab"] = (clave, filas)
    guardado = st.session_state.get("lab")
    # Solo se enseña si corresponde a los parámetros ACTUALES: si el usuario
    # los cambia, el resultado anterior deja de ser válido y no se muestra.
    filas = guardado[1] if guardado and guardado[0] == clave else None
    if guardado and filas is None:
        st.caption("Has cambiado los parámetros: vuelve a simular.")
    if filas is not None:
        st.plotly_chart(grafico_distribucion(filas, f["detectores"]),
                        config=CONFIG_PLOTLY)
        resumen = (filas.groupby("detector")
                   .apply(lambda g: pd.Series({
                       "detectan": int((g["resultado"] == "detecta").sum()),
                       "falsa alarma antes de τ": int((g["resultado"] == "falsa alarma antes de τ").sum()),
                       "no detectan": int((g["resultado"] == "no detecta").sum()),
                       "retardo mediano (meses)": g.loc[g["resultado"] == "detecta", "retardo_meses"].median(),
                       "retardo medio (meses)": g.loc[g["resultado"] == "detecta", "retardo_meses"].mean(),
                   }))
                   .reindex(f["detectores"]).round(1))
        st.dataframe(resumen)
        st.caption("La caja es el 50% central; la línea discontinua, la media. La dispersión es "
                   "enorme: por eso los resultados se dan como media de 1000 series y con su IC.")
