# Entrega 3 — Diseño del modelo de datos y capa gold

> **Proyecto: Signal Watch** — Detección secuencial de la degradación del rendimiento en modelos financieros.

---

## 0. Evolución del alcance respecto a la Entrega 2

Antes de entrar en el modelo de datos quiero dejar constancia de tres decisiones que he tomado **después** de la Entrega 2 y que cambian las fuentes y la capa gold. Las pongo aquí y no las escondo porque el enunciado pide que la capa gold funcione como "contrato de datos para las fases posteriores", y ese contrato tiene que describir lo que realmente voy a construir, no lo que yo preveía antes de bajarme los datos y mirarlos. La Entrega 2 se queda tal cual (para mantener la trazabilidad); esta sección es la que explica en qué he cambiado de opinión y por qué.

1. **La censura de Lending Club ya no es una sospecha, la he medido, y es la que fija la ventana temporal.** En la Entrega 2 marqué la censura de las cosechas recientes como el riesgo más serio de esa fuente. He hecho el análisis sobre el volcado completo —la fracción de préstamos que ya están resueltos en cada cosecha— y el resultado no deja lugar a dudas: para préstamos a **36 meses** la ventana fiable se acaba en **febrero de 2016**, y para los de 60 meses se acaba ya en 2014. Esto tiene dos consecuencias de diseño que asumo: uso **solo préstamos a 36 meses** y la ventana de cosechas queda en **2007-06 → 2016-02**. Lo desarrollo en las secciones 7 y 8, porque para mí es la decisión de calidad de datos más importante de todo el proyecto.

2. **La señal propia de _momentum_ (con yfinance) queda fuera.** Ya en la Entrega 2 la había clasificado como "deseable pero no obligatoria" y a yfinance como fuente de "riesgo medio" (es una API no oficial, tiene sesgo de supervivencia y límites de peticiones), así que no me contradigo: estoy ejecutando una salida que yo misma había dejado señalada. La sustituyo por el **factor Momentum de Kenneth French**, que ya viene en su librería, es descargable, es estable y lo puedo verificar por _hash_. Gano reproducibilidad y no pierdo nada del argumento de mercado. La señal propia pasa a la sección 9, como alternativa descartada.

3. **El volcado de Kaggle deja de ser una fuente de modelado y pasa a tener un único uso muy concreto.** Mi fuente de modelado sigue siendo la versión curada de Zenodo, que ya verifiqué. De Kaggle solo saco el campo `term` (el plazo del préstamo) cruzando por `id`, porque la versión curada no lo trae y lo necesito para poder aplicar la regla de los 36 meses. Es un _join_ puntual para recuperar una columna, no un segundo pipeline en paralelo.

En resumen: el proyecto pasa de cuatro ramas de datos a **tres** (crédito, factores de mercado y banco sintético), y la rama de crédito queda acotada en el tiempo por evidencia y no por intuición.

---

## 1. Resumen de la idea y datos del proyecto

**Qué problema resuelve.** Los modelos que se ponen en producción se van degradando con el tiempo sin que nadie se dé cuenta hasta que ya han causado un problema: un _scorecard_ de crédito pierde poder de discriminación cuando cambia el perfil de los solicitantes, y una señal de mercado pierde rentabilidad cuando el mercado acaba arbitrándola. Y las entidades no solo tienen ese problema técnico, sino que además están **obligadas por la regulación** a vigilar y documentar esa degradación (la guía SR 11-7 de la Reserva Federal, y en Europa el artículo 72 del Reglamento de IA para los sistemas de alto riesgo, entre los que está el _scoring_ de crédito).

**Qué solución quiero construir.** Un sistema que reciba un **flujo temporal con una métrica de rendimiento del modelo** y que aplique **detección secuencial de cambios** (CUSUM y el test de Page-Hinkley) para lanzar una alarma cuando la degradación es real y no simplemente ruido. Para mí la parte importante no es aplicar los detectores, sino **caracterizar el compromiso entre el retardo de detección y las falsas alarmas**, y demostrarlo sobre una degradación real.

**Qué fuentes uso y qué me aporta cada una.** Son tres, y hacen trabajos distintos que no se sustituyen entre sí:

