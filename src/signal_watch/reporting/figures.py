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