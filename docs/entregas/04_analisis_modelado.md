# Entrega 4 — Diseño del análisis y estrategia de modelado

> **Proyecto: Signal Watch** — Detección secuencial de la degradación del rendimiento en modelos financieros.

---

## 0. Evolución del alcance respecto a la Entrega 3

Igual que hice en la entrega anterior, empiezo dejando constancia de lo que he cambiado de opinión **después** de la Entrega 3, ya que el enunciado pide que la entrega sea incremental y que si el diseño del análisis obliga a modificar una decisión previa, lo explique. Las entregas anteriores se quedan tal cual; esta sección es la que dice en qué me he desviado y por qué. Son cuatro cosas, y la primera es la que más cambia el proyecto.

**1. La rama de crédito se despriorizó, y en su lugar entra una señal de ML sobre datos de mercado.** En la Entrega 3 la capa gold de crédito estaba marcada como 🟡 y yo misma escribí que mi incertidumbre no era *"¿tendré los datos?"* sino *"¿la degradación real será lo bastante nítida?"*. También dejé escrita la salida: *"reducir la validación real a solo mercado, que es la más barata"*. Es exactamente la salida que he tenido que ejecutar, por calendario. Todo el análisis de censura se conserva y su conclusión sigue siendo válida (solo 36 meses, ventana 2007-06 → 2016-02), pero el _scorecard_ no se construye. En su lugar entrenó una **señal de ML sobre HML**, que cumple el mismo papel en el argumento: ser un **modelo real al que vigilar**, distinto del factor, para demostrar que el monitor no depende del modelo. Lo desarrollo en la sección 3.4.

**2. La métrica de mercado pasa a ser mensual sin solape.** En la Entrega 3 lo dejé señalado como problema de calidad número 3 (*"autocorrelación por ventanas solapadas… es un problema técnico que tengo que tratar de frente"*) y di tres salidas posibles. He medido las tres y me he quedado con la segunda, porque los números no dejan mucho margen: con ventanas de 252 días solapadas, la autocorrelación de la serie de Sharpe es **ρ = +0,996**, y un umbral calibrado para una falsa alarma cada 100 pasos da en realidad **213**. Con la métrica mensual sin solape, ρ = +0,195. Lo desarrollo en la sección 2.2.

**3. La ventana de mercado empieza en 1963-07 y no en 1926.** Esto no estaba previsto en ninguna entrega anterior: salió de mirar los datos. Lo explico en la sección 2.2, porque el motivo (la Bolsa de Nueva York cotizaba los sábados hasta 1952) es de los que corrompen una métrica mensual sin avisar, que es justo el tipo de trampa que vengo persiguiendo desde la Entrega 2.

**4. Corrijo una fecha regulatoria que di en las entregas 2 y 3.** En ambas cité el artículo 72 del Reglamento de IA europeo como obligación de monitorización posterior a la comercialización para sistemas de alto riesgo, y sigue siendo correcto. Lo que ha cambiado es **cuándo aplica**: el paquete *Digital Omnibus* ha retrasado las obligaciones de los sistemas de alto riesgo del anexo III —donde entra la evaluación crediticia— hasta **diciembre de 2027**. Lo corrijo aquí porque una fecha regulatoria caducada es de las cosas que alguien del sector detecta al instante. Lo que **sí** obliga hoy, y en esto no hay cambio, es el artículo 22 del RGPD con la sentencia *Schufa*: las decisiones automatizadas sobre personas ya tienen que poder supervisarse y explicarse.

---

## 1. Problema que se busca resolver

### 1.1 Qué ocurre actualmente y por qué es un problema

Un banco tiene decenas o cientos de modelos en producción, y todos se degradan: cambia la población, cambia el ciclo, cambia el comportamiento que el modelo aprendió. Eso ya lo conté en las entregas anteriores. Lo que me interesa aquí es **cómo** se vigila esa degradación hoy.

La práctica de la industria es un umbral fijo sobre el _Population Stability Index_: **si PSI > 0,25, alarma**. Ese número no sale de ningún cálculo. Se repite en manuales, en presentaciones y en políticas internas desde hace dos décadas, y **nadie ha publicado nunca su tasa de falsas alarmas**. Ese hueco es lo que mi banco de pruebas permite medir por primera vez, porque mido la regla exactamente igual que mido un detector.

Eso deja al equipo que vigila con tres problemas concretos:

1. **No sabe cuántas veces al año le va a saltar la alarma sin que pase nada.** Si son muchas, el equipo acaba ignorándolas, que es el peor de los mundos. Si son pocas, no sabe si es porque el modelo está sano o porque la regla es sorda.
2. **No sabe cuánto va a tardar en enterarse de una degradación real**, con lo cual no puede dimensionar el riesgo de seguir usando un modelo que ya no sirve.
3. **Una regla que mira una sola observación desperdicia información.** Si el rendimiento baja poco pero de forma sostenida, cada observación por separado parece normal y el conjunto no lo es. Eso es lo que un método secuencial aprovecha y una regla puntual no.

Y no es solo un problema técnico, ya que además están obligados a vigilarlo y a documentarlo: la guía SR 11-7 exige monitorización continua, el artículo 22 del RGPD y la sentencia *Schufa* obligan hoy a poder supervisar las decisiones automatizadas sobre personas, y el Reglamento de IA europeo añadirá obligaciones específicas de monitorización poscomercialización para la evaluación crediticia a partir de diciembre de 2027.

### 1.2 Quién usará el resultado y para qué decisión

**El usuario principal es el equipo de validación de modelos / riesgo de modelo (MRM)** de una entidad financiera, que es a quien vengo apuntando desde la Entrega 2. No es el científico de datos que construyó el modelo: es quien tiene que decir si el modelo sigue siendo apto para el uso, y quien firma esa opinión. La diferencia importa para el diseño, porque lo que entrega al final es un expediente.