| Fuente                              | Qué me aporta                                                              | ¿Me deja medir el retardo?                                      |
| ----------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Lending Club** (Zenodo, curado)   | Demostrar que detecto la degradación **real** de un modelo de crédito real | No (nadie sabe el día exacto en que empezó)                     |
| **Kenneth French** (factores)       | Demostrar que detecto degradación **real** de mercado                      | No                                                              |
| **Banco sintético** (código propio) | **Medir** el detector: las curvas de retardo frente a falsas alarmas       | **Sí** (es el único sitio donde conozco el instante del cambio) |

Es decir: las fuentes reales **demuestran** y la sintética **mide**. Lo veo como un termómetro: primero lo calibro en agua con hielo, donde conozco la temperatura de verdad (el sintético), y solo después se lo pongo a un paciente (los datos reales).

---

## 2. Tecnología o formato de almacenamiento elegido

He decidido usar una **combinación de dos formatos**, cada uno donde tiene sentido, y descartar a propósito una base de datos relacional. Justifico las tres cosas, porque el criterio de corrección pide precisamente que la elección no sea "una tecnología más compleja porque sí".

**CSV para la capa `raw`.** Los datos me llegan en CSV (el Lending Club curado y los ficheros de Kenneth French), y los guardo **tal cual se descargan**, sin tocarlos, junto con su _hash_ de verificación. La razón es que la capa `raw` tiene que ser un espejo fiel de la fuente: es lo que me permite auditar después cualquier transformación y reproducir la descarga desde cero.

**Parquet para `processed` y `gold`.** En cuanto limpio los datos, paso a Parquet, y esto sí es una decisión de diseño y no de comodidad:

- **El tipo de dato viaja con el dato.** Parquet guarda el esquema (tipos y no-nulos) dentro del propio fichero. Un CSV no distingue un entero de un texto que parece un número, y en un proyecto donde una fecha mal parseada corrompe toda la serie temporal, que el tipo esté garantizado dentro del fichero es una tranquilidad, no un lujo.
- **Es columnar y comprimido.** Mis operaciones son analíticas: leo la columna `auc` de todas las cosechas, no préstamo a préstamo. Parquet lee solo las columnas que le pido y comprime bien, con lo cual el fichero de crédito ocupa bastante menos que en CSV.
- **Encaja con mi _stack_.** pandas y pyarrow lo leen de forma nativa, sin fricción.

**Por qué NO una base de datos relacional (SQLite o PostgreSQL).** Lo he descartado a conciencia. Mis datos son **artefactos de solo lectura que se regeneran**, no un estado que se escribe y reescribe: se calculan una vez, se congelan y se consumen. No tengo varios usuarios escribiendo a la vez, no tengo integridad referencial compleja que imponer en caliente, ni consultas ad-hoc de terceros. Meter un motor relacional me añadiría infraestructura (un esquema, migraciones, un servidor) sin resolverme ningún problema que Parquet no me resuelva ya. La reproducibilidad me la garantizan los _hashes_ de las fuentes y un pipeline determinista, no una base de datos.

> Una aclaración sobre integridad, porque no quiero que parezca que dejo un hueco: la parte de MRM del proyecto sí necesita un registro de auditoría **inalterable** (el historial de alarmas). Eso lo resuelvo con un fichero de log **encadenado por _hashes_** —cada entrada lleva el _hash_ de la anterior—, que detecta si alguien ha alterado, borrado o insertado una línea, y que para este caso es una garantía más fuerte que una tabla SQL. Pero eso pertenece a una fase posterior (la de monitorización), no a la capa gold; lo menciono solo para dejar claro que la ausencia de base de datos no deja nada sin cubrir.

---

## 3. Estructura de capas de datos

Uso la estructura de tres capas que propone el enunciado, con una subdivisión dentro de `gold`:

```
data/
├── raw/                    # espejo exacto de la fuente + su hash. No se edita nunca.
│   ├── lending_club/       # CSV curado de Zenodo
│   ├── french/             # CSV de factores (research factors + momentum)
│   └── _metadata/          # manifiesto de descargas: url, fecha, sha256
├── processed/              # limpio, tipado, tratado. Parquet.
│   ├── factors_daily.parquet
│   ├── lc_term_map.parquet         # id → term (del join con Kaggle)
│   └── loans_36m_maduros.parquet   # tras el filtro 36m + la regla de madurez
└── gold/                   # listo para consumir. Parquet.
    ├── real/               # métricas por periodo de modelos reales
    └── synthetic/          # flujos sintéticos con el cambio inyectado
```

**Qué hace cada capa en mi caso concreto:**

