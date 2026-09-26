"""Expediente de monitorización de un modelo, en PDF.

Qué es
──────
El documento que un analista de riesgo de modelo (MRM) adjuntaría a su
revisión cuando salta una alarma: qué se vigila, con qué umbrales y con qué
tasa de falsas alarmas, qué alarmas ha habido, qué evidencia hay de que el
detector funciona, qué límites tiene, y un hueco para que el analista deje
escrita SU decisión.

Qué NO es
─────────
· No calcula nada (R6). Todo número sale de las tablas selladas de
  outputs/tables/ (con su huella R7) o del informe de pytest. Si una tabla
  no existe, su sección lo dice; no se rellena con nada inventado.
· No decide. La herramienta no emite veredicto (no hay reglas de negocio
  definidas, por eso la app no tiene semáforo). La decisión —escalar,
  descartar, seguir vigilando— la escribe una persona, y el expediente le
  deja el sitio para hacerlo.
· No es un informe regulatorio. El formato se inspira en lo que SR 11-7 pide
  documentar en la monitorización continua, pero es un prototipo.

Diseño
──────
`expediente_pdf()` es una función pura: recibe los datos ya leídos y
devuelve los bytes del PDF. Quien lee las tablas es la app (state/session.py)
y quien ofrece la descarga también. Así se prueba sin levantar la app ni
tocar el disco.

La fuente es DejaVu Sans, la que trae matplotlib (que ya es dependencia):
las fuentes estándar de un PDF no tienen σ, τ ni ≈.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import pandas as pd
from fpdf import FPDF
from fpdf.fonts import FontFace

HUELLA = ("config_hash", "hash_datos", "commit")

# Paleta de la app, en sobrio: tinta, gris y un azul para cabeceras.
TINTA = (20, 27, 45)
GRIS = (95, 102, 115)
CABECERA_TABLA = (226, 232, 240)


def _fuentes() -> tuple[Path, Path]:
    carpeta = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    return carpeta / "DejaVuSans.ttf", carpeta / "DejaVuSans-Bold.ttf"


def _num(x, dec: int = 1) -> str:
    """Número con coma decimal, como el resto del proyecto."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if pd.isna(v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


