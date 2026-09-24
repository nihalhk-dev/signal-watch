# Limitaciones y trabajo futuro

Ninguna de estas limitaciones invalida los resultados. Se declaran porque un revisor las
encontraría, y porque declarar el límite de una medición es parte de la medición.

El criterio aplicado en todo el proyecto: **cuando un resultado se descubre incómodo, se
explica; no se cambia nada para arreglarlo**. Cambiar un parámetro después de ver el
resultado sería buscar el resultado deseado.

---

## 1. El banco de pruebas sintético

**1.1 · τ = 40 fijo en los 1.500 streams con cambio.** Solo varían el escenario y la
magnitud, no el *momento* del cambio. No se ha probado si el retardo depende de que el
cambio ocurra cerca del principio o del final de la ventana. Es una decisión de diseño
experimental defendible —controla una variable— pero limita la validez externa.

**1.2 · Censura alta en los puntos de ARL0 más exigente.** Con series de 100 pasos, un
ARL0 objetivo de 90 deja hasta 46 de 50 streams censurados: ese número es una **cota
inferior**, no una medición. La regla de dedo en control estadístico de procesos es que las
series sean varias veces más largas que el ARL0 objetivo. La comparación principal
(ARL0 ≈ 58-95) tiene censura aceptable; el extremo de la curva, no. Por eso la figura
oficial marca **con marcador hueco** todo punto con más del 20% de censura: un retardo
censurado presentado como un número normal es el error clásico de este análisis.

**1.3 · `cambio_varianza` significa cosas distintas en AUC y en PSI.** En AUC el generador
ignora `delta_sigma` y usa `factor_varianza = 4.0` fijo, así que las cinco filas de delta son
cinco réplicas de la misma condición; su oscilación sin tendencia es ruido Monte Carlo puro y
da una lectura útil del error de estas estimaciones (±5 pasos). En PSI sí usa delta, y ahí el
escenario es "deriva más inestable", no un cambio de varianza puro. Mismo nombre, dos cosas.

**1.4 · `clip_auc` recorta el 14,7% de las observaciones posteriores a τ con δ = 3,0.** El
suelo de 0,5 es semánticamente correcto —un AUC por debajo es peor que el azar— pero comprime
la magnitud efectiva del delta más grande.

**1.5 · El ruido del PSI es independiente entre periodos; el del AUC es AR(1) con ρ = 0,5.**
Es defendible (un PSI recalculado sobre una muestra nueva cada periodo no tiene por qué
heredar autocorrelación como un AUC sobre cosechas solapadas), pero es una asimetría entre
ramas y conviene decirla en voz alta.

**1.6 · El umbral PSI > 0,25 no está calibrado al tamaño de muestra.** Los resultados se
obtienen con n ≈ 800 observaciones por periodo. El hallazgo de que no detecta nada es correcto
para ese tamaño; con cohortes mucho menores el PSI de ruido sería mayor y el umbral se cruzaría
más. Esto **no debilita la crítica, la refuerza**: un umbral único e insensible al tamaño de
muestra es precisamente el problema.

**1.7 · Réplicas adyacentes de `cambio_varianza` (rama AUC) no son del todo independientes.**
El ruido extra usa `cfg.seed + 1`, que es la semilla del stream siguiente, así que el ruido
base de la réplica *r+1* y el ruido extra de la réplica *r* salen del mismo generador. No viola
R4 —calibración y evaluación siguen disjuntas— y el efecto está dentro del error de muestreo ya
declarado. Se declara en vez de arreglarse: corregirlo obligaría a regenerar el banco e invalidar
el `hash_datos` sellado, repitiendo los ~40 minutos de evaluación a cambio de un efecto menor que
la incertidumbre que ya se reporta. El arreglo correcto (`cfg.seed + 7_000_000`) queda anotado
para la próxima regeneración.

---

## 2. La validación sobre datos reales