- **Raw.** El CSV de Zenodo y los de French, sin tocar, con su _hash_ apuntado en `_metadata`. Si mañana la fuente cambia, el _hash_ deja de coincidir y el pipeline se detiene, en vez de darme números distintos sin avisar.
- **Processed.** Aquí es donde ocurren las transformaciones intermedias: el parseo con cuidado de los CSV de French (que traen varias tablas apiladas, los valores en porcentaje y códigos de dato ausente), el _join_ con Kaggle para recuperar `term`, la regla de madurez y el filtrado a 36 meses. Salen tablas limpias y tipadas, pero todavía a nivel de préstamo o de día.
- **Gold.** El salto que importa: paso de préstamo/día a **métrica por periodo**. Aquí el dato deja de ser "préstamos" y pasa a ser "el rendimiento del modelo cosecha a cosecha", que es exactamente lo que consume el detector. Lo detallo en la sección 4.

**Por qué esta estructura y no otra.** Separar `raw` de `processed` me deja auditar cualquier transformación comparando lo que entra con lo que sale. Y separar `processed` de `gold` me deja cambiar cómo calculo una métrica sin tener que volver a descargar ni a reprocesar los datos de base. Es la estructura habitual de un proyecto analítico de datos y encaja bien con mi flujo, así que no he visto motivo para inventarme otra.

---

## 4. Definición de la capa gold

Esta es la parte central de la entrega. Mi capa gold **no es la tabla de préstamos**, sino el conjunto de **series temporales de métricas de rendimiento**, que son la entrada directa de los detectores. Y todas comparten un mismo **contrato común** —la misma interfaz que consume el detector—, que para mí es la decisión de diseño más importante del proyecto: un flujo de AUC de un _scorecard_ y un flujo de Sharpe de un factor son, para el detector, **el mismo objeto**.

### 4.0 El contrato común: `metric_stream`

Todos los datasets gold, sean de crédito, de mercado o sintéticos, se materializan con el **mismo esquema**. Esto es lo que hace que el sistema sea agnóstico al modelo, y lo que me permite que la rama sintética y la real sean dos instancias de una misma interfaz en lugar de dos cosas distintas.

| Campo       | Tipo   | Descripción                                                                                |
| ----------- | ------ | ------------------------------------------------------------------------------------------ |
| `stream_id` | string | Identificador del flujo (p. ej. `credito_lc_auc_36m`, `factor_hml_sharpe`)                 |
| `t`         | int    | Índice temporal ordinal del periodo (0, 1, 2, …)                                           |
| `timestamp` | date   | Fecha del periodo (la cosecha mensual o la fecha de mercado)                               |
| `value`     | float  | Valor de la métrica en ese periodo                                                         |
| `value_se`  | float  | Error estándar de la métrica (mide el ruido de ese punto concreto)                         |
| `n_obs`     | int    | Nº de observaciones que sostienen la métrica (préstamos de la cosecha, días de la ventana) |
| `direction` | enum   | `lower_is_worse` (AUC, Sharpe) o `higher_is_worse` (PSI)                                   |

> **Por qué meto `value_se` y `n_obs` dentro del contrato**, que no es un detalle menor: el ruido de una métrica depende del tamaño de muestra. Un AUC calculado sobre 200 préstamos es muchísimo más ruidoso que uno sobre 20.000. Al meter el error estándar en el propio contrato, consigo que los detectores puedan trabajar en unidades de desviación estándar y que sus parámetros sean **portables entre flujos de naturaleza distinta**. Es también la forma que tengo de tratar el problema que ya había detectado en la Entrega 2: que las cosechas antiguas de Lending Club son pequeñas y sus métricas ruidosas.

### 4.1 Los datasets gold

**Estado de madurez.** Indico en qué punto de construcción está cada dataset a fecha de esta entrega, porque no todos se materializan a la vez y prefiero ser transparente con ello:

- 🟢 **Construible ya:** solo depende de datos ya verificados y de código de esta fase o la anterior.
- 🟡 **Diseñado, se materializa en una fase posterior:** el diseño (esquema, granularidad, fuente) está cerrado; lo que falta es ejecutar la fase que lo produce.

