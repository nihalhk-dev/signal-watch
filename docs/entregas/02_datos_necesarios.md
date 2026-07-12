# Entrega 2 — Selección de idea de proyecto y análisis de datos necesarios

> **Proyecto: Signal Watch** — Detección secuencial de la degradación del rendimiento en modelos financieros.

---

## 1. Idea seleccionada

He decidido continuar con la **Idea 1** de la entrega anterior (detectar cuándo un modelo de riesgo empieza a perder precisión con el tiempo), aunque la he ampliado con una parte de la Idea 3, ya que después de trabajarlas me he dado cuenta de que en el fondo las dos preguntan lo mismo: cómo detectar que algo ha cambiado en una serie temporal financiera y que un modelo ha dejado de funcionar como antes. Al proyecto le he puesto nombre, **Signal Watch**, porque quiero que sea un producto y no solamente un estudio.

**Párrafo 1 — Problema que resuelve.** Los modelos que se despliegan en producción no se mantienen buenos para siempre, sino que se van degradando con el tiempo. Un modelo de _scoring_ de crédito se entrena con datos históricos, pero las condiciones económicas y el perfil de los clientes cambian, lo cual hace que el modelo vaya perdiendo capacidad de discriminación y de calibración poco a poco, muchas veces sin que nadie se dé cuenta hasta que ya ha causado un problema. Con una señal de trading pasa algo parecido, ya que cuando una estrategia funciona el mercado acaba arbitrándola y su rentabilidad se va perdiendo. Quien tiene este problema son las entidades financieras que tienen modelos en producción —en concreto, los equipos de **model risk management (MRM)** y de validación interna, que son quienes usarían la herramienta—, y no es solo un problema técnico, ya que además están **obligadas por la regulación** a vigilar esa degradación y a documentarla: la monitorización continua de modelos es una exigencia del marco de _model risk management_ (la guía SR 11-7) y, en Europa, del artículo 72 del Reglamento de IA, que exige monitorización posterior a la comercialización para los sistemas de alto riesgo, entre los que está el _scoring_ crediticio. Creo que el valor de resolver esto está en poder detectar el deterioro pronto y con rigor estadístico, y no cuando ya ha costado dinero o un incumplimiento regulatorio.

**Párrafo 2 — Solución planteada.** Lo que quiero construir es un sistema que reciba un flujo temporal con una **métrica de rendimiento del modelo** (AUC/Gini, KS, PSI o calibración en el caso de un modelo de crédito; Sharpe o _Information Coefficient_ en el caso de una señal de inversión) y que aplique **métodos de detección secuencial de cambios** —principalmente CUSUM y el test de Page-Hinkley— para lanzar una alarma cuando aparece una degradación real y no simplemente ruido. Me parece que la parte más importante del proyecto no es aplicar los detectores, sino **demostrar que funcionan**, y para eso necesito dos tipos de datos que hacen trabajos distintos y que no se sustituyen entre sí. Por un lado, **datos reales de crédito** (Lending Club), sobre los que entreno un modelo de _scoring_ con las cosechas antiguas, lo aplico hacia adelante sobre las cosechas posteriores y obtengo una **degradación real y no inventada** sobre la que demostrar que el sistema sirve. Y por otro lado, un **banco de pruebas sintético**, en el que cojo una serie estable, le inyecto una degradación controlada en un instante que yo conozco, y **mido** cuánto tarda cada detector en detectarla y con qué tasa de falsas alarmas. Esto último es imprescindible porque el retardo de detección es una resta (_instante de la alarma_ menos _instante real del cambio_), y en los datos reales el segundo término sencillamente no existe: nadie sabe qué día exacto empezó a degradarse un modelo. Además quiero añadir una capa de _Deflated Sharpe Ratio_, para poder distinguir un modelo que se ha degradado de verdad de otro que en realidad nunca fue bueno y solo lo parecía por sobreajuste o por suerte.