**La decisión que tiene delante es:** *"¿retiro o recalibro este modelo, o lo que estoy viendo es ruido?"*. Es una decisión cara en las dos direcciones, y eso es lo que le da valor a resolverla bien: retirar un modelo sano cuesta un proyecto de remodelización y la pérdida de un activo que funcionaba, y no retirar uno degradado cuesta decisiones malas durante meses, que en crédito es mora.

El usuario secundario es el equipo propietario del modelo, que recibe la alarma con su expediente y tiene que responder.

### 1.3 Qué resultado concreto tendría que producir el proyecto

Una alarma **con dos números al lado que hoy no existen**:

- **La tasa de falsas alarmas del punto de operación**, elegida de antemano y verificada. No *"esto parece raro"*, sino *"este detector produce una falsa alarma cada diez años sobre el histórico de este modelo"*.
- **El retardo esperado ante una degradación de tamaño X**, para que el equipo sepa qué está comprando con esa tasa.

Y la alarma tiene que ser **auditable**: con qué configuración, sobre qué datos y con qué versión del código se produjo. Sin eso no entra en un expediente de validación, y si no entra en el expediente, no sirve para el usuario que he descrito.

**Mi criterio de utilidad, en una frase:** el proyecto es útil si demuestra, con verdad conocida, que un detector secuencial calibrado confirma una degradación **antes** que la regla que se usa hoy, **a la misma tasa de falsas alarmas**, y si declara con la misma claridad los casos en los que no lo consigue.

---

## 2. Análisis de datos planteado y utilidad esperada

### 2.1 Qué preguntas quiero responder

He organizado el trabajo en torno a tres preguntas, y me importa que se vea que **no son la misma pregunta en versiones distintas**:

| # | Pregunta | Cómo la contesto |
|---|---|---|
| **RQ1** | ¿Un detector secuencial separa degradación real de ruido antes que una métrica móvil, a igual tasa de falsas alarmas? | Banco sintético con el instante del cambio conocido, más inyección sobre ruido real de mercado |
| **RQ2** | ¿Cuánta de la degradación aparente es real y cuánta es que el rendimiento original nunca fue bueno y solo lo parecía? | _Deflated Sharpe Ratio_ sobre los retornos de la estrategia |
| **RQ3** | ¿Qué variable se rompió? | **Fuera de alcance**, queda en el roadmap |

> **Por qué separo RQ1 y RQ2 y no las mezclo nunca**, que no es un detalle de redacción. El _Deflated Sharpe_ contesta *"¿era alfa alguna vez?"* mirando los **retornos** de la estrategia; los detectores contestan *"¿se ha muerto?"* mirando la **métrica que vigilo**. Son dos preguntas con dos instrumentos y dos respuestas. Decir *"el DSR detectó la caída"* o *"el CUSUM demuestra que no era alfa"* sería un error de fondo, y es de las cosas que un director de validación pilla en dos segundos. Ya lo anuncié en la Entrega 2 cuando dije que quería el DSR para *"distinguir un modelo que se ha degradado de verdad de otro que en realidad nunca fue bueno"*; aquí lo formalizo como dos ejes que no se tocan.

### 2.2 Qué analizo antes del modelado, y qué me ha aportado

Esta parte no es una lista de gráficos: cada análisis ha cambiado una decisión de diseño, y por eso los cuento con lo que salió.

**Días hábiles por mes a lo largo del histórico.** Quería saber si podía usar la serie de French desde 1926, que es lo que dije en la Entrega 2. Al mirarlo me encontré con que hay **24,3–24,9 días hábiles por mes antes de 1950 y ~21 después**, y el motivo es que **la Bolsa de Nueva York cotizaba los sábados hasta 1952**. Como mi métrica es mensual y se construye con los días hábiles de cada mes, eso me metería una no-estacionariedad en el tamaño muestral que no tiene nada que ver con el fenómeno que estudio. **Decisión: la ventana empieza en 1963-07**, que además es la muestra canónica de la literatura de factores. Me quedan 757 meses, de sobra. (Llegué a esto porque los meses de los años treinta me salían con más días hábiles que los de ahora y estuve un rato convencida de que tenía un fallo en el código.)

**Verificación del _parser_ contra valores que ya conocía.** En la Entrega 2 marqué el parseo de los ficheros de French como riesgo (tablas apiladas, valores en porcentaje, códigos `-99.99`/`-999`), así que no me fiaba de que hubiera salido bien solo porque el programa no diera error. Lo contrasté contra valores que se saben de antemano: prima de mercado anualizada **+7,82%** (los libros dicen 6–9%), tasa libre de riesgo **+3,01%**, HML **+3,83%**, volatilidad diaria del mercado 1,08% → **17,1% anual**, y cero faltantes. Y miré los cinco días más extremos de la serie: salieron **1987-10-19** (Lunes Negro), **2020-03-16** (COVID), **1929-10-28 y 29**, **1933-03-15** y **2008-10-13**. Un fichero cuyos días extremos caen en las fechas que dice la historia es un fichero bien leído. No lo hice por gusto: si el parseo estuviera mal, todo lo que viene después sería ruido con formato bonito, y no me habría enterado hasta muy tarde.

**Sharpe por década.** Aquí me llevé la sorpresa más útil del proyecto. El relato fácil —*"Fama y French publican en 1992, el mercado arbitra el factor y este muere"*— **no se sostiene en los datos**: los años 2000 son la **mejor década posterior a la publicación**. La serie no decae: **cambia de régimen varias veces**. Lo desarrollo en 2.3, porque me obliga a cambiar qué puedo afirmar.

| década | 1960 | 1970 | 1980 | 1990 | 2000 | 2010 | 2020 |
|---|---|---|---|---|---|---|---|
| Sharpe | 0,60 | 1,37 | 0,89 | −0,09 | 0,74 | **−0,50** | 0,03 |
| volatilidad anual | 0,044 | 0,049 | 0,059 | 0,064 | 0,095 | 0,076 | **0,155** |