| Dataset gold                           | Estado                                         | Granularidad                                                | Campos clave                                                                      | Nº aprox. de registros                    | Fase que lo consume                     |
| -------------------------------------- | ---------------------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------- | --------------------------------------- |
| `gold/real/credito_lc_auc_36m.parquet` | 🟡 (se materializa al entrenar el _scorecard_) | 1 fila por cosecha mensual                                  | `stream_id, t, timestamp, value(=AUC), value_se, n_obs, direction=lower_is_worse` | ~104 antes de filtrar (2007-06 → 2016-02) | Detección, validación real, informe MRM |
| `gold/real/credito_lc_psi_36m.parquet` | 🟡 (ídem)                                      | 1 fila por cosecha mensual                                  | `… value(=PSI) …, direction=higher_is_worse`                                      | ~104 antes de filtrar                     | Detección, validación real              |
| `gold/real/factor_hml_sharpe.parquet`  | 🟢                                             | 1 fila por fecha (ventana móvil)                            | `… value(=Sharpe móvil) …, direction=lower_is_worse`                              | miles de días                             | Detección, validación real              |
| `gold/real/factor_mom_sharpe.parquet`  | 🟢                                             | 1 fila por fecha (ventana móvil)                            | ídem                                                                              | miles de días                             | Detección, validación real              |
| `gold/synthetic/calibracion.parquet`   | 🟢                                             | 1 fila por escenario × réplica × instante                   | `stream_id, t, value, value_se, n_obs, direction` (+ `tau` en fichero aparte)     | millones (lo controlo yo)                 | Calibración de detectores               |
| `gold/synthetic/evaluacion.parquet`    | 🟢                                             | ídem, pero con **semillas disjuntas** de las de calibración | ídem                                                                              | millones                                  | Curvas de retardo vs. falsas alarmas    |

**Descripción de las dos gold que más me importan:**

- **`credito_lc_auc_36m`** (la que sostiene el producto). Una fila por cosecha mensual de concesión. El `value` es el **AUC del _scorecard_** evaluado sobre los préstamos de esa cosecha, y el `value_se` es su error estándar por la fórmula de Hanley–McNeil (que depende de `n_obs`, el número de préstamos maduros de la cosecha). Es la serie que se degrada cuando el modelo pierde poder de discriminación, y por eso el campo relevante es `value`: es la métrica que vigila el monitor.

- **`credito_lc_psi_36m`** (el "folclore", pero sobre datos reales). Misma granularidad. El `value` es el **PSI** (Population Stability Index) de la distribución del _score_ de esa cosecha frente a una cosecha de referencia, y va como `higher_is_worse` (a más PSI, más deriva). Es el **único** flujo del proyecto con esa dirección, y eso me obliga a que el contrato la trate de forma explícita. Lo que lo hace interesante es que el umbral de PSI > 0,25 es la regla de alarma que usa media industria sin que nadie haya medido nunca su tasa de falsas alarmas, y eso sí lo puedo caracterizar con la rama sintética.

**Clave o identificador.** La clave primaria de cada dataset gold es la pareja (`stream_id`, `t`): el `stream_id` distingue de qué flujo hablo y `t` ordena el tiempo dentro de ese flujo.

**Una nota sobre la verdad-terreno sintética.** Los datasets sintéticos llevan asociado el instante real del cambio (`tau`), pero **ese campo lo guardo en un fichero separado, no dentro del `metric_stream`**. Lo hago a propósito: el detector no puede ver nunca el `tau`, porque eso sería hacer trampa. El `tau` solo se usa después, para medir el retardo. Es una salvaguarda de método, no un detalle de implementación.

---

## 5. Relaciones entre datos

El proyecto usa **varias fuentes**, pero la capa gold está **desnormalizada en flujos independientes** a propósito: cada `metric_stream` es autocontenido y el detector consume uno cada vez. Entre los flujos gold no hay un modelo relacional, y eso es una decisión, no un descuido. Lo que sí hay son relaciones **aguas arriba**, en el camino de `raw` a `gold`, que conviene dejar explícitas:

**Relación 1 — recuperar el plazo (join por `id`).**

```
zenodo_curado.id   1 --- 1   kaggle_volcado.id   →   me aporta term
```

Es una relación **1:1** por el identificador de préstamo. El curado de Zenodo tiene el préstamo y sus variables de solicitud pero no el `term`; el volcado de Kaggle sí lo tiene. Cruzo por `id` para traerme únicamente esa columna. **El problema que espero al cruzar** es que algún `id` del curado no aparezca en Kaggle (préstamos sin match): mido ese porcentaje en la fase de procesamiento y decido si los descarto o les asumo 36 meses. No construyo el _scorecard_ sobre Kaggle, solo le cojo `term`.

