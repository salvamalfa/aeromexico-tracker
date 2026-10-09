# Changelog

Cambios notables del proyecto, para humanos. Formato inspirado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); no se usa
versión semántica, las entradas van por fecha.

## 2026-10-08 · Limpieza de documentación: estado actual e historia

- Regla nueva en `AGENTS.md` («Ciclo de vida de la documentación»): lo vigente
  describe el presente; al cerrar un esfuerzo, lo que sigue vigente pasa a la
  documentación permanente, el resto se resume en `docs/archivo/README.md` y
  los originales se borran del árbol (quedan en Git, con enlace permanente).
  Las decisiones no se borran, se reemplazan.
- Se retiraron del árbol 215 documentos y recursos históricos: plan
  original, reportes de etapa 0–18, migración a Vite, construcción del MVP del
  chat, investigación de Vuelos de septiembre, mantenimiento cerrado y material
  de la app retirada. `docs/archivo/README.md` los resume y enlaza en el commit
  `7478082`; los enlaces vigentes apuntan ahí.
- El glosario de KPIs vuelve a `docs/glosario-kpis.md`: es un insumo vigente de
  `dim_metric` y del diccionario de datos.
- Se eliminó `docs/solicitud-pnt.md` (la solicitud a la PNT ya no se hará).
- La guía de entrada de Vuelos describe la app actual.
- `README.md`, `ROADMAP.md`, `REPO_MAP.md` y la documentación del chat
  describen el estado al 8 de octubre: MVP activo, topes de US$5, 16 consultas
  y fase 2 como siguiente paso.
- Decisión 009: el backend del chat se aloja en Railway.

## 2026-10-08 · Chat: tablas en las respuestas y diseño de presentación

- El chat muestra como tabla real las tablas que escribe el modelo; antes
  aparecían como renglones con barras `|`.
- Fase 2: F2.8 pasa a «presentación por referencia». Las herramientas
  devuelven la tabla validada y el modelo solo escribe su marca. Se agregan las
  decisiones del dueño del 8 de octubre: se conserva el aviso de avance de una
  oración, decimales con punto y fuentes sin duplicar.
- Detalle en `docs/etapas/chat-tablas-presentacion-20261008.md`.

## 2026-10-09 · Revisión privada del chat por turno

- `review.html` compara cada candidato como conversación ordenada por turno y muestra Markdown seguro; el texto original completo permanece disponible. Ver [bitácora](docs/etapas/chat-revision-conversaciones-20261009.md).
- La referencia distingue criterios `multi_turn` de valores numéricos y evita afirmar que faltan datos publicados. Detalle y validación en [la bitácora](docs/etapas/chat-revision-conversaciones-20261009.md).

## 2026-10-08 · Chat: límite de herramientas, reserva sin vencimiento y Railway

- Diagnóstico de la segunda pregunta real del dueño: falló por
  `tool_call_limit` (más de 8 consultas), y su reserva de US$1.50 quedó
  apartada sin vencimiento. Eso provocó el «daily cost budget exhausted» del
  reintento.
- Railway, a pedido del dueño: tope diario de US$3 a US$5 (usuario y global),
  `CHAT_MAX_TOOL_CALLS` de 8 a 16, y watch paths para que solo los cambios del
  backend o de los datos publicados redespliegan el chat (`railway.toml`).
- El worker cancela el turno del proveedor detenido por un límite local y
  registra su uso real; si sigue desconocido, conserva la reserva.
- Los mensajes INFO de Uvicorn van a stdout y Railway ya no los marca como
  error.
- `AGENTS.md`: revisión cruzada entre agentes para PRs de código sin revisión
  de Codex.
- Detalle en `docs/etapas/chat-limite-herramientas-presupuesto-20261008.md`.

## 2026-10-08 · Correcciones a la recuperación de turnos del chat

- Un stream cortado ya no guarda texto parcial como respuesta completa.
- La recuperación tras una conexión caída consulta el uso faltante y libera la
  reserva de gasto; antes, dos turnos así podían agotar el tope diario de Sol.
