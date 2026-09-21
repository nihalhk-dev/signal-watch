"""Gráficos de la métrica de un stream: la serie en el tiempo y el DSR.

Todo lo que dibujan estas funciones viene ya calculado (tablas selladas o
funciones de src/). Aquí solo se filtra por fechas, se agrega para la vista
anual y se dibuja.
"""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components import CONFIG_PLOTLY, GRIS, GRIS_SUAVE, TINTA, estilo  # noqa: F401
from components.alarm_markers import capa_alarmas


def grafico_serie(serie: pd.DataFrame, fin_referencia: str, alarmas: pd.DataFrame,
                  detectores: list[str], periodo: tuple[int, int], suavizado: int,
                  vista: str, mu0: float) -> go.Figure:
    """La serie del stream, interactiva.

    Vista mensual: cada punto es el valor de un mes (lo que ven los
    detectores), con su error estándar y los días de negociación al pasar el
    ratón, y una media móvil SOLO para leer la forma. Vista anual: la media
    de cada año, para ver los regímenes de un vistazo.

    La media móvil se calcula sobre la serie COMPLETA y luego se recorta al
    periodo, para que el borde izquierdo del periodo no salga truncado.
    """
    ini, fin = pd.Timestamp(f"{periodo[0]}-01-01"), pd.Timestamp(f"{periodo[1]}-12-31")
    media_movil = serie["value"].rolling(suavizado).mean()
    s = serie.loc[ini:fin]
    mm = media_movil.loc[ini:fin]
    corte = pd.Timestamp(fin_referencia)

    fig = go.Figure()
    if ini < corte:
        fig.add_vrect(x0=max(ini, s.index.min()), x1=min(corte, fin), fillcolor=GRIS_SUAVE,
                      line_width=0, layer="below",
                      annotation_text="referencia: solo calibra", annotation_position="top left",
                      annotation_font=dict(size=11, color=GRIS))

    if vista == "Anual":
        anual = s["value"].groupby(s.index.year).agg(["mean", "size"])
        fig.add_trace(go.Bar(
            x=pd.to_datetime([f"{a}-07-01" for a in anual.index]), y=anual["mean"],
            name="media del año", marker_color=GRIS, opacity=0.75,
            customdata=np.stack([anual.index, anual["size"]], axis=-1),
            hovertemplate="<b>%{customdata[0]}</b><br>Sharpe medio %{y:.2f}"
                          "<br>%{customdata[1]} meses<extra></extra>",
        ))
        rango_y = max(4.0, float(np.nanmax(np.abs(anual["mean"]))) * 1.35)
    else:
        fig.add_trace(go.Scatter(
            x=s.index, y=s["value"], mode="markers", name="Sharpe de cada mes",
            marker=dict(size=5, color=GRIS, opacity=0.55),
            customdata=np.stack([s["value_se"], s["n_obs"]], axis=-1),
            hovertemplate="<b>%{x|%b %Y}</b><br>Sharpe %{y:.2f} ± %{customdata[0]:.2f}"
                          "<br>%{customdata[1]} días de negociación<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=mm.index, y=mm, mode="lines", name=f"media móvil {suavizado} meses",
            line=dict(color=TINTA, width=2.6),
            hovertemplate="%{x|%b %Y}<br>media móvil %{y:.2f}<extra></extra>",
        ))
        rango_y = 18.0

    fig.add_hline(y=mu0, line_dash="dash", line_color=TINTA, line_width=1,
                  annotation_text=f"μ0 de referencia = {mu0:.2f}",
                  annotation_position="bottom right", annotation_font=dict(size=11))
    fig.add_hline(y=0, line_color=GRIS, line_width=0.8, opacity=0.6)

    if alarmas is not None and not alarmas.empty:
        a = alarmas[pd.to_datetime(alarmas["fecha"]).between(ini, fin)]
        capa_alarmas(fig, a, detectores, y_arriba=rango_y * 0.92, separacion=rango_y * 0.1)

    fig.update_yaxes(range=[-rango_y, rango_y], title_text="Sharpe anualizado", zeroline=False)
    fig.update_xaxes(
        range=[ini, fin],
        rangeslider=dict(visible=True, thickness=0.07),
        rangeselector=dict(buttons=[
            dict(count=5, label="5A", step="year", stepmode="backward"),
            dict(count=10, label="10A", step="year", stepmode="backward"),
            dict(count=20, label="20A", step="year", stepmode="backward"),
            dict(step="all", label="Todo"),
        ], x=1, xanchor="right", y=1.02, yanchor="bottom"),
    )
    estilo(fig, alto=580)
    # leyenda a la izquierda y botones de periodo a la derecha, sin pisarse
    fig.update_layout(margin=dict(t=70))
    return fig