**Relación 2 — de préstamo a cosecha (agregación 1:N).**

```
préstamo (processed)   N --- 1   cosecha (gold)
```

Muchos préstamos caen en una cosecha. Es una **agregación**, no un join relacional: agrupo los préstamos por el mes de `issue_d`, entreno o aplico el _scorecard_, y calculo una métrica (AUC, PSI) por grupo. Cada fila gold resume N préstamos.

**Relación 3 — de retornos diarios a Sharpe móvil (agregación por ventana).**

```
retorno diario (processed)   N --- 1   punto de Sharpe (gold)
```

Los retornos diarios de un factor se agregan en una **ventana móvil** para producir cada punto de Sharpe. Aquí me aparece un problema técnico que trato en la sección 7 (ventanas que se solapan → autocorrelación).

**Las tres ramas gold no se relacionan entre sí.** Crédito, mercado y sintético son universos separados que comparten el _esquema_ (el contrato `metric_stream`) pero no las _claves_. No necesito un modelo relacional que los una, porque el sistema los procesa de uno en uno. Y así es como justifico que el diseño no sea relacional: mi unidad de trabajo es el flujo individual, y el valor está en que todos los flujos tengan la misma forma, no en cruzarlos entre sí.

---

## 6. Diccionario de datos inicial

Documento los campos principales de las dos caras: las variables de crédito que entran, y el contrato gold que sale. No pongo las ~20 columnas del curado de Zenodo una a una (el enunciado dice que no hace falta si el dataset es grande); documento las que alimentan el _scorecard_ y las del contrato.

**Entrada — variables de solicitud del _scorecard_ (capa `processed`, fuente: Zenodo curado):**

| Campo            | Descripción                      | Tipo        | Obligatorio | Observaciones                                                       |
| ---------------- | -------------------------------- | ----------- | ----------- | ------------------------------------------------------------------- |
| `id`             | Identificador del préstamo       | int         | Sí          | Clave para el _join_ con Kaggle                                     |
| `issue_d`        | Fecha de concesión               | date        | Sí          | Me da la estructura por cosechas. Viene como `MMM-YYYY`             |
| `loan_amnt`      | Importe solicitado               | float       | Sí          | Variable de solicitud                                               |
| `annual_inc`     | Ingresos anuales declarados      | float       | Sí          | Variable de solicitud                                               |
| `dti`            | Ratio deuda/ingresos             | float       | Sí          | Variable de solicitud                                               |
| `fico_range_low` | Puntuación FICO (banda baja)     | int         | Sí          | Variable de solicitud                                               |
| `emp_length`     | Antigüedad laboral               | categórica  | No          | Puede traer nulos ("n/a")                                           |
| `home_ownership` | Régimen de vivienda              | categórica  | Sí          | RENT/OWN/MORTGAGE/…                                                 |
| `purpose`        | Finalidad del préstamo           | categórica  | Sí          | Variable de solicitud                                               |
| `term`           | Plazo del préstamo               | int (meses) | Sí          | **Lo recupero de Kaggle.** Filtro a 36                              |
| `Default`        | Estado final (variable objetivo) | int {0,1}   | Sí          | 1 = _charged off_, 0 = _fully paid_. Ya viene construida por Zenodo |

> **Exclusión deliberada:** `int_rate`, `grade` y `subgrade` **no entran** como variables de entrada, aunque estén disponibles, porque son la _salida_ del modelo de riesgo interno de Lending Club: usarlas sería fuga de información y me contaminaría la degradación que quiero observar con la de su modelo. (Es la misma decisión que tomaron los curadores de Zenodo, y la hago mía.) Y por privacidad excluyo también `zip_code`, `addr_state`, `title` y `desc` (ver sección 8).

**Salida — el contrato `metric_stream` (capa `gold`):** ya lo he detallado en la sección 4.0. Sus campos son `stream_id, t, timestamp, value, value_se, n_obs, direction`.

---

## 7. Problemas de calidad esperados

Aterrizo cada problema a mi caso concreto, porque una lista genérica no serviría de nada.