- El worker deja de correr el límite de tiempo antes de consultar el uso de una
  respuesta recuperada.
- Ya no se guarda `"None"` como identificador del turno del proveedor.
- Detalle en `docs/etapas/chat-recuperacion-correcciones-20261008.md`.

## 2026-10-07 · Fase 2 del chat: modelos, esfuerzo y nuevo conjunto de evaluación

- `docs/chat/fase-2-agente-analitico.md` reescrito como guía de implementación:
  - cuatro candidatos: Luna con esfuerzo medio y máximo, Sol con bajo y medio;
    Astra queda fuera;
  - nuevo paquete F2.0 para fijar y registrar el esfuerzo de razonamiento, que
    nunca se configuró;
  - F2.1 con formato de respuesta, reglas de criterio y las respuestas
    preferidas del dueño como referencia, sin contaminar el holdout;
  - F2.2 con 30 preguntas de negocio en lenguaje común;
  - F2.9 con etapas, regla de decisión y costo estimado de US$40–70, cargado
    por etapas;
  - un borrador del prompt de sistema basado en las guías oficiales de OpenAI y
    Anthropic, y una tabla de los puntos donde el agente debe pedir la decisión
    del dueño.
- `ROADMAP.md` actualizado.

## 2026-10-07 · Propuesta de la fase 2 del chat y diagramas de arquitectura

- Nuevo `docs/chat/fase-2-agente-analitico.md`: después del MVP, el chat pasa
  a ser un agente para preguntas de negocio.
  - Incluye glosario, métricas totales, rutas, índice de reportes, índice
    semanal de noticias con aprobación, explicaciones atribuidas a fuentes y
    herramientas de presentación.
  - Paquetes F2.1–F2.9 con criterios de salida.
  - Estimación de referencia del costo de las nuevas evaluaciones, que el
    dueño autorizó sujeto a una estimación previa.
- El traspaso de activación registra las calificaciones entregadas, que el MVP
  se activa sin cambios y el saldo actual de la API.
- Los diagramas «Anatomía del chat» y «Anatomía de las herramientas» viven en
  `docs/arquitectura/`, como HTML interactivo y como GIF en el `README.md`.
- Entradas nuevas en `ROADMAP.md`.

## 2026-10-06 · Traspaso para activar el MVP del chat

- Nuevo `docs/chat/traspaso-activacion-mvp-20261006.md`: roles (el dueño solo
  califica y elige modelo y tope; el agente administra Railway y la API key),
  decisiones vigentes (tope de US$1, crédito prepagado opcional, S14 fuera de la
  base del chat) y pasos pendientes de la activación.
