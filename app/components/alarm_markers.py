"""Capa de alarmas: marcadores y líneas verticales encima de cualquier serie.

Cada detector tiene su color, su marcador y su fila propia en la parte alta
del gráfico, así que se distinguen aunque se superpongan en el tiempo. Al
pasar el ratón se ve la fecha, el valor del mes, el estadístico del
detector y el umbral con el que saltó.
"""

import pandas as pd
import plotly.graph_objects as go

from components import COLOR, SIMBOLO


def capa_alarmas(fig: go.Figure, alarmas: pd.DataFrame, detectores: list[str],
                 y_arriba: float, separacion: float) -> go.Figure:
    if alarmas is None or alarmas.empty:
        return fig
    for i, det in enumerate(detectores):
        propias = alarmas[alarmas["detector"] == det]
        if propias.empty:
            continue
        fechas = pd.to_datetime(propias["fecha"])
        for f in fechas:
            fig.add_vline(x=f.to_pydatetime(), line_width=1, line_dash="dot",
                          line_color=COLOR[det], opacity=0.45)
        fig.add_trace(
            go.Scatter(
                x=fechas,
                y=[y_arriba - i * separacion] * len(propias),
                mode="markers",
                name=f"alarma {det}",
                legendgroup=det,
                marker=dict(symbol=SIMBOLO[det], size=13, color=COLOR[det],
                            line=dict(color="white", width=1.2)),
                customdata=propias[["valor", "estadistico", "umbral", "n_alarma"]].to_numpy(),
                hovertemplate=(
                    f"<b>{det}</b> · alarma nº %{{customdata[3]}}<br>"
                    "%{x|%b %Y}<br>"
                    "Sharpe del mes: %{customdata[0]:.2f}<br>"
                    "estadístico %{customdata[1]:.2f} > umbral %{customdata[2]:.2f}"
                    "<extra></extra>"
                ),
            )
        )
    return fig
