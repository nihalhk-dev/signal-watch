"""
reporting/figures.py

Todas las figuras del proyecto (memoria, informe, app) viven aquí.
Responsabilidad única: DIBUJAR. Funciones puras que reciben datos y
devuelven un Figure — nunca plt.show(), nunca savefig() aquí dentro.
Separar cálculo (evaluation/*) de dibujo (aquí) es lo que permite
testear el cálculo y regenerar las figuras sin recalcular (R6/R9).

Paleta categórica validada para small multiples (modo all-pairs, que es
el estricto): peor par en visión con deficiencia de color ΔE 9.2, peor
par en visión normal ΔE 16.3 — ambos por encima de sus umbrales. Además
cada serie lleva marcador y estilo de línea propios, para que la figura
siga siendo legible impresa en blanco y negro.
"""

import matplotlib.pyplot as plt

COLORES = {
    "CUSUM": "#2a78d6",                  # azul
    "Page-Hinkley": "#eb6834",           # naranja
    "3-sigma": "#1baf7a",                # aqua
    "UmbralFijo (PSI>0.25)": "#4a3aa7",  # violeta
}
MARCADORES = {
    "CUSUM": "o", "Page-Hinkley": "s",
    "3-sigma": "^", "UmbralFijo (PSI>0.25)": "X",
}
LINEAS = {
    "CUSUM": "-", "Page-Hinkley": "--",
    "3-sigma": "-", "UmbralFijo (PSI>0.25)": ":",
}
ORDEN = ["CUSUM", "Page-Hinkley", "3-sigma", "UmbralFijo (PSI>0.25)"]
ESCENARIOS = ["salto", "deriva", "cambio_varianza"]
TITULOS = {
    "salto": "Salto brusco",
    "deriva": "Deriva gradual",
    "cambio_varianza": "Cambio de varianza",
}
TINTA_1, TINTA_2, TINTA_3 = "#0b0b0b", "#52514e", "#8a8983"

# Rama real: el detector de una sola observación se llama "Shewhart" (su k
# está calibrado y ya no es 3). Es la misma familia que "3-sigma", así que
# hereda su color, marcador y línea: la identidad visual sigue a la regla.
COLORES["Shewhart"] = COLORES["3-sigma"]
MARCADORES["Shewhart"] = MARCADORES["3-sigma"]
LINEAS["Shewhart"] = ":"
ORDEN_REAL = ["CUSUM", "Page-Hinkley", "Shewhart"]