1. **Censura por selección de resueltos (el más grave, y que ya he medido).** La versión curada solo tiene préstamos resueltos. En las cosechas cercanas al corte del volcado (~marzo de 2019), solo aparecen los préstamos que se resolvieron _pronto_, y resolverse pronto está correlacionado con impagar. Lo que he medido: para préstamos a 36 meses, la fracción en estado terminal se mantiene por encima del 98 % hasta 2016-02, baja al 87 % en 2016-03 y al 69 % en 2016-04, y se estabiliza en torno al 65 % después. **Si metiera cosechas posteriores a 2016-02, el AUC de esas cosechas estaría artificialmente distorsionado y el detector dispararía una alarma que sería 100 % un artefacto de cómo se construyó el fichero, no una degradación real del modelo.** Es el problema de calidad número uno y me condiciona toda la ventana temporal.

2. **Desequilibrio de tamaño entre cosechas (verificado).** Las cosechas de 2007–2011 son órdenes de magnitud más pequeñas que las de 2013–2016 (de decenas o cientos de préstamos a decenas de miles), con lo cual sus métricas son mucho más ruidosas. Esto afecta a qué cosechas pueden entrar en el flujo monitorizado y me obliga a fijar un tamaño mínimo de cosecha (`n_min`). El `value_se` del contrato es precisamente lo que captura ese ruido.

3. **Autocorrelación por ventanas solapadas (rama de mercado).** El Sharpe móvil lo calculo sobre ventanas que se solapan (por ejemplo, 252 días que avanzan de uno en uno), lo cual introduce una autocorrelación fuerte en la serie de Sharpe. Si calibrara un detector suponiendo que las observaciones son independientes, su tasa de falsas alarmas real sería muy distinta de la nominal. Es un problema técnico que tengo que tratar de frente (pre-blanqueo, ventanas no solapadas, o calibrar sobre el ruido empírico real).

4. **Parseo de los ficheros de Kenneth French.** Traen **varias tablas apiladas** en el mismo CSV (retornos mensuales, luego anuales, luego medias), los valores vienen en **porcentaje** (hay que dividir entre 100) y usan **códigos de dato ausente** (`-99.99`, `-999`). Si no los detecto, me corrompen todos los cálculos sin avisar.

5. **Match incompleto en el _join_ con Kaggle.** Puede haber `id` del curado que no aparezcan en el volcado de Kaggle, dejando préstamos sin `term`. Tengo que decidir su tratamiento (descartarlos o asumirles el plazo) y medir cuántos son.

6. **Fechas mal formateadas.** `issue_d` viene como `MMM-YYYY` (por ejemplo `Dec-2015`), así que hay que parsearlo a fecha real y agregarlo a cosecha mensual con cuidado.

7. **Nulos en las variables de solicitud.** Campos como `emp_length` traen nulos codificados ("n/a") que hay que tratar antes de entrenar.

8. **Falta de histórico suficiente y potencia estadística.** Detectar un cambio de media en series con mala relación señal-ruido exige muchas observaciones, y con las cosechas antiguas pequeñas el retardo de detección puede acabar siendo modesto. Por eso enmarco el resultado como _caracterizar el compromiso entre retardo y falsas alarmas_, y no como "detecto rápido".

---

## 8. Decisiones de limpieza y transformación previstas

Son hipótesis iniciales —pueden ajustarse en fases posteriores—, pero las dejo fijadas aquí.

**Filtrado a 36 meses y ventana temporal (la decisión estructural).** Me quedo **solo con préstamos a 36 meses** y con **cosechas de 2007-06 a 2016-02**. El plazo de 60 meses lo descarto porque su ventana fiable se acaba en 2014 y, además, un préstamo a 60 meses concedido en 2015 no puede haber vencido antes de 2020, que está más allá del corte del fichero: no es que sea arriesgado, es que es imposible. Mi criterio para que una cosecha sea válida: préstamos a 36 meses, concedidos dentro de la ventana, con la métrica calculada sobre al menos `n_min` préstamos maduros.

**Regla de madurez.** Una cosecha solo entra en el flujo si sus préstamos han tenido tiempo de resolverse (36 meses desde la concesión, dentro del corte del volcado). Esto es lo que implementa el corte en 2016-02. Y como refuerzo, uso el `term` que recupero de Kaggle para aplicar el criterio préstamo a préstamo, no solo a nivel de cosecha.

**Tamaño mínimo de cosecha (`n_min`).** Descarto las cosechas con menos de `n_min` préstamos maduros, por ruido de muestreo. El valor concreto de `n_min` no lo fijo a ojo: lo voy a derivar de la fórmula del error estándar del AUC (Hanley–McNeil), que me dice cuánto ruido tiene la métrica con `n` préstamos. Hasta entonces, `n_min` es un parámetro pendiente de calibrar y no un número cerrado.

