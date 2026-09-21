"""Banco de pruebas sintético: el resultado central del Bloque 4, para explorar.

Aquí la verdad se conoce (τ y magnitud inyectados), así que el retardo se
MIDE. Filtros en la barra lateral: métrica, tasa de falsas alarmas común,
escenarios y detectores. Dos vistas:
  · Retardo por magnitud       — a una tasa de falsas alarmas igualada
  · Retardo frente a falsas alarmas — la curva operativa clásica: cada punto,
                                       un umbral

Siempre se compara a la misma tasa de falsas alarmas
(seleccionar_punto_comparable): el que más falsas alarmas permite siempre
parece el más rápido. Todo sale de outputs/tables/curvas_retardo.csv.
"""

import streamlit as st

from components import CONFIG_PLOTLY, cabecera
from components.delay_curve_plot import TITULO_ESCENARIO, grafico_banco, grafico_curva_operativa
from signal_watch.evaluation.delay_curves import seleccionar_punto_comparable
from state.session import cargar_tabla

st.markdown(cabecera(
    "Validación · verdad conocida",
    "Banco de pruebas sintético",
    "Series fabricadas donde se conoce el instante y el tamaño del cambio. Aquí el retardo se "
    "mide de verdad, y todos los detectores se comparan a la misma tasa de falsas alarmas.",
    ["1,28 M observaciones", "200 réplicas por celda", "τ = 40", "AUC y PSI"],
), unsafe_allow_html=True)


@st.cache_data
def _curvas():
    return cargar_tabla("curvas_retardo")


curvas = _curvas()
if curvas is None:
    st.info("Falta outputs/tables/curvas_retardo.csv. Ejecuta `python scripts/run_evaluation.py`.")
    st.stop()

st.sidebar.header("Filtros")
tipo = st.sidebar.radio("Métrica vigilada", ["auc", "psi"], horizontal=True,
                        format_func=lambda t: {"auc": "AUC", "psi": "PSI"}[t],
                        help="AUC: peor si baja. PSI: peor si sube.")
sub = curvas[curvas["tipo_metrica"] == tipo]
ref_3s = round(float(sub[sub["detector"] == "3-sigma"]["arl0"].iloc[0]), 1)
niveles = sorted({round(float(a), 1) for a in sub[sub["detector"] == "CUSUM"]["arl0"]} | {ref_3s})
referencia = st.sidebar.select_slider("Tasa de falsas alarmas común (ARL0, pasos)", options=niveles,
                                      value=ref_3s,
                                      help="Por defecto, la del baseline 3-sigma. Cada detector se toma "
                                           "en su punto de operación más cercano.")
escenarios = st.sidebar.multiselect("Escenarios", ["salto", "deriva", "cambio_varianza"],
                                    default=["salto", "deriva", "cambio_varianza"],
                                    format_func=lambda e: TITULO_ESCENARIO[e]) or ["salto"]
disponibles = [d for d in ["CUSUM", "Page-Hinkley", "3-sigma", "UmbralFijo (PSI>0.25)"]
               if d in set(sub["detector"])]
detectores = st.sidebar.multiselect("Detectores", disponibles, default=disponibles) or disponibles[:1]

punto, ref = seleccionar_punto_comparable(curvas, tipo, float(referencia))

s1 = punto[(punto["escenario"] == "salto") & (punto["delta_sigma"] == 1.0)].set_index("detector")
k1, k2, k3, k4 = st.columns(4)
k1.metric("ARL0 común", f"{ref:.0f} pasos", help="Pasos medios hasta una falsa alarma.")
if "CUSUM" in s1.index and "3-sigma" in s1.index:
    cu, tr = float(s1.loc["CUSUM", "arl1"]), float(s1.loc["3-sigma", "arl1"])
    k2.metric("Salto de 1σ · CUSUM", f"{cu:.1f} pasos",
              delta=f"{tr / cu:.1f}× más rápido que 3σ", delta_color="off")
    k3.metric("Salto de 1σ · 3-sigma", f"{tr:.1f} pasos")
