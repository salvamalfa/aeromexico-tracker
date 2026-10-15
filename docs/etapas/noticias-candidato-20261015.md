# Noticias y estrategia: candidato independiente del 15 de octubre de 2026

Base: `40a63d1905afde97ae8e3f8671c8217aafacc4aa` de master. Rama:
`codex/news-strategy-20261015`. Solo PR draft y vistas previas; no integrar,
publicar, activar evidencia ni habilitar cron sin decisión independiente.

## Comportamiento

Se añade un archivo mensual con tarjetas, fuentes con SHA-256, resúmenes
originales de hasta 320 caracteres y filtros por mes de publicación, aerolínea,
tema y palabras. Conserva publicación, intervalo del hecho y primera captura
por separado. El próximo evento anunciado por Aeroméxico se identifica como
programado en el resumen. Las fichas históricas sin primera captura explícita
conservan N/D; no se sustituye por la fecha de aprobación.

El candidato local contiene **14 historias**, de **6 meses de publicación**:
las tres noticias del índice aprobado (dos Aeroméxico, una Volaris) y once
candidatas nuevas (cuatro Aeroméxico, cuatro Viva —incluida una independiente—,
tres Volaris). Junio tiene la noticia de programación de AeroRoutes; no se
confunde con los meses agosto/septiembre del hecho. Septiembre es el mes
completo predeterminado. Octubre es parcial al corte del 15 de octubre.

Es una selección manual y no exhaustiva: **cuatro historias de septiembre**
representan las tres aerolíneas. Ausencia de fichas significa falta de cobertura
en este archivo, no ausencia de hechos. El conteo no mide importancia; el
sentimiento de medios no mide satisfacción del cliente.

## Fuentes, captura y revisión

Registro de descubrimiento: `config/news/sources.json`. Diez PDFs de los
emisores y una página de AeroRoutes respondieron HTTP 200; se cotejaron sus
fechas y contenido con los resúmenes. Las fichas conservan hash de los bytes
capturados, enlace, primera captura, fecha de verificación y hash de contenido
candidato. Los originales permanecen en Bronze ignorado. El repo público
recibe exclusivamente metadatos y resúmenes, sin cuerpos ni imágenes.

El archivo de Volaris requiere el filemanager público configurado en su página;
el HTML inicial no basta. Se registró la petición con categorías/año/idioma y
se siguieron sus URLs oficiales de PDF. La página RSS española de Aeroméxico
contiene un enlace relativo que devolvió 404; no se presenta como feed completo.
Dos enlaces históricos FlightGlobal devolvieron 403 durante la comprobación;
se conservan los tres registros aprobados y su evidencia previa sin eludir el
bloqueo. AeroRoutes añade una fuente independiente candidata, pendiente de la
revisión por fuente y ficha. Su nota describe programación, no vuelos observados.

Preparación reproducible, sin coste de API pagada:

```
uv run python -m scripts.news.prepare_monthly_cut --input config/chat/evidence/candidates/news/inbox/cut-20261015.json --out /tmp/news-next-version.json
# El comando anterior es dry-run: enumera llamadas y destinos.
# --capture guarda una versión nueva; rechaza sobrescribir un corte existente.
```

El índice aprobado, los recibos y sus pins externos no cambian. La exportación
normal incorpora exclusivamente fichas aprobadas; sin pin existente escribe
una vista explícitamente no habilitada. Un pin incorrecto bloquea la carga.
El candidato solo entra a la vista previa mediante una opción explícita:

```
uv run python -m src.dashboard.news --candidate config/chat/evidence/candidates/news/cut-20261015-v1.json --out web/public/data/v1/news.json
```

La variable de pin debe venir del registro de aprobación ya existente, como
explica `docs/cloud-development.md`; no se calcula una autorización nueva.
Exportar un candidato no lo habilita en el chat ni en tesis.

## RSS/GDELT y conservación mensual

El rebuild une todos los snapshots exitosos retenidos de cada feed. Deduplica
URLs sin parámetros de seguimiento, conserva la primera captura mínima y el
linaje del registro seleccionado. Prefiere la fecha de publicación del editor.
`seendate` de GDELT pasa a `first_seen_at`, con `published_at=null`; esos registros
no se asignan a un mes de publicación hasta verificarse. Las notas distintas
sobre una misma historia se agrupan por `story_id` curado conservando fuentes.
El RSS/GDELT de descubrimiento cubre las tres compañías; no se ejecutó una
captura amplia nueva ni se prometió cobertura completa del archivo histórico.

## Chat y pruebas

El botón Preguntar al chat prellena una pregunta natural en el chat existente
con aerolínea/mes/tema; el usuario aún debe enviarla. Mantiene autenticación,
credenciales, topes y herramientas actuales. La búsqueda del índice sigue
siendo determinista por palabras y máximo cinco resultados, no un archivo
completo ni un buscador semántico. El modelo existente interpreta la pregunta.
Las once candidatas siguen cerradas para chat hasta su revisión independiente.

Se verifican parser de fechas, unión histórica, primera captura, deduplicación,
filtros, inyección de HTML/URLs y rechazo de candidatos alterados o que alegan
aprobación. TypeScript, Vitest, build y comandos exactos de CI se registran en
el PR. Playwright prueba desktop/móvil y el enlace natural al chat con backend
**simulado**; no se realizó llamada pagada al modelo ni se desplegó el backend.
Las previews autocontenidas usan el mismo bundle y datos públicos; carecen de
conexión al chat real. No constituyen prueba de chat de producción.

