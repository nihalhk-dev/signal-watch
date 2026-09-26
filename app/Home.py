"""Signal Watch — punto de entrada de la app.

    streamlit run app/Home.py

Hace cuatro cosas: carga el estilo (tema en .streamlit/config.toml, detalles
en app/assets/styles.css), pinta la marca de la barra lateral, pinta la
portada y declara la navegación. La navegación se declara aquí con
st.navigation en vez de dejar que Streamlit muestre todo lo que haya en
pages/, porque el árbol tiene páginas fuera de alcance (crédito, valor
económico): así el menú solo enseña lo que existe de verdad. Del informe MRM
existen dos partes: la evidencia de pruebas (6_Informe_MRM.py, "Validación
del sistema") y el expediente en PDF de cada modelo, que se descarga desde
Salud de modelos (reporting/mrm_report.py).

Regla de la app (R6): no calcula resultados. Todo número sale de una tabla
sellada en outputs/tables/ o de una función de src/.
"""

from pathlib import Path

import streamlit as st

from components import (
    CONFIG_PLOTLY,
    DETECTORES_REAL,
    huella_lateral,
    marca_lateral,
    seccion,
)
from state.session import cargar_tabla, resumen_stream, serie, streams_monitorizados

_APP = Path(__file__).parent
_LOGO = _APP / "assets" / "logo.svg"

st.set_page_config(page_title="Signal Watch", page_icon="📉", layout="wide")