def fig_retardo_vs_magnitud(
    df_punto,
    tipo_metrica: str,
    arl0_referencia: float,
    horizonte: int = 60,
    notas: dict | None = None,
):
    """La figura central: retardo de detección frente a magnitud del
    cambio, un panel por escenario, una línea por detector.

    df_punto debe venir ya filtrado a UN punto de operación por detector,
    elegido a ARL0 comparable (ver delay_curves.seleccionar_punto_comparable).
    Comparar detectores a ARL0 distintos no significa nada: el que más
    falsas alarmas permite siempre parece el más rápido.

    Marcador relleno = medición fiable. Marcador HUECO = más del 20% de
    los streams están censurados, así que el valor es una COTA INFERIOR
    del retardo, no un retardo medido. Esa distinción va en la figura y
    no en una nota al pie a propósito: un retardo censurado presentado
    como un número normal es el error clásico de este tipo de análisis.
    """
    notas = notas or {}
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), sharey=True)

    for ax, escenario in zip(axes, ESCENARIOS):
        e = df_punto[df_punto["escenario"] == escenario].sort_values("delta_sigma")

        ax.axhline(horizonte, color=TINTA_3, lw=1, ls=(0, (1, 3)), zorder=1)

        for det in ORDEN:
            d = e[e["detector"] == det]
            if d.empty:
                continue
            x = d["delta_sigma"].to_numpy()
            y = d["arl1"].to_numpy()
            err = (d["arl1_ic_high"] - d["arl1"]).to_numpy()
            frac_cens = (d["arl1_censurados"] / d["arl1_n_streams"]).to_numpy()

            ax.errorbar(x, y, yerr=err, fmt="none", ecolor=COLORES[det],
                        elinewidth=1, alpha=0.45, capsize=0, zorder=2)
            ax.plot(x, y, LINEAS[det], color=COLORES[det], lw=2, zorder=3)
            for xi, yi, fc in zip(x, y, frac_cens):
                ax.plot(xi, yi, MARCADORES[det], color=COLORES[det],
                        mfc=COLORES[det] if fc < 0.2 else "#fcfcfb",
                        mec=COLORES[det], mew=1.6, ms=8, zorder=4)

        ax.set_title(TITULOS[escenario], fontsize=11, color=TINTA_1, pad=10)
        if escenario in notas:
            ax.text(0.5, 1.005, notas[escenario], transform=ax.transAxes,
                    ha="center", va="bottom", fontsize=8, style="italic",
                    color=TINTA_3)
        ax.set_xlabel("Magnitud del cambio (δ, en sigmas)", fontsize=9.5, color=TINTA_2)
        ax.set_xticks([0.5, 1.0, 1.5, 2.0, 3.0])
        ax.grid(axis="y", color="#e6e5e1", lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color("#d8d7d2")
        ax.tick_params(colors=TINTA_2, labelsize=9)

    axes[0].set_ylabel("Retardo de detección (pasos)\n← mejor",
                       fontsize=9.5, color=TINTA_2)
    axes[0].set_ylim(0, horizonte * 1.15)
    axes[0].text(0.42, horizonte + 1.5, "ventana observable (sin detección)",
                 fontsize=8, color=TINTA_3, va="bottom", ha="left")

    presentes = set(df_punto["detector"])
    manejadores = [
        plt.Line2D([], [], color=COLORES[d], marker=MARCADORES[d], ls=LINEAS[d],
                   lw=2, ms=8, label=d)
        for d in ORDEN if d in presentes
    ]
    manejadores.append(
        plt.Line2D([], [], color=TINTA_3, marker="o", ls="none", ms=8,
                   mfc="#fcfcfb", mec=TINTA_3,
                   label="marcador hueco: >20% censurado (cota inferior)")
    )
    fig.legend(handles=manejadores, loc="upper center", ncol=len(manejadores),
               frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.055),
               labelcolor=TINTA_2)

    fig.suptitle(
        f"{tipo_metrica.upper()} — retardo de detección por magnitud del cambio, "
        f"a tasa de falsas alarmas igualada (ARL0 ≈ {arl0_referencia:.0f})",
        fontsize=12.5, color=TINTA_1, y=0.99,
    )
    fig.tight_layout(rect=(0, 0.09, 1, 0.95))
    return fig

