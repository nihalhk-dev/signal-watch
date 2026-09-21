"""Gráficos de retardo: la medición (sintética y sobre ruido real), la curva
retardo frente a falsas alarmas, y el laboratorio.

Convención en todos: abajo es mejor (menos retardo). Un marcador HUECO
significa que más del 20% de las series no detectaron dentro de la ventana,
así que el valor es una cota inferior del retardo, no una medición.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from components import COLOR, GRIS, GRIS_SUAVE, SIMBOLO, TINTA, TRAZO, estilo

TITULO_ESCENARIO = {"salto": "Salto brusco", "deriva": "Deriva gradual",
                    "cambio_varianza": "Cambio de varianza"}


def _simbolos(det: str, frac_censura) -> list[str]:
    return [SIMBOLO[det] + ("-open" if f > 0.2 else "") for f in frac_censura]


def grafico_retardo_real(retardo: pd.DataFrame, escenario: str, detectores: list[str],
                         en_anos: bool = True) -> go.Figure:
    """Retardo sobre ruido real de HML frente al tamaño de la caída inyectada."""
    e = retardo[retardo["escenario"] == escenario].sort_values("delta_sigma")
    deltas = sorted(e["delta_sigma"].unique())
    etiquetas = [f"{d:g}σ" for d in deltas]
    escala = 12.0 if en_anos else 1.0

    fig = go.Figure()
    realistas = [x for x, d in zip(etiquetas, deltas) if d <= 0.25 + 1e-9]
    if realistas:
        fig.add_vrect(x0=-0.5, x1=len(realistas) - 0.5, fillcolor=GRIS_SUAVE, line_width=0,
                      layer="below", annotation_text="caídas realistas de HML",
                      annotation_position="top left", annotation_font=dict(size=11, color=GRIS))
    for det in detectores:
        d = e[e["detector"] == det].set_index("delta_sigma").reindex(deltas)
        frac = (d["n_censurados"] / d["n_streams"]).to_numpy()
        fig.add_trace(go.Scatter(
            x=etiquetas, y=d["arl1_meses"] / escala, name=det, mode="lines+markers",
            line=dict(color=COLOR[det], dash=TRAZO[det], width=2.6),
            marker=dict(symbol=_simbolos(det, frac), size=11, color=COLOR[det],
                        line=dict(color=COLOR[det], width=1.6)),
            error_y=dict(type="data", symmetric=False,
                         array=((d["arl1_ic_high"] - d["arl1_meses"]) / escala).to_numpy(),
                         arrayminus=((d["arl1_meses"] - d["arl1_ic_low"]) / escala).to_numpy(),
                         color=COLOR[det], thickness=1.2, width=0),
            customdata=np.stack([d["arl1_meses"], d["delta_sharpe"], d["n_streams"],
                                 d["n_censurados"], d["n_excluidos_pre_tau"]], axis=-1),
            hovertemplate=(f"<b>{det}</b> · caída de %{{x}} (%{{customdata[1]:.2f}} de Sharpe)<br>"
                           "retardo medio: %{customdata[0]:.1f} meses<br>"
                           "series que detectan: %{customdata[2]} · no detectan: %{customdata[3]}<br>"
                           "falsas alarmas antes del cambio: %{customdata[4]}<extra></extra>"),
        ))
    fig.update_xaxes(title_text="Tamaño de la caída inyectada (σ de la serie mensual)")
    fig.update_yaxes(rangemode="tozero",
                     title_text=("Años" if en_anos else "Meses") + " hasta detectar  (↓ mejor)")
    return estilo(fig, alto=440)


def grafico_banco(punto: pd.DataFrame, escenarios: list[str], detectores: list[str],
                  horizonte: int = 60) -> go.Figure:
    """Banco sintético: un panel por escenario, una línea por detector."""
    fig = make_subplots(rows=1, cols=len(escenarios), shared_yaxes=True,
                        subplot_titles=[TITULO_ESCENARIO.get(e, e) for e in escenarios],
                        horizontal_spacing=0.04)
    for c, esc in enumerate(escenarios, start=1):
        e = punto[punto["escenario"] == esc].sort_values("delta_sigma")
        fig.add_hline(y=horizonte, line_dash="dot", line_color=GRIS, line_width=1, row=1, col=c)
        for det in detectores:
            d = e[e["detector"] == det]
            if d.empty:
                continue
            frac = (d["arl1_censurados"] / d["arl1_n_streams"]).to_numpy()
            fig.add_trace(go.Scatter(
                x=d["delta_sigma"], y=d["arl1"], name=det, legendgroup=det,
                showlegend=(c == 1), mode="lines+markers",
                line=dict(color=COLOR[det], dash=TRAZO[det], width=2.4),
                marker=dict(symbol=_simbolos(det, frac), size=10, color=COLOR[det],
                            line=dict(color=COLOR[det], width=1.6)),
                error_y=dict(type="data", symmetric=False,
                             array=(d["arl1_ic_high"] - d["arl1"]).to_numpy(),
                             arrayminus=(d["arl1"] - d["arl1_ic_low"]).to_numpy(),
                             color=COLOR[det], thickness=1.1, width=0),
                customdata=np.stack([d["arl0"], d["arl1_censurados"], d["arl1_n_streams"],
                                     d["arl1_excluidos_pre_tau"]], axis=-1),
                hovertemplate=(f"<b>{det}</b> · δ = %{{x}}σ<br>retardo %{{y:.1f}} pasos<br>"
                               "ARL0 del punto: %{customdata[0]:.1f}<br>"
                               "censuradas %{customdata[1]} de %{customdata[2]} · "
                               "falsas alarmas antes de τ %{customdata[3]}<extra></extra>"),
            ), row=1, col=c)
        fig.update_xaxes(title_text="δ (sigmas)", tickvals=[0.5, 1, 1.5, 2, 3], row=1, col=c)
    fig.update_yaxes(title_text="Retardo de detección (pasos, ↓ mejor)", row=1, col=1,
                     rangemode="tozero")
    estilo(fig, alto=480)
    # la leyenda sube por encima de los títulos de cada panel
    fig.update_layout(legend=dict(y=1.14), margin=dict(t=80))
    return fig


def grafico_curva_operativa(curvas: pd.DataFrame, tipo: str, escenario: str, delta: float,
                            detectores: list[str]) -> go.Figure:
    """La gráfica clásica de detección secuencial: retardo frente a tasa de
    falsas alarmas. Cada punto es un umbral: más a la derecha = menos falsas
    alarmas; más abajo = detecta antes. Lo ideal es abajo a la derecha."""
    sub = curvas[(curvas["tipo_metrica"] == tipo) & (curvas["escenario"] == escenario)
                 & (np.isclose(curvas["delta_sigma"], delta))]
    fig = go.Figure()
    for det in detectores:
        d = sub[sub["detector"] == det].sort_values("arl0")
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["arl0"], y=d["arl1"], name=det, mode="lines+markers",
            line=dict(color=COLOR[det], dash=TRAZO[det], width=2.4),
            marker=dict(symbol=SIMBOLO[det], size=11, color=COLOR[det]),
            customdata=np.stack([d["umbral"].fillna(-1), d["arl1_censurados"],
                                 d["arl1_n_streams"]], axis=-1),
            hovertemplate=(f"<b>{det}</b><br>ARL0 %{{x:.1f}} pasos hasta una falsa alarma<br>"
                           "retardo %{y:.1f} pasos<br>umbral %{customdata[0]:.3f} "
                           "(−1 = umbral fijo)<br>censuradas %{customdata[1]} de "
                           "%{customdata[2]}<extra></extra>"),
        ))
    fig.update_xaxes(title_text="ARL0: pasos medios hasta una falsa alarma (→ mejor)")
    fig.update_yaxes(title_text="Retardo de detección (↓ mejor)", rangemode="tozero")
    return estilo(fig, alto=420)


def grafico_demo(resultado: dict, detectores: list[str]) -> go.Figure:
    """Laboratorio: una serie de ruido real con una caída inyectada en τ."""
    v = np.asarray(resultado["valores"])
    x = np.arange(1, len(v) + 1)
    tau = resultado["tau"]
    fig = go.Figure()
    fig.add_vrect(x0=tau + 0.5, x1=len(v) + 0.5, fillcolor=GRIS_SUAVE, line_width=0,
                  layer="below", annotation_text="después del cambio",
                  annotation_position="top left", annotation_font=dict(size=11, color=GRIS))
    fig.add_trace(go.Scatter(x=x, y=v, mode="markers", name="Sharpe de cada mes",
                             marker=dict(size=5, color=GRIS, opacity=0.6),
                             hovertemplate="mes %{x}<br>Sharpe %{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=resultado["nivel"], mode="lines",
                             name="nivel inyectado (sin ruido)",
                             line=dict(color=TINTA, width=2.6),
                             hovertemplate="mes %{x}<br>nivel %{y:.2f}<extra></extra>"))
    fig.add_vline(x=tau + 0.5, line_color=TINTA, line_dash="dash", line_width=1.4)
    for i, det in enumerate(detectores):
        info = resultado["detectores"].get(det)
        if not info or info["instante"] is None:
            continue
        fig.add_vline(x=info["instante"], line_color=COLOR[det], line_dash=TRAZO[det], line_width=2)
        fig.add_trace(go.Scatter(
            x=[info["instante"]], y=[15.5 - 2.4 * i], mode="markers+text", name=det,
            text=[f" {det}"], textposition="middle right",
            marker=dict(symbol=SIMBOLO[det], size=13, color=COLOR[det],
                        line=dict(color="white", width=1.2)),
            hovertemplate=f"<b>{det}</b><br>alarma en el mes %{{x}}<br>{info['lectura']}<extra></extra>",
        ))
    fig.update_xaxes(title_text="Mes de la serie simulada")
    fig.update_yaxes(range=[-18, 18], title_text="Sharpe anualizado")
    return estilo(fig, alto=430)


def grafico_distribucion(filas: pd.DataFrame, detectores: list[str]) -> go.Figure:
    """Laboratorio: la distribución del retardo en muchas series, no solo la media."""
    fig = go.Figure()
    for det in detectores:
        d = filas[(filas["detector"] == det) & (filas["resultado"] == "detecta")]
        fig.add_trace(go.Box(
            y=d["retardo_meses"], name=det, marker_color=COLOR[det], boxmean=True,
            boxpoints="outliers", line=dict(width=1.6),
            hovertemplate=f"<b>{det}</b><br>%{{y}} meses<extra></extra>",
        ))
    fig.update_yaxes(title_text="Meses hasta detectar (↓ mejor)", rangemode="tozero")
    fig.update_layout(showlegend=False)
    return estilo(fig, alto=400)
