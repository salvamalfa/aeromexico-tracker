# Fase 2 del chat: agente analítico para negocio

Propuesta de diseño aprobada en lo general por el dueño el 7 de octubre de 2026.
Es la **segunda etapa, posterior al MVP**: primero se activa el chat tal como
está, siguiendo el [traspaso de activación](traspaso-activacion-mvp-20261006.md),
y después se trabaja este documento por paquetes, cada uno en su propio PR.
Las reglas de `AGENTS.md` siguen vigentes.

Diagramas de la arquitectura actual, interactivos:
[anatomía del chat](../arquitectura/anatomia-chat.html) y
[anatomía de las herramientas](../arquitectura/anatomia-herramientas.html)
(ábrelos en un navegador; en GitHub se ven como código).

## Decisiones del dueño (7 oct 2026)

- **El MVP se activa sin cambios de código ni de prompt.** Todo lo de este
  documento, incluidas las correcciones de estilo que salieron de sus
  calificaciones, es fase 2.
- **Está de acuerdo con el plan** de las secciones siguientes y con el orden
  propuesto.
- **Autoriza nuevas rondas de evaluación en vivo con cada modelo candidato**
  para la fase 2. Antes de gastar, el agente debe presentarle la estimación
  de costo y **cuánto saldo necesita cargar** en OpenAI (ver
  [Evaluación y presupuesto](#evaluación-y-presupuesto)).
- **Saldo actual de la API:** US$2.72 gastados de US$10 cargados (7 oct 2026).
  El chat en producción consume del mismo saldo.

## El problema

El holdout de 40 preguntas (`tests/fixtures/chat_evals/holdout.json`) se
escribió desde el catálogo: primero el dato y después la pregunta, con jerga
técnica («¿Cuántos ASK-km publicó Volaris en 2T26?»). Mide bien la
**seguridad** (no inventar, no filtrar datos privados, no confundir puntos con
porcentaje) y se conserva como regresión. No mide la **utilidad** para el
público del dashboard: analistas de negocio y ejecutivos que preguntan en
lenguaje común, piden comparaciones y quieren saber por qué cambió algo.

Las notas del dueño al calificar repiten tres defectos de estilo:

- introducciones largas sobre el proceso antes de dar el dato;
- advertencias que nadie pidió («razón determinista», «no equivale a la
  rentabilidad total», «calculado a partir de las métricas publicadas»);
- respuestas en español a preguntas en inglés, o mezclando idiomas.

También marcó como problema dar una cifra cuando la pregunta era ambigua y
debía pedirse una aclaración primero (Q08, Q21, Q22, Q35), y un dato
incorrecto (Q40, corte histórico).

## Preguntas objetivo

Ejemplos del dueño del tipo de pregunta que la fase 2 debe responder:

- «¿Cuántos pasajeros transportó Aeroméxico en 2025?»
- «¿Cómo fueron los ingresos?» / «¿Cómo fue el costo operativo?»
- «¿Cuál fue el cambio de participación de Volaris contra Aeroméxico de 2025 a
  2026?» y «¿Qué rutas aumentaron más?»
- «¿Por qué aumentó el CASK de Aeroméxico este trimestre respecto al
  anterior?», cruzando las cifras con lo que dice el reporte trimestral y con
  noticias del periodo (por ejemplo, el precio del combustible).

Hoy el chat no puede responder bien ninguna de las tres últimas. El dashboard
no tiene ingresos ni costos **totales**, solo métricas por ASK-km. Los datos
por ruta existen en la pestaña de Vuelos, pero el chat no los consulta. Y el
contrato actual rechaza cualquier explicación causal.

## Arquitectura propuesta

Tres fuentes de conocimiento, cada una con sus herramientas. Todas son de
solo lectura, tienen versión y solo contienen material publicado o aprobado:

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
- años completos: suma de trimestres para flujos; las razones como RASK o
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
se reemplaza por «solo causas atribuidas a una fuente citada». Para eso hace
falta un fixture nuevo; el holdout histórico no se reescribe.

## Paquetes de trabajo

Cada paquete va en su propio PR, con pruebas y documentación.

| # | Paquete | Criterio de salida |
|---|---|---|
| F2.1 | **Estilo de respuesta** según las notas del dueño: dato primero; introducción de una línea o ninguna; el idioma de la pregunta; sin advertencias no pedidas; aclarar antes de dar cifras si hay ambigüedad material; fuente al final sin interrumpir la explicación. | Contrato de instrucciones actualizado y pruebas offline; mejora medida en la ronda de F2.9. |
| F2.2 | **Evaluación de negocio:** unas 25 preguntas en lenguaje común, de varios pasos y de «por qué». El agente redacta borradores y el dueño los ajusta o reescribe. Rúbrica por caso. El holdout de 40 queda como regresión de seguridad. | Fixture nuevo con versiones fijadas y rúbrica aprobada por el dueño. |
| F2.3 | **Glosario de negocio y métricas totales:** ingresos, costos, combustible, utilidad operativa y años completos, con procedencia y reglas de agregación. | Catálogo ampliado, conciliado con los reportes; pruebas de agregación. |
| F2.4 | **Rutas y comparaciones:** constructor de consultas sobre datos publicados de rutas; comparación de varias aerolíneas; las cifras estimadas se rotulan como estimación. | Herramientas validadas; «top N rutas» reproducible; ninguna estimación presentada como dato observado. |
| F2.5 | **Índice de reportes** con búsqueda citada. | Pasajes con empresa, periodo y página; pruebas de citas. |
| F2.6 | **Índice semanal de noticias** con rutina programada y aprobación del dueño. | Fichas sin texto completo de terceros; flujo de aprobación; herramienta de búsqueda. |
| F2.7 | **Explicaciones atribuidas:** nueva regla causal y casos de evaluación. | Casos de «por qué» con las tres capas citadas. |
| F2.8 | **Herramientas de presentación** (gráficas, comparaciones, tablas). | Componentes en `web/`, validación en el servidor, casos de evaluación. |
| F2.9 | **Ronda de evaluación con cada modelo candidato** y nueva propuesta de modelo y tope al dueño. | Reporte con calidad, latencia, tokens y costo por pregunta; elección explícita del dueño. |

**Orden recomendado:** F2.1 y F2.2 primero, porque son baratos y fijan cómo
se mide. Después F2.3 y F2.4 (datos) y F2.5 y F2.7 (reportes y explicaciones).
F2.6 y F2.8 pueden ir en paralelo. F2.9 cierra la fase, aunque pueden correrse
rondas intermedias baratas con el modelo más económico.

## Límites y riesgos

- Las preguntas de varios pasos necesitan más llamadas por turno (hoy
  `CHAT_MAX_TOOL_CALLS=8`), más tiempo y quizá un modelo más capaz. Cada cambio
  de límites se mide en F2.9 y se recalcula cuántas preguntas caben en el tope
  diario.
- Solo datos publicados o aprobados: nada de bronze, silver, warehouse
  privado, `flight_evidence_v1` ni contenido crudo de proveedores con licencia.
- Las estimaciones (por ejemplo, pasajeros por ruta y aerolínea) siempre se
  rotulan como estimación, según
  [`docs/estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md).
- Nada de búsqueda web abierta en vivo: el contexto externo entra por el índice
  de noticias aprobado.
- Las evaluaciones en vivo consumen la API pagada. Se aplican el procedimiento
  y las reglas de [evaluaciones y presupuesto](evaluaciones-presupuesto.md)
  más la autorización de este documento.

## Evaluación y presupuesto

### Consumo medido (validación real, 4 oct 2026)

| Modelo | Tarifa entrada / salida (USD por millón) | Entrada media | Costo medio por pregunta |
|---|---|---:|---:|
| `gpt-6-luna` | 0.10 / 0.50 | ~40,000 tokens | US$0.0043 |
| `gpt-6.1-sol` | 2 / 10 | ~38,000 tokens | ~US$0.077 (solo intentos completos) |
| `gpt-6-astra` | 10 / 50 | sin medición | ~US$0.43 (proyección con la entrada de Luna) |

Fuente: [validación real](../etapas/airline-tracker-validacion-real-20261004.md).
Las tarifas deben volver a comprobarse el día de la prueba.

### Estimación de referencia para la fase 2

No es una cotización. Supone unas 65 preguntas por ronda (40 del holdout y
25 de negocio) y una entrada de 2 a 3 veces la actual por las nuevas
herramientas y los pasajes de documentos.

| Concepto | Supuesto | Costo aproximado |
|---|---|---:|
| Rondas de desarrollo | 5 rondas completas con Luna | US$3–5 |
| Ronda final, Luna | 65 preguntas | ~US$1 |
| Ronda final, Sol | 65 preguntas | US$10–15 |
| Ronda final, Astra | Solo unas 20 preguntas difíciles | US$17–26 |
| **Subtotal** | | **US$31–47** |
| Margen para reintentos y desconocidos (25%) | | US$8–12 |
| **Total de referencia** | | **≈ US$40–60** |

Con unos US$7.28 de saldo disponible, el dueño tendría que cargar del orden de
**US$35–55**, más lo que consuma el chat en producción (como máximo US$1 al
día con el tope vigente). Astra en todas las preguntas costaría US$56–84 por
ronda; por eso solo se propone en un subconjunto.

### Lo que debe hacer el agente antes de gastar

1. Ejecutar `uv run python -m src.conversational_analytics.evaluation --dry-run`
   con los modelos y las tarifas del día, y presentar al dueño las llamadas,
   los tokens estimados, el costo por ronda y **el saldo que necesita cargar**.
2. Esperar a que el dueño cargue el saldo. La autorización cubre las rondas
   presentadas en esa estimación, no un gasto abierto.
3. Fijar en un fixture nuevo `data_version` y `semantic_version`, el prompt,
   los límites y las herramientas, iguales para todos los modelos; calificar a
   ciegas, sin nombres de modelo.
4. Reportar calidad (al menos 95% de casos soportados correctos y cero fallos
   críticos), latencia, tokens y costo por pregunta, y proponer modelo y tope.
   El dueño elige.