Auditoría Gold y decisiones: `docs/gold-exposure.md`. No se modifica el snapshot
privado ni `site/`; se conservan tesis, aprobaciones y toda la historia.

## Pendientes

Skills por fuente; coordinador mensual/trimestral; revisión mensual de Noticias;
aprobación de fuentes y de cada ficha antes del chat; aprobación independiente
para integrar y publicar; prueba real del chat sobre el código aprobado y su
presupuesto existente; futura limpieza con dependencias. Nada se programa ahora.


## Límite de aprobación comprobado en la validación final

El guard `src/analysis_agent/entity_adapter.py::require_current_presentation`
conserva una huella amplia que incluye `web/src`, los contratos y el código de
exportación/publicación. Las tesis publicadas no cambian, pero una interfaz
nueva no coincide con su versión técnica aprobada. La suite con datos privados
lo detecta en dos pruebas de paridad de `tests/test_site_parity.py`; no se
modificaron recibos, firmas ni aprobaciones para hacerlas pasar. El despliegue
requiere resolver esa revisión técnica con el dueño, además de aprobar el PR.
Las previews reutilizan los payloads ya publicados y se marcan candidatas;
no equivalen a una regeneración aprobada del sitio.

## Correcciones tras revisión Codex

La revisión del head `ef2d40f` detectó dos casos P2. Se monta Noticias si ya
estaba visible al terminar la carga inicial de Lectura ejecutiva; una prueba
retiene la respuesta de `executive.json`, abre Noticias y libera la carga para
reproducir esa carrera. Además, al agrupar una historia con fuentes aprobadas
y candidatas, toda la tarjeta conserva el estado candidato. Dos órdenes de
entrada comprueban que una fuente nueva nunca herede una aprobación anterior.

Los dos hilos quedaron respondidos y resueltos. La CI del head `2ae38e5`
terminó con éxito (corrida 413); el ensamble local con Mercado pasó 196 pruebas
web y 14 de navegador. Dos intentos de revisión final sobre ese head fallaron
en el servicio con `Provided git ref ... does not exist`, aunque GitHub y CI
resuelven la referencia. Se registra el límite y se vuelve a solicitar revisión
sin tratar esos errores como aprobación. Este registro no cambia el producto,
el índice de evidencia ni los límites de publicación.

Una segunda revisión detectó dos casos adicionales de procedencia: reutilizar
la misma URL canónica con otro hash descartaba el cambio, y una redirección al
mismo host podía bajar de HTTPS. Ahora un conflicto de hash bloquea la
proyección, incluso con distinto identificador de historia y en ambos órdenes;
cada redirección debe conservar HTTPS, host permitido y ausencia de usuario o
contraseña. Las pruebas usan transporte HTTP simulado: las URL rechazadas no
reciben una segunda solicitud y no generan archivos; una redirección relativa
HTTPS válida conserva su destino y estado candidato.
El presupuesto de dry-run incluye hasta cuatro solicitudes por fuente contando
redirecciones; treinta fuentes permiten como máximo 120 solicitudes públicas.

La siguiente revisión encontró una variante con bytes idénticos pero metadatos
o estado de revisión diferentes. Solo se deduplican alias con la misma ficha
semántica y el mismo estado; cualquier discrepancia exige revisar ambos registros
y bloquea la proyección. No se descarta una corrección candidata ni se conserva
una etiqueta aprobada que oculte esa corrección. Los manifiestos originales no
se modifican; el corte real conserva sus catorce fichas sin cambio de bytes.
La comprobación precede al filtro de publicación desconocida: quitar la fecha
de una revisión tampoco permite ocultarla detrás de una ficha aprobada. Una
fuente única sin fecha sigue excluida del agrupamiento mensual, sin inventarla.

La siguiente revisión atendió otras tres variantes: la proyección conserva el
editor por fuente y cada enlace usa su propia atribución; el rebuild prioriza
registros fechados y después la ingestión más reciente, incluso si corrige la
publicación hacia atrás; la primera captura se guarda por URL canónica,
deduplicando solo los bytes del original. Un sidecar histórico solo se hereda
si documenta esa misma URL y nunca se sobrescribe. Los manifiestos candidatos
no cambian; la proyección agrega la atribución por fuente a las mismas 14 fichas.

Durante esta validación, invocar el módulo RSS con `--help` ejecutó su `run`
porque no procesaba argumentos. Se consultaron cuatro fuentes gratuitas y se
conservaron únicamente Bronze/Silver ignorados: 392 titulares de dos feeds RSS;
El Economista y GDELT fallaron, sin captura exitosa de GDELT. No cambió Gold,
el corte curado, las aprobaciones ni el expediente privado. La ayuda ahora se
procesa antes de `run` y una prueba impide llamadas al pedir `--help`.
Se conservó un expediente local ignorado con los manifiestos de esa ejecución,
sus originales y el Silver de 392 filas. Los dos manifiestos versionados se
dejaron idénticos a su base, y Silver se reconstruyó offline desde ellos: 201
titulares. No se eliminó la evidencia nueva ni se añadió a los datos publicados.
