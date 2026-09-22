"""Salud de modelos: todos los streams vigilados, en una pantalla.

La lista no está escrita a mano: sale de state.session.streams_monitorizados().
Un stream nuevo —un scorecard, una señal de ML— aparece aquí en cuanto tiene
su YAML con bloque `monitorizacion:` y se ha corrido scripts/run_monitoring.py.

Lo que NO hay, a propósito: un semáforo verde/ámbar/rojo. Traducir alarmas
a un veredicto de negocio exige reglas declaradas y versionadas
(monitoring/verdict.py en el plan), y no se han escrito. Inventarse un
semáforo sería presentar como regla algo que nadie ha decidido.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import CONFIG_PLOTLY, GRIS, TINTA, cabecera, estilo
from components.alarm_markers import capa_alarmas
from state.session import cargar_tabla, resumen_stream, serie, streams_monitorizados

st.markdown(cabecera(
    "Monitorización",
    "Salud de modelos",
    "Cada stream es la métrica de rendimiento de un modelo. El detector no ve el modelo: ve su "
    "métrica. Por eso el mismo monitor sirve para un scorecard, un factor o una señal de ML.",
), unsafe_allow_html=True)


@st.cache_data
def _resumen(sid: str) -> dict:
    return resumen_stream(sid)


@st.cache_data
def _serie(sid: str) -> pd.DataFrame:
    return serie(sid)


streams = streams_monitorizados()
if not streams:
    st.info("Todavía no hay ningún stream monitorizado. Ejecuta `python scripts/run_monitoring.py`.")
    st.stop()

st.sidebar.header("Vista")
anos = st.sidebar.slider("Ventana del gráfico (años recientes)", 5, 40, 15)

resumenes = {sid: _resumen(sid) for sid in streams}
k1, k2, k3, k4 = st.columns(4)
k1.metric("Streams vigilados", len(streams))
k2.metric("Alarmas registradas", sum(int(r["detectores"]["alarmas"].sum())
                                     for r in resumenes.values() if len(r["detectores"])))
k3.metric("Esperadas por azar", f"{sum(r['esperadas_por_azar'] for r in resumenes.values()):.1f}",
          delta="por detector", delta_color="off",
          help="Meses vigilados / ARL0. Una alarma solo cuenta si se sale de lo esperable.")
k4.metric("Trazabilidad", "R7", delta="en cada alarma", delta_color="off",
          help="Cada alarma lleva config_hash, hash_datos y commit.")

for stream_id, r in resumenes.items():
    det = r["detectores"]
    peor = "baja" if r["direction"] == "lower_is_worse" else "sube"
    with st.container(border=True, key=f"card_{stream_id}"):
        st.markdown(
            f'<div class="sw-sec" style="margin-top:0.2rem"><h3>{stream_id}</h3>'
            f'<p>{r["metrica"]} · peor si {peor} · {r["frecuencia"]} · fuente {r["fuente"]}</p>'
            f'<span class="sw-tag">Referencia (solo calibra): {r["referencia"]}</span>'
            f'<span class="sw-tag">Vigilancia: {r["vigilancia"]}</span></div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Meses vigilados", r["meses_vigilados"])
        c2.metric("ARL0 objetivo", f"{r['arl0_objetivo']:.0f} meses",
                  help="Una falsa alarma cada tanto, por diseño.")
        c3.metric("Alarmas (todos los detectores)", int(det["alarmas"].sum()) if len(det) else 0)
        c4.metric("Esperadas por azar, por detector", f"{r['esperadas_por_azar']:.1f}")

        s = _serie(stream_id)
        desde = s.index.max() - pd.DateOffset(years=anos)
        s = s.loc[desde:]
        alarmas = cargar_tabla(f"alarmas_{stream_id}")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=s.index, y=s["value"], mode="markers", name="valor mensual",
                                 marker=dict(size=4, color=GRIS, opacity=0.5),
                                 hovertemplate="%{x|%b %Y}<br>%{y:.2f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=s.index, y=s["value"].rolling(12).mean(), mode="lines",
                                 name="media móvil 12 meses", line=dict(color=TINTA, width=2),
                                 hovertemplate="%{x|%b %Y}<br>media %{y:.2f}<extra></extra>"))
        if alarmas is not None:
            a = alarmas[pd.to_datetime(alarmas["fecha"]) >= desde]
            tope = float(s["value"].abs().max()) * 1.05
            capa_alarmas(fig, a, list(det["detector"]), y_arriba=tope, separacion=tope * 0.12)
        st.plotly_chart(estilo(fig, alto=300), config=CONFIG_PLOTLY)

        st.dataframe(det, hide_index=True)

        # Si el stream es la métrica de un modelo con baseline (la señal de ML),
        # su tabla resumen_<stream>.csv enseña si el modelo le gana o no.
        frente = cargar_tabla(f"resumen_{stream_id}")
        if frente is not None:
            with st.expander("¿Es bueno el modelo? Frente a sus listones", icon=":material/compare_arrows:"):
                st.dataframe(
                    frente[["modelo", "tramo", "desde", "hasta", "meses", "acierto",
                            "sharpe_anual_bruto", "sharpe_anual_neto", "cambios_por_ano", "psr_neto_vs_0"]]
                    .rename(columns={"sharpe_anual_bruto": "Sharpe bruto", "sharpe_anual_neto": "Sharpe neto",
                                     "cambios_por_ano": "cambios/año", "psr_neto_vs_0": "PSR vs 0"}),
                    hide_index=True,
                )
                st.caption("Filas «ML − …»: diferencia de retornos mensuales netos; su PSR ≥ 0,95 "
                           "querría decir que el ML le gana de verdad a ese listón. El monitor vigila "
                           "el Sharpe NETO del modelo; si el modelo tiene habilidad lo dice esta tabla, "
                           "no los detectores.")
                estab = cargar_tabla(f"estabilidad_pesos_{stream_id}")
                if estab is not None:
                    st.dataframe(estab.drop(columns=[c for c in ("config_hash", "hash_datos", "commit",
                                                                 "generado_en") if c in estab]),
                                 hide_index=True)
                    st.caption("Pesos del modelo entrenado en dos tramos que no se solapan. Un efecto "
                               "real mantiene el signo; con 6 características, ~3 coincidencias es lo "
                               "que daría el azar.")

        with st.expander("Huella de reproducibilidad (R7)", icon=":material/fingerprint:"):
            if r["huella"]:
                st.markdown(
                    f"- `config_hash` **{r['huella']['config_hash']}**: los parámetros exactos\n"
                    f"- `hash_datos` **{r['huella']['hash_datos']}**: el contenido exacto de los datos\n"
                    f"- `commit` **{r['huella']['commit']}**: el código que produjo estas tablas\n\n"
                    "Mismo par de hashes ⇒ mismas alarmas. Así se puede reproducir cualquiera de ellas."
                )
            else:
                st.markdown("Sin tabla de calibración.")

st.caption("ARL0 = meses medios hasta una falsa alarma. Todos los detectores de un stream se calibran "
           "al mismo objetivo; el de una sola observación (Shewhart) solo alcanza escalones discretos. "
           "Sin semáforo a propósito: las reglas de veredicto de negocio no se han definido.")