def grafico_resumen(serie: pd.DataFrame, fin_referencia: str, alarmas: pd.DataFrame | None,
                    detectores: list[str], ventana: int = 36) -> go.Figure:
    """Vista rápida para la portada: la media móvil de toda la historia, con
    la referencia sombreada y las alarmas encima. Sin puntos mensuales ni
    controles: es el resumen; el detalle está en la página del factor."""
    mm = serie["value"].rolling(ventana).mean().dropna()
    corte = pd.Timestamp(fin_referencia)
    fig = go.Figure()
    fig.add_vrect(x0=serie.index.min(), x1=corte, fillcolor=GRIS_SUAVE, line_width=0,
                  layer="below", annotation_text="referencia (calibra)",
                  annotation_position="top left", annotation_font=dict(size=11, color=GRIS))
    fig.add_trace(go.Scatter(
        x=mm.index, y=mm, mode="lines", name=f"Sharpe, media móvil {ventana} meses",
        line=dict(color="#0F4C81", width=2.4), fill="tozeroy", fillcolor="rgba(15,76,129,0.08)",
        hovertemplate="%{x|%b %Y}<br>media %{y:.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=GRIS, line_width=0.8, opacity=0.6)
    tope = float(mm.abs().max()) * 1.6
    if alarmas is not None and not alarmas.empty:
        capa_alarmas(fig, alarmas, detectores, y_arriba=tope, separacion=tope * 0.14)
    fig.update_yaxes(range=[-tope * 0.9, tope * 1.1], title_text="Sharpe anualizado", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return estilo(fig, alto=330)


def grafico_dsr(sr_anual: float, t: int, asimetria: float, curtosis: float,
                n_elegido: int, n_max: int = 1000) -> tuple[go.Figure, float, int | None]:
    """DSR en función del número de pruebas N, con el N elegido marcado.

    Usa las funciones de src/ (psr, sr0_maximo_esperado): la app no
    reimplementa ninguna fórmula. Devuelve también el DSR en el N elegido y
    el N máximo que aguanta por encima de 0,95.
    """
    from signal_watch.evaluation.deflated_sharpe import psr, sr0_maximo_esperado

    sr = sr_anual / math.sqrt(12)
    ns = np.unique(np.round(np.logspace(0, math.log10(n_max), 200)).astype(int))
    dsr = [psr(sr, sr0_maximo_esperado(int(n), t), t, asimetria, curtosis) for n in ns]
    dsr_elegido = psr(sr, sr0_maximo_esperado(n_elegido, t), t, asimetria, curtosis)
    aguanta = [int(n) for n, d in zip(ns, dsr) if d >= 0.95]
    n_corte = max(aguanta) if aguanta else None

    fig = go.Figure()
    fig.add_hrect(y0=0.95, y1=1.0, fillcolor="rgba(27,175,122,0.10)", line_width=0, layer="below")
    fig.add_hline(y=0.95, line_dash="dash", line_color=TINTA, line_width=1,
                  annotation_text="0,95", annotation_position="bottom left")
    fig.add_trace(go.Scatter(
        x=ns, y=dsr, mode="lines", name="DSR", line=dict(color="#2a78d6", width=3),
        hovertemplate="N = %{x}<br>DSR = %{y:.3f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[n_elegido], y=[dsr_elegido], mode="markers", name=f"N elegido = {n_elegido}",
        marker=dict(size=14, color="#eb6834", line=dict(color="white", width=1.5)),
        hovertemplate="N = %{x}<br>DSR = %{y:.3f}<extra></extra>",
    ))
    fig.update_xaxes(type="log", title_text="N = estrategias probadas antes de quedarse con esta")
    fig.update_yaxes(range=[0, 1.02], title_text="DSR")
    return estilo(fig, alto=420), dsr_elegido, n_corte
