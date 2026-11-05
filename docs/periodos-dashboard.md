# Periodos del dashboard

## Resumen

La entrega distingue el trimestre seleccionado, los financieros disponibles y
los meses efectivos de cada fuente. El diagnóstico inicial usó `master`
**3a299fbc**. El código revisado `089f48a6` y las cuatro lecturas exactas ya
pasaron la preparación, aprobación y publicación mediante el gate de Linux.
El sitio generado está en el [PR 188](https://github.com/salvamalfa/aeromexico-tracker/pull/188);
su integración y comprobación en Pages y Railway conservan el flujo normal.

Los financieros individuales y la proyección aprobada de Industria llegan a
**3T26** en el artefacto generado. La proyección conserva sumas y ponderaciones
por ASK; no se convierte en una observación de AFAC.
La revisión actual incorpora el resumen oficial AFAC de **septiembre de 2026**;
Mercado Q3 está completo. Las capturas anteriores con agosto documentan el diagnóstico,
no el estado actual. Datatur estaba rezagado respecto del catálogo AFAC.
En la revisión actual de rutas, **BTS y las frecuencias AeroDataBox llegan a julio**.
La captura oficial ANAC de noviembre incorpora Brasil hasta **septiembre** en
la preview por el proceso normal; no completa los meses de otras regiones.
Estos cortes siguen siendo distintos; la interfaz no inventa los meses restantes.
[Auditoría de los archivos reales](referencias/periodos-20261031/data-audit.json).

## Qué cambia para ti

- Mercado reúne cuatro KPI financieros, mapa, participación AFAC y mezcla de
  pasajeros. Los tres KPI AFAC se retiraron por instrucción posterior; los
  indicadores superiores conservan su fuente financiera.
- Sin `period` válido en la URL, abre el último trimestre con registro financiero
  completo y vista publicados. Busca en los emisores y en la serie principal;
  no fija Q3 ni espera un trimestre común de Industria. Los enlaces históricos
  válidos conservan su trimestre. El selector superior es el único de trimestres
  en todo el dashboard; el catálogo de aprobaciones determina qué lecturas
  existen para ese trimestre, sin sustituirlo por otro.
- Economía vuelve a dibujar las tres gráficas al cambiar de trimestre. Las
  historias temporales destacan la selección, incluso como ventana sin dato.
  La dispersión sólo rodea una observación existente del trimestre elegido.
  Cada gráfica informa de su entidad y su último corte si falta la selección.
  La tabla destaca la fila seleccionada cuando existe.
- Las tarjetas superiores de Mercado toman los financieros del emisor seleccionado. Ya no
  reutilizan el índice anterior cuando falta un trimestre en `flights/quarters`.
  La mezcla de pasajeros mantiene AFAC separado de los reportes corporativos
  y muestra sus meses disponibles. El mapa Q3 declara **parcial: 1 de 3 meses**.
- El mapa usa sólo el trimestre global, sin selector secundario de meses.
  Nacional e Internacional están dentro de la tarjeta. Si el periodo
  solicitado no tiene red en ese ámbito,
  se muestra vacío y con su periodo; no se sustituye por otro año o trimestre.
- Mercado usa el resumen oficial AFAC de septiembre de 2026 en la revisión
  local. La gráfica mantiene toda la historia y el mismo eje hasta el último
  mes real; cambiar el trimestre mueve sólo la franja. Las tarjetas financieras y
  el contexto de Pregunta conservan el trimestre seleccionado. El detalle AFAC
  muestra el mes del punto y su comparación contra ese mismo mes del año anterior;
  el desplegable AFAC se retiró por la instrucción posterior del dueño. Q3 está completo;
  los mapas conservan su corte parcial de julio.

## Riesgos

La falta inicial de Industria Q3 corresponde al baseline del diagnóstico. La
entrega actual reconstruye y autoriza la proyección desde los tres emisores:
suma pasajeros, ASK y RPK; pondera indicadores unitarios y ocupación reportada
por ASK. No se presenta como observado ni como participación AFAC. Las pruebas
y capturas de preview de este documento conservan su contexto histórico.
[Captura actual de Industria](referencias/periodos-20261031/desktop-industry-review-q3.png).

La auditoría y la decisión del 4 de noviembre cubren las cuatro lecturas y los
doce JSON exactos del nuevo alcance; las autorizaciones anteriores por emisor
no se reutilizaron para aprobar este agregado. La red mantiene cortes diferentes:
BTS y frecuencias a julio, ANAC Brasil a septiembre. Los mapas no acreditan
cobertura mundial completa ni actualizan modelos. La fase 2 con AFAC queda fuera.

## Apéndice técnico

### Causas y reparaciones

| Caso | Causa en 3a299fbc | Reparación y evidencia |
|---|---|---|
| Entrada limpia abre Q2 | `financial_projection.py` conservaba el corte común anterior; el consumidor confiaba en ese `default_period` | `financial_periods.py` normaliza los nuevos exports y el consumidor calcula la misma unión verificable. [Entrada limpia en ambos tamaños](referencias/periodos-20261031/browser-general.json) |
| Economía superior conserva estado anterior | `bootstrap.render` sólo redibujaba Unit Economics cuando reiniciaba su rango | Render en cada cambio; marca de trimestre en unitario y volumen; dispersión sin selección falsa. [Valores y geometría por entidad](referencias/periodos-20261031/browser-economy.json) |
| Industria sin Q3 | Las proyecciones por emisor preservaron los bloques de las otras entidades y el agregado | Pendiente visible y candidato separado reproducido con la función existente. [Insumos, resultado y requisitos](referencias/periodos-20261031/data-audit.json) |
| Vuelos reutiliza Q2 al pedir Q3 | `syncPeriodIndex` no cambiaba el índice si no encontraba el periodo; las tarjetas y la mezcla reutilizaban ese registro | Ventana de calendario seleccionada con valores nulos si falta el registro; cada bloque usa su propia fuente y no el último índice válido. [32 casos reales de navegador](referencias/periodos-20261031/browser-flights.json) |
| Mapa sustituye un periodo por otro | `currentMapPeriod` elegía el último periodo listado cuando faltaba el general | Sin sustitución; trimestre global único y descarte de solicitudes obsoletas. [Mapa histórico y regreso](referencias/periodos-20261031/browser-general.json) |
| Q3 de mapa aparenta trimestre | La etiqueta trimestral sola no expresaba sus meses efectivos | Cobertura por calendario y fuente: julio de tres meses; rutas, movimientos, estimaciones y programación siguen separados |
| Corte de Mercado confuso | La actualización de la integración introdujo un punto nulo para no unir coberturas distintas | La revisión posterior retira el punto nulo artificial, la marca y el aviso. Conserva todas las observaciones y porcentajes del payload AFAC; el corte sigue en agosto |

La guía del contrato ejecutivo documenta el significado de `default_period`;
el esquema y sus tipos conservan los bytes compatibles con los sitios firmados.
El exportador valida el **input original antes de normalizar**,
vuelve a validar el resultado y conserva privacidad. No cambia controles ni
aprueba una versión nueva de datos. Los contratos de Vuelos ya incluyen meses
esperados y observados; los consumidores ahora los usan junto con el calendario
completo del trimestre. No se modificaron cifras, fuentes ni archivos de `site/`.

### Pruebas locales

Datos usados: los JSON construidos y versionados de `site/data/v1`, con hashes
del original en la auditoría. El exportador real reconstruye `executive.json`
en `tmp/period-coherence-build/data/v1`, validado contra esquema y privacidad.
Esta prueba **no** reconstruye el warehouse ni renueva las capturas originales.
La preview usa los datos públicos y el manifiesto original sólo como catálogo
de lecturas; no se presenta como una nueva publicación firmada.

- TypeScript y compilación Vite: aprobados.
- Suite web: **318 pruebas en 46 archivos**, aprobadas con Node 22.
- Python focalizado: **15 aprobadas**, tres pruebas de warehouse omitidas porque
  ese archivo no está restaurado en este checkout. Incluye exportación real,
  candidato separado, contrato, privacidad y presupuestos del repositorio.
- Regresión del chat y contratos firmados: **17 aprobadas**, después de conservar
  el esquema original. La [verificación](referencias/periodos-20261031/verification.json)
  fija resultados y hashes del código local comprobado.
- Las regresiones reales comprueban valores de RASK, pasajeros, coordenadas de
  ocupación/RASK y todos los puntos históricos, huecos de Industria en comparación,
  fechas de las bandas y sumas de rutas contra los archivos de julio.
- Escritorio 1440 × 1050 y móvil 390 × 844: entrada limpia; las cuatro entidades;
  Q3 directo, Q2→Q3 y regreso; las tres gráficas; mapas nacional/internacional;
  selección de enero de 2015 y regreso al trimestre general. Los JSON de navegador
  guardan también los valores mostrados y la geometría del DOM, no sólo títulos.
- Mercado: seis segmentos de línea visibles (tres aerolíneas separadas en julio),
  sin septiembre ni agregado Q3 fabricados, y aviso de dos meses.

### Continuación: tarjetas de Industria y limpieza visual

La primera revisión preservaba la falta de Industria Q3 en producción y la
mostraba también en la preview. Esa pantalla no resolvía la petición visual del
dueño. Ahora la preview usa explícitamente la proyección calculada desde los
tres reportes: RASK 8,16, CASK 7,57 y margen +0,58 centavos USD/ASK; ASK 41,07 mil
millones. Los inputs, ponderaciones e históricos permanecen trazables.

Se retiró la apertura automática de tooltips: repetía tres cuadros completos
sobre el mismo trimestre y tapaba las líneas. Los tooltips quedan para la
interacción del cursor. La dispersión conserva los puntos históricos sin
etiquetas superpuestas y anota sólo el trimestre seleccionado.

La [comprobación en navegador](referencias/periodos-20261031/browser-industry-review.json)
registra Q2→Q3 en escritorio y móvil, las cuatro cifras y cero tooltips forzados.
El export de prueba [Industry review](referencias/periodos-20261031/industry-review-executive.json)
es evidencia calculada de revisión, no un nuevo sitio firmado. Su regeneración
usa el mismo comando de auditoría con `--review-industry` y otro `--build-dir`.

Ejemplos de capturas verificadas (las capturas iniciales conservan el baseline
publicado y no se sobrescriben con la nueva proyección):

- [Economía · Aeroméxico Q3 · escritorio](referencias/periodos-20261031/desktop-AEROMEXICO-q3.png).
- [Economía · Industria Q3 sin agregado · escritorio](referencias/periodos-20261031/desktop-INDUSTRY-q3.png).
- [Economía · Viva Q3 · móvil](referencias/periodos-20261031/mobile-VIVA_AEROBUS-q3.png).
- [Vuelos · Industria Q3 parcial · móvil](referencias/periodos-20261031/mobile-flights-INDUSTRY-q3.png).
- [Mercado · Q3 incompleto · escritorio](referencias/periodos-20261031/desktop-market-q3.png).

Comandos reproducibles desde la raíz:

```powershell
uv sync --locked --extra chat --extra analytics
.venv/Scripts/python.exe -m scripts.audit_dashboard_periods --build-dir tmp/period-coherence-build --out docs/referencias/periodos-20261031/data-audit.json
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_dashboard_financial_periods.py tests/test_web_export.py tests/test_repo_budgets.py -q
```

Desde `web/`: `npm run check`, `npm test` con Node 22 y `npm run build`.
Los ensayos amplios de Python y sus límites se registran en Pendientes; sus
resultados no se confunden con el grupo focalizado anterior.

### Revisión de Mercado: línea continua (1 de noviembre)

La petición posterior del dueño reemplaza la indicación previa de marcar julio.
Se retira la interrupción visual introducida por el consumidor, sin cambiar
pasajeros, denominadores ni porcentajes. La información de procedencia se
conserva en los datos; el dashboard muestra la fuente AFAC, la fórmula y el corte
mensual, sin el aviso. No se certifica con este ajuste una reconciliación nueva
del histórico contra todas las ediciones originales de AFAC.

Pruebas focalizadas: 11 correctas, incluidos todos los porcentajes reales de
las tres series contra el payload construido. TypeScript correcto. La captura
[Mercado continuo](referencias/periodos-20261031/desktop-market-continuous.png)
muestra una trayectoria por aerolínea desde junio a julio y agosto. Sólo vista
local: producción y el PR siguen sin actualizarse.

### Lectura unificada y único trimestre global (1 de noviembre)

La petición posterior del dueño reemplaza el selector independiente de lectura.
El encabezado superior es el único selector de trimestre del dashboard. La hoja
muestra un título de Industria y cuatro puntos: Industria, Aeroméxico, Viva y
Volaris. Se retiran selector de aerolínea y trimestre, encabezados repetidos,
notas de corte/contexto y acción de análisis completo de esta hoja.

El catálogo conserva sus controles: sólo se consultan documentos aprobados del
trimestre global exacto. Un trimestre sin lectura muestra su ausencia; nunca
se rellena con una tesis anterior. `readingPeriod` y `sel_reading` heredados
no cambian el contenido. El chat recibe Industria y el trimestre global.
Aeroméxico condensa ventas, combustible y margen en un punto con sus citas;
Viva y Volaris conservan sus entradas. El punto general Q3 es una síntesis
editorial local de esas tres lecturas, sin crear una aprobación ni activar
una tesis de Industria en el expediente. Su publicación queda pendiente del
proceso normal y de esta revisión visual.

El mapa sólo ofrece meses de detalle dentro del trimestre global. Los controles
de rango histórico y de grano mensual/trimestral no eligen otro trimestre.
Q3 mantiene julio como cobertura parcial, y los meses faltantes no se fabrican.

Evidencia local: [hoja de escritorio](referencias/periodos-20261031/desktop-reading-global-q3.png),
[hoja móvil](referencias/periodos-20261031/mobile-reading-global-q3.png) y
[valores en Q3→Q2→Q3 y opciones del mapa](referencias/periodos-20261031/browser-reading-global.json).
Las regresiones usan el catálogo firmado y los JSON reales: comprueban cuatro
puntos con fuentes, cifras de cada trimestre, ausencia de controles y notas,
y eliminación de lecturas anteriores cuando falta una aprobación.
Suite web final: **321 pruebas en 47 archivos**, correctas con Node 22.
TypeScript y compilación Vite correctos. La validación anterior de 318 pruebas
corresponde al baseline local previo; se conserva como evidencia histórica.
No se hizo push, merge ni publicación de esta revisión.

### Análisis completo y énfasis editorial (1 de noviembre)

Las dos capturas de Whitepaper aportadas por el dueño son referencia de estilo:
párrafo breve, contraste entre crecimiento y rentabilidad y negritas selectivas.
No se incorporan sus afirmaciones como fuente de datos. El resumen destaca
ventas, resultados y margen; el título gana jerarquía sin añadir colores.

El desarrollo completo se despliega debajo del resumen dentro de la misma
tarjeta de lectura ejecutiva, sin tarjeta ni contenedor visual independiente. Conserva todos los párrafos y citas de los documentos aprobados del
trimestre global, organizados por entidad, sin selectores adicionales ni las
notas al pie retiradas. Q3 contiene Aeroméxico, Viva y Volaris; no inserta la tesis
de Industria Q2. Al cambiar de trimestre se vacía el contenido anterior y el
desplegable se cierra; un trimestre sin documentos no muestra análisis anterior.

**Las tesis y sus aprobaciones no se cancelan ni se sustituyen.** Se conserva
su texto canónico y su expediente; el resumen conjunto es una presentación
editorial local distinta. Una futura revisión del contenido canónico deberá
conservar versión y pasar por su revisión y aprobación normales. Las skills
editoriales finales se definirán después de cerrar este estilo con el dueño;
no se crean ni activan en esta etapa.

Validación local final: **322 pruebas web en 47 archivos**, TypeScript y build
Vite correctos. La regresión coteja literalmente todos los párrafos del análisis
completo contra los JSON aprobados reales y comprueba citas, negritas,
Q3→Q2 y vaciado sin lectura. Navegador: el desplegable abre 20 párrafos de las
tres entidades Q3 con sus citas; en móvil no desborda (375/375 píxeles).
[Resumen con negritas](referencias/periodos-20261031/desktop-reading-emphasis.png)
y [análisis desplegado](referencias/periodos-20261031/desktop-reading-complete.png).
No se publica ni se modifica ningún expediente de aprobación.

Corrección visual posterior del dueño: el desplegable pertenece a la misma
tarjeta del resumen, al final de los cuatro puntos. Comprobado en navegador:
una tarjeta, despliegue interior y 20 párrafos completos. Las cuatro regresiones
focalizadas de lectura pasan. [Captura integrada](referencias/periodos-20261031/desktop-reading-inline.png).
Las capturas anteriores con una tarjeta aparte se conservan como evidencia de
la revisión previa y no representan la presentación actual.

### Preparación narrativa trimestral a partir de Viva y Volaris

La [guía narrativa](analysis-agent/narrativa-trimestral.md) analiza las dos
capturas Whitepaper y contrasta sus preguntas con fuentes primarias. Incluye
aplicaciones editoriales locales de Viva y Volaris 3T26 para revisión; no son
registros importados, aprobados ni publicados. La investigación adicional no se
inyecta en el contexto cerrado del analista ni en los datos del dashboard.

Se incorpora una skill de preparación, `airline-quarterly-story`, enlazada por
el coordinador antes del cierre de evidencia. La guía del analista y la del
auditor incorporan ese punto de entrada y los criterios de calidad editorial.
El objetivo es que el preparador investigue hitos, motores, referencias y
contrapuntos que expliquen una situación de negocio; no basta enumerar cifras.

Se conserva byte por byte la skill histórica de análisis: `lifecycle.py` compara
su hash para algunos registros aprobados. No se modifica ese control ni se
reinterpreta una aprobación anterior. Los textos publicados y sus manifiestos
permanecen intactos. No se ejecuta el calendario ni se despachan nuevas tareas.

Validación: ambas skills pasan el validador de estructura; **30 pruebas** de
lifecycle y contrato literal pasan. Revisión manual de rutas y ejemplos: fuentes
primarias enlazadas, periodos y unidades identificados, distinción entre
atribución e interpretación, y OAG/cancelaciones conservado como investigación
pendiente. La ampliación de un paquete o perfil sigue requiriendo el proceso
normal; no se afirma soporte automático de trimestres futuros. La skill queda
preparada localmente para revisión, sin publicación ni aprobación de otra tesis.


## Continuación del 1 de noviembre: fuente oficial y revisión editorial

La fuente AFAC encontrada es el [resumen de septiembre de 2026](https://www.gob.mx/cms/uploads/attachment/file/1112829/resumen-septiembre-2026-27102026.xlsx),
observado en el catálogo oficial y descargado por el agente de actualización.
SHA256 `d1f88a20511457ae0ec9ccc7c354c0a78c3e23c2bba8d1b20ec3d7c85193b60b`.
El parser existente procesó PAXREG y PAXFLET y reconcilió 36 controles domésticos
por segmento y mes. Octubre–diciembre son columnas vacías de plantilla; se excluyen.
No se fabricó septiembre. Se usa la edición completa enero–septiembre de 2026;
las revisiones de AFAC también cambian Q2 a 20,376,397 pasajeros. La base 2025
se conserva del payload firmado para comparar exactamente los mismos meses.

El generador `scripts/build_afac_market_review.py` construye una base temporal,
usa `src.dashboard.market.build_market_payload` y valida esquema y privacidad;
no modifica site, Gold ni aprobaciones. El payload generado alimenta la preview.
Q3 suma 21,890,201 pasajeros: AM+Connect 6,056,686; Volaris 8,362,452;
Viva 7,232,729 y resto mexicano 238,334. Contra Q3 2025: +753,156 y +3.56%.
Un trimestre incompleto ahora suma los meses presentes y compara los mismos meses
previos; no usa Q2 como sustituto. El icono de cobertura es amarillo si es parcial.
Las variaciones tienen signo y color, mientras pasajeros y participaciones
absolutas permanecen neutrales. Fuente y cobertura se explican en dos iconos.

Las cuatro lecturas regeneradas se muestran exclusivamente en desarrollo con
`?period=2026Q3&review=1`. La versión es una propuesta editorial, no una aprobación.
Se generaron a partir de paquetes retenidos: el replay AM y Viva coincide exactamente
con 81 y 74 nodos; Volaris conserva 74 cálculos congelados de la reconstrucción
permitida, pero su replay vuelve a bloquearse por `os.getxattr` en Windows. No se
eliminó ese control ni se declara una corrida completa del perfil aprobada.
La propuesta vincula cifras y atribuciones a la evidencia y permanece en tmp;
el middleware de Vite no existe en producción. Título sin prefijo Industria,
cuatro puntos, detalle desplegable dentro de la misma tarjeta y negritas.
Cada reporte nuevo debe reevaluar la candidata de Industria, conservando versiones
y cobertura; no cancela retrospectivamente las tesis aprobadas.

El chat faltaba porque `.env.production` lo activa y Vite desarrollo no carga ese
archivo. `.env.development` ahora activa el botón y usa la misma URL pública,
sin credenciales ni cambios a autenticación. El panel abre, pero el servicio
remoto devolvió HTTP 502; el navegador muestra «No se pudo conectar». No se
verificaron respuestas ni se cambió el despliegue de Railway. El conector de
Railway pide reautenticación, por lo que no se pudo inspeccionar su diagnóstico interno. Visibilidad local
resuelta; disponibilidad del agente sigue pendiente.

Validación actual: TypeScript correcto, compilación correcta y **328 pruebas web**
aprobadas; cuatro pruebas de selección financiera Python aprobadas. Las pruebas
reales cubren Q2→Q3→Q2, total/nacional/internacional, filas y agregados oficiales,
comparación parcial por los mismos meses, signos y colores y las cuatro lecturas.
En navegador de escritorio: etiquetas 0% y 2021 separadas verticalmente por 3.5px;
Q2 y regreso Q3 actualizan los valores. En móvil de 390px no hay desbordamiento
horizontal de página; tabla y pestañas conservan desplazamiento dentro de su bloque.
Detalle nuevo contiene cuatro artículos y doce énfasis en negrita.
No se publicó esta revisión ni se verificó como cambio de producción.

## Limpieza adicional de Economía y Vuelos

Por observación del dueño se retiraron las tres líneas visibles de selección y
cobertura bajo los títulos de Economía, y el párrafo superior de Vuelos. Las
marcas del trimestre en las gráficas, los valores y la selección global siguen
actualizando. El contexto de cobertura de Economía permanece en la descripción
accesible de cada gráfica, sin generar un párrafo ni ocupar otra línea.
Verificado localmente con TypeScript y 17 pruebas de Economía/Vuelos sobre datos
reales, y en navegador Q3 con los tres nodos de texto ausentes y los tres gráficos
seleccionados en 2026Q3. No es una verificación de producción.

## Interacción con el agente y revisión del 1 de noviembre por la tarde

El botón final dice «Pregunta», permanece dentro de cada tarjeta y gráfica y es
siempre visible. Hover sobre cualquier parte del componente cambia sólo su botón
a azul con letras blancas; el fondo de tarjetas y gráficas no cambia. Los iconos
de información de KPI financieros se movieron junto al título y usan SVG para
que el `text-transform` del título no convierta la i en una I. Los selectores
conservan nombres accesibles sin títulos visibles; en escritorio quedan alineados
con Pregunta (altura 30px), con menor ancho. En móvil la comparación de tres
controles permite acomodarse en otra fila para evitar desbordamiento.

Pregunta adjunta una instantánea estructurada de entidad, trimestre, componente
y filtros. El compositor presenta una etiqueta que se puede quitar/reemplazar;
no copia párrafos, no escribe una pregunta prefabricada ni envía automáticamente.
El texto escrito permanece intacto. La instantánea se conserva aunque cambie la
vista; sin adjunto el encabezado dice «vista actual al enviar», evitando anunciar
un trimestre anterior mientras el envío usa la selección actual. Los reintentos
conservan el contexto y la clave del envío original.

La revisión independiente detectó y permitió corregir el rótulo de contexto sin
adjunto, el icono `.info` de los KPI de Vuelos y el posible desbordamiento móvil
con tres selectores. Se verificó móvil 390px y la alineación exacta de controles
de escritorio. El cambio de formato editorial añade énfasis azules/negritas sin
alterar texto ni cifras. Por instrucción posterior del dueño se retiró también
la leyenda «Propuesta editorial para revisión» de la vista local; el estado privado
y las guardas de publicación no cambian por retirar esa leyenda.

Los próximos handoffs financieros de análisis incorporan referencias y SHA de la
skill narrativa y su guía, y exigen aplicarlos al redactar/juzgar. Las 23 pruebas
del outbox comprueban esos recursos físicos. La revisión independiente confirmó
que se despachan los criterios sin cambiar scopes, aprobar ni añadir jobs de
Industria. Esto configura el criterio editorial; no promete calidad automática
ni habilita publicaciones de Industria por sí solo.

La publicación autorizada por el dueño sigue **pendiente**. Se conservó su mensaje
real y la identidad exacta de la propuesta en el expediente privado. Se restauraron
381 archivos históricos de drafts/lifecycle desde el respaldo privado cuyo SHA
coincide con `b39ca7bc23fe88503d7d6ed52c1e5e049f39a777f63de33b9736973944cf4de4`;
se verificó la cadena de 174 eventos, sin crear ni alterar aprobaciones. Falta un
perfil versionado compatible con los cuatro nuevos textos, replay de identidad
Library de Volaris (el entorno Windows carece de `os.getxattr` y de WSL), auditoría
por claim, aprobación exacta y gate/PR/CI/Pages. No se acortó el texto aprobado
para satisfacer otro perfil ni se desactivaron controles. `site/` sigue intacto.

## Corrección del selector de métrica de Economía

Se reprodujo en el navegador que cambiar métrica actualizaba el título pero no
las líneas. La causa era `layout.datarevision` fijado al trimestre: Plotly trata
las matrices como mutables con esa opción y sólo recalcula al cambiar la revisión.
Los generadores de gráficas ya crean matrices nuevas; se eliminó esa revisión
fija para usar el modo inmutable de Plotly. Esto permite cambios de métrica,
selección y rango dentro del mismo trimestre sin congelar puntos.

Además, la serie legacy de AM omitía CASK sin combustible, aunque su propio bloque
de entidad ya lo exportaba. El consumidor une ese campo por trimestre desde dicho
bloque, conservando los demás valores legacy y faltantes como null. No se añadieron
cifras externas ni se sustituyó CASK total por CASK sin combustible.

La regresión usa los registros reales construidos de Industria y AM y verifica
las cuatro matrices completas. En navegador se comprobaron los trazados SVG,
las dos líneas y las escalas: RASK 5–11, CASK 6–9, CASK sin combustible 4.5–6.5 y
margen −2–2. Todos cambian dentro de Q3; evidencia en
[metric-switch-browser.json](referencias/periodos-20261031/metric-switch-browser.json).

Validación final de esta revisión local: TypeScript y build correctos, **333 pruebas
web aprobadas** y **75 pruebas del outbox/handoffs aprobadas**. La revisión
independiente posterior no encontró bloqueos nuevos en la corrección de métricas.
Hover comprobado en navegador: botón rgb(22,70,127), letras rgb(255,255,255),
fondo de tarjeta rgb(255,255,255). Inventario documental: 131 archivos sin pendientes
ni errores. Estos resultados no sustituyen el replay editorial ni una publicación.

## Ajustes finales de Vuelos y formato de indicadores

Vuelos conserva cuatro indicadores financieros arriba. La cobertura del mapa
está junto a los vuelos en el panel derecho. Sólo muestra porcentaje cuando la
representación y el denominador AFAC de la selección son comparables; si falta
esa base muestra «No disponible». La ayuda accesible identifica la base nacional
más internacional, las rutas representadas y mostradas, las rutas sin cifra y los
meses efectivos. Q3 conserva la declaración parcial de julio, sin completar
agosto o septiembre ni inventar un 80 % de cobertura.

Nacional e Internacional están en la barra del mapa, junto a los filtros de rutas.
El trimestre global es el único control temporal del mapa. Se retiraron el título
y resumen duplicados de rutas, la nota bajo «Rutas nacionales» y el pie de texto
del volumen. La cobertura de pasajeros permanece en la descripción accesible de
la gráfica, sin un párrafo visible. Fuente y Periodo conservan nombres accesibles.

Cada gráfica de Vuelos tiene su propio botón Pregunta, dentro de su tarjeta; ya
no se crea uno en el contenedor de toda la vista. El contexto del mapa conserva
todas las aerolíneas elegidas y el trimestre global. Los selectores dejan espacio
para el botón; el hover conserva el fondo blanco y destaca sólo Pregunta.

Las tarjetas financieras, de Mercado y Vuelos muestran un decimal. El redondeo
parte del valor sin formatear; por ejemplo, 8.149 se muestra como 8.1. Se conserva
la precisión original en datos, cálculos, gráficas, tablas y ayudas accesibles.
No se cambiaron Gold, contratos de datos, `site/` ni aprobaciones en esta ronda.

Validación de la integración actual: TypeScript y compilación Vite correctos;
**333 pruebas web en 52 archivos**, todas correctas. El Node local es 25.9.0;
su almacenamiento experimental interfiere con el de jsdom. La suite pasa con
`NODE_OPTIONS=--no-experimental-webstorage`, sin cambiar ni omitir pruebas.
Las regresiones verifican el cálculo AFAC, la ausencia de porcentaje cuando falta
base comparable, rutas mostradas y parcialidad en la ayuda, periodo global único,
controles del mapa y contexto independiente de cada gráfica.

## Fuentes junto a indicadores y gráficas

El dueño aprobó la presentación de información de Mercado. Esa aprobación se
refiere a la interfaz; no aprueba datos, noticias ni textos editoriales nuevos.
El mismo panel blanco, redondeado y con sombra se aplica a los indicadores
financieros de Economía y Vuelos, a los mini indicadores del mapa y a las seis
gráficas: economía unitaria, pasajeros/RASK, ocupación/RASK, participación de
Mercado, mapa de rutas y mezcla nacional/internacional.

Cada título tiene un solo control de información. La alineación compartida centra
el icono contra el nombre, también si ocupa dos líneas; el SVG no lleva un borde
nativo adicional. Los paneles abren con hover, foco y clic táctil y permiten
seguir su enlace sin cerrarse al entrar con el cursor. Los financieros enlazan
sólo «Aeroméxico», «Volaris» y «Viva», subrayados, conservando las URL originales.
Las ayudas AFAC muestran «Fuente: AFAC.» con AFAC como único enlace; se retiró
la invitación repetida de consulta al final. Las líneas visibles de fuente
redundantes de Economía y mezcla se retiraron; la procedencia está en los iconos.
Industria remite a los tres emisores y explica la suma o ponderación pertinente.

Los vuelos estimados remiten a AeroDataBox; no se atribuyen a AFAC por aparecer
AFAC en la etiqueta histórica del modelo de pasajeros. El panel de cobertura
identifica por separado el denominador AFAC. La ayuda de cada mini indicador
mantiene observados, programación, estimaciones, atribuciones y movimientos
provisionales separados. Los textos son breves y conservan las unidades reales.

Verificación integrada: **351 pruebas web, 56 archivos**, correctas; TypeScript
y build correctos. Después de simplificar los enlaces y los últimos textos,
las 15 regresiones de fuentes e interacción volvieron a pasar. Las pruebas con
los datos reales repiten Q2/Q3 y las cuatro entidades, exigen un único botón,
SVG y panel por indicador, prueban enlaces oficiales, apertura/cierre y retirada
del panel anterior al reconstruir el volumen. El helper compartido evita
registrar dos veces los mismos listeners y cierra paneles que se retiran.

La revisión en Chrome midió diferencia de centros de **0 px** entre nombre e
icono para los cuatro indicadores de Economía en escritorio y móvil de 390 px,
y para los cuatro de Vuelos en escritorio. Encontró un SVG y un botón por
nombre, sin borde adicional, y enlaces a los emisores. Las capturas locales
están en `tmp/ui-news-reading-20261101/`: `economy-info-desktop.jpg`,
`economy-info-mobile.jpg` y `flights-info-desktop.jpg`; son evidencia local
ignorada por Git, conservada para revisión. La captura de Vuelos precede la
corrección de atribución AFAC y no se usa como prueba de esa fuente actual.
El ensayo de cambios Q2/Q3 repetidos en navegador se interrumpió durante una
recarga; está pendiente, aunque las regresiones automatizadas sí pasaron.

## Mercado integrado y detalle de la mezcla

La petición más reciente une Mercado y Vuelos. Conserva sólo cuatro KPI
financieros arriba, después mapa, participación AFAC y mezcla de pasajeros.
Los identificadores internos preservan enlaces y consultas; el contexto de
Pregunta identifica el dataset de la gráfica. La participación mantiene su
historia completa y eje fijo; la franja sigue el trimestre elegido. La instrucción posterior retiró
el desplegable AFAC al cerrar el detalle mensual enriquecido de participación;
la comprobación real de escritorio y móvil se documenta en el cierre inferior.

El mapa aplica «sólo observados» a Norteamérica cuando ese periodo y selección
tienen observaciones. Filtra componentes antes de totales, rutas, búsqueda y
tooltips; la red internacional global aplica la misma regla a su parte norteamericana.
Si no hay observados, conserva los tipos disponibles y lo informa. Canadá estimado
queda fuera al activar la regla, sin afirmar cobertura completa de Norteamérica.
Brasil y las otras regiones conservan observados, estimados y programación como
tales. VCP (Viracopos) se incorporó a Sudamérica en la vista y en la proyección
de consultas para que sus dos salidas ANAC no se confundieran con Norteamérica.

La preview normalizada ANAC contiene 184 salidas observadas de Brasil, diez
celdas por operador, sentido y mes, de julio a septiembre. La cobertura se deriva
de las rutas seleccionadas: Norteamérica, Europa y Asia siguen en julio; el dato
brasileño no completa sus meses. En una red mezclada, «meses con algún dato» no
certifica cobertura completa. Las vistas regionales o de evidencia filtrada no
usan el porcentaje AFAC de toda la red como si su denominador fuera compatible.

El gráfico AFAC de Grupo Aeroméxico ahora usa el mismo paquete de septiembre
que las otras selecciones e incluye Connect. Su Q3 suma 3.852.023 pasajeros
nacionales y 2.204.663 internacionales; el KPI financiero del emisor sigue
usando su reporte (6.161.000), sin igualar universos distintos. La alternativa
corporativa mantiene sus meses, definiciones y fuentes propias.

El nuevo detalle MIX muestra una fecha y una comparación explícita: «3T26 /
vs. 3T25» o el mes frente al mismo mes del año anterior. Presenta pasajeros
compactos y variación anual por segmento, azul positiva y roja negativa. Una
selección múltiple añade el nombre de la aerolínea. Los periodos parciales usan
sólo los mismos meses por segmento y lo declaran; base faltante o cero queda
N/D. La comparación usa el periodo señalado, no el trimestre global por defecto.
La protección contra renders que terminan tarde evita restaurar detalles antiguos.

Últimos controles de esta parte: TypeScript correcto; 159 pruebas web focalizadas
en 24 archivos y once pruebas Python de la vista de consultas, correctas. El build
anterior a la última incorporación de meses/VCP pasó; requiere una compilación
integrada final después de que terminen las otras áreas. Las fixtures de AFAC y
ANAC se conservan en el repositorio para que estas regresiones no dependan de
la preview local. La fixture ANAC sólo contiene salidas derivadas del archivo
público, sin capturas privadas AeroDataBox.

En Chrome se verificó la vista unificada, los cuatro KPI con un único icono y
centros coincidentes, y Norteamérica Q3 sin filas ni mini KPI estimados. Un clic
sobre una barra real de Grupo Aeroméxico mostró 3T26 frente a 3T25, Nacional
3,9 M −4,3 % e Internacional 2,2 M −1,4 %. El toque a 390 × 844 mostró el mismo
detalle dentro del viewport, sin desbordamiento; la anchura se restauró después.
Capturas locales conservadas: `tmp/north-america-observed/mix-yoy-am-q3-desktop.jpg`
y `mix-yoy-am-q3-mobile.jpg`. Se registraron también coordenadas reales de las
barras SVG y trazas del mapa. La matriz completa de navegador para cuatro
entidades, Q2↔Q3, regiones, enlaces históricos y el chat final sigue pendiente
tras congelar los cambios de las otras áreas. No se reemplaza con pruebas unitarias.

### Cierre local: Mercado integrado y detalle mensual

La navegación queda en Lectura ejecutiva, Mercado, Economía unitaria y Noticias.
Mercado conserva los cuatro KPI financieros, el mapa, participación AFAC y mezcla,
en ese orden. Se retiraron únicamente las tres tarjetas AFAC y, por instrucción
posterior del dueño, la tabla desplegable AFAC. Los cálculos fuente se conservan.

El detalle de participación muestra una sola fecha, las tres aerolíneas,
participación y pasajeros en millones con un decimal como máximo. La variación
usa pasajeros del mismo mes, segmento y universo AFAC del año anterior;
la cabecera nombra esa base una sola vez. Positivo es azul, negativo rojo y
base ausente o cero es N/D. El foco y las flechas permiten consultar sin hover;
el toque fija el detalle. Los ejes y toda la historia permanecen fijos al cambiar
el trimestre global; Pregunta conserva el trimestre y el segmento seleccionados.

El detalle compartido por participación y mezcla aparece sobre el chat usando
la capa superior del navegador y respeta el ancho útil, incluida la barra de
scroll. La revisión real confirmó escritorio de 1366 px y móvil de 390 px:
[superposición sobre chat](referencias/periodos-20261031/market-tooltip-sobre-chat-normal.jpg),
[detalle mensual móvil](referencias/periodos-20261031/market-tooltip-movil.jpg),
[fuente AFAC](referencias/periodos-20261031/market-fuente-con-chat.jpg) y
[mezcla móvil](referencias/periodos-20261031/mix-tooltip-movil-final.jpg).
Las ayudas de fuente se cierran al cambiar tamaño; Escape cierra primero el
detalle y conserva el chat. La revisión global de todas las combinaciones de
entidad, trimestre y tamaño continúa pendiente del coordinador.

La proyección del chat aplica la política observada de Norteamérica **antes**
de ordenar y limitar rutas; conserva los demás tipos de evidencia fuera de esa
región y no modifica el snapshot. Hay [16 comparaciones exactas](referencias/periodos-20261031/chat-route-view-parity.json)
entre el consumidor TypeScript real y la herramienta Python, para cuatro
entidades, Q2/Q3 y vista global/Norteamérica. Se conservaron fuentes, componentes,
valores y restricciones de cobertura. Los contratos internos distinguen la
gráfica AFAC de los KPI financieros, mapa y mezcla, aunque compartan pestaña.

El servicio de chat remoto está vivo (health sin Origin 200), pero rechaza la
preview local con 403 `origin not allowed`. La corrección exacta de configuración
está preparada con autenticación intacta; [el procedimiento de Railway](chat/railway.md#origen-exacto-de-la-preview-local-revisión-del-1-de-noviembre-de-2026)
requiere reconectar ese plugin antes de inspeccionar o modificar el servicio.
No se solicitó otra clave, no se consumió una consulta pagada y no hubo despliegue.

Validación al cierre local: 385 pruebas web en 62 archivos, tipos y build
correctos. En Node 25 se usó `NODE_OPTIONS=--no-experimental-webstorage` para
conservar el almacenamiento de jsdom. Las regresiones de detalle comprueban meses reales de 2023 y
2026 en los tres segmentos, fuentes, N/D, teclado, toque, portal y repetición.
Se verificaron 43 pruebas de rutas/contexto y una repetición con UTF-8 por la
codificación CP1252 heredada de Windows. Además, 43 pruebas de API, orígenes
locales y runtime pasan; se excluyó una prueba POSIX de permisos no compatible
con Windows que había fallado en el ensayo amplio. No se relajó ese control.
La suite completa de Python y el gate de publicación no se declaran aprobados.

## Revisión independiente Fase 1

Revisión del 1 de noviembre sobre la preview local `http://127.0.0.1:5173/`
con `review=1`, mediante una pestaña nueva de Chrome. Se usaron los datos
construidos reales y la geometría SVG visible. Esta revisión precede al
exportador normal y al cierre del gate; no certifica producción ni autoriza
datos, noticias o lecturas nuevas.

- La entrada sin `period` abrió **3T26**. El enlace histórico `2025Q3`
  conservó **3T25**; las cuatro lecturas ausentes se informaron como no
  publicadas. La dispersión de Industria anotó 3T25 y mostró su anillo SVG.
- Economía se probó en **2T26 → 3T26 → 2T26**, para cada una de las cuatro
  entidades y sus tres gráficas. El RASK visible fue Aeroméxico
  **9.9 → 10.7 → 9.9**, Viva **6.5 → 7.1 → 6.5**, Volaris
  **5.9 → 6.4 → 5.9** e Industria **7.6 → 8.2 → 7.6** centavos USD.
  Las franjas cambiaron y el anillo de dispersión se reemplazó. Por ejemplo,
  Volaris pasó de `translate(202.46,80.79)` a `translate(266.54,33.5)`
  y regresó a la primera coordenada. La comparación de cuatro entidades
  dibujó curvas distintas para RASK, CASK, CASK sin combustible y margen.
- AFAC mantuvo idénticos los trazados SVG, una vez estabilizado el tamaño,
  al cambiar **3T26 → 2T26 → 3T26**. El eje conservó 2021–2026 y septiembre
  como último mes. La franja pasó de las coordenadas horizontales
  **1052.96–1099.02** a **1007.39–1052.96** y regresó. El detalle de septiembre
  comparó explícitamente septiembre de 2025: Aeroméxico **29.1%, 1.8 millones,
  −2.3%**; Volaris **36.7%, 2.3 millones, +5.4%**; Viva **33.2%, 2.1 millones,
  −6.8%**. Se probaron Total, Nacional e Internacional. Los cambios positivos
  fueron azules y los negativos rojos. El detalle vive en `BODY` y usa la
  capa superior nativa del navegador.
- El mapa Q3 se comprobó después de Q2. Norteamérica mostró sólo julio y
  observaciones BTS; declaró Canadá estimado excluido. En Industria excluyó
  **1,152** vuelos estimados y **21** rutas. En Aeroméxico fueron **840/13**,
  en Volaris **150/3** y en Viva **162/6**. Se revisaron las regiones
  disponibles de Aeroméxico y Volaris, y Nacional de las tres empresas.
  Brasil tuvo rutas con tres meses, mientras Europa y Asia conservaron julio.
  El conjunto internacional dijo «meses con algún dato», sin llamar completa
  a toda la región. La mezcla de Aeroméxico mostró fuentes AFAC y corporativa
  separadas; sus detalles mensuales de septiembre conservaron sus cifras y
  comparativos distintos. Volaris y Viva también mostraron sus reportes
  corporativos mensuales como tramos reservados, separados de AFAC trimestral.
  La selección conjunta de Aeroméxico, Volaris y Viva dibujó seis series
  nacionales/internacionales tanto por trimestre como por mes y un detalle
  con las seis filas. Por ejemplo, AFAC Q3 mostró Volaris **6.3 M nacionales
  y 2.1 M internacionales**, y Viva **6.4 M y 0.8 M**. El contexto adjunto
  identificó entidad y 3T26.
- Chat se inspeccionó en **390 × 844**, **1366 × 900** y **2560 × 1440**.
  En móvil, el panel midió **366 × 820**, desde **(12,12)** hasta **(378,832)**.
  La página y el lanzador quedaron inertes; Escape cerró el panel y devolvió
  el foco a «Abrir chat», sin desbordamiento horizontal. En la pantalla ancha,
  el panel midió **420** de ancho, quedó a **20** píxeles del contenido y
  dentro de la ventana. Se observaron cabecera «Chat», nueva conversación y
  cierre. El servicio remoto mostró indisponibilidad: **no se verificó una
  respuesta real del modelo**.
- Noticias mostró **26** artículos: **23 pendientes de aprobación** y tres
  anteriores. Se comprobaron títulos, resúmenes y enlaces de fuentes visibles,
  sin filtros. Verlos en la preview no equivale a aprobarlos.

Después de la decisión real del dueño sobre el lote de 23 noticias, se repitió
la verificación del exportador normal. El índice quedó en **33 registros**:
26 noticias y siete reportes. Los diez objetos anteriores coincidieron
exactamente con `origin/master`; los 23 nuevos conservaron los hashes del
paquete revisado. El exportador produjo `approved_only`, **26 noticias y 27
fuentes**, todas `owner_approved`. Su SHA-256 fue
`6e5206072e7a1288a6f27799b65ebd7aff804614030084217c8b1eda1c2c00fd`.
Esta decisión de Noticias no aprueba las cuatro nuevas lecturas trimestrales.

Se corrigió un defecto menor encontrado en esta revisión: el nombre accesible
de «Pregunta» conservaba el título inicial al cambiar la métrica. Ahora se
actualiza el botón existente. La prueba focal pasó **5/5** y el navegador mostró
«Preguntar sobre Margen unitario por aerolínea», con un solo icono de información.
El cambio se limita a `card-actions.ts` y su prueba; esa corrección propia queda
fuera de la independencia del resto de esta revisión.

El control TypeScript pasó. Una ejecución amplia durante la edición de
contratos terminó con **385 pruebas aprobadas y dos fallidas** por el tipo
generado de Industria todavía ausente; debe repetirse al congelar la entrega.
Al repetir con los tipos actualizados, la suite web pasó **387/387 pruebas en
62 archivos**. La revisión Python dirigida terminó con **176 aprobadas y una fallida**: detectó
que el esquema editorial de Aeroméxico se aplicaba incorrectamente a otras
entidades. El esquema separado para Industria eliminó ese error. Una repetición
focal pasó **22 pruebas**, pero el sitio anterior todavía falló la igualdad de
Noticias contra el índice recién aprobado: debe cerrar con el paquete nuevo.
El replay físico de los tres emisores y las cuatro historias pasó sin sustituir
fuentes por cachés: **308, 319, 346 y 324 palabras** respectivamente para
Aeroméxico, Viva, Volaris e Industria. No creó auditorías ni aprobaciones.
La última corrección dejó el contexto de Noticias sin trimestre implícito
cuando el archivo completo no tiene selector; las consultas con fechas explícitas
conservan esas fechas. Las otras cuatro vistas mantuvieron su trimestre.
Después de ese ajuste, la suite web pasó **388/388** y TypeScript pasó.
Las 20 regresiones de frontera y dos de contexto de Noticias también pasaron.

Se ejecutó además `quarterly_story_data.outputs` con las capturas físicas,
los tres paquetes financieros reproducidos y el índice aprobado fijado desde
fuera del proceso. Reconstruyó **12 JSON** en una carpeta temporal aislada,
sin escribir `site/`, Gold activo ni el registro de aprobaciones. Se verificó
Industria Q3, Mercado AFAC Q3 completo, los nueve archivos ANAC y Noticias
`approved_only` con 26 noticias. Los hashes del resultado fueron:
`executive.json` **ca21ebf8120826bdfd7bcfc54e465b0c143925c11cd4403e911907329ec5a77d**,
`market.json` **c3c55fffb2fce9e44e6139071791eff5d99b693d79a9c2fea0aaf0e609c688fe**,
`flights/quarters.json` **8ea8312130fff8ced0caac1ba4c9ff2b3ab64d40b7fa43f15e6773e597768e94**.
Esto valida la reproducción de datos; no constituye aprobación ni publicación
de las cuatro lecturas nuevas.

Tampoco se ha completado aquí la matriz de todas
las selecciones múltiples de mezcla, la respuesta remota del chat ni la
verificación del sitio publicado. Los cambios del gate y del expediente SEC
siguen su auditoría independiente antes de cerrar esta fase.

## Preparación de publicación con fuentes originales (2 de noviembre)

La versión actual reúne cuatro pestañas, la lectura completa y el chat visible.
El dueño aprobó las 23 noticias del paquete revisado: el exportador normal ya
produce 26 fichas aprobadas, con 27 enlaces y las tres noticias anteriores
conservadas. El índice y sus recibos distinguen el hash canónico que exige el
runtime del hash de los bytes del archivo. Su despliegue todavía requiere CI,
PR y actualización del pin externo del servidor.

Las cuatro historias nuevas usan un perfil versionado separado y pasan por el
lifecycle normal. Se capturaron los cuatro documentos originales de Volaris en
SEC: 446 celdas y 187 reconciliaciones, sin convertir los cuatro guiones faltantes
en ceros. Los 74 valores y formatos coinciden con la reconstrucción anterior.
La única corrección propuesta al texto explica que ahora se conservan y verifican
los originales. Esa procedencia nueva y las cuatro identidades finales requieren
revisión independiente y una decisión exacta; no se reutiliza una aprobación de
fuentes anteriores ni se cambia el expediente histórico.

La regresión independiente reprodujo doce JSON desde AFAC, ANAC, las tres fuentes
financieras y el índice aprobado. Conserva los meses reales de cada fuente y la
separación entre observaciones, movimientos y estimaciones. El nuevo gate conserva
Q2 con su verificador original completo; los tres textos Q3 sustituidos mantienen
su historia por hashes y estado aprobado y se declaran expresamente no reproducidos
ni consumidos como fuente nueva. Los controles Library anteriores siguen intactos.

El replay Q2 original requiere Linux: su cápsula de Industria compara rutas con
supuestos de separador POSIX. En Windows se restauraron únicamente insumos privados
faltantes del archivo verificado y se regeneró el warehouse desde Gold. No se
modificó la cápsula fijada por hash. El entorno Linux debe completar el gate antes
de generar los commits del sitio. Un artifact o build no acredita publicación.

Validación focal de los nuevos perfiles, adaptador SEC, límites de publicación,
revocación durante el build y presupuestos: 58 pruebas correctas. La revisión
independiente previa registra abajo las 388 pruebas web, TypeScript y los doce
payloads normales. El rediseño AFAC del mapa solicitado para después de publicar
permanece separado y sin activar.

El ensayo posterior del catálogo incluye la ruta explícita de Aeroméxico Q3 y
conserva la ruta histórica de Q2: 391 pruebas web y TypeScript correctos. El
replay Linux ya importó las cuatro historias sin alterar su texto; aún debe
cerrar la verificación del sitio histórico y después el replay original Q2.
Los errores del verificador histórico se conservan completos en diagnósticos
privados; los logs públicos identifican únicamente el módulo, commit y resultado.
El diagnóstico nativo aisló un conflicto de pins: el sitio histórico usa los diez
registros anteriores y la versión nueva conserva 33. El transporte histórico
exige el lote humano exacto, sus hashes raw/canónico anteriores, los mismos bytes
en Git del baseline y su productor, y la conservación de los diez registros.
Entrega el pin anterior únicamente al subproceso original; la nueva versión
sigue exigiendo su pin externo nuevo. Trece negativos específicos y la revisión
independiente validan esta separación; no se modifica el verificador anterior.

## Cierre del artefacto y autorización exacta (4 de noviembre)

El dueño autorizó las cuatro lecturas de 3T26 y el reemplazo de procedencia de
Volaris por los originales SEC bajo el alcance SHA-256
`708bedf937af692fc87de96cace34cbf55269ea27fb5b7196d74b31bcd026695`.
Se conservaron el mensaje real, las auditorías independientes y los eventos
normales del expediente privado. Las 23 noticias tenían su decisión propia,
que se preservó; no se volvieron a aprobar.

La preparación Linux `41928426414` reprodujo los cuatro 2T26 con sus lectores
originales, sin modificar cápsulas ni falsificar un veredicto. El intento 1 de
publicación `41932650875` rechazó un HTTP 503 del baseline servido antes del swap.
La única pasada diagnóstica y las lecturas secuenciales acotadas verificaron los
809 archivos exactos y la recuperación de diecinueve errores, con manifiesto y
master intactos. El intento 2 del mismo run terminó correctamente sin cambiar
productor, datos, registros, autoridad ni controles.

El sitio generado es `842d140a983f785e9d39e7d3d378fdfebe79981e`, con ancla
`2f6045aa4c207ec6eb51ef4fdd1e346db3275252`. Su manifiesto SHA-256 es
`61f6fab632088ee4c316515da397b78969cfada6c9ec098a8407ad3d9aef7729`.
El gate y la verificación fuerte pasaron; los consumidores independientes
reprodujeron **ocho análisis y doce JSON normales**. La auditoría posterior
verificó las siete salidas del recibo, los 823 archivos declarados, las ocho
identidades, los cuatro 2T26 byte a byte y los doce pins contra el alcance.
Las cuatro identidades y el estado histórico explícito están en el
[ancla pública](../config/publish/quarterly-story-release.json).

La revisión del sitio exacto confirmó cuatro pestañas, cambios Q2↔Q3 por emisor,
fuente SEC, 26 noticias y adjuntos de contexto del chat. En móvil estable
390×844 no hay desbordamiento horizontal del documento. Los commits de sitio
conservan ascendencia desde el código revisado `089f48a6`; el cierre documental
no modifica runtime ni datos firmados. El PR y los recibos de despliegue
distinguen estos resultados locales de la comprobación servida.

El lector del chat selecciona el contrato exacto declarado por la identidad y
ruta de cada análisis presente en el manifiesto. Así acepta Aeroméxico e Industria
3T26 bajo sus contratos propios, mientras 2T26 conserva el contrato histórico y
sus límites de citas. Verifica hashes de contratos y cinco campos de identidad
antes de reutilizar una validación en caché. Este arreglo de consumidor conserva
byte a byte sitio, ancla y autoridades del productor original `602ea2a4`; el
lector nuevo tiene revisión técnica propia y no reasigna el alcance aprobado.

## Pendientes

- La integración conserva CI y revisión del head final del PR 188, despliegue
  normal y comprobación de Pages y Railway. Un build local no sustituye esa
  verificación de producción ni la respuesta del servidor del chat.
- La red conserva cortes diferentes: BTS y AeroDataBox julio; ANAC Brasil
  julio–septiembre. Completar meses futuros mediante sus fuentes y su aprobación,
  sin atribuir a esta entrega cobertura uniforme. El mapa AFAC de fase 2 queda
  fuera de la publicación actual.
- Cerrar la suite amplia de Python en un entorno compatible y restaurar el
  warehouse para las pruebas locales que lo necesitan. El primer ensayo del
  entorno heredado carecía de dependencias; se creó `.venv` aislado desde el lock.
  Windows usó CP1252 por defecto y provocó errores de lectura; se repitió con
  `-X utf8`: **202 aprobadas y un fallo**, al exigir crear un enlace simbólico
  sin el privilegio de Windows (WinError 1314). Se detuvo en ese primer fallo;
  no es una suite completa aprobada. Las 17 regresiones de contratos/chat y el
  grupo focalizado pasaron. No se relajaron pruebas ni controles.
- El restorer del checkpoint requiere atributos de Linux no disponibles en
  Windows; los expedientes originales se conservan sin simular esos atributos.

El inventario conserva fuentes, pruebas, guías y evidencia. No se retiró ningún
archivo ajeno. Las seis ediciones locales iniciales de continuidad de Mercado
se guardaron en `tmp/period-coherence-initial` antes de aplicar la instrucción
posterior de conservar el corte. Los datos de preview, `.venv`, compilados y
recibos temporales son locales e ignorados; no son expedientes de aprobación.

El inventario completo y la disposición vigente se conservan en el cuerpo del [PR 188](https://github.com/salvamalfa/aeromexico-tracker/pull/188), junto al diff exacto de esta entrega.