**2.1 · La validación real es sobre un factor de mercado, no sobre un modelo bancario.** La
afirmación defendible es *"sobre ruido financiero real y sobre un banco sintético donde conozco
la verdad"*, **nunca** *"validado sobre modelos bancarios reales"*. El puente es el contrato: el
detector solo ve `MetricObservation`, venga de un scorecard o de un factor.

**2.2 · En la rama real no hay τ, y por tanto no se mide retardo sobre la serie cruda.** El
retardo sale de **inyectar un cambio de tamaño y fecha conocidos sobre ruido real**. La serie
cruda solo sostiene una afirmación más débil y verificable: dónde se encienden los detectores y
en qué ventanas históricas caen. El lenguaje obligatorio es *"la alarma cae en la ventana donde
la literatura sitúa X"*, nunca *"el sistema detectó X"*.

**2.3 · Sobre la serie cruda no hay evidencia de detección.** Las alarmas de 1991-2026 (2, 4 y 2
según el detector) no superan las ~3,6 esperadas por puro azar, y su coincidencia con episodios
famosos es en buena parte circular: los meses extremos son los que hacen famosos los episodios.
Se usan para ilustrar, nunca como detección.

**2.4 · El umbral fijo PSI > 0,25 no aplica a la rama de mercado.** Es una regla sobre el PSI, y
un Sharpe no tiene PSI. La comparación aquí es contra la regla de una sola observación
(Shewhart), a la misma tasa de falsas alarmas. Confundir las dos cosas sería exactamente el error
sobre el que avisó el tutor en la Entrega 3.

**2.5 · La ventana empieza en 1963-07 y se descartan 37 años disponibles.** Dos razones, ambas
decididas **antes** de calibrar nada: la NYSE cotizaba los sábados hasta 1952 (24,3-24,9 días
hábiles por mes frente a ~21 después), lo que metería una no-estacionariedad en el tamaño
muestral de una métrica mensual; y julio de 1963 es la muestra canónica de la literatura de
factores. No es un recorte elegido por los resultados.

**2.6 · La métrica real no es independiente del todo: ρ(lag 1) = +0,195.** Menos de la mitad del
ρ = 0,5 del banco sintético y muy lejos del +0,996 de un Sharpe móvil solapado, pero no cero. Se
maneja calibrando el umbral sobre la propia serie real en vez de importarlo. Queda declarado
porque es la diferencia entre "es independiente" y "es lo bastante independiente para lo que hago
con ella".

**2.7 · El error estándar de Lo (2002) asume retornos normales e independientes, y los reales
tienen colas gordas.** `value_se` en la rama de mercado es probablemente algo optimista. Parte del
exceso de dispersión observado (σ = 5,71 frente a ±3,53 de error de medición) podría ser eso y no
variación real del Sharpe. No se pueden separar sin trabajo adicional, así que se declara y no se
saca más punta.

**2.8 · Los Sharpe mensuales extremos están dominados por el denominador.** Los cinco peores meses
tienen volatilidad anualizada de 0,03-0,05: un Sharpe de −16,8 sale de dividir un retorno malo
entre una volatilidad diminuta. Es una propiedad del cociente, no un artefacto, pero hay que
saberlo antes de leer un valor extremo como "un mes catastrófico".

**2.9 · El retardo sobre ruido real usa el ruido de una sola historia.** Las series de la inyección
remuestrean los mismos 330 meses de referencia con los que se calibró el umbral (con otra semilla).
Mide el rendimiento sobre el ruido de esa historia, no sobre ruido fuera de muestra.

**2.10 · La referencia 1963-1990 no es un tramo perfectamente estable.** El bootstrap la trata como
"sin cambios", pero el Sharpe de los 60 (0,60) y el de los 70 (1,37) no son iguales. Si hubo cambios
dentro de la referencia, la sigma sale algo inflada y los detectores algo más conservadores de lo que
dice su ARL0.