if tipo == "psi" and "UmbralFijo (PSI>0.25)" in set(punto["detector"]):
    uf = punto[punto["detector"] == "UmbralFijo (PSI>0.25)"]
    k4.metric("PSI > 0,25: celdas sin detectar", f"{int((uf['arl1_censurados'] == uf['arl1_n_streams']).sum())} / {len(uf)}")
else:
    cv = punto[(punto["escenario"] == "cambio_varianza") & (punto["delta_sigma"] == 1.0)].set_index("detector")
    if "CUSUM" in cv.index and "3-sigma" in cv.index:
        k4.metric("Cambio de varianza · 3-sigma", f"{cv.loc['3-sigma', 'arl1']:.1f} pasos",
                  delta=f"CUSUM {cv.loc['CUSUM', 'arl1']:.1f}: aquí gana 3σ", delta_color="off")

t1, t2, t3 = st.tabs([":material/trending_down: Retardo por magnitud",
                      ":material/balance: Retardo frente a falsas alarmas",
                      ":material/table_chart: Tabla"])

with t1:
    with st.container(border=True, key="card_banco"):
        st.plotly_chart(grafico_banco(punto, escenarios, detectores), config=CONFIG_PLOTLY)
    st.markdown(
        "- **Salto y deriva:** los detectores secuenciales confirman las caídas sutiles bastante antes "
        "que 3-sigma, a la misma tasa de falsas alarmas.\n"
        "- **Cambio de varianza:** gana 3-sigma. Un detector que vigila la media es ciego a un cambio "
        "que no la mueve: es un límite real del CUSUM, y se enseña en vez de esconderlo.\n"
        "- **Marcador hueco:** más del 20% de las series no alarmaron en la ventana; el valor es una "
        "cota inferior. La línea de puntos es la ventana observable (60 pasos)."
    )
    if tipo == "psi":
        st.warning("**PSI > 0,25** no detecta ningún cambio en ninguna celda: su línea es la ventana "
                   "observable, lo que sale cuando un detector nunca se entera. Resultado con ~800 "
                   "observaciones por periodo; con cohortes pequeñas el ruido del PSI crece, y eso "
                   "refuerza la crítica: un umbral fijo, insensible al tamaño de muestra, es el problema.")

with t2:
    st.markdown("**La gráfica clásica de la detección secuencial.** Cada punto es un umbral: más a la "
                "derecha, menos falsas alarmas; más abajo, detecta antes. Lo mejor está **abajo a la "
                "derecha**. 3-sigma y el umbral fijo son un solo punto porque su umbral no se ajusta.")
    a, b = st.columns(2)
    esc = a.selectbox("Escenario", escenarios, format_func=lambda e: TITULO_ESCENARIO[e])
    delta = b.select_slider("Magnitud del cambio (δ)", options=[0.5, 1.0, 1.5, 2.0, 3.0], value=1.0,
                            format_func=lambda d: f"{d:g}σ")
    with st.container(border=True, key="card_operativa"):
        st.plotly_chart(grafico_curva_operativa(curvas, tipo, esc, float(delta), detectores),
                        config=CONFIG_PLOTLY)

with t3:
    tabla = punto[punto["detector"].isin(detectores) & punto["escenario"].isin(escenarios)]
    st.dataframe(
        tabla.pivot_table(index=["escenario", "delta_sigma"], columns="detector", values="arl1",
                          aggfunc="first").round(1),
    )
    st.download_button("Descargar la tabla completa (CSV, con huella R7)",
                       curvas.to_csv(index=False).encode("utf-8"),
                       file_name="curvas_retardo.csv", mime="text/csv")
    h = curvas.iloc[0]
    st.caption(f"Huella: config_hash `{h['config_hash']}` · hash_datos `{h['hash_datos']}` · "
               f"commit `{h['commit']}`")