**Párrafo 3 — MVP del proyecto final.** El producto mínimo viable que quiero presentar es un **dashboard funcional** (en Streamlit) que se pueda ver ejecutándose: recibe un flujo de métricas, lo evalúa periódicamente y muestra la métrica móvil con los **marcadores de alarma**, la banda del _Deflated Sharpe_, un **veredicto de salud** del modelo explicado en lenguaje claro, y la **exportación de un informe estilo MRM con registro de auditoría** (identificador y versión del modelo, métrica, umbral, historial de alarmas con marca temporal y acción recomendada). Por debajo del dashboard estará el _pipeline_ de detección ya validado, con sus **curvas de retardo de detección frente a falsas alarmas** (obtenidas del banco de pruebas sintético) y una **simulación de valor económico** (cuánto se ahorraría reaccionando a la alarma frente a no reaccionar). Quiero que se pueda ver funcionando sobre los tres frentes: la degradación real de un modelo de crédito (Lending Club), la degradación real de factores de mercado (Kenneth French) y el banco de pruebas sintético.

---

## 2. Datos necesarios

**Qué variables necesito.** Como el proyecto tiene varias ramas, necesito datos de cuatro tipos:

- **Rama de crédito (la que sostiene el producto):** datos de préstamos a nivel de operación, con las **variables conocidas en el momento de la solicitud** (importe, plazo, tipo de interés, _grade_, antigüedad laboral, régimen de vivienda, ingresos anuales, ratio deuda/ingresos, historial de morosidad, tramo FICO, cuentas abiertas, utilización de crédito revolvente…), más dos campos que para mí son críticos: la **fecha de concesión** (`issue_d`), que es lo que me da la estructura temporal por cosechas, y el **estado final del préstamo** (`loan_status`), que es mi variable objetivo.
- **Rama de mercado (factores):** fecha y **retornos de factores** (Mkt-RF, SMB, HML, Momentum y, si me sirven, RMW y CMA), además del activo libre de riesgo (RF).
- **Señal construida por mí:** **precio ajustado de cierre** por _ticker_ y fecha, con el que construyo una señal de _momentum_ 12-1. Esta rama me importa porque es la única del lado de mercado en la que controlo la "fecha de nacimiento" de la señal.
- **Banco de pruebas sintético:** no son datos que descargue, sino que **los genero yo** con un proceso documentado, inyectando una degradación de forma y momento conocidos.

Como el proyecto combina cuatro ramas con frecuencias distintas, resumo en una tabla la granularidad, el histórico y el volumen de cada una, y después lo desarrollo:

| Rama                      | Granularidad                                       | Profundidad histórica | Volumen aproximado                    |
| ------------------------- | -------------------------------------------------- | --------------------- | ------------------------------------- |
| Crédito (Lending Club)    | 1 fila por préstamo → agregado por cosecha mensual | 2007–2018 (11 años)   | ~2M préstamos, ~1–2 GB                |
| Factores (Kenneth French) | 1 fila por día y factor                            | Desde 1926            | ~26.000 días × 6–7 factores           |
| Señal propia (precios)    | 1 fila por _ticker_ y día                          | ~20 años              | Decenas de _tickers_ × ~5.000 días    |
| Banco sintético           | 1 fila por escenario, réplica e instante           | La que yo defina      | Millones de filas (controlado por mí) |

**Granularidad.** En la rama de crédito, **a nivel de préstamo**, que después agrego **por cosecha** (mensual o trimestral) para poder calcular la métrica del modelo periodo a periodo. En la rama de mercado, serie temporal **diaria** a nivel de factor, y a nivel de **_ticker_ y fecha** para la señal propia.

**Profundidad histórica.** Necesito **años, no meses**, y esto no es negociable, ya que para validar detectores de cambio hacen falta varios **regímenes distintos** y episodios de degradación reales. En crédito, los datos de Lending Club van de **2007 a 2018** (once años), suficiente para que un modelo entrenado con las cosechas antiguas se degrade de verdad sobre las nuevas. En mercado, la librería de Kenneth French tiene histórico desde **1926**, lo cual me da varios regímenes y episodios documentados en la literatura (el debilitamiento de ciertos factores a partir de los 2000, o la ruptura de marzo de 2020 con la COVID).

**Volumen.** Razonable y manejable: en crédito, del orden de **2 millones de préstamos** con unas decenas de variables (un par de GB); en mercado, **miles de observaciones diarias** para unas decenas de factores y _tickers_; más los flujos sintéticos que genere yo. No es _big data_, cabe en memoria con un poco de cuidado y no necesito infraestructura pesada, lo cual lo he decidido a propósito para que el proyecto sea realista dentro del curso.

**Imprescindibles y deseables.**