**2.11 · Shewhart se compara a ARL0 110, no 120.** Un ARL0 de 120 no es alcanzable con una regla de
una sola observación sobre 330 valores: su probabilidad de alarma es exactamente j/330, así que su
ARL0 solo puede valer 330, 165, 110, 82,5… Se calibra al escalón alcanzable más cercano y se declara
en una columna. **La diferencia juega a favor de Shewhart, no en contra.**

**2.12 · Con una referencia finita, el ARL0 va a saltos en el umbral.** El bootstrap remuestrea un
número finito de valores, así que ciertas sumas del CUSUM se repiten y el ARL0 salta de forma
discontinua (en una prueba con datos sintéticos, de 99,5 a 129 entre h = 3,5684 y h = 3,5686). La
bisección puede caer en el borde de un salto. No ocurrió con CUSUM ni Page-Hinkley sobre datos
reales; sí se nota en el Shewhart de la señal de ML (+16%). `run_monitoring.py` avisa cuando un ARL0
verificado se aleja más de un 10% del alcanzable.

---

## 3. RQ2 — Deflated Sharpe

**3.1 · El PSR supone meses independientes.** Si los retornos mensuales de HML tienen
autocorrelación, el error estándar real difiere algo del calculado. El efecto es pequeño con
retornos mensuales, pero es un supuesto.

**3.2 · El DSR supone que las N pruebas son independientes.** En la realidad los factores probados
se parecen entre sí (variantes de ratios contables), así que el N efectivo es menor que el nominal y
el DSR con N grande **castiga de más**. Es una razón más por la que N = 316 es exagerado para HML,
que es de 1992 y anterior a casi toda esa literatura.

**3.3 · 1991 no es fuera de muestra del todo.** La muestra de Fama y French (1993) llegaba a 1991,
así que los doce primeros meses de la ventana "fuera de muestra" se solapan. Con 427 meses, su peso
es pequeño.

---

## 4. La señal de ML

**4.1 · La señal de ML no demuestra alfa, y no se presenta como tal.** Gana a los listones en
1991-2026 y pierde en 1974-1990; sus características se eligieron conociendo la literatura de
*factor momentum*, que es búsqueda implícita que ningún N nominal recoge del todo. Su papel en el
trabajo es ser **un modelo real que vigilar**, no una estrategia.

**4.2 · Su ventaja sobre los listones no es estadísticamente significativa.** El PSR de la
diferencia frente a estar siempre largo y frente a la regla de momentum de 12 meses es **0,88** en
1991-2026, por debajo de 0,95. Y la estabilidad de sus pesos (5 de 6 signos coincidentes en dos
tramos disjuntos) es sugerente pero compatible con el azar: p ≈ 0,11.

**4.3 · Los pesos individuales no se interpretan por separado.** Las características a 1, 3 y 12
meses se solapan y están correlacionadas. Con multicolinealidad el signo de cada peso por separado
no es fiable: el −0,20 de `hml_3m` entre dos positivos **no** es "reversión a tres meses".

**4.4 · Los costes (10 pb por unidad de rotación) son un supuesto, no una medición.** Los factores
de French no son carteras negociables tal cual; con costes realistas de una cartera larga-corta la
ventaja neta se reduce. Esto **no es** la simulación de valor económico, que queda fuera de alcance.

**4.5 · La referencia de la señal de ML es más corta: 198 meses (1974-1990)**, porque el modelo
necesita diez años de entrenamiento antes de su primera predicción. Todo su bootstrap sale de esos
198 valores, y de ahí vienen las limitaciones 2.12 y 4.6.

**4.6 · En el stream de ML, el Shewhart parece más rápido que el CUSUM ante caídas pequeñas (31
frente a 50 meses con 0,15σ). No es una ventaja real, y se ha verificado por qué.** Su umbral
(1,973σ) lo fijan los dos meses más extremos de una referencia de 198 cuya cola inferior salió más
fina que la de una normal (asimetría +0,22, curtosis de exceso −0,19). Con una caída de 0,15σ, los
meses que cruzan el umbral pasan de 2 a 6 —el triple—: eso predice un retardo de 198/6 ≈ 33 meses y
se miden 30,8. La misma cuenta sobre HML (330 meses, de 3 a 5) predice 66 y se miden 65,9. Sobre
ruido normal ese umbral daría un ARL0 de 41 meses, no de 115: la "ventaja" viene de una tasa de
falsas alarmas que una referencia corta subestima. Con ruido normal y a igual ARL0, el CUSUM gana
(60 frente a 81 meses).

