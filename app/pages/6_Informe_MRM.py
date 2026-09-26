"""Validación del sistema: la evidencia de que el código hace lo que dice.

Ocupa el hueco del árbol reservado al informe MRM, y de ese informe tiene
la parte de la evidencia de pruebas, que en validación de modelos (SR 11-7)
es parte del expediente. El expediente en PDF de cada modelo (umbrales,
alarmas, evidencia, limitaciones y el hueco para la decisión del analista)
se descarga desde Salud de modelos y lo construye reporting/mrm_report.py;
cita el resumen de este mismo informe de pruebas.

Dos fuentes, y no se mezclan:
  · El informe SELLADO: outputs/tables/tests_junit.xml, escrito por
    `pytest --junitxml` (el formato estándar de CI) con el commit dentro
    (tests/conftest.py). Se versiona como cualquier resultado (R7).
  · La ejecución EN DIRECTO: el botón lanza pytest en este momento y enseña
    el resultado, sin sobrescribir el informe sellado.

La página no calcula nada (R6): lee el XML con state.session.leer_informe_tests.
"""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import CONFIG_PLOTLY, cabecera, estilo, seccion
from signal_watch.config import obtener_commit
from signal_watch.paths import PATHS
from state.session import INFORME_TESTS, leer_informe_tests

COLOR_ESTADO = {"pasa": "#1baf7a", "fuera de alcance": "#b8bcc4", "falla": "#eb6834", "error": "#eb6834"}
CAPAS = {
    "methodology": ("Metodología", "Que los resultados son válidos: la muralla τ (R2), calibración y "
                                   "evaluación disjuntas (R4), el ML sin fuga (placebo y fuga plantada), R5."),
    "unit": ("Unidad", "Que cada pieza hace lo que dice: CUSUM paso a paso, la identidad CUSUM = "
                       "Page-Hinkley, ARL, generador, escenarios, escala del PSI, PSR y DSR."),
    "integration": ("Integración", "Que las piezas encajan: el contrato en disco, el motor con reinicio "
                                   "y huella R7, del zip de French al stream gold."),
    "smoke": ("Humo", "Que el producto arranca: las páginas de esta app y el comando signal-watch."),
}

informe = leer_informe_tests()

st.markdown(cabecera(
    "Auditoría · evidencia de validación",
    "Validación del sistema",
    "Qué comprueba la batería de tests y si pasa. Cada fallo grave encontrado durante el proyecto "
    "tiene un test que impide que vuelva.",
    [f"commit {informe['commit']}", f"{informe['duracion_s']:.0f} s",
     informe["fecha"][:16].replace("T", " ")] if informe else ["sin informe"],
), unsafe_allow_html=True)

if informe is None:
    st.info("Todavía no hay informe sellado. Genéralo con "
            f"`python -m pytest --junitxml=outputs/tables/{INFORME_TESTS}`.")
