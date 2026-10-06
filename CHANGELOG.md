# Changelog

Cambios notables del proyecto, para humanos. Formato inspirado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); no se usa
versión semántica, las entradas van por fecha.

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
  `docs/etapas/mantenimiento-pruebas-ci-20261006.md`.

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
- Detalle en `docs/etapas/chat-mvp-preparacion-20261006.md`.

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
  `docs/etapas/airline-tracker-revision-ui-20261004.md`.

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
  `docs/etapas/airline-tracker-evaluation-recovery-20261004.md`.

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
  `docs/etapas/airline-tracker-auditoria-chat-20261004.md`.

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
  `docs/etapas/airline-tracker-remediacion-20261004.md`.

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
  [`docs/etapas/flujo-agentes-punta-a-punta-20260927.md`](docs/etapas/flujo-agentes-punta-a-punta-20260927.md).

### Fixed

- Los gráficos de Economía unitaria ahora se ajustan al abrir la pestaña. El
  cambio usa la instancia local de Plotly, corrige gráficos estrechos o
  desbordados y valida que cada SVG ocupe el ancho de su contenedor. Detalle en
  [`docs/etapas/ajuste-graficos-economia-20260927.md`](docs/etapas/ajuste-graficos-economia-20260927.md).

- El diagnóstico de etapa 12 registra un hash del contenido lógico del
  warehouse en vez de los bytes del archivo, así que un warehouse restaurado
  del respaldo privado ya no falla la prueba de reproducibilidad.

- `just rebuild` ya no borra los cuatro derivados privados de AeroDataBox: los
  lleva al checkout limpio como insumos, así que el warehouse reconstruido
  conserva la red nacional estimada. `validate_stage9` acepta el registro de
  41 pasos. Las pruebas de la guarda de rutas ya no dependen del Bronze local.
  Detalle en
  [`docs/etapas/rebuild-datos-privados-20260927.md`](docs/etapas/rebuild-datos-privados-20260927.md).

- Vuelos: el total de vuelos de la red cuenta solo vuelos observados; los
  programados (slots del AICM, anuncio fechado de OMA) y los inferidos de
  mercado AFAC van en líneas aparte. Las rutas con presencia documentada sin
  volumen atribuible se declaran como N/D en vez de desaparecer en silencio.
  Además, la región seleccionada se limpia al pasar a un trimestre sin rutas
  de esa región, y el mapa recalcula su recorte al redimensionar la ventana.
  Detalle en
  [`docs/etapas/vuelos-total-red-codex-20260927.md`](docs/etapas/vuelos-total-red-codex-20260927.md).

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
  histórico en `docs/archivo/migracion-2026-09/`).

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

Ver `docs/etapas/` (trabajo vigente) y `docs/archivo/etapas/` (reportes de
etapa 0–18 y de la app retirada) para el detalle completo de cada entrega
desde el inicio del proyecto (agosto de 2026).