**Autocorrelación, que es lo que decide cómo construyo la métrica.** Comparé las tres opciones que había dejado abiertas en la Entrega 3, y el resultado es contundente: el mismo umbral, calibrado para una falsa alarma cada 100 pasos, da **91** sobre el ruido del banco sintético, **213** sobre un Sharpe móvil de 252 días solapado (ρ = +0,996) y **575** sobre una métrica mensual sin solape (ρ = +0,005). Lo que menos me esperaba es que la ventana solapada no da más falsas alarmas, da menos, porque la serie es tan suave que se mueve despacio. Tardé un rato en ver que eso es peor y no mejor: una tasa que crees que es de 100 y en realidad es de 213 significa que también detectas el doble de lento sin enterarte. Probé además la salida de las ventanas anuales no solapadas y me deja 40 puntos en 40 años, con lo cual el detector no llega a alarmar nunca. **Decisión: métrica mensual sin solape y recalibrar el umbral sobre la propia serie real.**

**Dispersión frente a error de medición.** σ = 5,71 frente a un error estándar mediano de ±3,53, lo cual sugiere que hay variación real del Sharpe mensual y no solo ruido de estimación. Con un matiz honesto que dejo dicho: parte de ese exceso puede venir de que la fórmula de Lo supone normalidad y los retornos tienen colas gordas, con lo cual subestima el error. No puedo separar las dos cosas sin más trabajo, así que lo digo y no le saco más punta.

**Y el análisis de crédito de la Entrega 3 sigue en pie**, aunque la rama no se construya: para préstamos a 36 meses la fracción de resueltos se mantiene por encima del 98% hasta **2016-02** y se desploma después (87,2% en 2016-03, 69,2% en 2016-04). Esa ventana está decidida con datos reales y quedaría lista si la rama se retoma.

### 2.3 Qué hipótesis quiero comprobar

| Hipótesis | Qué salió |
|---|---|
| **H1** · A igual tasa de falsas alarmas, un detector secuencial detecta antes que una regla de una sola observación | Confirmada. Ante un salto de 1σ: **18,0 pasos frente a 41,1** |
| **H2** · El umbral fijo PSI > 0,25 tiene una tasa de falsas alarmas desconocida y un retardo malo | Confirmada, y más de lo que esperaba: **no detecta nada**, 200/200 series censuradas en las 15 combinaciones de escenario y magnitud |
| **H3** · El CUSUM tiene un punto ciego ante cambios que no mueven la media | **Confirmada, y me perjudica:** ante un cambio de varianza, la regla de una observación gana (16–20 pasos frente a 38–42) |
| **H4** · Un umbral calibrado sobre una serie no se puede trasladar a otra | Confirmada: el mismo umbral da 91, 213 o 575 según cómo construya la métrica |

Las dos últimas me perjudican y las compruebo igual. La H3 la reporto con el mismo peso que los casos en los que gano: un detector que vigila la media es ciego a un cambio que no mueve la media por construcción, con lo cual es una característica del método y no algo que pueda esconder sin que se note.

### 2.4 Qué analizo durante y después del modelado

**Durante:** la calibración del umbral por bisección (aprovechando que la tasa de falsas alarmas crece de forma monótona con el umbral), el barrido de la rejilla detector × escenario × magnitud × umbral, y la comparación **siempre a igual tasa de falsas alarmas**, que explico en 6.4 porque es una regla, no una preferencia.

**Después:** la estratificación de los resultados por escenario y magnitud (un promedio sobre escenarios no mide el detector, mide la composición de mi banco de pruebas), el análisis de dónde pierde el método, y el _Deflated Sharpe_ para la RQ2.

### 2.5 Qué de todo esto acaba en el MVP

Casi todo, y a propósito, ya que mi producto es un panel donde el usuario ve el análisis y no un informe cerrado. Concretamente, la serie mensual con las alarmas de cada detector y la ventana de referencia sombreada; la curva de retardo frente a falsas alarmas; el retardo según la magnitud del cambio; el DSR frente al número de pruebas, recalculado en vivo; y un **laboratorio** donde el usuario inyecta una caída del tamaño que elija sobre ruido real y ve reaccionar a los tres detectores. Ese último es el que más me importa, ya que es lo que convierte *"confía en mi detector"* en *"pruébalo tú"*.

---

## 3. Tipo de modelos que se van a plantear

### 3.1 Qué es "el modelo" en este proyecto

Esta es la decisión de encuadre más importante de la entrega, y la pongo la primera porque si no se entiende, el resto se lee mal: **el modelo de este trabajo es el detector, no el modelo vigilado**.

El _scorecard_ de crédito o la señal de inversión son **insumos congelados**: no los entreno aquí para lucirlos, no los optimizo, y su calidad no es el objeto de estudio. Lo que diseño, comparo y valido es **el sistema que decide si el rendimiento de otro modelo ha cambiado**. Es justo lo que me avisó el tutor en su revisión de la Entrega 3 cuando pidió que el _scorecard_ y la distribución de referencia del PSI quedaran congelados antes de evaluar las cosechas posteriores: si el modelo vigilado se mueve durante el periodo monitorizado, la serie deja de medir una degradación comparable.

Con lo cual mi tarea de modelado es **detección secuencial de cambios en una serie temporal**, emparentada con la detección de anomalías pero distinta: una anomalía es un punto raro, y un cambio es una **alteración persistente del régimen**. Y no es clasificación supervisada, ya que en producción no existe una etiqueta *"aquí se degradó"* contra la que entrenar. Eso condiciona toda la estrategia de validación y lo desarrollo en la sección 6.2.

### 3.2 Las alternativas que comparo