else:
    k1, k2, k3, k4 = st.columns(4)
    total = informe["pasan"] + informe["fallan"]
    k1.metric("Tests que pasan", f"{informe['pasan']} / {total}")
    k2.metric("Fallan", informe["fallan"], delta="ninguno" if informe["fallan"] == 0 else "revisar",
              delta_color="off" if informe["fallan"] == 0 else "inverse")
    k3.metric("Fuera de alcance", informe["fuera_de_alcance"],
              help="Archivos del árbol cuyo módulo no se construyó. Se declaran con su motivo en vez "
                   "de dejarlos vacíos.")
    k4.metric("Sellado con el commit", informe["commit"], help="Escrito en el informe por tests/conftest.py (R7).")

    actual = obtener_commit()
    if informe["commit"] not in ("—", actual):
        st.warning(f"El informe sellado es del commit `{informe['commit']}` y el código actual es "
                   f"`{actual}`. Vuelve a generarlo para que la evidencia corresponda al código.")

    tabla = informe["tabla"]
    st.markdown(seccion("Por capa", "Qué demuestra cada capa y cuántos de sus tests pasan."),
                unsafe_allow_html=True)
    izq, der = st.columns([3, 2])
    with izq, st.container(border=True, key="card_capas"):
        conteo = tabla.groupby(["capa", "estado"]).size().unstack(fill_value=0)
        orden = [c for c in CAPAS if c in conteo.index]
        fig = go.Figure()
        for estado in [e for e in COLOR_ESTADO if e in conteo.columns]:
            fig.add_trace(go.Bar(y=[CAPAS[c][0] for c in orden], x=conteo.loc[orden, estado],
                                 name=estado, orientation="h", marker_color=COLOR_ESTADO[estado],
                                 hovertemplate="%{y}: %{x} tests<extra>" + estado + "</extra>"))
        fig.update_layout(barmode="stack", legend=dict(traceorder="normal"))
        fig.update_xaxes(title_text="tests")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(estilo(fig, alto=280), config=CONFIG_PLOTLY)
    with der:
        for clave in orden:
            nombre, texto = CAPAS[clave]
            st.markdown(f"**{nombre}** — {texto}")

    t1, t2, t3 = st.tabs([":material/folder: Por archivo", ":material/checklist: Todos los tests",
                          ":material/block: Fuera de alcance"])
    with t1:
        por_archivo = (tabla.assign(n=1).pivot_table(index=["capa", "archivo"], columns="estado",
                                                     values="n", aggfunc="sum", fill_value=0)
                       .reset_index())
        por_archivo["segundos"] = tabla.groupby(["capa", "archivo"])["segundos"].sum().round(2).to_numpy()
        st.dataframe(por_archivo, hide_index=True)
    with t2:
        a, b = st.columns([1, 2])
        capa = a.selectbox("Capa", ["todas", *orden], format_func=lambda c: CAPAS.get(c, ("Todas",))[0])
        busca = b.text_input("Buscar en el nombre del test", placeholder="p. ej. tau, identidad, fuga")
        vista = tabla if capa == "todas" else tabla[tabla["capa"] == capa]
        if busca:
            vista = vista[vista["test"].str.contains(busca, case=False) | vista["archivo"].str.contains(busca, case=False)]
        if vista.empty:
            st.info("Ningún test coincide con el filtro.")
        else:
            st.dataframe(vista[["capa", "archivo", "test", "estado", "segundos"]], hide_index=True)
            st.caption(f"{len(vista)} tests. Los nombres dicen lo que se comprueba: se leen como frases.")
    with t3:
        fuera = tabla[tabla["estado"] == "fuera de alcance"][["capa", "archivo", "motivo"]]
        if fuera.empty:
            st.info("Ningún test fuera de alcance.")
        else:
            st.dataframe(fuera, hide_index=True)
            st.caption("Declarar lo que no se hizo, con su motivo, es parte de la evidencia.")

    st.download_button("Descargar el informe (JUnit XML)",
                       (PATHS.outputs_tables / INFORME_TESTS).read_bytes(),
                       file_name=INFORME_TESTS, mime="application/xml")

# ── Ejecución en directo ─────────────────────────────────────────────
st.markdown(seccion("Ejecutar los tests ahora",
                    "Lanza pytest sobre el código actual. No sobrescribe el informe sellado."),
            unsafe_allow_html=True)
if importlib.util.find_spec("pytest") is None:
    st.info("pytest no está instalado en este entorno (`pip install -e \".[dev]\"`).")
elif st.button("Ejecutar los tests", type="primary", icon=":material/play_arrow:"):
    destino = Path(tempfile.gettempdir()) / "signal_watch_tests_en_directo.xml"
    with st.spinner("Ejecutando la batería completa (unos 20 segundos)..."):
        proceso = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                  f"--junitxml={destino}"], cwd=PATHS.root, capture_output=True,
                                 text=True, timeout=600)
    directo = leer_informe_tests(destino)
    if directo is None:
        st.error("pytest no llegó a escribir el informe. Salida:")
        st.code(proceso.stdout[-3000:] + proceso.stderr[-2000:])
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Pasan ahora", directo["pasan"])
        c2.metric("Fallan ahora", directo["fallan"], delta_color="inverse",
                  delta=None if directo["fallan"] == 0 else "revisar")
        c3.metric("Duración", f"{directo['duracion_s']:.1f} s")
        if directo["fallan"] == 0:
            st.success(f"Todo pasa sobre el código actual (commit {directo['commit']}).")
        else:
            st.error("Hay tests que fallan:")
            st.dataframe(directo["tabla"][directo["tabla"]["estado"].isin(["falla", "error"])],
                         hide_index=True)
        with st.expander("Salida completa de pytest", icon=":material/terminal:"):
            st.code(proceso.stdout[-5000:])