_css = _APP / "assets" / "styles.css"
if _css.exists():
    st.markdown(f"<style>{_css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.logo(str(_LOGO), size="large")
st.sidebar.markdown(marca_lateral(), unsafe_allow_html=True)


@st.cache_data
def _resumenes() -> dict:
    return {s: resumen_stream(s) for s in streams_monitorizados()}


def inicio() -> None:
    resumenes = _resumenes()
    curvas = cargar_tabla("curvas_retardo")
    retardo = cargar_tabla("retardo_ruido_real_factor_hml_sharpe")
    dsr = cargar_tabla("deflated_sharpe_hml")

    n_streams = len(resumenes)
    n_alarmas = sum(int(r["detectores"]["alarmas"].sum()) for r in resumenes.values()
                    if len(r["detectores"]))
    n_meses = sum(r["meses_vigilados"] for r in resumenes.values())
    n_det = sum(len(r["detectores"]) for r in resumenes.values())

    st.markdown(
        f"""
<div class="sw-hero">
  <div>
    <div class="sw-eyebrow">Trabajo Fin de Máster · Data Science &amp; IA</div>
    <h1>Signal Watch</h1>
    <p><b>Detección secuencial de degradación en modelos financieros.</b> Vigila la métrica de
    rendimiento de un modelo —un AUC, un PSI, un Sharpe— y decide, con una tasa de falsas
    alarmas fijada de antemano, cuándo una caída es real y no ruido.</p>
    <span class="sw-chip">CUSUM · Page-Hinkley · Shewhart</span>
    <span class="sw-chip">ARL0 igualado</span>
    <span class="sw-chip">Verdad conocida + ruido real (Kenneth French)</span>
    <span class="sw-chip">Deflated Sharpe</span>
    <span class="sw-chip">Trazabilidad R7</span>
  </div>
  <div class="sw-panel">
    <div class="sw-eyebrow">Estado de la monitorización</div>
    <div class="sw-stats">
      <div><b>{n_streams}</b><span>streams vigilados</span></div>
      <div><b>{n_det}</b><span>detectores calibrados</span></div>
      <div><b>{n_meses}</b><span>meses en vigilancia</span></div>
      <div><b>{n_alarmas}</b><span>alarmas registradas</span></div>
    </div>
    <div class="sw-estado"><span class="sw-punto"></span>Prototipo validado · no desplegado en producción</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(seccion("Resultados clave", "Cada cifra sale de una tabla sellada en outputs/tables/."),
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    if curvas is not None:
        uf = curvas[(curvas["tipo_metrica"] == "psi")
                    & (curvas["detector"] == "UmbralFijo (PSI>0.25)")]
        nunca = int((uf["arl1_censurados"] == uf["arl1_n_streams"]).sum())
        c1.metric("Regla PSI > 0,25", f"{nunca} / {len(uf)}",
                  delta="celdas sin ninguna detección", delta_color="off",
                  help="Banco sintético. La regla de la industria no detecta ningún cambio "
                       "en ninguna combinación de escenario y magnitud.")
        au = curvas[(curvas["tipo_metrica"] == "auc") & (curvas["escenario"] == "salto")
                    & (curvas["delta_sigma"] == 1.0)]
        ref = float(au[au["detector"] == "3-sigma"]["arl0"].iloc[0])
        cu = au[au["detector"] == "CUSUM"].assign(d=lambda x: (x["arl0"] - ref).abs())
        cu = cu.sort_values("d").iloc[0]
        tres = float(au[au["detector"] == "3-sigma"]["arl1"].iloc[0])
        c2.metric("Sintético · salto de 1σ", f"{cu['arl1']:.0f} pasos",
                  delta=f"{tres / cu['arl1']:.1f}× más rápido que 3σ", delta_color="off",
                  help="CUSUM frente a 3-sigma a la misma tasa de falsas alarmas.")
    if retardo is not None:
        r = retardo[(retardo["escenario"] == "salto") & (retardo["delta_sigma"] == 0.25)]
        cusum = float(r[r["detector"] == "CUSUM"]["arl1_meses"].iloc[0])
        shew = float(r[r["detector"] == "Shewhart"]["arl1_meses"].iloc[0])
        c3.metric("Ruido real · caída de 0,25σ", f"{cusum / 12:.1f} años",
                  delta=f"{shew - cusum:.0f} meses antes que Shewhart", delta_color="off",
                  help="Caída inyectada sobre el ruido real de HML, con una falsa alarma por década.")
    if dsr is not None:
        d10 = float(dsr[dsr["muestra_descubrimiento"] & (dsr["n_pruebas"] == 10)]["dsr"].iloc[0])
        fuera = float(dsr[~dsr["muestra_descubrimiento"]]["psr_vs_0"].iloc[0])
        c4.metric("RQ2 · DSR de HML (N = 10)", f"{d10:.3f}",
                  delta=f"fuera de muestra PSR {fuera:.2f}", delta_color="off",
                  help="¿Era alfa de verdad? Sí con búsqueda modesta; después de 1991 ya no "
                       "se puede afirmar que sea positivo.")

    factores = [s for s in resumenes if s.startswith("factor_")]
    if factores:
        from components.metric_chart import grafico_resumen
        from state.session import cargar_config

        sid = factores[0]
        cfg = cargar_config(sid)
        st.markdown(seccion(f"Vista rápida · {cfg.get('factor', sid).upper()}",
                            "Sharpe del factor (media móvil de 36 meses) con las alarmas de los tres "
                            "detectores. El detalle, con filtros y zoom, en Factores de mercado."),
                    unsafe_allow_html=True)
        with st.container(border=True, key="card_resumen"):
            st.plotly_chart(grafico_resumen(serie(sid), cfg["fin_calibracion"],
                                            cargar_tabla(f"alarmas_{sid}"), DETECTORES_REAL),
                            config=CONFIG_PLOTLY)

    st.markdown(seccion("Cómo funciona"), unsafe_allow_html=True)
    st.markdown(
        """
<div class="sw-pasos">
  <div class="sw-paso"><span class="n">1</span><b>Métrica</b><span>Cada periodo el modelo produce
  una métrica con su error estándar: AUC, PSI o Sharpe.</span></div>
  <div class="sw-paso"><span class="n">2</span><b>Calibración</b><span>El umbral se fija para una
  tasa de falsas alarmas elegida (ARL0), sobre el histórico del propio modelo.</span></div>
  <div class="sw-paso"><span class="n">3</span><b>Vigilancia</b><span>El detector acumula evidencia
  periodo a periodo y alarma cuando la degradación es estadísticamente real.</span></div>
  <div class="sw-paso"><span class="n">4</span><b>Auditoría</b><span>Cada alarma lleva el hash de la
  configuración, de los datos y del código que la produjeron.</span></div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(seccion("Dos preguntas, dos herramientas",
                        "No se mezclan: una mide si el rendimiento murió, la otra si alguna vez existió."),
                unsafe_allow_html=True)
    st.markdown(
        """
<div class="sw-dos">
  <div class="sw-q"><div class="sw-eyebrow">RQ1 · Detectores secuenciales</div>
  <b>¿Se ha degradado el modelo?</b><span>Cuánto se tarda en confirmar una caída, a una tasa de
  falsas alarmas fijada. Se mide con verdad conocida: cambios inyectados de tamaño y fecha
  conocidos.</span></div>
  <div class="sw-q alt"><div class="sw-eyebrow">RQ2 · Deflated Sharpe</div>
  <b>¿Era alfa de verdad?</b><span>Si el rendimiento original supera lo que daría la mejor de N
  estrategias de puro ruido. Separa la suerte o la búsqueda de un rendimiento real.</span></div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(seccion("Explorar"), unsafe_allow_html=True)
    destinos = [
        ("pages/1_Salud_de_modelos.py", "Salud de modelos", ":material/monitor_heart:",
         "Todos los streams vigilados: umbrales calibrados, alarmas y huella de cada uno."),
        ("pages/3_Factores_de_mercado.py", "Factores de mercado", ":material/show_chart:",
         "La rama real: serie con alarmas, retardo sobre ruido real, RQ2 y un laboratorio en vivo."),
        ("pages/4_Banco_de_pruebas.py", "Banco de pruebas sintético", ":material/science:",
         "El resultado central: retardo por magnitud y la curva retardo frente a falsas alarmas."),
    ]
    for col, (ruta, titulo, icono, texto) in zip(st.columns(3), destinos):
        with col.container(border=True, key=f"card_nav_{ruta[6]}"):
            st.markdown(f"**{titulo}**")
            st.caption(texto)
            st.page_link(ruta, label=f"Abrir {titulo.lower()}", icon=icono)

    st.markdown(
        '<p class="sw-nota">Prototipo validado, no un sistema desplegado en un banco. Los '
        'resultados son sobre un banco sintético con verdad conocida y sobre ruido financiero '
        'real (factores de Kenneth French), no sobre modelos bancarios propietarios.</p>',
        unsafe_allow_html=True,
    )


navegacion = st.navigation(
    {
        "Resumen": [st.Page(inicio, title="Inicio", icon=":material/space_dashboard:", default=True)],
        "Monitorización": [
            st.Page("pages/1_Salud_de_modelos.py", title="Salud de modelos", icon=":material/monitor_heart:"),
        ],
        "Validación": [
            st.Page("pages/3_Factores_de_mercado.py", title="Factores de mercado",
                    icon=":material/show_chart:"),
            st.Page("pages/4_Banco_de_pruebas.py", title="Banco de pruebas sintético",
                    icon=":material/science:"),
        ],
        "Auditoría": [
            st.Page("pages/6_Informe_MRM.py", title="Validación del sistema",
                    icon=":material/verified_user:"),
        ],
    }
)
navegacion.run()

# Pie de la barra lateral: la huella del stream principal (config, datos, código).
_res = _resumenes()
if _res:
    st.sidebar.markdown(huella_lateral(next(iter(_res.values()))["huella"]), unsafe_allow_html=True)