| Alternativa | Tipo | Por qué la planteo | Limitación principal |
|---|---|---|---|
| **UmbralFijo (PSI > 0,25)** | Regla fija del sector, sin calibración | Es lo que se usa hoy. Lo implemento **con la misma interfaz que los demás detectores**, y eso es lo que me permite medirle por primera vez su tasa de falsas alarmas | Un único umbral para cualquier serie y cualquier tamaño de muestra. No se puede mover a otro punto de operación, con lo cual no tiene curva: es un punto |
| **Shewhart / 3-sigma** | Regla de una sola observación, calibrable | Es mi baseline honesto, y es **difícil de superar de forma trivial**: ante un cambio grande y brusco, una regla de una observación es imbatible en velocidad | Ignora la historia, con lo cual un desplazamiento pequeño y sostenido nunca llega a cruzar el umbral. Y su tasa de falsas alarmas la deciden los pocos valores más extremos del histórico, que es la parte peor estimada de cualquier distribución |
| **CUSUM** | Acumulador de la razón de verosimilitud | Es óptimo (Lorden, 1971) para detectar un desplazamiento de la media de tamaño conocido con el menor retardo a igual tasa de falsas alarmas. Y es interpretable: es un número que sube, y eso se puede enseñar en una pantalla | **Ciego por construcción ante un cambio que no mueve la media.** Hay que elegir `k`, que es decir de antemano qué tamaño de cambio quiero cazar |
| **Page-Hinkley** | Distancia al mínimo histórico | Otra parametrización, con memoria más larga | Es **el mismo test** que el CUSUM bajo cambio de parámetros (ver 3.3), con lo cual aporta puntos de operación distintos, no un enfoque distinto |
| **BOCPD** _(descartado por calendario)_ | Bayesiano en línea | Daría una distribución posterior del punto de cambio, no solo una alarma | Coste de implementación y de calibración. Lo dejo en el roadmap y no lo vendo como si estuviera |

### 3.3 Un hallazgo que me obligó a cambiar la parametrización

Al arreglar la estandarización de Page-Hinkley me apareció algo que no esperaba y que merece estar en la entrega:

$$S_t = \max(0,\ S_{t-1} + u_t) \;=\; m_t - \min_{j \le t} m_j$$

Es decir: **el acumulador recortado del CUSUM y la "distancia al mínimo histórico" de Page-Hinkley son la misma cantidad**. Con `delta = k` y `lambda = h`, los dos detectores producen exactamente las mismas alarmas. Lo verifiqué sobre 500 series y cuatro combinaciones de parámetros: **500 de 500 alarmas idénticas en las cuatro**. Y con `delta ≠ k` solo coinciden 102 de 500, con lo cual la coincidencia venía de la igualdad de parámetros y no de un fallo de mi prueba.

Me importa por dos motivos. Mucha literatura aplicada los trata como dos detectores distintos, con lo cual poder demostrar que son el mismo test bajo otra parametrización dice algo sobre si entiendo la matemática o solo la uso. Y el segundo es más práctico y menos elegante: si los hubiera dejado con los mismos parámetros habría dibujado dos curvas superpuestas y las habría presentado como dos métodos, sin darme cuenta. Por eso uso `delta = 0,25` frente a `k = 0,5`.

### 3.4 Sí hay un modelo predictivo, pero está en su sitio

Aquí es donde entra el cambio de alcance de la sección 0. El proyecto **sí** incluye un modelo predictivo, pero no como detector: como **modelo vigilado**. Una regresión logística decide cada mes si estar largo o corto en HML, a partir de seis variables conocidas al cierre del mes anterior (retorno de HML a 1, 3 y 12 meses, su volatilidad realizada a 3 meses, retorno del mercado a 12 meses y su volatilidad a 3 meses).

Su papel es demostrar que el monitor es **agnóstico al modelo**, que es la promesa del contrato `metric_stream` de la Entrega 3 llevada hasta el final: su Sharpe mensual neto entra por el mismo contrato y el mismo script que el factor, **sin tocar una línea del monitor ni del panel**. De hecho apareció en el panel sola, porque el panel descubre los flujos vigilados leyendo las configuraciones.

Elijo logística y no algo más flexible por tres razones, en este orden:

1. **Es interpretable**: puedo mirar el signo de cada peso y discutirlo, y puedo comprobar si se mantiene entre épocas distintas.
2. **Cada hiperparámetro que ajustase sería una prueba más que el _Deflated Sharpe_ tendría que descontar**, con lo cual estaría contradiciendo la RQ2 de mi propio trabajo. La forma legítima de ajustar (validación hacia delante anidada, eligiendo el parámetro dentro del entrenamiento de cada año) la dejo como roadmap, y no ajusto nada.
3. Con unas 600 observaciones mensuales, un modelo flexible sobreajustaría con comodidad.

Y le pongo dos baselines en vez de uno, con los mismos costes, porque con uno solo me quedaba la duda de a cuál se parecía: estar siempre largo (que es el propio factor) y la regla de una línea *"largo si HML subió en los últimos 12 meses"*, que usa la misma información que tiene el modelo. Si la regla simple hiciera lo mismo que la logística, el ML no aportaría nada y tendría que decirlo.

---

## 4. Datos de entrada del análisis y los modelos

### 4.1 El contrato `metric_stream` de la Entrega 3, ya construido

La entrada del detector es exactamente la capa gold que definí en la Entrega 3, sin cambios en el esquema. La resumo en corto porque todo lo demás se apoya en ella: **el detector no sabe de dónde viene el número**, y por eso añadir un modelo nuevo no obliga a tocar el monitor.

| Entrada | Descripción | Granularidad / tipo | Uso en el análisis |
|---|---|---|---|
| `gold/real/*.parquet` | Serie de métricas de un modelo vigilado | **Una fila = un modelo, un periodo** | Fuente única de entrada del detector |
| `stream_id` | Identificador del flujo | string | Clave, junto con `t` |
| `t` | Índice ordinal del periodo | entero ≥ 0 | Orden temporal |
| `timestamp` | Fecha de cierre del periodo | fecha | Eje temporal y auditoría |
| `value` | La métrica de rendimiento | float | **Lo que mira el detector** |
| `value_se` | Error estándar de la métrica | float ≥ 0 | Cuánto de un movimiento es ruido de estimación |
| `n_obs` | Observaciones que sostienen la métrica | entero > 0 | Sostiene el error estándar |
| `direction` | Si "peor" es subir o bajar | enum | Orienta el detector: un PSI empeora subiendo y un AUC bajando |