def fig_rama_real(
    serie,
    alarmas,
    retardo,
    fin_calibracion: str,
    arl0_objetivo: float,
    esperadas_por_azar: float,
    ventana_media: int = 36,
):
    """La figura de la rama real, en una sola pieza.

    Arriba — la serie mensual de HML entera (1963-2026): cada punto es el
    Sharpe de un mes (lo que ven los detectores), la línea es una media
    móvil SOLO para leer la forma (los detectores nunca la ven), y la
    referencia 1963-1990 va sombreada porque solo calibra, nunca se vigila.
    La media es de 36 meses y no de 12 a propósito: con σ ≈ 5,7, una media
    de 12 meses fluctúa ±1,6 por puro azar y sus picos parecerían regímenes
    que no existen; la de 36 (±0,95) deja ver los tramos reales.

    En medio — una franja por detector con sus alarmas 1991-2026. Sin τ,
    esto se lee como "la alarma cae en la ventana donde la literatura sitúa
    X", nunca como una detección. El número esperado por puro azar va en la
    propia figura, para que nadie cuente alarmas sin esa referencia.

    Abajo — lo que SÍ es una medición: el retardo ante caídas inyectadas de
    tamaño conocido sobre el ruido real, en años, con la franja de las
    caídas realistas de HML (0,15-0,25σ) marcada.

    Entradas:
      serie    DataFrame con índice fecha (datetime) y columna "sharpe"
      alarmas  DataFrame con columnas "detector" y "fecha"
      retardo  DataFrame con detector, escenario, delta_sigma, arl1_meses,
               arl1_ic_low, arl1_ic_high, n_censurados, n_streams
    """
    import matplotlib.dates as mdates
    import numpy as np
    import pandas as pd

    fig = plt.figure(figsize=(13.5, 9.6))
    rejilla = fig.add_gridspec(3, 2, height_ratios=[3.1, 1.0, 3.4], hspace=0.35, wspace=0.12)
    ax_serie = fig.add_subplot(rejilla[0, :])
    ax_alarmas = fig.add_subplot(rejilla[1, :], sharex=ax_serie)
    ax_salto = fig.add_subplot(rejilla[2, 0])
    ax_deriva = fig.add_subplot(rejilla[2, 1], sharey=ax_salto)

    corte = pd.Timestamp(fin_calibracion)
    inicio = serie.index.min()
    fin = serie.index.max()

    def _estilo(ax):
        ax.grid(axis="y", color="#e6e5e1", lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color("#d8d7d2")
        ax.tick_params(colors=TINTA_2, labelsize=9)

    # ── Arriba: la serie ──────────────────────────────────────────────
    ax = ax_serie
    ax.axvspan(inicio, corte, color="#f1f0ec", zorder=0, lw=0)
    ax.text(inicio + (corte - inicio) / 2, 16.2, "referencia 1963-1990\n(solo calibra, no se vigila)",
            ha="center", va="top", fontsize=8.5, color=TINTA_2)
    ax.text(corte + (fin - corte) / 2, 16.2, "vigilancia 1991-2026",
            ha="center", va="top", fontsize=8.5, color=TINTA_2)
    ax.axhline(0, color="#d8d7d2", lw=0.8, zorder=1)
    mu0 = serie.loc[:corte, "sharpe"].mean()
    ax.axhline(mu0, color=TINTA_2, lw=1, ls=(0, (4, 3)), zorder=2)
    ax.text(fin, mu0 + 0.9, f"μ0 de referencia = {mu0:.2f}", ha="right", va="bottom",
            fontsize=8, color=TINTA_2, zorder=5,
            bbox=dict(boxstyle="square,pad=0.15", fc="#fcfcfb", ec="none"))
    ax.plot(serie.index, serie["sharpe"], "o", ms=2.2, color=TINTA_3, alpha=0.45,
            mec="none", zorder=2, label="Sharpe de cada mes (lo que ven los detectores)")
    media = serie["sharpe"].rolling(ventana_media).mean()
    ax.plot(media.index, media, color=TINTA_1, lw=2, zorder=3,
            label=f"media móvil {ventana_media} meses (solo para leer la forma)")
    ax.set_ylim(-18, 18)
    ax.set_ylabel("Sharpe anualizado\ndel mes", fontsize=9.5, color=TINTA_2)
    ax.legend(loc="lower left", frameon=False, fontsize=8.5, labelcolor=TINTA_2)
    ax.set_title("HML mensual, 1963-2026: el ruido de cada mes es mucho mayor que los cambios de régimen",
                 fontsize=11, color=TINTA_1, loc="left", pad=8)
    _estilo(ax)
    plt.setp(ax.get_xticklabels(), visible=False)

    # ── En medio: las alarmas ─────────────────────────────────────────
    ax = ax_alarmas
    ax.axvspan(inicio, corte, color="#f1f0ec", zorder=0, lw=0)
    fechas_alarma = pd.to_datetime(alarmas["fecha"]) if len(alarmas) else pd.Series([], dtype="datetime64[ns]")
    for i, det in enumerate(ORDEN_REAL):
        y = len(ORDEN_REAL) - 1 - i
        ax.axhline(y, color="#ecebe7", lw=0.8, zorder=1)
        sel = fechas_alarma[alarmas["detector"] == det] if len(alarmas) else fechas_alarma
        ax.plot(sel, [y] * len(sel), MARCADORES[det], color=COLORES[det], ms=9,
                mec="#fcfcfb", mew=1.2, zorder=3, ls="none")
        ax.text(fin + pd.Timedelta(days=200), y, f"{len(sel)}", va="center", ha="left",
                fontsize=9, color=TINTA_2)
    ax.set_yticks(range(len(ORDEN_REAL)))
    ax.set_yticklabels(list(reversed(ORDEN_REAL)))
    ax.set_ylim(-0.7, len(ORDEN_REAL) - 0.3)
    ax.set_title(f"Alarmas 1991-2026 — por puro azar se esperan ~{esperadas_por_azar:.1f} "
                 "por detector. Sin τ, se leen como \"caen en la ventana de X\", nunca como detecciones",
                 fontsize=9.5, color=TINTA_2, loc="left", pad=6)
    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_xlim(inicio, fin + pd.Timedelta(days=900))
    _estilo(ax)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)

    # ── Abajo: el retardo sobre ruido real ────────────────────────────
    deltas = sorted(retardo["delta_sigma"].unique())
    posiciones = np.arange(len(deltas))
    realistas = [i for i, d in enumerate(deltas) if d <= 0.25 + 1e-9]
    for ax, escenario in ((ax_salto, "salto"), (ax_deriva, "deriva")):
        e = retardo[retardo["escenario"] == escenario]
        if realistas:
            ax.axvspan(min(realistas) - 0.4, max(realistas) + 0.4, color="#f1f0ec", zorder=0, lw=0)
            ax.text((min(realistas) + max(realistas)) / 2, 0.97,
                    "caídas realistas de HML", transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=8, color=TINTA_2)
        for det in ORDEN_REAL:
            d = e[e["detector"] == det].set_index("delta_sigma").reindex(deltas)
            y = d["arl1_meses"].to_numpy() / 12
            lo = (d["arl1_meses"] - d["arl1_ic_low"]).to_numpy() / 12
            hi = (d["arl1_ic_high"] - d["arl1_meses"]).to_numpy() / 12
            frac = (d["n_censurados"] / d["n_streams"]).to_numpy()
            ax.errorbar(posiciones, y, yerr=[lo, hi], fmt="none", ecolor=COLORES[det],
                        elinewidth=1, alpha=0.45, capsize=0, zorder=2)
            ax.plot(posiciones, y, LINEAS[det], color=COLORES[det], lw=2, zorder=3)
            for xi, yi, fc in zip(posiciones, y, frac):
                ax.plot(xi, yi, MARCADORES[det], color=COLORES[det],
                        mfc=COLORES[det] if fc < 0.2 else "#fcfcfb",
                        mec=COLORES[det], mew=1.6, ms=8, zorder=4)
        ax.set_xticks(posiciones)
        ax.set_xticklabels([f"{d:g}σ" for d in deltas])
        ax.set_xlabel("Tamaño de la caída inyectada (σ de la serie mensual)",
                      fontsize=9.5, color=TINTA_2)
        ax.set_title(f"{TITULOS[escenario]} sobre ruido real", fontsize=11,
                     color=TINTA_1, loc="left", pad=8)
        _estilo(ax)
    ax_salto.set_ylabel("Retardo de detección (años)\n← mejor", fontsize=9.5, color=TINTA_2)
    ax_salto.set_ylim(bottom=0)
    plt.setp(ax_deriva.get_yticklabels(), visible=False)

    manejadores = [
        plt.Line2D([], [], color=COLORES[d], marker=MARCADORES[d], ls=LINEAS[d],
                   lw=2, ms=8, label=d)
        for d in ORDEN_REAL
    ]
    fig.legend(handles=manejadores, loc="lower center", ncol=len(manejadores),
               frameon=False, fontsize=9.5, bbox_to_anchor=(0.5, 0.005), labelcolor=TINTA_2)
    fig.suptitle(
        "HML, datos reales — los tres detectores a la misma tasa de falsas alarmas "
        f"(ARL0 ≈ {arl0_objetivo:.0f} meses; Shewhart ≈ 110, su escalón alcanzable)",
        fontsize=12.5, color=TINTA_1, y=0.995,
    )
    fig.subplots_adjust(left=0.08, right=0.97, top=0.93, bottom=0.10)
    return fig