**No se ha cambiado nada para arreglarlo** —ni la referencia, ni el entrenamiento, ni el método de
calibración—: cambiarlo tras ver el resultado sería buscar el resultado deseado. La lección de fondo
es un argumento a favor del CUSUM: la tasa de falsas alarmas de una regla de una sola observación la
deciden los tres o cuatro meses más extremos del histórico, la parte peor estimada de cualquier
distribución. El CUSUM depende del grueso de la distribución, no de su cola.

---

## 5. Código y trazabilidad

**5.1 · Hay dos caminos de calibración en el repositorio y solo uno produce los resultados.**
`detectors/calibration.py` calibra por simulación con ruido AR(1) propio; `evaluation/delay_curves.py`
calibra por bisección sobre los streams reales del banco de calibración. **Todos los números del
trabajo salen del segundo**, que es metodológicamente preferible porque calibra con los mismos datos
que declara haber usado. El primero se mantiene como utilidad independiente, declarado aquí para que
nadie tenga que adivinar cuál produjo qué.

**5.2 · R5 (no evaluar sin configuración congelada) está implementado como mecanismo, pero no se usa
en el pipeline de evaluación.** Es coherente con el diseño —la curva barre muchos umbrales a
propósito, no despliega uno solo— pero el umbral que se despliegue en una monitorización real sí
tendría que pasar por ahí. Se declara para no confundir "existe el mecanismo" con "se está usando".

**5.3 · `curvas_retardo.csv` está sellado con el commit anterior al que contiene su código**, porque
se generó antes de adoptar la regla de orden de commits (código → resultados). El `config_hash` y el
`hash_datos` siguen fijando el resultado; solo el campo `commit` no es exacto.

---

## 6. Trabajo futuro

Por orden de lo que más aportaría:

1. **Validar sobre un modelo bancario real.** Es la limitación 2.1 y la única que separa este
   prototipo de un caso de uso completo. El contrato `MetricObservation` ya está preparado: un
   scorecard con su AUC por cosecha entra sin tocar el monitor.
2. **Simulación de valor económico con costes de transacción.** Traducir el retardo de detección a
   dinero: cuánto cuesta cada mes de retraso en retirar un modelo degradado. Convierte una métrica
   estadística en un argumento de negocio.
3. **Informe MRM en PDF y registro de auditoría persistente.** La evidencia de validación ya existe
   y se enseña en la app; falta el expediente exportable que un equipo de validación adjuntaría a su
   revisión, en la línea de SR 11-7.
4. **Atribución a nivel de característica (RQ3): qué se rompió, no solo que algo se rompió.** Es la
   pregunta natural después de una alarma y la que más valor tendría para el usuario final.
5. **BOCPD** (*Bayesian Online Changepoint Detection*) como tercer detector, para contrastar el
   enfoque frecuentista con uno bayesiano que da distribución posterior del punto de cambio.
6. **Walk-forward anidado para la señal de ML**: elegir el hiperparámetro C dentro del entrenamiento
   de cada año, en vez de fijarlo. Es la forma legítima de ajustar sin fuga de información, y la
   razón por la que aquí no se ajustó nada.
7. **Rama de crédito.** La ventana sin censura está decidida con datos reales (term 36,
   2007-06 → 2016-02) y documentada; falta construir el scorecard y sus streams de AUC y PSI por
   cosecha.
8. **τ variable en el banco sintético** (limitación 1.1) y corrección de la semilla de
   `cambio_varianza` (limitación 1.7), ambas aprovechando la próxima regeneración del banco.