La simetría entre ramas, que en la Entrega 3 era una promesa de diseño, ahora está construida en las dos direcciones:

| rama | `value` | `value_se` | `n_obs` |
|---|---|---|---|
| crédito | AUC de la cosecha | Hanley–McNeil (1982) | préstamos |
| mercado | Sharpe del mes | **Lo (2002)** | días hábiles |

Son dos dominios que no se parecen en nada y el mismo contrato. El error estándar de Lo, que es el que he tenido que construir en esta fase, tiene la misma intuición que Hanley–McNeil —el ruido baja con la raíz del número de observaciones— más un término que recoge que **estimar el denominador (la volatilidad) también cuesta precisión**, y cuesta más cuanto mayor es el Sharpe.

### 4.2 Variables de entrada del modelo vigilado

Las seis que he dicho en 3.4, todas conocidas al cierre del mes *t* para predecir el signo del retorno de *t+1*. El escalado va **dentro** del _pipeline_, con la media y la desviación aprendidas solo con los datos de cada reentreno, para que no se cuele información de meses que en ese momento no existían.

### 4.3 Qué variables NO uso, y por qué

| Variable | Motivo |
|---|---|
| **τ, el instante real del cambio** | Es la regla invariante del proyecto. Ya lo anuncié en la Entrega 3 (*"ese campo lo guardo en un fichero separado… el detector no puede verlo nunca, porque eso sería hacer trampa"*), y aquí está implementado con tres barreras: vive en un esquema distinto, cargar un Parquet con una columna `tau` junto a las observaciones lanza una excepción, y solo se puede llegar a la vista del detector por una única función de paso |
| `int_rate`, `grade`, `subgrade` | Fuga de información: son la salida del modelo de riesgo interno de Lending Club, no información del solicitante. Decisión de la Entrega 2, sin cambios |
| `zip_code`, `addr_state`, `title`, `desc` | Privacidad: son las columnas con más capacidad de reidentificación por combinación. Decisión de la Entrega 2, sin cambios |
| Meses con menos de 15 días hábiles | Un Sharpe calculado con seis observaciones no es una medición. Afecta a cierres de emergencia, a la crisis administrativa de la Bolsa de Nueva York de 1968 y a septiembre de 2001 |

### 4.4 Qué información estaría disponible en el momento real

En producción, el detector solo dispone de la métrica del periodo que acaba de cerrar y de su propio estado acumulado. No mira hacia delante, y no puede, porque su interfaz no se lo permite.

En el modelo vigilado, la **validación hacia delante con ventana creciente** reproduce exactamente eso: reentreno cada diciembre con todas las filas cuyo resultado ya se conoce, con un mínimo de 120 meses, con lo cual la primera predicción es de julio de 1974. Y dentro del bucle hay **una aserción que para la ejecución si el último dato de entrenamiento no es anterior al mes que se predice**. Es la misma regla de la muralla de τ, aplicada al aprendizaje automático: prefiero que el programa se caiga a que me dé un número bonito que no significa nada.

---

## 5. Datos de salida y forma de consumo

### 5.1 La salida principal: la alarma como registro auditable

| Campo de salida | Descripción | Tipo | Uso posterior |
|---|---|---|---|
| `stream_id` | Modelo que disparó la alarma | string | Trazabilidad y unión con el resto |
| `timestamp` | Fecha del periodo de la alarma | fecha | Cuándo |
| `detector` | Qué detector la produjo | string | Comparación entre métodos |
| `valor_metrica` | La métrica en ese periodo | float | Contexto |
| `estadistico` · `umbral` | Evidencia acumulada y umbral cruzado | float | **Cuánta evidencia había**, no solo que hubo alarma |
| `numero_orden` | Cuántas alarmas van en esta vigilancia | entero | Distinguir un régimen que persiste de cambios nuevos |
| `config_hash` | Huella de los parámetros del análisis | string | ¿Con qué ajustes? |
| `hash_datos` | SHA-256 del contenido de los datos | string | ¿Sobre qué datos? |
| `commit` | Versión del código al ejecutar | string | ¿Con qué código? |
| `generado_en` | Marca temporal UTC | datetime | Cuándo se produjo |

> **Por qué las cuatro últimas columnas no son decoración.** En la Entrega 3 dije que la reproducibilidad me la garantizaban los _hashes_ de las fuentes y un _pipeline_ determinista, y no una base de datos. Esto es esa promesa construida: **cada alarma es reproducible por sí sola**. Los dos _hashes_ son complementarios a propósito, ya que los mismos parámetros sobre otros datos dan otros números, y los mismos datos con otros parámetros también; solo el par completo fija el resultado. Lo he comprobado de la forma que importa: al cambiar el generador del banco sintético pude demostrar en cinco segundos que los datos **no** se habían movido, y por tanto que los resultados guardados seguían siendo válidos sin repetir 40 minutos de evaluación.

### 5.2 Las tablas de análisis

| Fichero | Qué contiene |
|---|---|
| `curvas_retardo.csv` | Una fila por detector × punto de operación × escenario × magnitud, con tasa de falsas alarmas, retardo, censurados y excluidos |
| `calibracion_<stream>.csv` | Umbral calibrado y tasa de falsas alarmas verificada de cada detector |
| `alarmas_<stream>.csv` | Cada alarma con su expediente completo |
| `retardo_ruido_real_<stream>.csv` | Retardo medido inyectando cambios conocidos sobre ruido real |
| `deflated_sharpe_hml.csv` | PSR y DSR dentro y fuera de muestra, para varios números de pruebas |
| `resumen_<stream>.csv` | El modelo vigilado frente a sus baselines, con significancia |

Formato CSV y no base de datos, que es la decisión que ya justifiqué en la Entrega 3: son artefactos de solo lectura que se regeneran, no un estado que se escribe y reescribe.

### 5.3 Cómo lo consume el usuario, y qué decisión toma

Un panel donde el equipo de MRM ve el estado de todos los modelos vigilados, entra en uno, y obtiene la serie con sus alarmas, el retardo esperado por magnitud y la huella de reproducibilidad. La acción que habilita es **escalar al propietario del modelo con el expediente**, o descartar la alarma dejando constancia.