- **Imprescindibles:** los datos de crédito de Lending Club (con fecha de concesión y estado final), los retornos de factores de Kenneth French, y poder **generar el banco de pruebas sintético**.
- **Deseables pero no obligatorios:** los precios para la señal propia de _momentum_; más factores y más _tickers_; y los datos hipotecarios de Fannie Mae como versión más representativa de un entorno bancario (ver la nota al final de la sección 3).

---

## 3. Fuentes de datos previstas

Antes de detallarlas, resumo **qué papel juega cada una**, ya que no son intercambiables y creo que es la decisión de diseño más importante de esta entrega:

| Fuente                         | Para qué sirve                                                             | ¿Permite medir el retardo de detección?                         |
| ------------------------------ | -------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Lending Club**               | Demostrar que detecto la degradación **real** de un modelo de crédito real | No (nadie sabe el día exacto en que empezó)                     |
| **Kenneth French**             | Demostrar que detecto degradación **real** de mercado                      | No                                                              |
| **Banco de pruebas sintético** | **Medir** el detector: curvas de retardo frente a falsas alarmas           | **Sí** (es el único sitio donde conozco el instante del cambio) |

Es decir: las fuentes reales **demuestran**, y la sintética **mide**. Necesito las dos cosas.

---

**Fuente 1 — Lending Club (datos reales de crédito).** Es la fuente que sostiene la rama de producto.

