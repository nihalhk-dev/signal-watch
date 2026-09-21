"""Filtros de la barra lateral. Todos los gráficos y cifras de la página
se recalculan con lo que se elige aquí."""

import streamlit as st

from components import DETECTORES_REAL


def filtros_serie(anio_min: int, anio_max: int, clave: str = "serie") -> dict:
    """Periodo, detectores, vista y suavizado para una serie en el tiempo."""
    st.sidebar.header("Filtros")
    periodo = st.sidebar.slider("Periodo", min_value=anio_min, max_value=anio_max,
                                value=(anio_min, anio_max), key=f"{clave}_periodo",
                                help="Recorta gráficos, alarmas y cifras al intervalo elegido.")
    detectores = st.sidebar.multiselect("Detectores", DETECTORES_REAL, default=DETECTORES_REAL,
                                        key=f"{clave}_det")
    vista = st.sidebar.radio("Vista", ["Mensual", "Anual"], horizontal=True, key=f"{clave}_vista",
                             help="Mensual: lo que ven los detectores. Anual: media de cada año.")
    suavizado = st.sidebar.select_slider("Suavizado (media móvil, meses)",
                                         options=[12, 24, 36, 60], value=36, key=f"{clave}_suav",
                                         help="Solo para leer la forma: los detectores nunca "
                                              "ven la media móvil. Con 12 meses la línea es casi "
                                              "todo ruido.")
    st.sidebar.caption("Sin τ en datos reales, una alarma se lee como «cae en la ventana donde "
                       "la literatura sitúa X», nunca como una detección.")
    return {"periodo": periodo, "detectores": detectores or DETECTORES_REAL[:1],
            "vista": vista, "suavizado": suavizado}