class _Expediente(FPDF):
    def __init__(self, stream_id: str, generado_en: str):
        super().__init__(format="A4")
        self.stream_id, self.generado_en = stream_id, generado_en
        normal, negrita = _fuentes()
        self.add_font("dejavu", "", str(normal))
        self.add_font("dejavu", "B", str(negrita))
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, margin=18)

    def footer(self):
        self.set_y(-12)
        self.set_font("dejavu", "", 7)
        self.set_text_color(*GRIS)
        self.cell(0, 5, f"Signal Watch · expediente {self.stream_id} · generado {self.generado_en} "
                        f"· página {self.page_no()}/{{nb}}", align="C")

    # ── bloques de texto ──
    def titulo(self, texto: str):
        # Un título solo al pie de página, con su contenido en la siguiente, no.
        if self.get_y() > self.h - 60:
            self.add_page()
        self.set_font("dejavu", "B", 11)
        self.set_text_color(*TINTA)
        self.ln(3)
        self.cell(0, 7, texto, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*CABECERA_TABLA)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def parrafo(self, texto: str, tam: float = 8.5, color=TINTA):
        self.set_font("dejavu", "", tam)
        self.set_text_color(*color)
        self.multi_cell(0, 4.3, texto, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def campos(self, pares: list[tuple[str, str]]):
        self.set_text_color(*TINTA)
        for etiqueta, valor in pares:
            self.set_font("dejavu", "B", 8.5)
            self.cell(48, 5, etiqueta)
            self.set_font("dejavu", "", 8.5)
            self.multi_cell(0, 5, valor, align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def tabla(self, cabecera: list[str], filas: list[list[str]], anchos: tuple | None = None):
        self.set_font("dejavu", "", 8)
        self.set_text_color(*TINTA)
        with self.table(
            col_widths=anchos, text_align="LEFT", line_height=5, padding=1,
            headings_style=FontFace(emphasis="BOLD", fill_color=CABECERA_TABLA),
            borders_layout="HORIZONTAL_LINES",
        ) as t:
            for fila in [cabecera, *filas]:
                r = t.row()
                for celda in fila:
                    r.cell(str(celda))
        self.ln(2)


def expediente_pdf(
    stream_id: str,
    config: dict,
    resumen: dict,
    calibracion: pd.DataFrame | None,
    alarmas: pd.DataFrame | None,
    retardo: pd.DataFrame | None = None,
    retardo_fuera: pd.DataFrame | None = None,
    informe_tests: dict | None = None,
    generado_en: str | None = None,
) -> bytes:
    """Construye el expediente de un stream y devuelve el PDF en bytes.

    `config` es el YAML del stream; `resumen` lo que devuelve
    state.session.resumen_stream (referencia, vigilancia, meses vigilados,
    alarmas esperadas por azar); las tablas son las selladas tal cual; el
    informe de tests, lo que devuelve state.session.leer_informe_tests.
    """
    generado_en = generado_en or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf = _Expediente(stream_id, generado_en)
    pdf.add_page()

    # ── Portada ──
    pdf.set_font("dejavu", "B", 16)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 9, "Expediente de monitorización", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dejavu", "", 11)
    pdf.cell(0, 6, stream_id, new_x="LMARGIN", new_y="NEXT")
    pdf.parrafo(
        "Signal Watch · prototipo validado, no desplegado en producción. Este documento reúne "
        "la evidencia sellada del monitor; no emite veredicto. La decisión la toma y la firma "
        "el analista (sección 7).", tam=8, color=GRIS,
    )

    # ── 1. Qué se vigila ──
    peor = {"lower_is_worse": "si baja", "higher_is_worse": "si sube"}.get(
        str(config.get("direction")), str(config.get("direction", "—")))
    mon = config.get("monitorizacion", {})
    pdf.titulo("1. Qué se vigila")
    pdf.campos([
        ("Stream", stream_id),
        ("Métrica", f"{config.get('metrica', '—')} (empeora {peor})"),
        ("Frecuencia · fuente", f"{config.get('frecuencia', '—')} · {config.get('fuente', '—')}"),
        ("Referencia (solo calibra)", str(resumen.get("referencia", "—"))),
        ("Vigilancia", f"{resumen.get('vigilancia', '—')} ({resumen.get('meses_vigilados', '—')} periodos)"),
        ("Tasa de falsas alarmas", f"ARL0 objetivo {_num(mon.get('arl0_objetivo_meses'), 0)} periodos "
                                   "entre falsas alarmas, igual para todos los detectores"),
    ])

    # ── 2. Trazabilidad ──
    pdf.titulo("2. Trazabilidad (R7)")
    if calibracion is not None and len(calibracion):
        h = calibracion.iloc[0]
        pdf.campos([(k, str(h.get(k, "—"))) for k in HUELLA])
        pdf.parrafo("Mismos config_hash y hash_datos ⇒ mismos umbrales y mismas alarmas. El commit "
                    "es el código que produjo las tablas.", tam=7.5, color=GRIS)
    else:
        pdf.parrafo("Sin tabla de calibración: no hay huella que citar.")
    if informe_tests:
        pdf.campos([("Batería de tests",
                     f"{informe_tests.get('pasan', '—')} pasan · {informe_tests.get('fallan', '—')} fallan · "
                     f"{informe_tests.get('fuera_de_alcance', '—')} fuera de alcance "
                     f"(commit {informe_tests.get('commit', '—')}, {informe_tests.get('fecha', '—')})")])

    # ── 3. Calibración ──
    pdf.titulo("3. Umbrales calibrados")
    if calibracion is not None and len(calibracion):
        pdf.tabla(
            ["Detector", "Umbral", "ARL0 alcanzable", "ARL0 verificado", "IC 95%"],
            [[c["detector"], _num(c["umbral"], 3), _num(c["arl0_alcanzable"]),
              _num(c["arl0_verificado"]),
              f"{_num(c['arl0_ic_low'], 0)} – {_num(c['arl0_ic_high'], 0)}"]
             for _, c in calibracion.iterrows()],
            (30, 20, 30, 30, 30),
        )
        pdf.parrafo("ARL0 verificado en series distintas de las que fijaron el umbral (R4). La regla "
                    "de una sola observación (Shewhart) solo alcanza escalones discretos; se usa el "
                    "primero que no es más estricto que el objetivo.", tam=7.5, color=GRIS)
    else:
        pdf.parrafo("No existe la tabla de calibración de este stream.")

    # ── 4. Alarmas ──
    pdf.titulo("4. Alarmas en la vigilancia")
    esperadas = resumen.get("esperadas_por_azar")
    if alarmas is None:
        pdf.parrafo("No existe la tabla de alarmas de este stream.")
    else:
        pdf.parrafo(f"Sin ningún cambio real se esperarían ~{_num(esperadas)} falsas alarmas por detector "
                    "en este periodo. Una alarma no es una detección confirmada: sin fecha de cambio "
                    "conocida, se lee como «la alarma cae en tal fecha», no como «se detectó X».")
        if len(alarmas):
            por_det = alarmas.groupby("detector").size()
            pdf.campos([("Alarmas por detector",
                         " · ".join(f"{d}: {n}" for d, n in por_det.items()))])
            pdf.tabla(
                ["Fecha", "Detector", "Valor", "Estadístico", "Umbral", "Nº"],
                [[str(a["fecha"]), a["detector"], _num(a["valor"], 2), _num(a["estadistico"], 2),
                  _num(a["umbral"], 3), str(a["n_alarma"])]
                 for _, a in alarmas.sort_values("fecha").iterrows()],
                (26, 30, 22, 26, 22, 14),
            )
        else:
            pdf.parrafo("Ninguna alarma en el periodo vigilado.")

    # ── 5. Evidencia de que el detector funciona ──
    pdf.titulo("5. Evidencia: cuánto tarda en confirmar una caída")
    if retardo is None or not len(retardo):
        pdf.parrafo("No existe la tabla de retardo sobre ruido real de este stream.")
    else:
        deltas = sorted(retardo["delta_sigma"].unique())
        pdf.parrafo("Caídas de tamaño conocido inyectadas sobre el ruido real de la referencia, con "
                    "los umbrales de la sección 3. Retardo medio en periodos desde el cambio; a igual "
                    "tasa de falsas alarmas (dentro de muestra).")
        for esc in retardo["escenario"].unique():
            sub = retardo[retardo["escenario"] == esc]
            filas = []
            for det in sub["detector"].unique():
                fila = sub[sub["detector"] == det].set_index("delta_sigma")["arl1_meses"]
                filas.append([det, *[_num(fila.get(d)) for d in deltas]])
            pdf.set_font("dejavu", "B", 8)
            pdf.cell(0, 5, f"Escenario: {esc}", new_x="LMARGIN", new_y="NEXT")
            pdf.tabla(["Detector", *[f"{_num(d, 2)}σ" for d in deltas]], filas)
        pdf.parrafo("Si la regla de una sola observación (Shewhart) parece más rápida ante caídas "
                    "pequeñas, no es una ventaja: su tasa de falsas alarmas la fijan los pocos meses "
                    "más extremos de la referencia y, con referencias cortas, se subestima. Ver "
                    "limitaciones 2.12 y 4.6.", tam=7.5, color=GRIS)
    if retardo_fuera is not None and len(retardo_fuera):
        arl0 = (retardo_fuera.drop_duplicates(["direccion", "detector"])
                .pivot(index="detector", columns="direccion", values="arl0_ruido_inyeccion"))
        pdf.set_font("dejavu", "B", 8)
        pdf.cell(0, 5, "Fuera de muestra: ¿aguanta la tasa de falsas alarmas?", new_x="LMARGIN", new_y="NEXT")
        pdf.tabla(["Detector", *[f"calibra {d[0]} → mide en {d[-1]}" for d in arl0.columns]],
                  [[det, *[_num(v, 0) for v in arl0.loc[det]]] for det in arl0.index])
        pdf.parrafo(f"ARL0 medido en años que el umbral no ha visto (prometido: "
                    f"{_num(mon.get('arl0_objetivo_meses'), 0)}). Se desvía en torno a un factor 2: la "
                    "tasa de falsas alarmas es una estimación y también hay que vigilarla.",
                    tam=7.5, color=GRIS)

    # ── 6. Alcance ──
    fuera_medido = retardo_fuera is not None and len(retardo_fuera) > 0
    pdf.titulo("6. Alcance y limitaciones")
    pdf.parrafo(
        "· Prototipo validado sobre un banco sintético con verdad conocida y sobre ruido financiero "
        "real; no validado sobre un modelo bancario en producción.\n"
        "· El monitor no emite veredicto: no hay reglas de negocio definidas que traduzcan alarmas "
        "en decisiones.\n"
        "· La tasa de falsas alarmas es una estimación calibrada con la referencia. "
        + ("Fuera de muestra se desvía (sección 5).\n" if fuera_medido else
           "Para este stream no se ha medido fuera de muestra; donde se midió, se desvía en "
           "torno a un factor 2 (limitación 2.9).\n")
        + "· Detalle completo: docs/limitaciones_y_trabajo_futuro.md del repositorio."
    )

    # ── 7. Decisión del analista ──
    pdf.titulo("7. Decisión del analista")
    pdf.parrafo("A rellenar por el responsable de la revisión. La herramienta no la propone.",
                tam=7.5, color=GRIS)
    pdf.set_font("dejavu", "", 9)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 7, "☐ Escalar a revisión del modelo      ☐ Descartar (falsa alarma)      "
                   "☐ Seguir vigilando", new_x="LMARGIN", new_y="NEXT")
    for etiqueta in ("Motivo", "", "Responsable", "Fecha y firma"):
        pdf.ln(2)
        pdf.cell(32, 7, etiqueta)
        y = pdf.get_y() + 6
        pdf.line(pdf.l_margin + 32, y, pdf.w - pdf.r_margin, y)
        pdf.ln(7)

    return bytes(pdf.output())
