"""Componentes de la app: gráficos interactivos (Plotly) y filtros.

Aquí vive la IDENTIDAD VISUAL compartida, para que todas las páginas hablen
el mismo idioma: cada detector tiene siempre el mismo color, el mismo
marcador y el mismo trazo, en la app y en las figuras de la memoria
(reporting/figures.py). La paleta está validada para daltonismo (peor par
ΔE 9,2 en modo estricto), y además cada detector lleva marcador y trazo
propios, para que nunca se distinga solo por el color.

Las figuras OFICIALES de la memoria siguen saliendo de reporting/figures.py
(R9). Esto es la capa de exploración de la app: los mismos datos, para
mirarlos con zoom, filtros y valores al pasar el ratón.
"""

from html import escape

from signal_watch.reporting.figures import COLORES

COLOR = {
    "CUSUM": COLORES["CUSUM"],
    "Page-Hinkley": COLORES["Page-Hinkley"],
    "Shewhart": COLORES["3-sigma"],
    "3-sigma": COLORES["3-sigma"],
    "UmbralFijo (PSI>0.25)": COLORES["UmbralFijo (PSI>0.25)"],
}
SIMBOLO = {  # marcadores de Plotly
    "CUSUM": "circle", "Page-Hinkley": "square", "Shewhart": "triangle-up",
    "3-sigma": "triangle-up", "UmbralFijo (PSI>0.25)": "x",
}
TRAZO = {  # dash de Plotly
    "CUSUM": "solid", "Page-Hinkley": "dash", "Shewhart": "dot",
    "3-sigma": "dot", "UmbralFijo (PSI>0.25)": "dashdot",
}
DETECTORES_REAL = ["CUSUM", "Page-Hinkley", "Shewhart"]
GRIS = "#8a8983"
GRIS_SUAVE = "rgba(138,137,131,0.14)"
TINTA = "#52514e"
FUENTE = "Inter, system-ui, -apple-system, Segoe UI, sans-serif"


def estilo(fig, alto: int = 420, titulo: str | None = None):
    """Ajustes comunes a todos los gráficos. No fija fondos: st.plotly_chart
    aplica el tema de Streamlit (claro u oscuro) por encima."""
    fig.update_layout(
        height=alto,
        margin=dict(l=10, r=10, t=60 if titulo else 30, b=10),
        font=dict(family=FUENTE, size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    title_text=""),
        hoverlabel=dict(font=dict(family=FUENTE, size=12)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    if titulo:
        fig.update_layout(title=dict(text=titulo, x=0, xanchor="left", font=dict(size=15)))
    return fig


CONFIG_PLOTLY = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


# ── Bloques HTML de la interfaz (estilos en app/assets/styles.css) ──────
# Solo maquetan texto: ningún número se calcula aquí (R6).

def cabecera(eyebrow: str, titulo: str, texto: str, etiquetas: list[str] | None = None) -> str:
    """Cabecera común de página: rótulo pequeño, título, una frase y etiquetas."""
    tags = "".join(f'<span class="sw-tag">{escape(e)}</span>' for e in (etiquetas or []))
    return (f'<div class="sw-head"><div class="sw-eyebrow">{escape(eyebrow)}</div>'
            f'<h1>{escape(titulo)}</h1><p>{escape(texto)}</p>{tags}</div>')


def seccion(titulo: str, texto: str | None = None) -> str:
    """Título de sección con subtítulo opcional."""
    sub = f"<p>{escape(texto)}</p>" if texto else ""
    return f'<div class="sw-sec"><h3>{escape(titulo)}</h3>{sub}</div>'


def marca_lateral() -> str:
    """Nombre del producto bajo el logo de la barra lateral."""
    return ('<div class="sw-brand"><b>Signal Watch</b>'
            '<span>Monitorización de rendimiento de modelos</span></div>')


def huella_lateral(huella: dict | None) -> str:
    """Caja de trazabilidad (R7) al pie de la barra lateral."""
    if not huella:
        return ""
    filas = "<br>".join(f"{k} <code>{escape(str(v))}</code>" for k, v in huella.items())
    return f'<div class="sw-huella"><b>Trazabilidad R7</b><br>{filas}</div>'
