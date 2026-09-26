# Signal Watch

[![tests](https://github.com/nihalhk-dev/signal-watch/actions/workflows/ci.yml/badge.svg)](https://github.com/nihalhk-dev/signal-watch/actions/workflows/ci.yml)

**Detección secuencial de degradación de rendimiento en modelos financieros.** Vigila la métrica
de rendimiento de un modelo —un AUC, un PSI, un Sharpe— y decide, con una tasa de falsas alarmas
elegida de antemano, cuándo una caída es real y no ruido. Trabajo Fin de Máster en Data Science e
Inteligencia Artificial.

El contraste es con la regla de folclore que usa la industria (*"PSI > 0,25 = alarma"*), cuya tasa
de falsas alarmas nadie ha medido nunca.

> **Techo honesto.** Esto es un **prototipo validado** más un caso comercial creíble. **No** es un
> sistema desplegado en un banco, y no se presenta como tal. Los resultados son sobre un banco de
> pruebas sintético con verdad conocida y sobre ruido financiero real (factores de Kenneth French),
> no sobre modelos bancarios propietarios.

## Resultados

| Pregunta | Resultado | Dónde |
|---|---|---|
| ¿Detectan antes los detectores secuenciales? | A igual tasa de falsas alarmas, ante un salto de 1σ: **CUSUM 18,0 pasos frente a 41,1 del baseline 3-sigma** | `outputs/tables/curvas_retardo.csv` |
| ¿Y la regla de la industria? | **PSI > 0,25 no detecta nada**: 200/200 series censuradas en las 15 combinaciones de escenario y magnitud | idem |
| ¿Tiene límites el CUSUM? | **Sí, y se declaran**: ante un cambio de varianza que no mueve la media, 3-sigma gana (16-20 pasos frente a 38-42) | idem |
| ¿Se transfiere a ruido financiero real? | Sobre ruido real de HML, con una falsa alarma por década: **CUSUM 37,7 meses frente a 55,0 de la regla de una sola observación** ante la caída de los 2010 | `retardo_ruido_real_factor_hml_sharpe.csv` |
| ¿Aguanta la tasa de falsas alarmas fuera de muestra? | **No del todo, y se mide**: calibrando con años alternos y probando en los otros, en las dos direcciones, se desvía un factor ~2 (CUSUM: 191 y 67 meses frente a 120 prometidos). Es una estimación, no una garantía | `retardo_fuera_muestra_factor_hml_sharpe.csv` |
| ¿Era alfa de verdad? (RQ2) | **DSR 0,957** con 10 pruebas en la muestra de descubrimiento; fuera de muestra el Sharpe cae de 0,63 a 0,23 y **PSR 0,916**, ya no significativo | `deflated_sharpe_hml.csv` |
| ¿Sirve para un modelo de ML? | Una señal de ML vigilada por el mismo monitor, sin tocarlo. Su ventaja sobre los listones **no es significativa (PSR 0,88)**, y se dice | `resumen_senal_ml_hml_sharpe.csv` |

**Cuánto se tarda en confirmar una caída realista: 3-4 años.** No es un límite del detector, es el
límite de información del problema. Quien prometa detectarlo en un trimestre está prometiendo
falsas alarmas, no velocidad.

## Reproducirlo entero

Python 3.12. Cada paso deja sus resultados sellados con su huella de reproducibilidad (R7:
`config_hash` de los parámetros, `hash_datos` del contenido de los datos, `commit` y fecha).

```bash
pip install -e ".[dev,app]"

python -m signal_watch.ingest.french              # descarga los factores + manifiesto con SHA-256
python scripts/build_synthetic.py                 # banco sintético: 1,28 M observaciones (~3 min)
python scripts/run_evaluation.py                  # curvas retardo / falsas alarmas (~40 min)

python -m signal_watch.gold.factor_metrics        # stream real: Sharpe mensual de HML
python scripts/run_monitoring.py factor_hml_sharpe        # calibración, alarmas y retardo, dentro y fuera de muestra (~10 min)
python -m signal_watch.evaluation.deflated_sharpe         # RQ2: PSR y DSR

python -m signal_watch.gold.signal_momentum               # señal de ML (logística hacia delante)
python scripts/run_monitoring.py senal_ml_hml_sharpe      # el mismo monitor, otro modelo

python -m pytest -q                               # 126 tests + 10 fuera de alcance declarados
streamlit run app/Home.py                         # el panel
```

Los datos crudos no se versionan (pesan y su licencia manda), pero sí su huella:
`data/raw/_metadata/download_manifest.json` guarda URL, bytes, SHA-256, fecha y commit de cada
descarga. No se guardan los datos: se guarda su huella.

## Cómo está montado

```
configs/streams/*.yaml   un stream = un modelo vigilado. Única fuente de sus parámetros
src/signal_watch/
  gold/          el contrato metric_stream + la muralla de τ
  synthetic/     el banco de pruebas: ruido AR(1), escenarios, métricas (AUC, PSI)
  detectors/     CUSUM, Page-Hinkley, Shewhart y el folclore como detector medible
  evaluation/    ARL0/ARL1, curvas de retardo, calibración sobre ruido real, PSR/DSR
  monitoring/    el motor: recorre, alarma, reinicia y sella cada alarma
  processing/    de retornos diarios a la métrica mensual (Sharpe + SE de Lo, 2002)
app/             el panel (Streamlit): salud de modelos, factores, banco y validación
tests/           126 tests; 10 archivos declarados fuera de alcance con su motivo
```

**La pieza de diseño central es el contrato.** Toda serie —sintética, un factor de mercado, una
señal de ML— se materializa como `MetricObservation`: valor, error estándar, tamaño de muestra y
dirección ("peor" es subir o bajar). El detector no sabe de dónde viene el número. Por eso **añadir
un modelo nuevo no obliga a tocar el monitor ni la app**: basta su YAML y una ejecución.

**La muralla de τ (R2).** El instante real del cambio vive en un esquema y un archivo separados, y
nunca llega a un detector. Está protegido por tipos, por una guardia al cargar y por una única
puerta de paso, con tests en las tres capas.

## Alcance

**Dentro:** CUSUM y Page-Hinkley con calibración por simulación; banco sintético con verdad
conocida; curvas retardo frente a falsas alarmas; validación sobre ruido real de mercado; Deflated
Sharpe; una señal de ML vigilada; panel y evidencia de validación.

**Fuera, a propósito:** NLP y deep learning; API REST, base de datos y Docker; la rama de crédito
(su ventana sin censura está decidida con datos reales, pero el scorecard no se construyó); BOCPD;
simulación de valor económico; informe MRM en PDF. Cada archivo de test correspondiente está
declarado como fuera de alcance con su motivo, en vez de dejarlo vacío.

## Validación

- **126 tests** sobre el código real: la muralla de τ, calibración y evaluación disjuntas (R4, también
  por datos en el retardo fuera de muestra), el
  convenio del ARL, cada detector, el generador y los escenarios, el contrato en disco, el motor,
  el pipeline desde el zip crudo, la señal de ML sin fuga (placebo y fuga plantada) y el panel.
- **Los fallos encontrados durante el proyecto tienen su test.** Se comprobó reintroduciéndolos uno
  a uno: **12 de 12 quedaron atrapados**.
- La página **Validación del sistema** del panel enseña el informe de pytest sellado con su commit,
  y permite ejecutar la batería en directo.

## Limitaciones

Están declaradas en [`docs/limitaciones_y_trabajo_futuro.md`](docs/limitaciones_y_trabajo_futuro.md).
Las principales: τ fijo en el banco sintético; censura en los puntos de ARL0 más exigente; la
validación real es sobre un factor de mercado, no sobre un modelo bancario; en datos reales no hay
τ, así que el retardo se mide inyectando un cambio conocido sobre ruido real; fuera de muestra la
tasa de falsas alarmas se desvía un factor ~2, así que en producción también se vigila; y la ventaja
de la señal de ML sobre sus listones no es estadísticamente significativa.

## Licencia y datos

Código bajo la licencia del repositorio. Los factores diarios provienen de la biblioteca pública de
[Kenneth R. French](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) y
están sujetos a sus condiciones de uso.
