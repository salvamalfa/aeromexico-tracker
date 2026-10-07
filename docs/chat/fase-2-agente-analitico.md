# Fase 2 del chat: agente analítico para negocio

Documento de diseño e implementación de la **segunda etapa del chat, posterior
al MVP**. Primero se activa el chat tal como está, siguiendo el
[traspaso de activación](traspaso-activacion-mvp-20261006.md). Después, el
agente que implemente (ChatGPT u otro) trabaja este documento paquete por
paquete, cada uno en su propio PR. Las reglas de `AGENTS.md` siguen vigentes.

Diagramas de la arquitectura actual, interactivos:
[anatomía del chat](../arquitectura/anatomia-chat.html) y
[anatomía de las herramientas](../arquitectura/anatomia-herramientas.html)
(ábrelos en un navegador; en GitHub se ven como código).

## Decisiones del dueño (7 oct 2026)

- **El MVP se activa sin cambios de código ni de prompt.** Todo lo de este
  documento es fase 2, incluidas las correcciones de estilo que salieron de sus
  calificaciones.
- **Aprueba el plan** de este documento y el orden de los paquetes.
- **Cuatro candidatos para la fase 2:** `gpt-6-luna` con esfuerzo medio y
  máximo, y `gpt-6.1-sol` con esfuerzo bajo y medio. El objetivo es encontrar
  el mejor equilibrio entre inteligencia y costo en el salto entre Luna y Sol.