- Dependabot se limita a versiones menores y de parche, y excluye el runtime
  del chat (`openai`, `fastapi`, `uvicorn`); sus primeros PRs (#93–#95) se
  cerraron sin integrar.
- Estado actualizado en `README.md` y `docs/chat/README.md`.
- Correcciones de una revisión adversarial independiente: el modo simulado
  registra su uso a US$0; `import-usage` solo exige `--allow-admission-block`
  para filas `unknown` nuevas; la guía aclara que Sol requiere un tope mayor que
  su reserva, el commit previo de `web/.env.production` antes de `src.publish`
  y la prueba de la clave de login detrás de Railway.

## 2026-10-06 · Pruebas más rápidas y CI más estricta

- La suite pública baja de ~7 min a ~2 min 15 s: la validación de esquemas
  se reutiliza para archivos idénticos (mismo hash) dentro de un proceso.
- La CI revisa errores reales de Ruff (`--select F`) en `src/` y `scripts/`,
  corre con permisos de solo lectura y Dependabot propone actualizaciones
  mensuales agrupadas.
- `playwright` y `plotly` (Python) dejan de instalarse en la base. Detalle en
  [`docs/archivo/mantenimiento-2026-09/mantenimiento-pruebas-ci-20261006.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/mantenimiento-pruebas-ci-20261006.md).

## 2026-10-06 · Preparación del MVP del chat

- El lanzador de Railway acepta OpenAI cuando se configura explícitamente
  (modelo, precios, contraseña y topes); por defecto sigue en `mock` con la
  admisión cerrada.
- El gasto se controla con un tope diario de US$1 configurable en Railway; el
  cupo de tokens queda como freno de seguridad. La reserva se sigue cobrando a
  la tarifa de salida (Luna cabe; Sol y Astra requieren subir el tope).
- La versión de datos del chat ya no cambia con republicaciones de interfaz.
- El importador de consumo exige una bandera explícita para filas desconocidas,
  que pausan todo el chat; S14 queda fuera de la base del chat.
- `web/.env.production` versiona la URL de la API con el panel apagado; la
  activación del panel queda documentada en `docs/chat/railway.md`.
- Detalle en [`docs/archivo/chat-mvp/chat-mvp-preparacion-20261006.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/chat-mvp-preparacion-20261006.md).

## 2026-10-04 · Revisión de respuestas y acceso al MVP

- Interfaz separada para revisar respuestas ciegas cargadas desde un archivo
  privado, guardar el avance local y exportar/importar calificaciones. La
  publicación contiene una interfaz vacía y ninguna respuesta de evaluación.
- Página para comprobar y cerrar la sesión del piloto con HTTPS, sin enviar
  preguntas. La contraseña inicial se entrega por un archivo privado.
- El login acepta cuerpos legítimos reenviados por Railway sin exigir
  `Content-Length`; el límite se aplica a los bytes recibidos y al tiempo de
  lectura antes de analizar el JSON.
- El dueño confirmó las definiciones y el alcance del MVP. El catálogo registra
  esa aprobación; no modifica las aprobaciones del Analysis Agent.
- El contrato del proveedor prioriza el alcance explícito de la pregunta sobre
  el contexto del dashboard y exige comprobar la identidad y disponibilidad de
  las filas obtenidas. La comparación anterior conserva sus resultados: estos
  cambios requieren validación de calidad antes de activar el chat.
- Guía en `docs/chat/revision-respuestas.md` y corte de entrega en
  [`docs/archivo/chat-mvp/airline-tracker-revision-ui-20261004.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/airline-tracker-revision-ui-20261004.md).

## 2026-10-04 · Recuperación segura de turnos del chat

- El cierre bloquea claims de turnos nuevos. En Railway, Uvicorn da hasta 5 s a
  conexiones SSE y luego el worker drena hasta 90 s, dentro del límite de 100 s;
  en otros despliegues locales el timeout del worker es `max_turn_seconds + 5`.
  La autorización de entrada al SDK se coordina con el cierre y conserva
  compatibilidad con proveedores legados.
- En una sesión reutilizada, si la cancelación llega durante la escritura
  síncrona del mensaje al SDK, se intenta cancelar la sesión al terminar esa
  escritura; el mensaje no se vuelve a enviar. Una prueba integrada verifica que
  el cierre sigue acotado aun si esa segunda cancelación se bloquea.
- Los errores terminales usan códigos permitidos; el evaluador de comparación
  reconcilia uso tras cancelar durante hasta 30 segundos y seis lecturas. Sin
  confirmación, conserva el uso como desconocido y la reserva, sin reproducir
  entradas ni convertir el valor a cero. Esto no aprueba calidad ni habilita
  el proveedor.
- Contexto de recuperación en
  [`docs/archivo/chat-mvp/airline-tracker-evaluation-recovery-20261004.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/airline-tracker-evaluation-recovery-20261004.md).

## 2026-10-04 · Arranque del backend en Railway

- Build Docker explícito con dependencias del grupo `chat-runtime`, snapshot
  público y arranque en el puerto de Railway; conserva el CLI local en loopback.
- Piloto con contraseña, una instancia, volumen persistente, permisos privados,
  proveedor simulado y admisión apagada hasta completar los gates.
- Historial del backend con retención de 30 días acordada por el dueño.

## 2026-10-04 · Correcciones de la auditoría del chat (PRs #81–#83)

- El límite de intentos de login ya no agrupa a todos los clientes bajo la IP
  del edge de Railway: `CHAT_TRUSTED_PROXY` acepta redes privadas o compartidas
  y el launcher confía en `100.64.0.0/10`. Un tercero ya no puede bloquear el
  login del dueño con cinco contraseñas erróneas.
- `get_time_series` conserva los periodos más recientes cuando el intervalo
  excede el límite, informa cuántos omitió y lo indica en el título de la
  gráfica; antes perdía los últimos meses sin aviso o fallaba con más de 32.
- Las referencias se etiquetan por su host; ya no se rotula como AFAC un
  documento de SEC o del repositorio.
- Se documenta la capacidad efectiva de la política de tokens (unas dos
  preguntas al día). Detalle en
  [`docs/archivo/chat-mvp/airline-tracker-auditoria-chat-20261004.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/airline-tracker-auditoria-chat-20261004.md).

## 2026-10-04

### Changed

- **Cuotas del piloto y hosting intermitente.** El chat aplica 200.000 tokens
  diarios por usuario y globales, reservando al menos 150.000 por turno OpenAI.
  Un importador privado incorpora consumo de evaluaciones sin duplicarlo y
  bloquea admisión ante registros desconocidos. Se evalúan Railway Free/Hobby
  para un único usuario con suspensión; el perfil `chat-runtime` evita instalar
  las dependencias del pipeline en el backend. No se contrató ni publicó nada.

- **Chat analítico — contraseña y correcciones de auditoría.** El piloto se
  protege con una contraseña (hash scrypt, sesiones de 12 h, límite de
  intentos) en lugar de tokens. Se corrigen la exposición del modo local
  detrás de un proxy, el signo de `compare_metrics`, la reanudación de turnos
  en cola, la pérdida de historial al recrear la sesión del proveedor, el uso
  de turnos fallidos y bloqueos del servidor. El sitio publicado no cambia y el
  chat sigue apagado. Detalle en
  [`docs/archivo/chat-mvp/airline-tracker-remediacion-20261004.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/airline-tracker-remediacion-20261004.md).

### Fixed

- **Revisión del PR e integración real.** El modo local rechaza todas las
  cabeceras `X-Forwarded-*` y la fábrica de API aplica la exigencia de contraseña
  para OpenAI. El evaluador conserva checkpoints privados, representa consumo
  desconocido como tal, mantiene sesiones para reconciliación y acepta formatos
  numéricos regionales equivalentes. El adaptador consulta el uso del turno si
  falta en el evento final; el panel libera observers y listeners al desmontar.
  Una sonda real confirmó acceso y respuesta correcta. El hosting Business
  actual requiere un VPS separado para la API Python; el piloto sigue pendiente.
  El timeout se registra antes de despertar al proveedor; el worker espera a
  que termine su cancelación antes del siguiente turno y contabiliza uso
  conocido de respuestas tardías sin cambiar el estado terminal.
  La cancelación explícita conserva la sesión creada tarde y espera su cierre;
  borrar una conversación durante la creación mantiene la limpieza remota
  durable. Las reservas de uso desconocido sobreviven cambios de día UTC,
  borrado y retención, con contabilización única cuando se confirma el uso.
  La comparación real conserva errores y contadores entre fases: Luna tiene
  7/9 consultas soportadas correctas y Sol 8/8, con cobertura parcial. Un turno
  fallido sin uso confirmado pausó la continuación antes de admitir Astra.
  El reporte separa mediciones, revisión automática y aprobaciones pendientes.
  La revisión del PR también conserva consumo recuperado de turnos fallidos o
  cancelados, protege reintentos de envíos HTTP inciertos con la misma clave
  y corrige la precedencia de entidades y el denominador AFAC en modo simulado.

## 2026-10-03

### Added

- **Chat analítico — base offline lista.** Se entregan auditoría offline
  del snapshot público, un holdout de 40 preguntas bilingües separado de los
  ejemplos de prompt, gate de dry-run y documentación de operación, presupuesto
  y evaluación. La integración live, elección de modelo y piloto alojado siguen
  pendientes; no se hicieron llamadas pagadas.

## 2026-09-30

### Added

- **Dashboard v2: Aerolíneas MX Tracker.** El dashboard pasa de Grupo Aeroméxico a
  la industria mexicana: Aeroméxico, Volaris, Viva e Industria (la suma de las
  tres).
  - **Selector de aerolínea** por tarjeta, con la selección guardada en la URL.
  - **Participación AFAC:** una tarjeta nueva de participación de pasajeros.
  - **Economía unitaria:** "vs. industria" y comparación de varias aerolíneas.
  - **Mapa de rutas por aerolínea:** nacional estimado, México–EE. UU. con T-100 y
    resto internacional estimado.
  - **Capacidad por ruta:** asientos y ocupación de Volaris y Viva por promedio de
    flota.
  - **Documentación por fase:** `docs/etapas/dashboard-v2-fase{0,2,3,4}-*.md`.

### Changed

- **Estimación internacional publicada:** la estimación internacional de pasajeros
  por ruta queda publicada para las tres aerolíneas, siempre como "estimado", por
  decisión del dueño.
- **Vista previa `/v2/` retirada:** la v2 pasa a la raíz del sitio. El mecanismo de
  vista previa de `pages.yml` se conserva.
- **Tesis por aerolínea (fase 5):** quedan para un cambio posterior. Mientras tanto,
  solo Aeroméxico muestra una tesis aprobada.

## 2026-09-27

### Changed

- Los agentes del proyecto tienen autorización permanente para completar
  cambios rutinarios solicitados: implementación, PR, merge, publicación en
  Pages y verificación final. `AGENTS.md` define las puertas y las acciones de
  mayor riesgo que siguen requiriendo autorización específica. Detalle en
  [`docs/archivo/mantenimiento-2026-09/flujo-agentes-punta-a-punta-20260927.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/flujo-agentes-punta-a-punta-20260927.md).

### Fixed

- Los gráficos de Economía unitaria ahora se ajustan al abrir la pestaña. El
  cambio usa la instancia local de Plotly, corrige gráficos estrechos o
  desbordados y valida que cada SVG ocupe el ancho de su contenedor. Detalle en
  [`docs/archivo/mantenimiento-2026-09/ajuste-graficos-economia-20260927.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/ajuste-graficos-economia-20260927.md).

- El diagnóstico de etapa 12 registra un hash del contenido lógico del
  warehouse en vez de los bytes del archivo, así que un warehouse restaurado
  del respaldo privado ya no falla la prueba de reproducibilidad.

- `just rebuild` ya no borra los cuatro derivados privados de AeroDataBox: los
  lleva al checkout limpio como insumos, así que el warehouse reconstruido
  conserva la red nacional estimada. `validate_stage9` acepta el registro de
  41 pasos. Las pruebas de la guarda de rutas ya no dependen del Bronze local.
  Detalle en
  [`docs/archivo/mantenimiento-2026-09/rebuild-datos-privados-20260927.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/mantenimiento-2026-09/rebuild-datos-privados-20260927.md).

- Vuelos: el total de vuelos de la red cuenta solo vuelos observados; los
  programados (slots del AICM, anuncio fechado de OMA) y los inferidos de
  mercado AFAC van en líneas aparte. Las rutas con presencia documentada sin
  volumen atribuible se declaran como N/D en vez de desaparecer en silencio.
  Además, la región seleccionada se limpia al pasar a un trimestre sin rutas
  de esa región, y el mapa recalcula su recorte al redimensionar la ventana.
  Detalle en
  [`docs/archivo/vuelos-2026-09/vuelos-total-red-codex-20260927.md`](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/vuelos-2026-09/vuelos-total-red-codex-20260927.md).

- Rutas internacionales: las bandas de ocupación fuera de [0, 100%] se omiten igual que en las nacionales.

- Cinco hallazgos abiertos de Codex (PRs #10, #19, #20): capacidad "Boeing
  737" genérica corregida a su punto medio real (175.1, no 175.7); rango de
  sensibilidad de ocupación acotado a [0, 100%] en vez de publicar valores
  como 103.41%; suma de mínimos/máximos de pasajeros a través de celdas con
  distintos escenarios de sensibilidad del IPF ya no infla el rango por
  ruta/red — se retiene solo cuando ningún componente requirió reparación
  temporal; la mezcla trimestral de pasajeros/ASM/RPM exige los tres meses
  no nulos y finitos en vez de sumar con `NaN` silencioso; y
  `build_warehouse` falla en vez de omitir en silencio el Gold de extensión
  de rutas cuando su bronce fuente está presente pero el generador no corrió.

- Tres hallazgos de Codex sobre el PR anterior: el cliente web ya no
  fabricaba una banda de sensibilidad cuando `passengers_low/high` o
  `load_factor_low/high` llegaban como `null` (sustituía el punto o cero);
  la guarda de bronce de `fact_aifa_shared_route_presence` incluía un
  documento que ese generador no lee. Detalle y validación en
  [`docs/etapas/correcciones-codex-estimaciones-20260927.md`](docs/etapas/correcciones-codex-estimaciones-20260927.md).

## 2026-09-26

### Changed

- Remediación de la auditoría de arquitectura (R1–R5): endurecimiento del
  gate de publicación (`src/publish`) contra registros duplicados del mismo
  periodo; exportación de análisis reescrita para aislar cada periodo con
  intercambio atómico ([PR #59](https://github.com/salvamalfa/aeromexico-tracker/pull/59));
  trazabilidad y documentación corregidas ([PR #60](https://github.com/salvamalfa/aeromexico-tracker/pull/60));
  dependencias de `web/` actualizadas para reducir avisos de `npm audit`
  ([PR #61](https://github.com/salvamalfa/aeromexico-tracker/pull/61)); limpieza
  de archivos y código muerto de la migración
  ([PR #62](https://github.com/salvamalfa/aeromexico-tracker/pull/62)).
- Republicación de `site/` para 2T26 con un `code_commit` resoluble en el
  manifiesto de publicación (expediente y aprobación sin cambios, versión de
  análisis `186ba823`) ([PR #64](https://github.com/salvamalfa/aeromexico-tracker/pull/64)).
- Reglas de PR para agentes documentadas en `AGENTS.md`: autorización
  permanente para suscribirse a la actividad de sus PRs y fusionarlos con
  checks verdes e hilos atendidos, incluida la política de auto-merge
  ([PR #66](https://github.com/salvamalfa/aeromexico-tracker/pull/66),
  [PR #67](https://github.com/salvamalfa/aeromexico-tracker/pull/67)).

### Removed

- Migración a Vite + TypeScript completada (P0–P8): `web/` es ahora la única
  implementación del dashboard, publicada en GitHub Pages
  (<https://salvamalfa.github.io/aeromexico-tracker/>); la app Streamlit y el
  consumidor HTML de una sola página se retiraron por completo (detalle
  histórico en [`docs/archivo/migracion-2026-09/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/migracion-2026-09)).

## 2026-09-19 a 2026-09-25

### Added

- Estimador de pasajeros por ruta y aerolínea nacional (IPF) con evidencia de
  cobertura de semilla y publicación como `passengers_estimated`
  (`docs/estimacion-pasajeros-ruta-aerolinea.md`).
- Integración de AeroDataBox para vuelos internacionales: semilla de
  frecuencias, crosswalks de aeropuerto/aerolínea/puerta, captura mensual y
  estimación de capacidad/ocupación del Grupo Aeroméxico.
- Corrección de portabilidad del Analysis Agent entre Windows y Linux
  (decodificación de referencias de control C1 en HTML de la SEC,
  `src/parse/sec/common.py::html_text`).

## Antes de 2026-09-19

Ver `docs/etapas/` (trabajo vigente) y [`docs/archivo/etapas/`](https://github.com/salvamalfa/aeromexico-tracker/tree/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/etapas) (reportes de
etapa 0–18 y de la app retirada) para el detalle completo de cada entrega
desde el inicio del proyecto (agosto de 2026).