**Exclusión de variables por fuga de información.** Quito `int_rate`, `grade` y `subgrade` de las variables de entrada, porque son salida del modelo interno de Lending Club.

**Exclusión de variables por privacidad.** Quito de entrada `zip_code`, `addr_state`, `title` y `desc` (los dos últimos son texto libre escrito por el propio solicitante). Son las columnas con más capacidad de reidentificación por combinación de cuasi-identificadores, y no las necesito para el _scorecard_. En ningún momento intento reidentificar a nadie. La consecuencia es que el proyecto no procesa datos personales directos y el riesgo residual me parece bajo.

**Tratamiento de nulos.** Las variables de solicitud con nulos (como `emp_length`) las imputo o las codifico como categoría "desconocido" según el caso; lo decido en la fase del _scorecard_.

**Parseo de French.** Detecto el corte entre las tablas apiladas y me quedo solo con la de retornos diarios, divido los valores entre 100 y convierto los códigos `-99.99`/`-999` en ausentes.

**Normalización temporal.** Parseo `issue_d` (`MMM-YYYY`) a fecha y lo agrego a cosecha mensual; en mercado, alineo las fechas de los factores.

**Variables derivadas que construyo.**

- La **métrica por cosecha** (AUC, PSI), que es el corazón de la capa gold de crédito.
- El **Sharpe móvil** por factor, con su error estándar corregido por la autocorrelación (Lo, 2002).
- El **error estándar** de cada métrica (Hanley–McNeil para el AUC), que va en `value_se`.

**Qué descarto y por qué (en resumen):** los préstamos a 60 meses (por imposibilidad de madurez), las cosechas posteriores a 2016-02 (por censura), las cosechas con n < `n_min` (por ruido) y las columnas de fuga y de privacidad que ya he citado.

---

## 9. Riesgos del modelo de datos

**¿Qué parte veo más clara?** La capa gold **sintética** y la de **factores de mercado** (🟢). El contrato `metric_stream` está definido, los factores de French son estables y verificables, y el generador sintético lo controlo yo por completo. Esta parte está garantizada pase lo que pase, y es la que sostiene el resultado central del proyecto (las curvas de retardo).

**¿Qué parte me genera más incertidumbre?** La capa gold de **crédito** (🟡), y no por la fuente —que ya está verificada— sino por el eslabón que la produce: el _scorecard_ tiene que entrenarse y dar un AUC con señal suficiente para que la degradación sea observable, y la ventana ya está recortada por la censura. Mi incertidumbre no es "¿tendré los datos?", sino "¿la degradación real será lo bastante nítida como para ser un buen caso de demostración?".

**¿Qué fuente o tabla puede darme más problemas?** El **join con Kaggle** para recuperar `term`. Depende de que los `id` crucen bien y de que el volcado (1,6 GB) sea manejable en la fase de procesamiento. Es el punto con más piezas móviles de todo el pipeline de crédito.

**¿Qué pasaría si no puedo construir la capa gold de crédito como la he definido?** El proyecto **no se cae**, y esto es deliberado: el resultado central (las curvas de retardo de detección) sale del **banco sintético**, que no depende de ninguna fuente externa. Perdería una de las dos validaciones reales, pero conservaría la de mercado (French) y todo el instrumento de medida. La rama de crédito es la que sostiene el _producto_ (el argumento de MRM), no el _resultado científico_.

**¿Qué alternativa tengo para simplificar el modelo si hiciera falta?**

1. **Reducir la validación real a solo mercado** (French + COVID), que es la más barata (un CSV, sin _scorecard_ ni censura). El sintético junto con mercado ya es un trabajo completo y defendible.
2. **Simplificar el _scorecard_** a menos variables y sin transformaciones sofisticadas, priorizando tener una serie de AUC por cosecha aunque sea modesta, antes que un modelo elaborado.
3. Si Zenodo me diera problemas, **replicar yo misma la curación** desde el volcado de Kaggle (está documentada por sus autores) o, como último recurso, pasar a **Fannie Mae** (fuente primaria, que cubre 2008), asumiendo el mayor volumen y la peor madurez de la etiqueta.

En el fondo, el diseño es **robusto por construcción**: ninguna rama depende de una única fuente crítica, y la rama que garantiza el resultado central (la sintética) no depende de nadie.