- **Astra queda fuera:** es excesivo para este caso de uso.
- **Autoriza las rondas de evaluación en vivo** de este plan con esos cuatro
  candidatos. El gasto se hace por etapas: antes de cada etapa con costo, el
  agente presenta la estimación y **cuánto saldo debe cargar**, y espera a que
  lo cargue (ver [Costo](#costo-estimado-de-las-evaluaciones)).
- **Saldo de la API al 7 oct 2026:** US$2.72 gastados de US$10 cargados. El
  chat en producción consume del mismo saldo.

## Qué aprendimos de la primera evaluación

El dueño reveló los alias de la revisión a ciegas: **A = Luna, B = Sol,
C = Astra**. Sus calificaciones (`calificaciones-paquete.json`, entregado al
agente y no versionado) muestran dos problemas distintos.

**1. Redacción, que se corrige con el prompt.** Luna casi siempre obtuvo el
dato correcto, pero lo envolvía en:

- introducciones largas que narran el proceso («voy a consultar…»);
- advertencias que nadie pidió («razón determinista», «no equivale a la
  rentabilidad total», «calculado a partir de las métricas publicadas»);
- respuestas en español a preguntas en inglés, o mezclando idiomas.

El prompt de sistema actual (`SYSTEM_INSTRUCTIONS` en
`src/conversational_analytics/providers/_openai_helpers.py`) casi no dice cómo
redactar: solo pide respuestas «concisas» que declaren periodo y unidad. En
cambio, insiste en «distinguir reportado, calculado y estimado» y en
«explicar cualquier supuesto», y el modelo lo cumple al pie de la letra.

**2. Criterio, que se corrige con el prompt y con más esfuerzo de
razonamiento.** Todos los casos marcados como problema fueron de Luna:

- Q08, Q21 y Q22 del corte histórico, y Q35 del corte actual: dio una cifra
  cuando debía pedir aclaración o rechazar;
- Q40: dio un dato incorrecto.

**3. El esfuerzo de razonamiento nunca se fijó.** El proveedor manda
`CHAT_MODEL` sin parámetro de esfuerzo, así que todas las evaluaciones
usaron el valor por omisión de la API, y ese valor no quedó registrado. La
fase 2 lo hace explícito (F2.0) y lo mide (F2.9).

**Respuestas preferidas del dueño** (referencia de estilo para F2.1):

| Corte | Pregunta / alias | Por qué la prefirió |
|---|---|---|
| Histórico | Q02/C, Q03/C, Q05/C, Q09/C | Introducción mínima, dato directo, explicación y fuente separadas al final; en Q05, aclarar que Aeroméxico incluye Connect. |
| Histórico | Q06/C, Q07/C | La fuente va al final y no interrumpe el cálculo. |
| Histórico | Q04/B y Q04/C, Q10/B, Q20/B, Q24/B | Breves, directas y con saltos de línea entre la respuesta y las aclaraciones. |
| Histórico | Q12/A, Q15/A, Q25/A | Dicen directamente «no está disponible», sin explicación larga. |
| Histórico | Q13/B, Q19/B, Q32/B | Dejan claro por qué no se puede y ofrecen una alternativa o una pregunta útil. |
| Actual | Q19/A | «Directo al punto, sin introducción innecesaria». |

## Preguntas objetivo

Ejemplos del dueño del tipo de pregunta que la fase 2 debe responder:

- «¿Cuántos pasajeros transportó Aeroméxico en 2025?»
- «¿Cómo fueron los ingresos?» / «¿Cómo fue el costo operativo?»
- «¿Cuál fue el cambio de participación de Volaris contra Aeroméxico de 2025 a
  2026?» y «¿Qué rutas aumentaron más?»
- «¿Por qué aumentó el CASK de Aeroméxico este trimestre respecto al
  anterior?», cruzando las cifras con lo que dice el reporte trimestral y con
  noticias del periodo (por ejemplo, el precio del combustible).

Hoy el chat no puede responder bien ninguna de las tres últimas:

- el dashboard no tiene ingresos ni costos **totales**, solo métricas por
  ASK-km;
- los datos por ruta existen en la pestaña de Vuelos, pero el chat no los
  consulta;
- el contrato actual rechaza cualquier explicación causal.

## Arquitectura propuesta

Tres fuentes de conocimiento y una capa de presentación, cada una con sus
herramientas. Todas son de solo lectura, tienen versión y solo contienen
material publicado o aprobado:

```text
                        ┌── A. Métricas ── capa semántica + glosario ── datos publicados
Modelo ── herramientas ─┼── B. Reportes ── búsqueda con cita (empresa, periodo, página)
                        ├── C. Noticias ── índice semanal aprobado por el dueño
                        └── D. Presentación ── gráficas, comparaciones y tablas validadas
```

**A. Métricas.** Se amplía lo que ya existe:

- un glosario de negocio que lleve «ingresos», «costos», «eficiencia» o
  «cuánta gente voló» a la métrica correcta o a una aclaración;
- métricas totales (ingresos, costos, combustible, utilidad operativa)
  extraídas de los reportes con su procedencia;
- años completos: suma de trimestres para flujos; las razones como RASK u
  ocupación se recalculan con numerador y denominador, nunca se promedian;
- rutas y comparaciones de varias aerolíneas.

Mientras los datos quepan en pocos cientos de KB, el JSON publicado basta.
Cuando no, se publican archivos Parquet y se consultan con **DuckDB embebido
de solo lectura**, sin servidor. El modelo **no escribe SQL libre**: usa una
herramienta tipo constructor de consultas (métrica, agrupación, filtros, orden
y «top N») que el servidor valida contra el catálogo y traduce a SQL.

**B. Reportes.** Los reportes trimestrales y comunicados públicos se parten en
fragmentos con empresa, periodo, página y sección. Una herramienta
`buscar_en_reportes(texto, empresa, periodo)` devuelve pasajes con su cita.
Basta con búsqueda de texto completo (SQLite FTS5 o DuckDB FTS); la búsqueda
semántica es opcional.

**C. Noticias.** Una rutina semanal recopila noticias de Aeroméxico y del
sector y guarda **fichas**, no artículos completos (derechos de autor): fecha,
medio, liga, resumen propio, entidades, temas y una cita breve. El lote
semanal entra al índice publicado **solo con aprobación del dueño**. La
herramienta es `buscar_noticias(texto, desde, hasta, empresa)`.

**D. Presentación.** Las gráficas, comparaciones y tablas pasan a ser
herramientas, por ejemplo `mostrar_grafica(métricas, entidades, periodos,
tipo)`. El modelo elige qué mostrar y con qué IDs; el servidor valida y llena
los números con datos publicados. Hoy la única gráfica la arma
`get_time_series` de forma automática.

### Explicaciones atribuidas, no causalidad inventada

«¿Por qué?» se responde separando tres capas, cada una con su fuente:

1. **El dato:** por ejemplo, el CASK subió y el CASK sin combustible casi no
   cambió.
2. **Lo que dice la empresa:** «En su reporte de 2T26, Aeroméxico atribuye el
   aumento a …» [reporte, página].
3. **El contexto de prensa:** «Notas del periodo relacionan el alza del
   combustible con …» [ligas].

El modelo no afirma causas propias. La regla actual («no inferir causalidad»)
se reemplaza por «solo causas atribuidas a una fuente citada». Si ninguna
fuente atribuye una causa, la respuesta dice qué muestran los datos y que no
hay una explicación publicada.

## Paquetes de trabajo

Cada paquete va en su propio PR, con pruebas y documentación.

| # | Paquete | Criterio de salida |
|---|---|---|
| F2.0 | **Modelo y esfuerzo explícitos** (detalle abajo). | El esfuerzo se configura, se valida, se registra y se reporta. |
| F2.1 | **Prompt de redacción y criterio** (detalle abajo). | Prompt nuevo con pruebas offline; mejora medida en la etapa 1 de F2.9. |
| F2.2 | **Conjunto de evaluación de negocio y harness** (detalle abajo). | Fixture con versiones fijadas, rúbrica aprobada por el dueño y harness con conversaciones de varios turnos y candidatos `modelo@esfuerzo`. |
| F2.3 | **Glosario de negocio y métricas totales:** ingresos, costos, combustible, utilidad operativa y años completos, con procedencia y reglas de agregación. | Catálogo ampliado y conciliado con los reportes; pruebas de agregación. |
| F2.4 | **Rutas y comparaciones:** constructor de consultas sobre datos publicados de rutas y comparación de varias aerolíneas. Las cifras estimadas se rotulan como estimación. | «Top N rutas» reproducible; ninguna estimación presentada como dato observado. |
| F2.5 | **Índice de reportes** con búsqueda citada. | Pasajes con empresa, periodo y página; pruebas de citas. |
| F2.6 | **Índice semanal de noticias** con rutina programada y aprobación del dueño. | Fichas sin texto completo de terceros; flujo de aprobación; herramienta de búsqueda. |
| F2.7 | **Explicaciones atribuidas:** nueva regla causal y casos de evaluación. | Casos de «por qué» respondidos con las tres capas citadas. |
| F2.8 | **Herramientas de presentación** (gráficas, comparaciones, tablas). | Componentes en `web/`, validación en el servidor y casos de evaluación. |
| F2.9 | **Evaluación comparativa de los cuatro candidatos** (detalle abajo). | Reporte con calidad, latencia, tokens y costo por candidato; elección explícita del dueño. |

**Orden y dependencias:**

1. **F2.0, F2.1 y F2.2 primero.** Son baratos y fijan qué se mide y cómo.
   Con ellos ya se pueden correr las etapas 1 y 2 de F2.9 sobre las preguntas
   que no necesitan herramientas nuevas.
2. **Después, F2.3 y F2.4** (datos) y **F2.5 y F2.7** (reportes y
   explicaciones). F2.6 y F2.8 pueden ir en paralelo.
3. **La etapa 3 de F2.9** (comparación final de los cuatro candidatos) corre
   cuando estén las herramientas que exige el conjunto de negocio.

## F2.0 · Modelo y esfuerzo explícitos

- Nueva variable `CHAT_REASONING_EFFORT`, validada contra los valores que
  acepte cada modelo. Usa los nombres exactos de la API del día; Artificial
  Analysis los llama `medium`, `max`, `low`, etc., y pueden no coincidir. Si la
  API ofrece un control de verbosidad, se agrega igual (`CHAT_TEXT_VERBOSITY`).
- Una tabla versionada por modelo con los esfuerzos permitidos y sus tarifas,
  por ejemplo en `config/chat/`. El lanzador rechaza combinaciones no
  permitidas.
- El proveedor manda el esfuerzo en cada llamada. Cada turno guarda modelo y
  esfuerzo en la base del chat; `/api/chat/health` los muestra, y los reportes
  de evaluación los registran por respuesta.
- **Control de gasto:** más esfuerzo produce más tokens de salida. Revisa que la
  reserva por pregunta (hoy 150k tokens a la tarifa de salida) siga cubriendo
  el peor caso de cada combinación y documenta cuántas preguntas caben en el
  tope diario con cada candidato.
- Cambiar de modelo o de esfuerzo en producción sigue siendo solo un cambio de
  variables en Railway, sin redesplegar Pages.

## F2.1 · Prompt de redacción y criterio

**Formato de respuesta** (en el prompt, con ejemplos):

1. El dato o la conclusión en la primera oración. Sin narrar el proceso
   («voy a consultar…», «revisaré…»).
2. Una línea en blanco.
3. Solo el contexto que cambie cómo se lee el dato. Por ejemplo, que
   «Aeroméxico» incluye Connect, o que una cifra es estimada.
4. Al final, en una línea aparte: cómo se calculó, si aplica, y la fuente.

**Reglas:**

- Responder en el idioma de la pregunta, sin mezclar idiomas.
- No agregar advertencias que no cambien la respuesta. «Reportado o
  calculado» solo se menciona cuando importa para interpretar el dato.
- **Decidir antes de consultar:**
  - ¿Es ambigua de forma que cambie la cifra? Pregunta, y no des una cifra
    provisional.
  - ¿Está fuera de alcance? Dilo en una línea y, si existe, ofrece una
    alternativa.
  - ¿Es clara? Responde.
- Las respuestas de «no disponible» van en una o dos líneas.
- Lenguaje para ejecutivos: si se usa un término técnico (ASK-km, CASK), se
  explica en pocas palabras la primera vez.

**Ejemplos y contaminación:**

- Las respuestas preferidas del dueño (tabla de arriba) **son preguntas del
  holdout**. Incluirlas tal cual en el prompt contaminaría la evaluación;
  `evaluaciones-presupuesto.md` lo prohíbe.
- Úsalas para escribir la guía de estilo y redacta **3 o 4 ejemplos nuevos**
  sobre preguntas que no estén en ningún conjunto de evaluación.
- El agente tiene el texto de esas respuestas en el expediente privado de la
  revisión.

## F2.2 · Conjunto de evaluación de negocio

### Principios

- **Las preguntas se escriben desde la persona, no desde el catálogo.** Son de
  analistas y ejecutivos que no conocen los nombres de las métricas ni los
  periodos exactos.
- **Los valores de oro se calculan después y por código**, a partir de los
  datos publicados, nunca con un modelo.
- Cada caso define el **comportamiento esperado**: responder, aclarar,
  rechazar o responder con límites. También define sus **fallos críticos** y
  el **paquete que necesita** (F2.3–F2.8).
- El holdout de 40 queda intacto como **conjunto de seguridad**. Ambos
  conjuntos corren en cada etapa.
- El dueño revisa y ajusta la lista antes de fijarla y puede agregar
  preguntas propias.

### Preguntas propuestas (30)

El agente debe convertirlas en fixture: valores de oro, rúbrica y paquete
requerido. Las preguntas marcadas como «varios turnos» exigen que el harness
mande el historial de la conversación; hoy cada caso es de un solo turno.

**A. Lenguaje cotidiano → métrica correcta**

| # | Pregunta | Qué debe hacer | Requiere |
|---|---|---|---|
| N01 | ¿Cuántas personas viajaron con Aeroméxico el año pasado? | Sumar los trimestres del año; aclarar si son pasajeros de la compañía o AFAC si cambia la cifra. | F2.3 |
| N02 | ¿Qué tan llenos van los aviones de Aeroméxico últimamente? | Factor de ocupación del último periodo, explicado en palabras simples. | — |
| N03 | ¿A quién le cuesta más operar cada asiento, a Aeroméxico o a Volaris? | CASK del mismo periodo, explicado sin jerga; advertir solo si los modelos de negocio cambian la lectura. | — |
| N04 | ¿Cómo le fue a Aeroméxico en ingresos el último trimestre? | Ingresos totales y cambio contra el año anterior. Sin F2.3, aclarar que solo hay ingreso por asiento-km. | F2.3 |
| N05 | ¿Quién es la aerolínea más grande de México? | Elegir un criterio explícito (pasajeros AFAC) o preguntar; nunca dar un «más grande» sin criterio. | — |
| N06 | How is Aeroméxico doing compared with last year? | Responder en inglés: resumen breve de 3 o 4 indicadores contra el año anterior, o preguntar qué aspecto le interesa. | — |

**B. Comparaciones y rankings**

| # | Pregunta | Qué debe hacer | Requiere |
|---|---|---|---|
| N07 | ¿Volaris le está quitando mercado a Aeroméxico? | Tendencia de la participación de ambas en los últimos trimestres, con el segmento declarado. | — |
| N08 | Compara la participación de Volaris y Aeroméxico entre 2025 y 2026. | Aclarar qué periodos («¿2T25 contra 2T26?») o usar trimestres equivalentes y decirlo; separar puntos porcentuales del cambio relativo. | — |
| N09 | ¿Cuáles fueron las cinco rutas nacionales de Aeroméxico que más crecieron este año? | Top 5 con la cifra y el crecimiento; rotular las estimaciones. | F2.4 |
| N10 | ¿En qué rutas compiten directamente Aeroméxico y Viva? | Rutas compartidas según los datos publicados, con su cobertura. | F2.4 |
| N11 | ¿Qué aerolínea mejoró más su ocupación en el último año? | Comparar el cambio anual del factor de ocupación de las tres. | — |

**C. Tendencias**

| # | Pregunta | Qué debe hacer | Requiere |
|---|---|---|---|
| N12 | ¿Cómo ha evolucionado el costo por asiento de Aeroméxico en los últimos dos años? | Serie de CASK con gráfica y una frase de tendencia. | — |
| N13 | ¿Se está recuperando el tráfico internacional? | Tendencia de pasajeros internacionales AFAC contra el año anterior. | — |
| N14 | Muéstrame los pasajeros mensuales de Aeroméxico en 2026. | Serie mensual AFAC con gráfica, aclarando el universo. | — |

**D. «¿Por qué?» con explicaciones atribuidas**

| # | Pregunta | Qué debe hacer | Requiere |
|---|---|---|---|
| N15 | ¿Por qué subió el costo por asiento de Aeroméxico este trimestre? | CASK contra CASK sin combustible, más lo que dice el reporte, con cita. | F2.5, F2.7 |
| N16 | ¿Qué dijo Aeroméxico sobre el combustible en su último reporte? | Pasajes citados con página; sin parafrasear de más. | F2.5 |
| N17 | ¿Hubo alguna noticia que explique la caída de pasajeros de [mes]? | Fichas de noticias del periodo con ligas; si no hay, decirlo. | F2.6 |
| N18 | ¿Por qué bajó la ocupación de Volaris? | Si ninguna fuente atribuye una causa, decir qué muestran los datos y que no hay explicación publicada. | F2.5, F2.7 |
| N19 | ¿El alza del combustible afectó igual a todas las aerolíneas? | Comparar CASK y CASK sin combustible de las tres, más contexto citado. | F2.5, F2.6 |

**E. Varios pasos y cálculos**

| # | Pregunta | Qué debe hacer | Requiere |
|---|---|---|---|
| N20 | Si Aeroméxico mantiene su ritmo, ¿cuántos pasajeros tendrá en 2027? | No inventar proyecciones: no hay un pronóstico publicado. Ofrecer el crecimiento histórico. | — |
| N21 | ¿Qué parte del mercado doméstico tienen juntas Volaris y Viva? | Sumar participaciones del mismo periodo, segmento y denominador. | — |
| N22 | ¿Cuánto pesó el combustible en el costo de Aeroméxico? | Proporción del combustible en el costo, o CASK menos CASK sin combustible, explicando qué mide. | F2.3 |
| N23 | ¿Cuántos pasajeros más transportó Viva que Volaris en el primer semestre? | Sumar dos trimestres por aerolínea y restar, con la fuente declarada. | F2.3 |

**F. Seguimiento en varios turnos**

| # | Conversación | Qué debe hacer | Requiere |
|---|---|---|---|
| N24 | «¿Cómo le fue a Aeroméxico en el 2T26?» → «¿Y a Volaris?» → «¿Quién creció más?» | Mantener periodo y métricas entre turnos; definir «crecer» o preguntar. | Harness |
| N25 | Una cifra → «Explícamelo más simple». | Reformular sin consultar de nuevo ni cambiar la cifra. | Harness |
| N26 | Una respuesta → «Now in English, please». | Cambiar de idioma y conservar el contenido. | Harness |

**G. Ambigüedad y límites en lenguaje común**

| # | Pregunta | Qué debe hacer | Requiere |
|---|---|---|---|
| N27 | ¿Cuál es la mejor aerolínea? | No elegir una por opinión; ofrecer comparar por indicadores concretos. | — |
| N28 | ¿Me conviene invertir en Aeroméxico? | Sin recomendación de inversión; ofrecer datos operativos. | — |
| N29 | ¿Cuánto gana Aeroméxico por pasajero? | Explicar en pocas líneas que no hay utilidad por pasajero; el margen por asiento-km no lo es. | F2.3 |
| N30 | ¿Cuántos vuelos se cancelaron ayer? | Fuera de alcance (no hay datos operativos diarios), en una o dos líneas. | — |

### Calificación

- **Automática**, donde se pueda: valores numéricos contra el oro, presencia de
  fuentes, idioma, que no haya cifra cuando se esperaba aclaración, y los
  fallos críticos del holdout.
- **Del dueño**, a ciegas, sobre el conjunto de negocio: las cuatro respuestas
  de cada pregunta lado a lado en `review.html`, como en la primera ronda.
  Califica si es correcta, si es útil y si está bien redactada, y elige la
  mejor de cada pregunta.

## F2.9 · Evaluación comparativa

### Candidatos

| Candidato | Modelo | Esfuerzo |
|---|---|---|
| Luna-M | `gpt-6-luna` | medio |
| Luna-X | `gpt-6-luna` | máximo |
| Sol-B | `gpt-6.1-sol` | bajo |
| Sol-M | `gpt-6.1-sol` | medio |

Todos corren con el mismo snapshot, versión semántica, prompt, herramientas y
límites. Los nombres de modelo y esfuerzo se ocultan en la revisión del dueño.

### Etapas

| Etapa | Qué corre | Para qué | Cuándo |
|---|---|---|---|
| 1 | Luna-M con el prompt actual contra Luna-M con el prompt de F2.1, en los 70 casos | Medir cuánto arregla el prompt por sí solo. | Tras F2.0–F2.2 |
| 2 | Los cuatro candidatos en unas 15 preguntas (piloto) | Medir el costo y la latencia reales por candidato y recalcular el presupuesto de la etapa 3. | Tras F2.0–F2.2 |
| 3 | Los cuatro candidatos en los 70 casos; Luna-M y Luna-X dos veces, para medir variación | Comparación final. | Tras F2.3–F2.8 |

### Regla de decisión (propuesta, el dueño decide)

1. Descartar a los candidatos con algún fallo crítico o con menos de 95% de
   casos soportados correctos.
2. Entre los que queden, preferir la mejor calificación del dueño en utilidad
   y redacción del conjunto de negocio.
3. Si la diferencia es pequeña, elegir el más barato y rápido. Se reportan la
   latencia mediana y el percentil 90 por candidato; se propone que el p90 no
   pase de 60 s.
4. Opción a evaluar después: Luna como modelo por omisión y Sol solo para
   preguntas de «por qué» con varias fuentes, con ruteo automático o un botón
   de «análisis profundo».

El reporte incluye, por candidato: calidad con denominador, fallos críticos,
tokens de entrada, de salida y de razonamiento, costo por pregunta, latencia y
cuántas preguntas caben en el tope diario.

## Costo estimado de las evaluaciones

**Es una estimación de referencia, no una cotización.** Las tarifas deben
comprobarse el día de la prueba.

### Base medida (validación real, 4 oct 2026)

| Modelo | Tarifa entrada / salida (USD por millón) | Entrada media | Costo medio por pregunta |
|---|---|---:|---:|
| `gpt-6-luna` | 0.10 / 0.50 | ~40,000 tokens | US$0.0043 |
| `gpt-6.1-sol` | 2 / 10 | ~38,000 tokens | ~US$0.077 (solo intentos completos) |

Fuente: [validación real](../etapas/airline-tracker-validacion-real-20261004.md).
En Sol, el costo lo domina la entrada (prompt, fichas y resultados de
herramientas que se reenvían en cada llamada).

### Supuestos para la fase 2

- **Entrada:** 1.5 a 2.5 veces la medida, por el prompt con ejemplos, más
  herramientas y pasajes de documentos. Son 60,000 a 100,000 tokens por
  pregunta.
- **Salida más razonamiento por pregunta:** Luna-M 3k–6k, Luna-X 10k–25k,
  Sol-B 1k–3k, Sol-M 3k–8k. El razonamiento se cobra como salida.
- **Ronda completa:** 70 casos (40 de seguridad y 30 de negocio).
- No se descuenta la caché de entrada, que podría bajar mucho el costo de Sol.

| Candidato | Costo por pregunta | Ronda de 70 casos |
|---|---:|---:|
| Luna-M | US$0.008–0.013 | US$0.5–0.9 |
| Luna-X | US$0.011–0.023 | US$0.8–1.6 |
| Sol-B | US$0.13–0.23 | US$9–16 |
| Sol-M | US$0.15–0.28 | US$11–20 |

| Etapa | Costo aproximado |
|---|---:|
| Desarrollo de F2.1–F2.8 (unas 5 rondas con Luna-M) | US$3–5 |
| Etapa 1 (Luna-M, dos prompts) | US$1–2 |
| Etapa 2, piloto (4 candidatos × 15 preguntas) | US$4–8 |
| Etapa 3, final (4 candidatos y repetición de los dos Luna) | US$22–41 |
| **Subtotal** | **US$30–56** |
| Margen para reintentos y desconocidos (25%) | US$8–14 |
| **Total de referencia** | **≈ US$40–70** |

**Cómo se carga el saldo:**

- Con lo que queda hoy (~US$7) alcanzan el desarrollo y la etapa 1, si el chat
  en producción no consume mucho.
- Antes de la etapa 2 (piloto), cargar unos **US$10**.
- Antes de la etapa 3, el agente recalcula el costo con las mediciones reales
  del piloto y le dice al dueño cuánto cargar. Con estos supuestos serían del
  orden de **US$30–50**, más lo que consuma el chat en producción.
- Casi todo el gasto es de Sol: si el piloto muestra que Sol-B no mejora sobre
  Luna-X, el dueño puede sacarlo de la etapa 3 y ahorrar US$9–16.

### Lo que debe hacer el agente antes de gastar

1. **Preparar una estimación con la carga real de la fase 2.** El `--dry-run`
   actual **no sirve tal cual**: siempre carga el holdout de 40 casos, supone
   1,200 tokens de entrada por pregunta (contra ~40,000 medidos) y, sin
   `--models` ni `--model-price`, no calcula ningún candidato. En F2.2 amplía el
   evaluador para que acepte:
   - el fixture nuevo;
   - tokens de entrada y de salida por pregunta;
   - candidatos `modelo@esfuerzo` con sus tarifas.

   Hasta entonces, calcula a mano con las tablas de arriba y explica los
   supuestos.
2. **Esperar a que el dueño cargue el saldo** de cada etapa. La autorización
   cubre las etapas presentadas en la estimación, no un gasto abierto.
3. **Fijar** en el fixture `data_version`, `semantic_version`, prompt, límites,
   herramientas, modelo y esfuerzo.
4. **Reportar** lo que pide F2.9 y proponer modelo, esfuerzo y tope. El dueño
   elige.

## Límites y riesgos

- Las preguntas de varios pasos necesitan más llamadas por turno (hoy
  `CHAT_MAX_TOOL_CALLS=8`) y más tiempo. Cada cambio de límites se mide en
  F2.9.
- El esfuerzo máximo puede subir mucho la latencia; se mide y entra en la
  regla de decisión.
- Solo datos publicados o aprobados: nada de bronze, silver, warehouse privado,
  `flight_evidence_v1` ni contenido crudo de proveedores con licencia.
- Las estimaciones (por ejemplo, pasajeros por ruta y aerolínea) siempre se
  rotulan como estimación, según
  [`docs/estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md).
- Nada de búsqueda web abierta en vivo: el contexto externo entra por el índice
  de noticias aprobado.
- No reescribir el holdout histórico ni mover sus versiones: el conjunto de
  negocio es un fixture nuevo.
- Las evaluaciones en vivo siguen el procedimiento de
  [evaluaciones y presupuesto](evaluaciones-presupuesto.md), más la
  autorización de este documento.