- **Qué es:** todos los préstamos concedidos por Lending Club entre **2007 y 2018**, con las variables de la solicitud y el estado final del préstamo.
- **Acceso:** público y gratuito. Mi referencia principal es la **versión curada específicamente para modelos de concesión** publicada en Zenodo (<https://zenodo.org/records/11295916>), que es un repositorio académico con DOI y que se queda solo con las variables conocidas en el momento de la solicitud y con los préstamos en estado final (_default_ o _fully paid_). Esta versión me interesa porque me evita de entrada los problemas de fuga de información. El volcado completo está además replicado en Kaggle (<https://www.kaggle.com/datasets/wordsforthewise/lending-club>) y en Figshare, que uso como copias de seguridad.
- **Formato:** CSV.
- **Estabilidad:** el histórico es estático y está replicado en varios repositorios (Zenodo, Kaggle, Figshare), con lo cual no depende de que una web concreta siga viva.
- **Licencia:** al ser datos abiertos replicados en repositorios académicos, puedo trabajar con ellos y publicar el código en un repositorio público sin problemas de redistribución.
- **Riesgos que he detectado:**
  - **Madurez de la etiqueta.** Un préstamo a 36 o 60 meses concedido en 2018 todavía no tiene estado final, con lo cual las cosechas más recientes están censuradas. Si no lo controlo, la métrica del modelo se corrompe en silencio. Lo mitigo usando solo cosechas maduras o definiendo una ventana fija de incumplimiento.
  - **Sesgo de selección ("through the door").** Los datos solo contienen préstamos **concedidos**, no los rechazados, lo cual es un sesgo bien conocido en _credit scoring_. Lo asumo y lo declaro.
  - **Representatividad.** Lending Club es una plataforma de préstamos P2P, no un banco. El problema de modelado es el mismo (_scoring_ de crédito al consumo), pero no lo voy a presentar como si fueran datos bancarios.

**Fuente 2 — Kenneth French Data Library (Tuck School of Business, Dartmouth).** Mi fuente principal para la rama de mercado. Es la librería de datos de factores del economista Kenneth R. French (el de los modelos de Fama-French).

- **Acceso:** abierta y pública, sin restricciones, sin pagos ni permisos.
- **Enlace:** <https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html>
- **Formato:** ficheros **CSV** comprimidos en ZIP, descargables directamente o con librerías como `pandas-datareader`.
- **Histórico:** desde **1926**, y se actualiza de forma continua.
- **Estabilidad:** es la fuente de referencia en investigación de factores, mantenida durante décadas y estable en su estructura.
- **Riesgos que he detectado:** los CSV traen **varias tablas apiladas** en el mismo fichero (retornos mensuales, luego anuales, luego medias), los valores vienen en **porcentaje** y no en decimales (hay que dividir entre 100), y usan **códigos de dato ausente** (`-99.99` / `-999`). Son riesgos controlados, pero obligan a hacer el _parsing_ con cuidado, ya que si no se detectan corrompen todos los cálculos sin avisar.

**Fuente 3 — yfinance (Yahoo Finance), con Stooq de respaldo.** Para los precios de la señal que construyo yo.

- **Acceso:** librería _open source_ de Python (`pip install yfinance`), gratuita. Respaldo: **Stooq** (<https://stooq.com>), CSV descargable de acceso libre.
- **Estabilidad:** **riesgo medio**, ya que yfinance es una API **no oficial** que puede cambiar o dejar de funcionar, tiene límites de peticiones, tiene **sesgo de supervivencia** (los _tickers_ deslistados no aparecen, lo cual hace que los resultados parezcan mejores de lo que son) y obliga a usar el **precio ajustado**, porque si no los _splits_ y los dividendos corrompen los retornos.
- **Mitigación:** descargo los precios **una sola vez** y los guardo en disco, con lo cual la inestabilidad de la API deja de afectarme durante el resto del curso.

**Fuente 4 — Banco de pruebas sintético (generado por mí).** No es una fuente de datos al uso, sino **mi instrumento de medida**.

- **Origen:** **código propio**, con un proceso generador documentado y una degradación inyectada de forma y momento conocidos.
- **Por qué lo necesito:** el resultado central del proyecto es un número del tipo _"el detector tarda X observaciones en detectar una caída de tamaño δ, con un Y% de falsas alarmas"_. Ese retardo es una **resta**: instante de la alarma menos instante real del cambio. En los datos reales el segundo término **no existe**, ya que nadie sabe qué día exacto empezó a degradarse un modelo (es una limitación reconocida en toda la literatura de detección de cambios). La única forma de conocer ese instante es inyectarlo yo. Es decir, **el sintético no sustituye a los datos reales ni es una excusa para evitarlos**: es la única manera de _medir_ el detector, igual que un termómetro se calibra en agua con hielo antes de ponérselo a un paciente.
- **Qué aporta y qué no:** aporta las **curvas de retardo de detección frente a falsas alarmas**, que son el resultado central del proyecto. No aporta **ninguna** evidencia de que el sistema sirva en el mundo real — para eso están Lending Club y Kenneth French.
- **Ventaja añadida:** control total y **cero dependencia de terceros**, con lo cual esta rama está garantizada pase lo que pase.
- **Riesgo:** ser un dato sintético. Lo asumo, lo declaro explícitamente como parte del diseño de validación, y en ningún momento lo presento como si fuera un dato real.

### Fuentes que he explorado y descartado (y por qué)

Antes de decidirme busqué datos de crédito **europeos y a nivel de préstamo**, que serían más representativos del entorno bancario en el que se aplicaría el producto. La conclusión es que **prácticamente no existen de forma pública**, y creo que el motivo es la parte más interesante:

- **Banco Nacional de Suiza (data.snb.ch):** es una fuente gratuita, descargable y mantenida desde hace décadas, pero lo que publica son **datos agregados** (balances, agregados monetarios, tipos de interés, estadística bancaria anual). No hay información préstamo a préstamo, y sin ella **no puedo entrenar un _scorecard_** ni calcular su rendimiento cosecha a cosecha. Serviría como covariable macro, pero no para el núcleo del proyecto.
- **European DataWarehouse (<https://eurodw.eu>):** es el repositorio de titulizaciones designado por ESMA y sí contiene datos **a nivel de préstamo** de toda Europa (más de 2.000 millones de registros, entre hipotecas, consumo, auto y pymes). Sería exactamente lo que necesitaría, pero es una **plataforma comercial de suscripción**, con lo cual no es viable dentro del alcance de este proyecto salvo que exista un acceso institucional (lo consulto con el tutor, ver nota más abajo).
- **Registros de crédito supervisores** (tipo AnaCredit del BCE o la CIRBE del Banco de España): contienen exactamente el detalle que haría falta, pero **no son de acceso público**, ya que están reservados a supervisores y a programas de investigación restringidos.

**Y aquí está el punto que me parece importante:** que no existan datos públicos europeos de crédito a nivel de préstamo no es una casualidad ni una mala suerte mía, sino una consecuencia directa del **secreto bancario y de la protección de datos**. Es decir, es exactamente la misma restricción de confidencialidad que hace que este producto tenga sentido: si yo pudiera descargarme el rendimiento del modelo de _scoring_ de un banco, la herramienta no haría falta. Esa restricción es justamente la razón por la que la monitorización tiene que ejecutarse **dentro** de la entidad, que es donde se desplegaría Signal Watch.

**Alternativa institucional — Fannie Mae, _Single-Family Loan Performance Data_.** La tengo como **plan B y como posible extensión**, no como fuente principal, y creo que merece la pena explicar por qué en ambos sentidos.

- **Qué es:** los datos de comportamiento crediticio que publica la propia Fannie Mae sobre una parte de su cartera hipotecaria: características estáticas en el momento de la originación más el **rendimiento mensual** de cada préstamo, desde el año **2000** hasta la actualidad, en ficheros CSV trimestrales y con actualización trimestral (<https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/fannie-mae-single-family-loan-performance-data>). Es gratuito, pero requiere registro en su plataforma Data Dynamics. Freddie Mac publica un conjunto prácticamente equivalente.
- **Por qué es mejor que un volcado de Kaggle:** es una **fuente primaria**, publicada por la propia entidad, y no un espejo de terceros. Además cubre la crisis de 2008, que es una ruptura real, fechada y no discutida en el rendimiento de los modelos de crédito.
- **Por qué no la uso como fuente principal:** son **hipotecas a 30 años**, con lo cual el incumplimiento tarda años en materializarse y el problema de madurez de la etiqueta se agrava mucho respecto a Lending Club; el volumen es de decenas de millones de préstamos (la propia Fannie Mae advierte de que el conjunto completo es muy grande); y sus **condiciones de uso prohíben la redistribución a terceros**, lo cual choca con la obligación de mantener un repositorio público (podría publicar el código de descarga, pero no los datos). Para un proyecto de un curso, como fuente principal me comería el tiempo que necesito para los detectores.

> **Nota sobre el alcance de las fuentes (pendiente de consultar con el tutor).** Las ramas real y sintética son complementarias y mantengo las dos, ya que responden preguntas distintas: la sintética es el **instrumento de medida** y Lending Club es la **validación sobre degradación real**. Lo que sí queda abierto es una decisión de **alcance**, y son dos preguntas concretas: (1) si Lending Club es suficiente como demostración real, o si merece la pena asumir el coste de añadir además Fannie Mae, más representativa de un entorno bancario pero considerablemente más pesada y con restricciones de redistribución; y (2) si existe algún **acceso institucional** al European DataWarehouse a través de la universidad, en cuyo caso podría contemplarse como extensión, aunque no construyo el proyecto sobre esa posibilidad.

---

## 4. Consideraciones de privacidad y protección de datos

Esta sección cambia respecto a lo que había pensado al principio, ya que al incorporar datos reales de crédito el proyecto **sí toca datos de personas**, aunque sea de forma indirecta, y me parece más honesto analizarlo bien que decir que no hay ningún riesgo.

**¿Los datos incluyen información personal identificable?** No de forma directa. Los datos de Lending Club se publican **sin identificadores directos** (no hay nombres, ni documentos de identidad, ni números de cuenta), y es la propia plataforma la que los hace públicos. Sin embargo, **sí contienen cuasi-identificadores**: ingresos anuales, tramo FICO, antigüedad y puesto de trabajo, estado y prefijo del código postal. Combinados, en teoría podrían reducir bastante el anonimato de una persona concreta, y por eso no los trato como si fueran inocuos.

**¿Sería necesario anonimizar, agregar o filtrar?** Sí, y lo voy a hacer. Mi plan es **eliminar de entrada las columnas geográficas y de texto libre** (código postal, estado y puesto de trabajo), que son las que más capacidad de reidentificación aportan y que además apenas necesito para el modelo. Me quedo únicamente con las variables que el _scorecard_ necesita, y **en ningún momento voy a intentar reidentificar a nadie**. La versión curada de Zenodo ya reduce el conjunto a las variables de solicitud, con lo cual me ayuda también en esto.

**¿Se pueden usar de forma segura en un proyecto académico?** Sí. Son datos publicados de forma abierta por la propia entidad, replicados en repositorios académicos (Zenodo, Figshare) y ampliamente utilizados en investigación de riesgo de crédito. Su uso académico es legítimo, y con el filtrado que he descrito el riesgo residual me parece bajo.

**¿Existen riesgos éticos o legales?** Aquí quiero hacer dos precisiones que creo que son importantes:

- Sobre **mis datos**: el riesgo real no es de identificación directa, sino de **reidentificación por combinación de cuasi-identificadores**, y lo mitigo eliminándolos.
- Sobre el **dominio de aplicación**: los modelos de _scoring_ de crédito toman decisiones automatizadas sobre personas y están sujetos al RGPD (artículo 22 y la sentencia _Schufa_) y al Reglamento de IA, que los clasifica como sistemas de alto riesgo. Esto forma parte de la **motivación** del proyecto (es justamente lo que obliga a monitorizarlos), y no de un problema en mi manejo de los datos. De hecho me parece relevante señalar una implicación ética: si un modelo se degrada de forma desigual entre distintos grupos de población, eso no es solo un problema de rendimiento sino también de equidad. **No voy a abordar el análisis de sesgos en este proyecto**, para no abrir un frente que no podría cerrar bien en el tiempo disponible, pero sí quiero dejarlo señalado como una extensión natural del sistema.

**¿He decidido evitar algún dato por privacidad?** Sí, dos cosas. Primero, las columnas geográficas y de puesto de trabajo de Lending Club, como acabo de explicar. Y segundo, **no voy a usar métricas ni distribuciones de _scores_ de modelos reales de ninguna entidad financiera**, que serían confidenciales y potencialmente sensibles, y que además no son públicas; para esa parte uso el banco de pruebas sintético.

---

## 5. Viabilidad inicial del proyecto

**¿Parece viable obtener los datos?** Sí, y creo que es una de las partes más fuertes del proyecto. Los datos de crédito de Lending Club son públicos, gratuitos, están replicados en varios repositorios y existe una versión ya curada; los factores de Kenneth French son abiertos, estables y con décadas de histórico; los precios los puedo sacar de yfinance o Stooq; y el banco de pruebas sintético lo controlo yo por completo. Además he evitado a propósito las fuentes difíciles de conseguir (CRSP, Compustat, Bloomberg, registros supervisores o datos internos de una entidad), que son justo las que suelen hundir este tipo de proyectos por problemas de acceso.

**¿Tienen suficiente calidad, granularidad e histórico?** Sí. En crédito tengo once años de cosechas reales, que es justo lo que necesito para que un modelo entrenado con datos antiguos se degrade de verdad sobre datos nuevos. En mercado tengo décadas de datos diarios con varios regímenes y episodios de degradación documentados en la literatura. Y la granularidad (préstamo a préstamo, día a día) es la adecuada para lo que quiero hacer.

**¿Se puede desarrollar de forma realista durante el curso?** Sí. El volumen es manejable, los métodos se pueden implementar con librerías estándar de Python, y tengo el desarrollo planificado por fases, con un núcleo bien delimitado y con las extensiones marcadas explícitamente como opcionales para poder recortarlas si me quedo sin tiempo.

**¿Qué parte veo más arriesgada ahora mismo?** Siendo honesta, veo cuatro cosas:

1. La **madurez de la etiqueta** en Lending Club, que es la trampa más seria de esa fuente: si no controlo que las cosechas recientes están censuradas, mi métrica se corrompe sin avisar.
2. La **potencia estadística**: detectar un cambio de media en series con mala relación señal-ruido exige muchas observaciones, con lo cual el retardo de detección puede acabar siendo más modesto de lo que suena. Por eso enmarco el resultado como _caracterizar el compromiso entre retardo y falsas alarmas_, y no como "detecto rápido".
3. El **rigor de mi propia validación**, es decir, no sobreajustar la evaluación ajustando los hiperparámetros de los detectores hasta que salga la curva bonita. Lo mitigo fijando las configuraciones de antemano y reservando el periodo de validación real.
4. La **estabilidad de yfinance**, al ser una API no oficial, aunque la mitigo descargando los datos una sola vez y guardándolos en disco.

**¿Qué alternativa tengo si falla la fuente principal?** El proyecto es **robusto en datos** por diseño, ya que ninguna rama depende de una única fuente. Si Lending Club diera problemas, mi alternativa es el _Single-Family Loan Performance Data_ de **Fannie Mae**: es fuente primaria, gratuita, cubre desde el año 2000 e incluye la crisis de 2008, aunque a cambio tendría que asumir un volumen mucho mayor, un problema de madurez de la etiqueta más severo (son hipotecas a 30 años) y sus restricciones de redistribución. Freddie Mac publica un conjunto equivalente que serviría igual. Si la librería de Kenneth French no estuviera disponible (muy improbable), se puede acceder también con `pandas-datareader` y existen conjuntos de factores alternativos. Si falla yfinance, tiro de Stooq. Y el **banco de pruebas sintético no depende de ninguna fuente externa**, con lo cual el resultado central del proyecto —las curvas de retardo de detección— está garantizado pase lo que pase.

---