### 5.4 Qué información acompaña obligatoriamente al resultado

Para mí esto es parte de la salida y no del diseño visual, ya que un número suelto puede hacer más daño que bien:

- **El error estándar de cada métrica**, para que un movimiento no se lea como un cambio cuando cabe dentro del ruido de estimación.
- **La tasa de falsas alarmas verificada del punto de operación**, que es lo que se ha comprado.
- **El retardo esperado según la magnitud**, para que la ausencia de alarma no se lea como ausencia de problema: puede ser, sencillamente, que aún no haya dado tiempo.
- **La marca de censura.** Cuando más del 20% de las series no llegó a alarmar, el número es una **cota inferior y no un retardo**, y eso va **dentro de la figura**, no en una nota al pie. Un retardo censurado presentado como un número normal es el error clásico de este tipo de análisis.
- **Un cambio respecto a la Entrega 2: no hay veredicto semáforo.** Lo explico en la Entrega 5, porque es una decisión de producto, pero lo adelanto aquí: las reglas de negocio que convierten una alarma en una acción no están definidas en este trabajo, y ponerle un semáforo sería decir más de lo que sé.

---

## 6. Estrategia para diseñar y seleccionar el modelo

### 6.1 Preparación

De la capa gold sale el flujo de métricas. El baseline del detector (la media μ₀ y la desviación σ del comportamiento normal) lo estimo **sobre la ventana de referencia y nunca sobre la ventana que luego vigilo**, que es lo que haría en producción: fijas el comportamiento normal con el histórico antes de empezar a vigilar.

En la rama de mercado la referencia es **1963-1990**, y la elección tiene un motivo concreto: es el periodo **anterior a la publicación de Fama-French (1992)**, cuando nadie estaba arbitrando el factor. Es la misma disciplina que me pidió el tutor para la referencia del PSI —congelarla antes de evaluar—, aplicada a la rama que sí he construido.

### 6.2 No hay variable objetivo, y eso condiciona todo lo demás

En producción nadie etiqueta *"aquí se degradó el modelo"*. Es la limitación de la que llevo hablando desde la Entrega 2, y la salida es la misma que ya expliqué con la analogía del termómetro: **primero lo calibro en agua con hielo, donde conozco la temperatura de verdad, y solo después se lo pongo a un paciente**.

Con lo cual la verdad **la fabrico**: genero series donde el instante y el tamaño del cambio son conocidos porque los he inyectado yo. Y quiero ser precisa con lo que es: **control estadístico de procesos de manual** —inyectar señales conocidas para caracterizar un detector es lo que se hace desde los años cincuenta—, aplicado a series financieras. No es un método nuevo y no lo presento como tal. Lo que aporto es aplicarlo con rigor a un problema donde la práctica habitual no lo hace.

### 6.3 Construyo el baseline antes que los candidatos

Y son dos: la regla del sector y una regla de una sola observación calibrable. El segundo es deliberadamente **difícil de superar de forma trivial**, que es justo lo que pide el enunciado: ante un cambio grande y brusco, una regla de una observación es imbatible en velocidad. Si mi detector ganara también ahí, lo primero que haría sería revisar el experimento.

### 6.4 La regla de comparación: siempre a igual tasa de falsas alarmas

Shewhart y UmbralFijo tienen **un solo punto de operación**, ya que su umbral es fijo por definición. CUSUM y Page-Hinkley tienen uno por cada nivel de tasa de falsas alarmas que les pida. Con lo cual comparar el mejor retardo del CUSUM —el de su punto más agresivo— contra el único punto del baseline es compararlos a tasas distintas: mi detector estaría disparando cinco veces más falsas alarmas a cambio de esa velocidad, y la comparación no significaría nada.

**La regla que aplico:** para cada detector elijo el punto cuya tasa de falsas alarmas **medida** esté más cerca de la del baseline, y todas las tablas y figuras muestran exactamente esos números. Un resumen intermedio de mi propio proyecto llegó a tomar el mínimo del retardo sobre todos los puntos, que es justo el error que acabo de describir. Lo corregí.

### 6.5 Criterios de comparación, en orden

1. **Retardo a igual tasa de falsas alarmas, por estrato.** No un promedio: un promedio sobre escenarios mide la composición de mi banco de pruebas y no el detector, y además —esto lo comprobé— **puede invertir la conclusión**.
2. **Honestidad del número:** un retardo con censura alta es una cota inferior y se marca como tal.
3. **Interpretabilidad:** el estadístico del CUSUM es un número que sube y que se puede enseñar en una pantalla a alguien que no es estadístico.
4. **Coste:** la calibración se hace una vez, y la vigilancia es aritmética por observación. No es un criterio que me limite, pero lo dejo dicho.

### 6.6 Regla de decisión final

Selecciono un detector si, **a la misma tasa de falsas alarmas verificada**, su retardo es menor en la mayoría de los estratos, **y declaro explícitamente los estratos en los que pierde**. Lo segundo no es un añadido de cortesía: si un método gana en todas partes en un trabajo de este tamaño, lo más probable es que el experimento esté mal montado.

---

## 7. Estrategia de validación y evaluación

### 7.1 Cómo separo los datos

| Elemento | Decisión prevista | Justificación |
|---|---|---|
| **Banco sintético** | Dos conjuntos completos, uno de calibración y otro de evaluación, con **rangos de semillas disjuntos**, verificados por una aserción sobre los **seis pares** posibles de los cuatro rangos | Calibrar y evaluar con los mismos datos infla el resultado. La aserción lo convierte en algo mecánico en vez de una promesa mía |
| **Rama de mercado** | Referencia 1963-1990, que **solo calibra y nunca se vigila** · vigilancia 1991-2026 | Calibrar una tasa de falsas alarmas exige un tramo donde no pase nada. La serie completa está llena de cambios de régimen, con lo cual σ saldría inflada y el detector, sordo |
| **Calibración sobre una sola serie real** | **Bootstrap de bloques móviles** de la referencia (bloques de 6 meses), con **dos conjuntos de semillas distintas**: con uno calibro y con el otro verifico la tasa conseguida | Con una sola serie real no se puede medir una tasa de falsas alarmas: 330 meses con una alarma esperada cada 120 darían dos o tres. El bootstrap conserva la distribución real y la autocorrelación de corto plazo sin que yo tenga que suponer una forma |
| **Modelo vigilado (ML)** | **Validación hacia delante**, ventana creciente, reentreno anual, mínimo 120 meses | Es la única separación que se parece al uso real. Una partición aleatoria sobre una serie temporal es fuga de información con otro nombre |

### 7.2 Cómo evito que se cuele información futura

Tres barreras, y están en capas distintas a propósito, ya que una sola se puede saltar por descuido:

1. **De tipo.** El objeto que consume el detector no tiene campo `tau`, y su firma solo acepta ese objeto. Con lo cual la fuga no se puede ni escribir sin cambiar antes el contrato.
2. **En disco.** Cargar un Parquet que traiga una columna `tau` junto a las observaciones lanza una excepción.
3. **En el flujo.** Hay una única función de paso, y el motor de monitorización pasa por ella.

Y en el modelo vigilado, la aserción dentro del bucle de reentreno. Su eficacia la comprobé de dos maneras, porque una salvaguarda que nunca se ha disparado no está comprobada: **planté una fuga a propósito** y verifiqué que la ejecución se detiene, e hice un **placebo** entrenando el modelo sobre ruido puro, donde no debe ganar al baseline. Empató (0,616 frente a 0,609), que es lo que tenía que pasar; si hubiera ganado con claridad, habría fuga en alguna parte.

### 7.3 Qué métricas uso y por qué son las adecuadas

| Métrica | Qué mide | Por qué es la adecuada aquí |
|---|---|---|
| **ARL₀** (_Average Run Length_ bajo H₀) | Periodos medios hasta una **falsa** alarma | Es la tasa de falsas alarmas, es decir, el precio de la velocidad. Y es exactamente lo que nadie ha medido nunca para el PSI > 0,25 |
| **ARL₁ / EDD** | Periodos desde el cambio hasta la alarma | Es **retardo**, no tiempo absoluto: es lo que le cuesta al banco enterarse |
| **Curva ARL₁ frente a ARL₀** | Las dos a la vez, barriendo umbrales | Un detector se describe con una curva entera, y comparar puntos sueltos de dos curvas distintas no dice nada |
| **Tasa de censura** | Series que nunca llegaron a alarmar | Si las descartara, sesgaría el resultado hacia abajo, porque **las rachas más largas son justo las que se censuran** |
| **Tasa de alarma anterior al cambio** | Alarmas disparadas antes de que el cambio ocurriera | No son detecciones, pero **tampoco son gratis**: son falsas alarmas y un coste real del punto de operación |

> **El par honesto que reporto siempre es (tasa de falsa alarma antes del cambio, retardo condicionado a detección genuina)**, nunca el retardo solo. Detrás hay un sesgo de selección que he medido: un detector agresivo alarma antes del cambio en la mayoría de las series, con lo cual las que sobreviven a la exclusión son justo aquellas en las que el ruido le fue favorable. En un punto agresivo, mi CUSUM conservaba el 15% de las series mientras el UmbralFijo conservaba el 100%, porque como nunca alarma, nunca se le excluye nada. Sin reportar la exclusión, esa comparación no es una comparación.

### 7.4 Cómo analizo los errores, los casos extremos y los segmentos

- **Por estrato:** una medición por cada combinación de escenario y magnitud, nunca un agregado.
- **El punto ciego, medido en vez de escondido:** ante un cambio de varianza que no mueve la media, mi detector pierde contra la regla de una observación, y lo reporto con el mismo peso que los casos en los que gana.
- **Un efecto de discretización que no esperaba:** una regla de una sola observación sobre una referencia de *n* valores solo puede tener una tasa de falsas alarmas de *n/j*. Con 330 meses, pedirle una alarma cada 120 **no es posible**: los valores alcanzables son 330, 165, 110, 82,5… Calibro al escalón alcanzable más cercano y lo declaro en una columna, y el sistema avisa cuando la tasa verificada se aleja más de un 10% de la alcanzable. La lección de fondo juega a favor del método secuencial: la tasa de falsas alarmas de una regla puntual la deciden los tres o cuatro meses más extremos de 27 años, que es la parte peor estimada de cualquier distribución, mientras que el CUSUM depende del grueso de la distribución y no de su cola.
- **Y un resultado incómodo que cuento entero:** en el flujo del modelo de ML, la regla de una observación parece más rápida que el CUSUM ante caídas pequeñas. Lo investigué hasta el mecanismo —su umbral lo fijan los dos meses más extremos de una referencia corta cuya cola salió más fina que una normal; con una caída de 0,15σ los meses que cruzan el umbral pasan de 2 a 6, lo que predice 33 meses de retardo y se miden 30,8, y la misma cuenta sobre el otro flujo predice 66 y se miden 65,9— y **no cambié nada para arreglarlo**. Cambiar la referencia, el entrenamiento o el método de calibración después de ver el resultado sería buscar el resultado que me gusta, que es precisamente lo que critico en la RQ2.

### 7.5 Qué resultado mínimo considero aceptable, y qué hago si no lo alcanzo

**Mínimo aceptable:** que a igual tasa de falsas alarmas el detector secuencial reduzca el retardo frente al baseline en los escenarios de desplazamiento de la media, con una censura por debajo del 20% en el punto de comparación.

**Y si ningún detector superase al baseline**, el trabajo seguiría teniendo resultado, y esto no es una salida de emergencia sino parte del diseño desde la Entrega 2, cuando escribí que enmarcaba el resultado como *caracterizar el compromiso entre retardo y falsas alarmas* y no como "detecto rápido". *"La regla que usa el sector tiene una tasa de falsas alarmas de X, nunca medida hasta ahora"* es un hallazgo por sí mismo, y *"un método óptimo bajo sus supuestos no mejora al baseline sobre ruido financiero real"* sería un resultado negativo importante. Mi regla es que los resultados negativos se publican, y me ha tocado cumplirla de forma bastante literal con el escenario de cambio de varianza.

---

## 8. Riesgos y alternativas

**¿La variable objetivo está disponible y representa el fenómeno que quiero predecir?** **No está disponible, y ese es el riesgo central del proyecto.** En datos reales nadie etiqueta el instante de degradación, y además he comprobado que en HML **no existe un instante único**, ya que la serie cambia de régimen varias veces. Lo gestiono como dije en la Entrega 2: la verdad la fabrico inyectando cambios conocidos, primero sobre ruido sintético y después **sobre ruido real de mercado**. Y la serie cruda solo sostiene una afirmación débil, que es la que uso: *"la alarma cae en la ventana donde la literatura sitúa este episodio"*, **nunca** *"el sistema detectó este episodio"*. Es exactamente el aviso que me dio el tutor en la Entrega 3 cuando dijo que las ramas reales ilustran pero no permiten medir el instante con certeza; lo que he añadido es que ahora la rama real **también mide**, porque la única parte sintética es el cambio.

**¿Existe riesgo de fuga de información?** Sí, y sería el fallo que invalidaría todo el trabajo, con lo cual es donde más he invertido: tres barreras en capas distintas para el instante del cambio (sección 7.2), y para el modelo vigilado, validación hacia delante, aserción dentro del bucle, prueba con fuga plantada y placebo sobre ruido.

**¿El volumen, el histórico y la calidad son suficientes?** En mercado sí, con 757 meses. Donde voy justa es en la referencia del modelo de ML: son **198 meses**, porque el modelo necesita diez años de entrenamiento antes de su primera predicción. Todo su bootstrap sale de esos 198 valores, y de ahí salen dos limitaciones que declaro expresamente sobre la calidad de su calibración.

**¿Hay desequilibrio de clases, cambios temporales o segmentos con pocos datos?** Desequilibrio de clases no aplica al detector, porque no hay clases, y en el modelo vigilado el signo del retorno de HML está razonablemente equilibrado. Cambios temporales sí, y confirmados: HML cambia de régimen varias veces y su volatilidad se triplica entre décadas. Y segmentos con pocos datos, sí: los puntos de tasa de falsas alarmas más exigente dejan muchas series censuradas, y los marco como cotas inferiores.

**¿Qué parte me genera más incertidumbre?** Siendo honesta, **la transferencia a un modelo bancario real**. Mi validación es sobre ruido financiero real y sobre un banco sintético con verdad conocida, no sobre modelos bancarios propietarios, y eso no lo puedo resolver desde fuera de una entidad — de hecho es la misma restricción de confidencialidad que ya expliqué en la Entrega 2 y que es la razón de ser del producto. Lo declaro como mi limitación principal, y el puente que tengo es el contrato: el detector solo ve un `metric_stream`, venga de donde venga.

**Un riesgo que resultó ser el argumento comercial.** El umbral **no es trasladable entre series**: el mismo valor da tasas de falsas alarmas de 91, 213 o 575 según cómo construya la métrica. Visto de frente, eso es la demostración numérica de por qué el PSI > 0,25 no puede funcionar: *el folclore usa el mismo número para todo el mundo*. Signal Watch calibra contra el histórico del cliente y no viene con un número de fábrica.

**Y un riesgo propio de la RQ2:** el número de pruebas que hubo antes de publicar un factor **no se conoce**, y el castigo del DSR depende de él. Lo gestiono dando un rango (1, 10, 100 y 316, este último contado en la literatura) y calculando el punto de corte, es decir, **hasta cuántas pruebas aguanta mi resultado**.

### ¿Qué alternativa aplicaría si algo falla?

| Si… | Entonces… |
|---|---|
| El detector no superase al baseline sobre datos reales | Lo reporto como resultado negativo, con la tasa de falsas alarmas del folclore como hallazgo principal |
| La rama de crédito no llega por calendario | La sustituyo por una señal de ML como modelo vigilado. **Es lo que ha ocurrido**, y ha funcionado mejor de lo que esperaba como prueba de que el monitor es agnóstico al modelo |
| El modelo vigilado no bate a sus baselines | Lo declaro y lo uso igual, ya que **su papel es ser un modelo real al que vigilar, no una estrategia**. Y de hecho su ventaja no resulta significativa, y así lo digo |
| Un resultado sale mejor de lo que esperaba | **Desconfío.** Es la regla que me ha encontrado los cuatro fallos graves del proyecto, y el más serio de ellos invertía mi conclusión principal |

---

## 9. Qué tendría que poder afirmar al terminar

1. Cuánto tarda cada detector en confirmar una degradación de tamaño conocido, **a la misma tasa de falsas alarmas**.
2. Cuál es la tasa de falsas alarmas real de la regla que usa hoy la industria.
3. En qué casos mi método **no** es la mejor opción.
4. Si el rendimiento original de la estrategia era alfa o era búsqueda (RQ2, separada de lo anterior).
5. Y que todo lo anterior se vuelve a generar con un comando, sobre los mismos datos y con el mismo resultado.

El techo del proyecto lo mantengo desde el principio: esto es un prototipo validado más un caso comercial creíble. No es un sistema desplegado en un banco y no lo voy a presentar como tal.

Y lo que me queda abierto, para no cerrar la entrega con todo atado: el `n_min` de la rama de crédito sigue sin derivarse (lo dejé pendiente en la Entrega 3 y ahí sigue, porque esa rama no se ha construido); el mecanismo que impide evaluar con una configuración sin congelar está implementado pero el pipeline de evaluación todavía no lo usa, porque la curva barre muchos umbrales a propósito y no despliega uno solo; y no he decidido si la referencia de 1963-1990 debería recortarse más, ya que el Sharpe de los sesenta y el de los setenta no son iguales y eso infla algo la desviación con la que calibro.
