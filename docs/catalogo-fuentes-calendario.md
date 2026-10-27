# Catálogo de fuentes, métricas y rondas de actualización

Revisión: 26 de octubre de 2026 (UTC). **Skills y coordinador implementados;
integración técnica autorizada. Calendario sin activar y sin publicación de datos.**

## Resumen

Ya hay una herramienta ejecutable para preparar las actualizaciones por fuente.
Incluye ocho skills por familia y un coordinador. Primero muestra qué haría.
Después puede capturar y comprobar un lote candidato en una carpeta separada.
La aprobación del calendario ya está recibida. La revisión del contenido y su
publicación conservan sus permisos separados.

La continuación del 22 de octubre añade certificadores offline para las tres
series Banxico, combustible EIA y las cinco cotizaciones. Validan el producto
retenido mensual o trimestral y sus cálculos; no prueban disponibilidad actual
ni completitud del calendario de observaciones. La reconciliación local de los
cuatro PR está preparada; su integración remota y la evidencia externa indicada
al final siguen pendientes.

La integración de esta infraestructura no aprueba una ronda de datos. Aerocivil
y GDELT permanecen **requeridos y bloqueados**. Sus fallos impiden aceptar una
ronda que los requiera; no se sustituyen por cero ni por otro producto. Ningún
comando instala un calendario o incorpora candidatos a producción al fusionar
el código. Los originales y candidatos conservan sus recibos y revisión propia.

La continuación del 23 de octubre añade también el certificador GAP/ASUR de
originales julio 2026, con países y redondeo explícitos; su prueba y estado de
integración están en el apéndice. Incorpora comprobaciones integrales de AICM
y un control estricto del archivo AIFA. AICM permite probar originales de julio
y agosto; AIFA sigue bloqueado por fechas internas contradictorias. Esto no
declara lista la ronda completa. RSS añade un certificador integral de los XML
retenidos, con fechas declaradas y cobertura parcial explícitas. Su estado
de pruebas e integración está en [PR157](https://github.com/salvamalfa/aeromexico-tracker/pull/157). Viva conserva su lote trimestral separado. PR152 conserva por separado sus certificadores
macro/mercado y espera una revisión adicional; este cambio no modifica su head.

La continuación BTS añade certificación mensual desde los ZIP oficiales
retenidos. Comprueba mayo y julio y detecta cinco altas retrospectivas de mayo.
Conserva una incidencia de abril y bloquea ese mes si se solicita. No acredita
cobertura completa por operador ni disponibilidad reciente.

La revisión oficial del 24 de octubre no encontró un error del parser que
justifique aceptar los originales rechazados. Confirmó contradicciones de
Volaris/AIFA, la leyenda pendiente de Aerocivil y un nuevo fallo de acceso a
GDELT. Identificó los días declarados de los tres reportes 2T26; no inventó
horas de publicación ni festivos de 2027. La evidencia está en el apéndice.

La continuación local del 26 de octubre reúne los cuatro PR pendientes sobre
master `dad0a39b`, conservando las publicaciones existentes. Nueve cadenas de
originales retenidos reproducen sus 53 salidas. La revisión independiente local
es favorable. Esto acredita la preparación técnica local: todavía faltan los
controles del futuro head remoto, la revisión técnica del nuevo runtime que
exige la preservación financiera y resolver el estado desconocido de las
revisiones adicionales. La disponibilidad actual de las fuentes no se comprobó.

## Qué cambia para ti

Estas son las ocho skills. Cada enlace abre instrucciones técnicas para un
agente, con su alcance y sus límites:

- [Reportes de empresas](../.agents/skills/airline-update-corporate/SKILL.md): resultados, tráfico corporativo y documentos regulatorios.
- [Tráfico AFAC y BTS](../.agents/skills/airline-update-traffic/SKILL.md): estadísticas de las autoridades de México y Estados Unidos.
- [Aeropuertos](../.agents/skills/airline-update-airports/SKILL.md): tráfico de aeropuertos y grupos aeroportuarios.
- [Macro y mercado](../.agents/skills/airline-update-macro-market/SKILL.md): tipo de cambio, combustible y precios bursátiles.
- [Rutas](../.agents/skills/airline-update-routes/SKILL.md): datos de autoridades y evidencia fechada de presencia o programación.
- [Referencias y contexto](../.agents/skills/airline-update-context/SKILL.md): códigos de aeropuertos, regulación y diccionarios.
- [Noticias](../.agents/skills/airline-update-news/SKILL.md): revisión mensual de titulares y enlaces, con sus fuentes.
- [Derivados y curación](../.agents/skills/airline-update-internal/SKILL.md): cálculos internos y contexto revisado.

El [coordinador](../.agents/skills/airline-update-coordinator/SKILL.md) organiza
esas familias en rondas. Las skills dan instrucciones; el programa ejecuta los
pasos permitidos. Sus comandos están en el apéndice. Tener una skill no implica
que todos sus adaptadores estén terminados ni que la fuente esté actualizada.

La receta devuelve la entrada exacta, los identificadores, el formato y los
pasos de cada fuente. Este cuadro conserva el alcance comprobado al 19 de
octubre; la continuación del 21 y su matriz aparecen abajo:

| Familia | Alcance actual |
|---|---|
| Empresas | BMV: catálogo y ZIP oficiales capturados; parseo offline acotado implementado. SEC preservado reconstruido; Ryanair FY2026 tiene un lector XBRL retenido separado, sin convertirlo a trimestre. Tráfico mensual y finanzas 2T26 IR de Aeroméxico tienen candidatos dedicados desde PDF; Viva 2T26 añade tablas financieras/operativas completas retenidas con 1T26 solo como soporte. Véase alcance abajo. Otros periodos nuevos IR/SEC siguen condicionados. |
| Tráfico AFAC y BTS | AFAC: aeropuertos y marginales de julio tienen adaptadores offline; países conserva cajas acumuladas exactas. Boletines/base julio–agosto conservan su evidencia previa. BTS añade candidato integral offline de mayo/julio y revisiones, sin certificar cobertura completa por operador. La retención no es una captura nueva. |
| Aeropuertos | AICM julio/agosto tienen certificador integral offline. AIFA julio falla por fechas internas anteriores al cierre del mes; sus comprobaciones históricas de tabla no acreditan el producto integral. GAP/ASUR julio tienen certificador integral preparado con países y redondeo explícitos; véase continuación abajo. OMA julio y slots AICM verano 2026 tienen adaptadores de originales retenidos. OMA septiembre enlazado falló; no se acredita septiembre completo. |
| Macro y mercado | EIA, tres series Banxico y cinco series bursátiles verificadas hasta Gold para septiembre. H.10 tiene una cadena dedicada de certificación mensual aislada; véase su alcance y evidencia abajo. La familia completa no está certificada. |
| Rutas | ANAC junio, CAA junio y Aena enero–julio tienen adaptadores retenidos con ámbitos separados. Cuatro documentos aportan pasajes fechados. Aerocivil conserva comprobación numérica; falta su leyenda de códigos. No representan una red mundial uniforme. |
| Referencias y contexto | OurAirports conserva 9.051 referencias verificadas. FAA y diccionario tienen snapshots candidatos por SHA: 84 categorías y 86.553 palabras, sin inferir seguridad de aerolínea ni tono empresarial. |
| Noticias | PR142 ya está integrado. Corte RSS retenido de septiembre: 12 URLs fechadas en seis días observados. Los 11 candidatos de PR142 pasan controles de metadatos; no se releen sus cuerpos aquí. GDELT devolvió 503 en un intento sin reintentos. Sin cobertura universal ni activación. |
| Derivados y curación | Sin descarga propia. Mapas documentales ejecutables para cinco perfiles y 21 eventos; conservan discrepancias y decisiones pendientes. No aprueban perfiles, impacto ni confianza de los eventos. |

El [inventario de los 42 productos del 19 de octubre](referencias/source-updates-20261019/product-coverage.json)
separa las capas comprobadas de aquel corte. Registró **35 alcances acotados comprobados**:
26 de producto/periodo o snapshot y nueve de datos históricos retenidos.
No significa 35 fuentes actualizadas ni 35 reportes completos. Además hay un
corte RSS parcial comprobado, dos revisiones documentales preparadas, tres
condiciones de fuente o atribución y una exclusión intencional de errores.
Las revisiones documentales no son certificación Silver/Gold. Los detalles
están en el apéndice y en el inventario.

La ronda mensual será el primer día hábil bancario mexicano en o después del
15. Noticias se revisa en esa misma ronda. La muestra de 2026 da **15 de
octubre, 17 de noviembre y 15 de diciembre**. Octubre ya pasó; esta muestra no
crea una ejecución retroactiva. [Ver calendario reproducible](referencias/source-updates-20261019/calendar.json).

La ronda trimestral será dos días hábiles después del último reporte financiero
confirmado de Aeroméxico, Volaris y Viva. El día del reporte no cuenta. Si queda
a siete días naturales o menos de una mensual, ambas se hacen en la fecha
posterior. Los días se calculan en **America/Mexico_City**. La hora de captura
se conserva en UTC, y cada anuncio conserva su zona original.

La propuesta aprobada sí especifica días bancarios mexicanos y un lote de las
tres entidades. El código concreta «última publicación central confirmada» como
**los tres reportes financieros del trimestre realmente publicados**. Excluir
anuncios y llamadas, y esperar esos tres documentos, es una interpretación
operativa conservadora; no es una definición literal adicional aprobada por el
dueño. Debe revisarse antes de activar el coordinador. La zona de México procede
del encargo actual; el texto original registraba el calendario operativo en UTC.
[Propuesta aprobada, líneas 169–182](https://github.com/salvamalfa/aeromexico-tracker/blob/6d8da2c4c0b96371c26521aedb5828610451d03a/docs/catalogo-fuentes-calendario.md#L169).

El **2 de noviembre de 2026 es inhábil bancario**. El 16 también lo es. Se usa
el calendario oficial de 2026, contrastado con BMV. Un año aún no verificado
queda bloqueado; no se extrapolan sus festivos.
[DOF](https://www.dof.gob.mx/nota_detalle.php?codigo=5775684&fecha=10%2F12%2F2025),
[BMV](https://www.bmv.com.mx/es/grupo-bmv/calendario-de-dias-festivos).

## Qué necesitas hacer

Para probarlo, ejecuta la vista previa del apéndice. El resultado muestra las
fuentes y los pasos previstos. No hace falta aprobar otra vez el calendario.

**Criterio aprobado el 21 de octubre:** exigir el núcleo obligatorio y permitir
contexto complementario pendiente cuando no se utilice. El control global ya
está implementado para comprobar esa selección, sus dependencias y los recibos
reales disponibles. No declara una ronda lista cuando faltan pruebas.

En la **mensual**, el núcleo cubre el tráfico de Aeroméxico, Volaris y Viva;
pasajeros y mercado de la autoridad aeronáutica mexicana (AFAC), rutas
México–Estados Unidos de la oficina estadística de transporte estadounidense
(BTS), tráfico de los grupos aeroportuarios, AICM y AIFA; contexto macroeconómico,
cotizaciones y noticias. Se conserva el periodo propio de cada fuente: AFAC/BTS pueden tener
rezago frente al mes corporativo. No se promete información todavía no publicada.

En la **trimestral**, el núcleo cubre los reportes financieros de las tres
aerolíneas para el mismo trimestre, contexto macroeconómico y cotizaciones.
Aerocivil sigue requerido en su alcance trimestral; GDELT sigue requerido en
noticias mensuales. Sus dos bloqueos actuales siguen impidiendo declarar listo
el calendario. Un paquete financiero individual puede prepararse sin declarar
completa la ronda; Industria necesita sus tres insumos compatibles.

Los comparables secundarios y el contexto adicional pueden quedar pendientes
sin bloquear el núcleo. **Si se usa uno de sus datos para un resultado, debe
validarse antes de incorporarlo**, aunque su frecuencia habitual sea otra.
No se sustituye automáticamente una fuente por otra: compartir empresa,
moneda o nombre de métrica no prueba que midan lo mismo. Aena queda opcional.
H.10, la referencia cambiaria de la Reserva Federal estadounidense, se presenta
por separado cuando falta el tipo de cambio FIX de Banxico. No lo reemplaza
como dato FIX ni completa inflación o tasa de interés.

**Efecto de la aprobación:** autoriza implementar y probar esta regla de aceptación.
No aprueba datos nuevos, publicaciones ni ejecuciones automáticas. La consecuencia
de negocio es permitir un núcleo completo con contexto secundario pendiente,
siempre visible con su fecha y alcance. La aceptación de una ronda sigue bloqueada mientras falten insumos o pruebas.
La clasificación exacta está en el
[apéndice técnico](#política-mínima-aprobada).

## Preparación comprobable del calendario

La continuación del 21 de octubre distingue **herramienta probada**, **original
real comprobado** y **fuente disponible para el siguiente lote**. La matriz de
los 42 productos conserva el alcance histórico y la revalidación nueva por
separado: [matriz de preparación](referencias/source-updates-20261021/readiness-matrix.json).
No convierte la existencia de Gold ni una prueba con fixtures en captura real.

| Prioridad | Evidencia real de esta continuación | Pendiente que limita el siguiente lote |
|---|---|---|
| Viva tráfico | Tras autorización específica del dueño, un GET al PDF oficial BMV de septiembre de 2026 respondió 200. Se extrajeron 24 observaciones: cuatro métricas, tres segmentos y año actual/comparativo; linaje completo y replay idéntico. La regresión 2021 conserva su formato distinto. | Septiembre queda comprobado como candidato, sin activar. Otros meses/ediciones requieren su documento y validación; el formato 2026 usa millas y miles de pasajeros reservados, no las unidades del original 2021. |
| Aerocivil | Metadata y consultas oficiales HTTP 200. Diez filas crudas, ocho bajo códigos literales S/I, 347 movimientos; baseline con ocho filas iguales. Disponibilidad acotada: julio de 2026 para AMX/SLI. El diccionario de columnas oficial coincide exactamente con la metadata del mismo conjunto. | Las definiciones no incluyen equivalencias de códigos. Sin aclaración primaria de `jh8x-n6h6` no se traduce S/N/I ni se aprueba atribución. Julio presente no prueba mes completo. |
| GDELT | Dos consultas iniciales 503. El reintento mensual posterior respondió 200 con 164 artículos, pero 14 tienen primera observación en octubre de México y el validador rechazó el lote de septiembre. Una consulta diagnóstica reducida recibió 429. Se conservan todos los cuerpos y recibos. | No hay candidato mensual válido. Se detuvieron las peticiones tras 429; no atribuir una caída general, inferir cero noticias, filtrar silenciosamente fechas o sustituir por RSS. |
| Perfiles curados | Extracción candidata de unidades y entidades por edición desde originales primarios; el detalle y las referencias de códigos se verifican aparte. | Las decisiones de comparación y elegibilidad no se deducen de una extracción. Matriz financiera, operadora y año fiscal permanecen separados. |

Para considerar un lote listo para revisión se exigen criterios medibles:

1. Cada tarea tiene producto, entidad cuando corresponde, periodo, corte, adaptador,
   insumos y condición requerida u opcional explícitos. El preflight completo
   rechaza pasos, dependencias o controles incompatibles **antes** de capturar.
2. Cada captura acredita URL real, HTTP válido, cuerpo, manifiesto, sidecar y SHA;
   una retención se rotula como tal. Último disponible, validado y publicado son
   tres campos separados. Publicación y rezago desconocidos quedan nulos.
3. Silver y Gold candidatos pasan contrato, grano, unidades, cobertura y linaje
   exacto del alcance solicitado. Un faltante sigue N/D; un código literal sin
   leyenda y un mes incompleto conservan esa condición pendiente.
4. La reproducción offline de los mismos originales es idéntica. El baseline es
   explícito y fijado por hash; se cuentan altas, bajas, cambios y filas iguales.
   El recibo y su corte son inmutables; un byte alterado bloquea la reproducción.
5. Un fallo de fuente o validación conserva el último candidato aceptado y sus
   recibos. No publica ni transforma un HTTP 200 con error en ausencia de datos.
   Los reintentos siguen el máximo de dos reprogramaciones ya definido.
6. El calendario usa días bancarios mexicanos verificados para el año, en
   America/Mexico_City. La trimestral exige trimestre cerrado y tres reportes
   realmente publicados después del cierre; una llamada o anuncio no los suple.
   Un año sin festivos verificados bloquea el cálculo.
7. La prueba en seco muestra los destinos y cero disparadores instalados. La
   ejecución candidata y su revisión no activan calendarios, noticias ni nuevas
   tesis. Las tesis 2T26 de Viva, Volaris e Industria ya aprobadas y publicadas se
   conservan; las versiones nuevas mantienen su aprobación independiente.

La muestra mensual sigue siendo 15/oct, 17/nov y 15/dic de 2026. La fecha
trimestral nula en la muestra sin `--releases` significa **sin documentos de
release suministrados a esa prueba**, no que los emisores no hayan publicado.
No se fija una fecha futura con información inventada ni se extrapola 2027.

### Detalle técnico de la continuación

Viva se selecciona con `recipe --product viva_traffic --output selection
--catalog-file <catalogo-real.html> --period <mes>`. El selector aplica la política
antes de HTTP. El dueño autorizó añadir **únicamente `bmv.com.mx`** a
`viva_ir.allowed_hosts`; no se añadió el host S3 ni se siguieron redirecciones
fuera de la política. El lector `retained --product viva_traffic`, rol `pdf`,
construye `fact_viva_monthly_source_metrics` candidato. La edición septiembre de
2026 conserva pasajeros reservados en miles, ASM/RPM en millones de millas y
ocupación de itinerario. Excluye acumulados de la salida mensual y conserva su
comparativo de 2025. El original histórico 2021 conserva ASK/RPK en kilómetros.
No armoniza las unidades silenciosamente ni confunde ocupación de itinerario
con el cociente RPM/ASM total que incluye chárter. Fecha documental 9/oct y
rezago documental nueve días; publicación inicial, hora y rezago de publicación
siguen desconocidos. [Original oficial](https://www.bmv.com.mx/docs-pub/eventemi/eventemi_1594478_1.pdf).

Aerocivil añade `recipe --availability --period 2026M07`, que consulta el máximo
mes del año para AMX/SLI, y el modo `availability` que verifica su recibo.
`certify --baseline baselines/<anterior.parquet>` fija la comparación de filas
y vuelve a comprobarla en `--check`. No toma la fecha de actualización global del
dataset como fecha de primera publicación mensual.

La investigación adicional identifica **el mismo recurso**, no otro de nombre
parecido: `jh8x-n6h6`, tabla y grupo de publicación `20263639`, propietario
`aba2-n32i` (DATOS ABIERTOS AEROCIVIL), procedencia oficial. Sus filas llevan
actualización global `2026-08-20T21:27:45Z`; esa fecha no es primera publicación
de julio. `resourceName=operaciones-aereas-acumulado-2025` es una etiqueta y no
acredita versión ni cobertura anual. La versión examinada se fija por captura
y SHA, porque el proveedor no expone un número de edición en esos metadatos.
El [diccionario exacto de columnas](https://www.datos.gov.co/api/views/jh8x-n6h6/columns.json)
(HTTP 200, SHA `49f54fefa6b4b6263596f0a8f701379acea2a99c19933c71f7d965bf2f47cc4b`)
coincide con `columns` de la
[metadata del mismo ID](https://www.datos.gov.co/api/views/jh8x-n6h6.json).
Describe campos, pero no desarrolla `TIPO_VUELO` G/M/N/S/X ni `TRAFICO` I/N.
Son valores observados, no una leyenda. Tampoco enlaza un diccionario adjunto
con esas equivalencias. Las búsquedas oficiales no localizaron una leyenda
atribuible al ID; no prueban que no exista. No se reutiliza la de otro conjunto
ni se elude el desafío de la portada. EMPRESA y EXPLOTADOR son derivados del
callsign y matrícula; el nombre del campo no acredita por sí solo una unión
jurídica independiente con la aerolínea.

GDELT tiene su comando separado, porque primera observación no es publicación:

```bash
python -m src.source_updates.gdelt recipe --period 2026M09 --as-of 2026-10-21T00:35:00Z
python -m src.source_updates.gdelt certify --workspace tmp/source-updates/<gdelt> --period 2026M09 --as-of <corte-original> --collection <id> --dry-run
```

Después de `collect`, `--execute` verifica el original y produce JSON Silver/Gold
aislados bajo un contrato específico; `--check` repite sin red ni escrituras.
Un recibo de captura fallido bloquea antes de crear esos outputs. Se deduplica URL
canónica y primera observación, conservando todos los punteros y metadatos; no se
descargan artículos ni imágenes. El tope de 250 resultados y los días observados
se declaran; ni siquiera una respuesta vacía prueba cobertura mensual completa.
Publicación/evento permanecen nulos y el candidato no alimenta el archivo mensual
de noticias. Las pruebas con respuestas sintéticas son **pruebas de contrato**;
los recibos históricos de 503 se conservan aunque cambie la disponibilidad.

La comprobación posterior contrastó la
[guía oficial DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
y su [actualización de mayo de 2018](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/).
La sintaxis seleccionada coincide: OR entre paréntesis, `mode=artlist`,
`format=json`, `sort=datedesc`, máximo 250 y límites UTC explícitos de septiembre
de México. La guía inicial decía tres meses; la actualización amplió el
horizonte y mantuvo una ventana de tres meses para salidas no temporales. No
se confunde ese anuncio histórico con una garantía de disponibilidad actual.
La ventana solicitada aquí es un mes. El límite de resultados no acredita
cobertura completa ni paginación.

El HTTP 200 posterior contiene 164 artículos, de los cuales 150 quedan en
septiembre y **14 fuera del mes solicitado** al convertir primera observación a
México. La normalización lo rechaza sin crear Silver/Gold. Además, la captura
diagnóstica quedó rotulada `current`, y la certificación exige el mes exacto:
ese segundo control también bloquea. No se cambia el recibo ni se filtran filas
para hacerlo pasar. El diagnóstico reducido siguiente devolvió 429 con la
instrucción explícita de una petición cada cinco segundos. No se hicieron
más llamadas. El recolector ahora limita GDELT a una cada **seis segundos por
proceso** y omite nuevas peticiones a una fuente tras 429 en la misma captura.
Es un control de un proceso, no una cuota distribuida: usar un solo runner
autorizado y no lanzar capturas concurrentes. No se acredita extracción válida
del periodo ni se afirma una interrupción general del servicio.
La certificación ejecutada y su replay devuelven un código de proceso distinto
de cero cuando no pasan las comprobaciones, incluido un resultado vacío:
`empty_result_unproven_coverage` no acredita ausencia de noticias. Generar una
receta o una vista previa continúa siendo una operación sin captura.
Los SHA, consultas, recibos, límites y rechazos están en
[la evidencia agregada existente](referencias/source-updates-20261021/verification.json)
y sus originales en el borrador privado #38.

El comprobador `src.source_updates.readiness` reúne candidatos ya construidos
con adaptadores distintos, sin repetir capturas. Después de restaurar los
candidatos del paquete privado según el apéndice, la receta de ejemplo prueba
AFAC julio y finanzas Aeroméxico 2T26, conservando sus cortes originales:

```bash
python -m src.source_updates.readiness --recipe config/source_update_readiness.example.json --workspace tmp/source-updates/readiness-ejemplo --dry-run
python -m src.source_updates.readiness --recipe config/source_update_readiness.example.json --workspace tmp/source-updates/readiness-ejemplo --execute
python -m src.source_updates.readiness --recipe config/source_update_readiness.example.json --workspace tmp/source-updates/readiness-ejemplo --check
```

`--execute` aquí significa **verificación offline y recibo de ronda**. Las tareas
requeridas se declaran tanto en `required_items` como en cada elemento, antes
de ejecutar. Un fallo requerido bloquea la ronda conservando los éxitos previos;
los opcionales se enumeran. El recibo liga fuentes, salidas y código de cada
comprobador. `--check` conserva corte, condiciones y permisos exactos, sin
escrituras. El resultado lista productos no ejercitados y distingue listo para
revisión de listo para automatizar. La muestra no es una ronda actual completa
de los 42 productos. Curación conserva su comprobador dedicado, con emisores
y periodos fiscales propios.

Una reproducción numérica de Aerocivil puede pasar con la condición de leyenda
pendiente; eso no acepta su significado ni su cobertura. `ready_for_review`
no es un permiso de calendario. Cada receta define sus tareas requeridas: el
comprobador no impone una política global que incluya Aerocivil y GDELT en todas
ellas. Antes de usarlo como control de aceptación del calendario se necesita
esa política explícita y resolver ambos bloqueos. Los indicadores
`ready_for_calendar_incorporation` y `ready_for_automatic_execution` permanecen
falsos incluso en la receta numérica exitosa.

La política global aprobada se implementa en `global_readiness`, separada de esa
reproducción parcial. Impone la clasificación del apéndice y conserva pendientes
de fuente y adaptadores completos; una tarea local exitosa no la sustituye.
Los controles de reportes y festivos siguen vigentes. Aerocivil/GDELT continúan
bloqueando incorporación y no se presume equivalencia entre IR, SEC y BMV.

La revisión final corrigió dos fallos de contrato: una certificación GDELT
vacía ya no devuelve éxito de proceso y los replay H.10, tráfico Aeroméxico,
Aerocivil y retenidos exigen el `effective_as_of` exacto del recibo. Pasaron
204 pruebas afectadas offline, incluidas negativas antes de recalcular.
La comprobación de originales históricos mantuvo 2.730 filas AFAC, 20 de
finanzas Aeroméxico, 24 Viva y ocho Aerocivil con su leyenda aún pendiente;
GDELT siguió bloqueado. No hubo captura nueva ni reescritura de sus recibos.

## Riesgos

La política recomendada permitiría avanzar con el núcleo y conservar contexto
secundario antiguo o pendiente, claramente identificado. No significaría que
los 42 productos estén actualizados. Un fallo de un insumo obligatorio seguiría
bloqueando la ronda; un fallo de una dependencia adicional impediría incorporar
su resultado. Aprobar el alcance no resuelve la falta de leyenda de Aerocivil,
la captura inválida de GDELT ni un formato nuevo que el lector no admita.

Capturar un archivo no demuestra que sus cifras se hayan incorporado. La
herramienta comprueba el periodo que aparece en las filas. Si el formato nuevo
supera el parser disponible, lo deja pendiente. El adaptador AFAC candidato admite el formato de boletines 2026 y requiere
todos los PDF y fletamento de sus meses. Otros años y formatos corporativos
requieren revisión.
BMV registra miembros ZIP sin red y conserva los catálogos históricos. La cadena
de selección nueva solo admite trimestres; los años se rechazan antes de la
captura hasta contar con comprobador anual. Los anuales retenidos se conservan.
Las notas AFAC de cada página acompañan únicamente a las filas regulares de su
mes y mercado; no se trasladan entre doméstico e internacional ni a fletamento.
La cadena
completa de parseo y validación ya permite reconstruir Gold candidato. Los
periodos se derivan de las observaciones, sin corte fijo de agosto; la tasa
objetivo conserva unidad `percent` y su valor original. El puente de linaje se
reconstruye y se contrasta con Bronze. Algunas incidencias de calidad heredadas
solo tienen declaración; se reportan y no pasan como trazabilidad documental.
La validación de una tabla no certifica todas las fuentes de una familia.

Un error de acceso no significa que no exista un reporte. Una fecha desconocida
permanece sin fecha. Las noticias pueden tener cobertura parcial del mes.
Los datos retenidos de AeroDataBox se conservan; esta entrega no los consulta
ni modifica.

## Apéndice técnico

La implementación vive en [`src/source_updates/`](../src/source_updates/).
Las instrucciones están en la [skill del coordinador](../.agents/skills/airline-update-coordinator/SKILL.md)
y el [contrato común](../.agents/skills/source-updates-common.md). El mapa
operativo cubre las 29 claves del catálogo en 42 productos, con brechas
explícitas y comprobación de cambios en el catálogo. No sustituye los contratos.

### Política mínima aprobada

**Estado: aprobada; control global implementado, sin activación.** Las asignaciones
siguientes concretan el alcance ya descrito en las secciones de fuentes centrales,
complementarias y familias de métricas. No añaden métricas, modelos o productos.
El catálogo mantiene sus 42 productos y frecuencias. Base verificable:
[`PRODUCTS`](../src/source_updates/catalog.py), [catálogo y prioridades](../config/source_catalog.yaml),
[contratos Silver](../config/silver_schema_contracts.yaml),
[contratos Gold](../config/gold_schema_contracts.yaml) y
[diccionario de métricas](diccionario-datos.md).

**R** significa requerido para aceptar el núcleo completo. **C** es dependencia
condicional: pasa a ser obligatoria para el resultado que la utiliza. **O** es
complementaria: no bloquea el núcleo, pero cualquier dato suyo incorporado debe
pasar los mismos controles. Esta última regla también rige fuera de su cadencia
habitual; por ejemplo, un código aeroportuario nuevo requiere una referencia
válida aunque aparezca durante la ronda mensual. No se admiten resultados sin
sus dependencias para evitar un bloqueo.

Mensual: 16 productos R y cinco C en el plan actual de 21 tareas.

| Productos | Clase aprobada | Resultado existente que deben sustentar |
|---|---|---|
| `am_traffic_ir`, `volaris_sec`, `viva_traffic` | R | Tráfico mensual de cada grupo, capacidad y ocupación según lo reportado. Separar pasajeros reservados/transportados, millas/kilómetros, itinerario/chárter. Un reporte de tráfico no satisface finanzas. |
| `afac_carriers`, `afac_airports` | R | Pasajeros por empresa/mercado y estadísticas aeroportuarias, con sus granos y ediciones propios. El total del aeropuerto no se atribuye a una aerolínea. |
| `bts_segments` | R | Pasajeros, asientos y operaciones observadas México–EEUU, por operador, segmento y clase. No representa la red mundial ni pasajeros de itinerario. |
| `gap_traffic`, `asur_traffic`, `oma_traffic`, `aicm_traffic`, `aifa_traffic` | R | Tráfico de aeropuertos y grupos; separar México de otros países y grupos de aerolíneas. |
| `banxico`, `fuel`, `equities` | R | FIX, INPC y tasa por separado; referencia EIA de combustible; cinco series bursátiles existentes con identidad/moneda y ajustes. No son costos contratados ni ingresos de las aerolíneas. |
| `rss`, `gdelt` | R | Metadatos de noticias dentro del corte/consulta declarados. No promete todo lo ocurrido en el mes; una respuesta vacía sin cobertura acreditada o fechas inválidas no satisface GDELT. |
| `am_sec` | C | Si una métrica del lote o su revisión depende de su anexo regulatorio. No obliga a descargar una segunda copia idéntica de un documento ya verificado. No se presume equivalente al PDF IR. |
| `afac_countries`, `afac_margins` | C | Si se actualizan resultados por país o marginales de rutas/empresas. Países conserva acumulados; las marginales exigen misma edición. No autoriza recalcular estimaciones ni modelos. |
| `h10` | C | Referencia USD/MXN rotulada cuando no se dispone de FIX; condiciones específicas abajo. |
| `derived` | C | Si se recalcula una fórmula existente con insumos nuevos validados. No autoriza entrenamiento, forecasts ni fórmulas nuevas. |

Trimestral: siete productos R, diez C y diez O en el plan actual de 27 tareas.

| Productos | Clase aprobada | Resultado existente que deben sustentar |
|---|---|---|
| `am_financials`, `volaris_sec`, `viva_financials` | R | Expediente financiero/operativo primario de las tres entidades para el trimestre solicitado: magnitudes ya definidas, monedas, escalas, balances y flujos separados, y notas de preliminar/no auditado. Un parser de una edición anterior no acredita otra nueva. |
| `banxico`, `fuel`, `equities` | R | Contexto y agregados trimestrales de las mismas series mensuales, con días cubiertos. No fuerza que una serie de inflación o tasa tenga observación diaria. |
| `aerocivil` | R | Movimientos y atribución del alcance colombiano declarado, con leyenda oficial del conjunto exacto. No pasajeros, red completa ni cobertura trimestral inferida de un mes. Sigue bloqueado. |
| `am_sec`, `bmv_xbrl` | C | Si aportan una partida, una definición o una revisión necesaria para las métricas del expediente. Prioridad de fuente no es equivalencia. Sin prueba de la métrica faltante, el resultado afectado sigue bloqueado. |
| `h10` | C | Referencia cambiaria separada ante falta de FIX; no cierre contable sustitutivo. |
| `aicm_slots`, `airports_reference` | C | Si se incorpora programación o se necesita un código/cruce de aeropuertos. Los slots no acreditan vuelos realizados. Una versión histórica válida puede sustentar un dato histórico, sin probar actualidad. |
| `dictionary`, `peer_profiles`, `curated_context`, `derived` | C | Si se usan sus versiones, atributos, eventos o cálculos en resultados nuevos. Exigen padres/versión válidos; no aprueban tono, equivalencia de emisores/operadores, confianza o impacto ni cambian tesis existentes. |
| `aena` | C | Sigue opcional para el núcleo. Si se incluye un resultado de España, requiere sus exportaciones válidas y controles específicos; no basta con un boletín agregado. Sin nuevas credenciales ni login automatizado. |
| `delta_sec`, `ryanair_sec`, `ryanair_ir`, `anac`, `caa`, `am_routes`, `oma_routes`, `colima`, `aifa_roster`, `iasa` | O | Comparables y contexto acotados. Una ausencia no bloquea el núcleo financiero mexicano; un dato utilizado sí exige validación y no convierte año fiscal, anuncio, puntualidad o categoría de país en otro indicador. |

`news_errors` queda excluido de ejecución (`never`): los errores se conservan
para auditoría, no cuentan como noticias. La combinada conserva la unión de
obligaciones mensuales y trimestrales con sus periodos distintos; no omite una
para evitar un fallo. Noticias se captura en la mensual, no abre otra ronda
trimestral. Aerocivil/GDELT mantienen su condición requerida y sus bloqueos
impiden aceptar el calendario; esta política no los convierte en opcionales
ni cambia sus frecuencias.

**Condiciones de aceptación y alternativas.**

1. Se comprueba disponibilidad de los productos de la cadencia y se registran
   pendientes; revisar no promete descargar ni actualizar todos. El mes objetivo
   corporativo es el anterior. Autoridades y otras series conservan el último
   periodo publicado que se pueda acreditar al corte, con su rezago visible.
   Una comprobación de Gold o un SHA retenido no acredita disponibilidad actual.
   Un fallo de acceso no equivale a «sin novedades» y no satisface un R.
2. No se reduce el alcance para hacer pasar el núcleo. Se conservan entidad,
   métrica, universo, moneda, escala, periodo, versión y linaje por fila.
   Un N/D permitido por el contrato y respaldado por el documento permanece N/D;
   un insumo faltante de una métrica requerida no se inventa ni se vuelve cero.
   Para Industria deben existir los tres insumos compatibles; las razones se
   ponderan según sus denominadores, sin promedios simples.
3. No se registra ninguna equivalencia general entre IR, SEC y BMV. Una copia
   del mismo original con bytes/SHA verificados puede evitar capturar otra vez
   ese original; no prueba equivalencia entre un PDF y un XBRL distintos. Una
   alternativa futura necesita prueba por métrica de entidad, definición,
   universo, periodo, unidad, moneda, versión y reconciliación de valores. Si
   falta esa prueba, no se sustituye. El orden de `priorities` solo selecciona
   entre filas ya validadas; no aporta esa prueba.
4. H.10 conserva `usd_mxn`, serie `H10/H10/RXI_N.B.MX` y su calendario propio;
   FIX conserva `usd_mxn_fix`, serie `SF43718`. No se empalman ni se renombran.
   H.10 no satisface FIX, `SP1`/INPC ni `SF61745`/tasa, ni una conversión contable
   primaria que exija FIX. Si faltan estos insumos requeridos, el núcleo sigue
   pendiente aunque exista contexto H.10 válido. Esto sigue la
   [limitación del catálogo](../config/source_catalog.yaml) y el
   [lector H.10](../src/source_updates/h10_gold.py).
5. Aena requiere exportaciones con fuente, fecha, periodo y SHA verificados.
   Compañía×aeropuerto y mercado×aeropuertos son granos distintos; no existe un
   cruce compañía×ambos extremos en los cuatro originales revisados. Puede
   conservarse el núcleo sin ese extra; no puede incorporarse el extra inválido.
6. Se mantienen los tres reportes reales del trimestre cerrado, el calendario
   bancario verificado, el corte inmutable, los checks Bronze/Silver/Gold,
   revisiones y deduplicación, y el recibo offline reproducible. Una propuesta de
   fecha o una receta local exitosa no acredita una ronda global. El comando global aplica ese control; un recibo local válido por sí solo
   sigue sin certificar disponibilidad. La bandera automática permanece falsa
   y ningún disparador se instala.

Las condiciones anteriores se apoyan en los [checks de candidato](../src/source_updates/checks.py),
la [precedencia existente](../src/transform/stage6_facts.py),
el [constructor macro](../src/transform/stage6_macro.py), los
[lectores de originales retenidos](../src/source_updates/retained.py) y la
[reproducción de ronda](../src/source_updates/readiness.py). Se reutilizan sin reinterpretar sus recibos históricos.

### Certificación de series retenidas (22 de octubre)

`series_candidate` reconstruye desde originales físicos, sin red, los tres
productos requeridos `banxico`, `fuel` y `equities`. Exige todas sus entradas:
tres CSV SIE; un XLS EIA; o cinco JSON Yahoo y el original SEC que prueba la
identidad y fecha de inicio de AERO. No acepta una cotización o FIX como producto
completo. La retención conserva fecha de captura, URL, manifiesto, sidecar y SHA.
El descargador y sus recetas siguen separados: certificar un original retenido
no equivale a comprobar hoy la fuente ni a recolectar una edición nueva.

El lector estricto rechaza fechas repetidas, N/D sin interpretación documentada,
valores inválidos, unidades o entidades distintas y meses ausentes. No elimina
filas corruptas ni rellena ceros. Banxico conserva la inflación mensual y la tasa
con su calendario nativo. EIA conserva dólares por galón; no es costo contratado.
El trimestre exige los tres meses y calcula promedio sobre cada observación
nativa, sin promediar los promedios mensuales. Cierre es el último valor observado,
no una cotización inventada para el último día natural.

Las cinco cotizaciones mantienen su historia desde la solicitud canónica de
2015, o desde la salida a bolsa de AERO del 6/nov/2025. Se comprueban la primera
observación retenida y todos los meses de contexto. Rendimientos diarios,
rendimiento del año y volatilidad se calculan antes de recortar la ventana.
Eso evita perder el día anterior o reiniciar el año al comienzo del trimestre.
No se acredita por ello que el proveedor contenga cada sesión bursátil esperada.

Las salidas usan contratos Silver/Gold existentes y linaje de cada registro:
`fact_macro` con dimensión de periodo, o `fact_market_data` con emisores. AERO
requiere también su original SEC físico en el puente. El recibo fija código,
contratos, fuentes, corte, salidas y baseline explícito si se aporta. Ese baseline
es la tabla Silver nativa: Banxico/combustible por serie y fecha; cotizaciones
por ticker y fecha, incluidos precios, ajustes y volumen. No se comparan solo
promedios Gold que puedan ocultar cambios diarios compensados. `--check`
reconstruye y compara sin escribir; cualquier diferencia bloquea. Una edición
nueva requiere una carpeta nueva. La falta de baseline se declara, no se presenta
como ausencia de revisiones.

```bash
# Seleccionar únicamente originales ya retenidos; tres roles exactos para Banxico.
uv run python -m src.source_updates.series_candidate retain --product banxico --workspace tmp/source-updates/banxico-sep --source-root <Bronze> --original SF43718=<CSV-FIX> --original SP1=<CSV-INPC> --original SF61745=<CSV-tasa> --dry-run
# Tras comprobar la selección, --execute copia esos originales sin descargarlos.
uv run python -m src.source_updates.series_candidate certify --product banxico --workspace tmp/source-updates/banxico-sep --period 2026M09 --as-of 2026-10-22T12:00:00-06:00 --retention <ID> --dry-run
# En carpeta retenida: sustituir --dry-run por --execute y después por --check.
# Para trimestre: --period 2026Q3 en otra carpeta; combustible usa workbook=<XLS>.
# Equities exige AERO,VLRS,RYAAY,DAL,ICAGY e identity=<original-SEC>, sin subconjuntos.
```

Prueba real offline con los originales ya capturados el 19 de octubre (SEC de
identidad capturado el 20 de agosto), código `22517c4d`, corte explícito
`2026-10-22T00:00:00Z`. El lote de seis tareas de
`retained_round` pasó reconstrucción, contratos, linaje por registro y replay
exacto. Después se comprobó el enlace documental del verificador global:

| Producto | Septiembre 2026 | Trimestre julio–septiembre 2026 |
|---|---|---|
| Banxico | 21 FIX, 1 INPC y 30 tasas; 6 agregados Gold | 65 FIX, 3 INPC y 91 tasas; 24 agregados Gold, incluidos meses |
| EIA | 21 observaciones; 2 agregados Gold | 64 observaciones; 8 agregados Gold, incluidos meses |
| Cotizaciones | 21 fechas por cada uno de los cinco tickers; 105 registros Gold | 64 fechas por ticker; 320 registros Gold |

La historia Silver bursátil conserva 12.037 filas para calcular los retornos.
Los recibos están en las carpetas locales ignoradas
`tmp/source-updates/series-batch-proof-20261022-22517c4d/<producto>-<periodo>/receipts/`;
no se copian originales al repositorio público. El resumen local único
`tmp/source-updates/series-batch-proof-20261022-22517c4d-summary.json` tiene SHA-256
`c94bd08d3ca75850ae34c91c2c2fc7ea1736da54828c15875dcec266c353a09b`.
Además, tres candidatos trimestrales compararon sus tablas Silver contra una
copia de la misma edición retenida: 159 observaciones Banxico, 64 EIA y 12.037
cotizaciones sin diferencias. Se fijaron los hashes de baseline y se reprodujo
cada recibo. Es una prueba de comparación/replay, no evidencia de que el
proveedor no haya publicado revisiones posteriores.
Estos conteos describen observaciones retenidas, no sesiones esperadas ni prueba
de fuente actual. No se consultaron fuentes ni se procesó/publicó la edición
financiera 3T26 de la tarea separada.

En `readiness` o `global_readiness`, elegir `adapter=series`, producto exacto,
periodo mensual/trimestral y el ID de retención. `retained_round` selecciona
automáticamente ese certificador para los tres productos, también al mezclar
meses y trimestres en un lote. El comando individual antiguo `retained`
rechaza estos tres productos y remite al certificador integral. El control global
sigue bloqueado por productos requeridos pendientes, disponibilidad, releases y
festivos no acreditados; no cambia ninguna clasificación R/C/O.

### Control global ejecutable

```bash
uv run python -m src.source_updates.global_readiness --recipe config/source_update_global.example.json --workspace tmp/source-updates/global-preview --dry-run
# Después de seleccionar candidatos reales y completar la receta:
uv run python -m src.source_updates.global_readiness --recipe tmp/receta-global.json --workspace tmp/source-updates/global-review --execute
uv run python -m src.source_updates.global_readiness --recipe tmp/receta-global.json --workspace tmp/source-updates/global-review --check
```

La receta de ejemplo deja tareas y reportes vacíos a propósito: la vista previa
lista los 23 productos/periodos obligatorios ausentes de la combinada, conserva
`monthly_date=2026-10-15`, `quarterly_date=null`, cero llamadas y ninguna
activación. Es un ejemplo de bloqueo, no evidencia de extracción.

`core_ready` verifica los requeridos de la cadencia y sus dependencias;
`requested_bundle_ready` exige además todos los C/O utilizados. Un extra inválido
no se incorpora ni hace pasar el paquete; un núcleo independiente válido conserva
su estado. `ready_for_calendar_incorporation` exige también Aerocivil/GDELT,
disponibilidad acreditada, festivos y reportes correspondientes. Ningún resultado
activa ejecución o publicación. El CLI devuelve 1 en una ejecución/replay bloqueado;
el modo seco devuelve 0 con estado `planned_not_executed` y bloqueos visibles.

Cada tarea declara `id`, `product`, `cadence`, `period`, `used`, `depends_on`,
`adapter`, `workspace`, `receipt_id` y `candidate_as_of`. Los periodos objetivo
`monthly_period` y `quarterly_period` son contextos separados y cerrados. El
campo opcional `source_period` conserva el mes nativo rezagado de AFAC/BTS/AICM/AIFA
o un mes de Aerocivil dentro de su trimestre: no transforma ese mes en cobertura
trimestral ni acredita última disponibilidad. Las tareas financieras primarias
no aceptan otro trimestre. Una referencia usada fuera de cadencia se revalida
sin adquirirla de nuevo. Las dependencias transitivas deben estar usadas y
validadas; ciclos, duplicados, sustituciones de producto y reducciones de
métricas/filtros se rechazan. No hay interfaz para aportar resultados aprobados
por el usuario como si provinieran de un verificador.

Los adaptadores completos admitidos son los mismos de `readiness`: originales
retenidos, series macro/mercado (`series`), tráfico IR Aeroméxico, H.10, Aerocivil y GDELT. Un producto sin ese
adaptador se declara `unsupported` y bloquea si se utiliza. Los checks genéricos
existentes siguen sirviendo para comprobar tablas, pero no certifican todas las
métricas obligatorias de un producto. Esto evita dar por Banxico completo una
prueba de FIX que omita INPC/tasa, o por mercado completo una sola cotización.
**No todos los R disponen todavía de un adaptador global completo.** La cobertura
de herramientas de la matriz no debe confundirse con esa certificación.

Los reportes centrales añaden a los campos existentes `task_id` y
`source_sha256`; deben corresponder a la entidad/trimestre del candidato y a un
original contribuyente de su linaje verificado, con URL y SHA idénticos. La fecha
de publicación sigue siendo una afirmación explícita revisada contra el documento,
no se deduce de la descarga. Anuncios y llamadas no sirven. La combinación
rechaza fechas separadas por más de siete días naturales. El año 2027 sigue sin
festivos acreditados y bloqueado. No se crea ninguna fecha de release.

El recibo inmutable congela receta, política, código reutilizado, contratos,
catálogo, calendario y resultados/fingerprints de los candidatos. El replay
repite los verificadores reales con red bloqueada y comprueba igualdad; nunca
recolecta ni escribe en los candidatos. Un escritor crea solo el recibo global
en una carpeta nueva. Un cambio de esos insumos exige otro recibo.

En el head de implementación `70edaeda` pasaron 172 pruebas focales, incluidas
76 independientes de política y 32 GDELT. El replay real comprobó 2.730 filas AFAC,
24 de Viva y ocho numéricas Aerocivil sin aceptar su semántica; el recibo GDELT
seleccionado seguía incompleto. Los 41 archivos originales/candidatos quedaron
idénticos, con cero red y sin declarar lista la ronda. El [seguimiento del PR151](https://github.com/salvamalfa/aeromexico-tracker/pull/151#issuecomment-6323453408)
conserva el SHA del recibo y distingue esa evidencia de CI/revisión final.

Las pruebas positivas de la decisión usan resultados internos sintéticos para
probar el contrato; **no acreditan fuentes reales**. La extracción real sigue
siendo la evidencia de la matriz. Los verificadores actuales conservan
`latest_source_availability_verified=false`: hasta añadir prueba de descubrimiento
oficial por producto, un original retenido no hará pasar esa puerta. Aerocivil
permanece sin aceptación semántica y GDELT sin candidato mensual válido.

### Prueba en seco

Desde la raíz del repositorio, con las dependencias instaladas:

```bash
uv run python -m src.source_updates calendar --start 2026-10 --months 3 --quarter 2026Q3 --as-of 2026-10-18T12:00:00-06:00
uv run python -m src.source_updates plan --round combined --quarter 2026Q3 --as-of 2026-10-18T12:00:00-06:00
uv run python -m src.source_updates round --recipe config/source_update_round.example.json --workspace tmp/source-updates/prueba --dry-run
uv run pytest -q tests/test_source_update*.py tests/test_document_lifecycle.py tests/test_pipeline_orchestration.py tests/test_pipeline_route_extension_steps.py tests/test_repo_budgets.py
```

Para que el agente obtenga los sitios y parámetros sin adivinarlos:

```bash
uv run python -m src.source_updates recipe --product fuel
uv run python -m src.source_updates recipe --product fuel --output round --period 2026M09 --as-of 2026-10-18T18:00:00-06:00 > tmp/combustible.json
uv run python -m src.source_updates round --recipe tmp/combustible.json --workspace tmp/source-updates/combustible --dry-run
```

`recipe` consulta el [catálogo operativo por producto](../config/source_update_acquisition.json)
y las constantes de los adaptadores existentes. Ese catálogo enlaza al
[catálogo de instituciones](../config/source_catalog.yaml). Incluye también
procedimientos de descubrimiento, revisiones y bloqueos de las ocho familias.
Los productos `fuel`, `banxico`, `h10` y `equities` emiten recetas candidatas con
parámetros exactos. Los demás muestran su estado real y, cuando corresponde,
una selección de catálogo o descarga; no se ofrecen como ocho procesos
autónomos completos.

Salidas conservadas: [calendario](referencias/source-updates-20261018/calendar.json),
[plan por producto](referencias/source-updates-20261018/plan.json) y
[prueba en seco del lote](referencias/source-updates-20261018/dry-run.json).
La receta es un ejemplo EIA, no una captura realizada ni una ronda completa. La [muestra bursátil nueva](referencias/source-updates-20261019/market-round-dry-run.json) declara cinco GET, hasta 25 llamadas contando redirecciones, cero llamadas pagadas y la evidencia SEC previa requerida.
La muestra anuncia un GET previsto, hasta cinco llamadas contando redirecciones,
cero llamadas pagadas y ningún periodo validado. El modo en seco no escribe.
Para fechar la trimestral, pasar `--releases` con una copia de
[`source_update_releases.example.json`](../config/source_update_releases.example.json)
completada con reportes reales. La plantilla no afirma fechas de publicación.

Validación local: **143 controles focalizados aprobados**. La suite general de
`b9e1d33` pasó **1.524 pruebas y 29 subpruebas**, con 75 omisiones por insumos
locales ausentes o vista previa sin fijar. Ese recibo es histórico de PR137; la propuesta de Gold lleva pruebas y evidencia
propias. Las pruebas unitarias usan muestras controladas.
[Recibo de validación](referencias/source-updates-20261018/validation.json).

Después se ejercitaron fuentes públicas reales, sin publicar sus datos.
EIA se capturó y pasó Bronze y Silver para septiembre: 21 observaciones. El XLS
original contiene datos hasta el 14 de octubre; la receta limita el parseo al
30 de septiembre. Por ello, el último periodo parseado no se presenta como el
último disponible de la fuente. La fecha de publicación sigue sin verificarse.
Del catálogo IR de Aeroméxico se capturó HTML y se extrajeron 69 enlaces; esto
solo acredita descubrimiento, sin certificar reportes nuevos. Ese recibo inicial llegó hasta Silver; la prueba posterior de Gold se describe abajo.
Las recetas generadas también capturaron y procesaron las tres series Banxico:
21 filas FIX, una INPC y 30 de tasa en septiembre. El endpoint H.10 devolvió
contenido vacío para la consulta explícita; quedó bloqueado y no produjo datos.
En ese piloto, su parser solo se había probado con muestras controladas; la
certificación real posterior de H.10 está descrita más abajo. No se sustituyó FIX ni
se rellenaron datos ausentes. Las demás familias conservan límites por producto; no se certifican como rondas completas.
[Evidencia del piloto real](referencias/source-updates-20261018/real-source-pilot.json).

### Reconstrucción aislada del 19 de octubre

La propuesta posterior a PR137 conserva su recibo limpio del commit `f20c244`.
Las correcciones de Gold y los nuevos adaptadores tienen rama y revisión
separadas en [PR141](https://github.com/salvamalfa/aeromexico-tracker/pull/141). Un rebuild público offline pasó los contratos Stage 6 y cuatro
controles Gold de septiembre (EIA, FIX, INPC y tasa). La evidencia posterior por
producto y sus límites está en el [recibo del candidato](referencias/source-updates-20261019/validation.json)
y el [inventario de los 42 productos](referencias/source-updates-20261019/product-coverage.json).
Los 16 pasos offline, 25 controles Stage 6 y 19 controles por producto pasaron.
AFAC llegó a agosto; AICM a agosto y AIFA a julio. Las cinco series bursátiles
llegaron al 30 de septiembre. OurAirports tiene su comprobación de referencia
separada. Eso no acredita ocho familias completas ni periodos nuevos de las
fuentes solo reproducidas desde originales retenidos.

El puente declara 211.074 registros: 209.282 con artefacto y 1.766 mediante
padres; 26 incidencias de calidad carecen de vínculo documental exacto. No se
presentan como trazabilidad documental completa. La prueba negativa rechaza
AFAC septiembre. El historial bursátil añade 140 días/ticker y muestra 9.105
filas con alguna diferencia exacta frente al original retenido; 5.851 cierres
ajustados difieren en más de USD 0,01. Se conserva el [diagnóstico de magnitud](referencias/source-updates-20261019/market-revisions.json),
sin atribuir una causa ni aprobar revisiones automáticamente.

La revisión inicial de PR141 detectó notas de vuelos regulares también presentes
en filas de fletamento. Se corrigió la atribución: las notas PDF solo acompañan
sus propias filas. Se regeneró AFAC y cambiaron únicamente las notas de 296
filas; todos los demás campos quedaron iguales. Los contratos Gold y el puente
volvieron a pasar. [Evidencia de la corrección](referencias/source-updates-20261019/afac-notes-review-fix.json).

No se copiaron insumos privados ni se consultó AeroDataBox.

### Certificación mensual aislada H.10

El comando dedicado `h10` certifica un mes cerrado desde seis originales de la
Reserva Federal: CSV, histórico HTML de México, calendario K.8, definición,
release que explica `ND` y aviso de transición del portal. La prueba de septiembre
de 2026 conserva 22 fechas hábiles: 21 cotizaciones y `ND` el 7 de septiembre.
El 16 de septiembre sí tiene cotización. No se aplica el calendario bancario
mexicano a esta serie ni se exige un número fijo de 21 observaciones por mes.

H.10 expresa **pesos mexicanos por un dólar estadounidense**, par `USD/MXN`.
Es la cotización compradora de mediodía en Nueva York, distinta del FIX de
Banxico. En Silver, `rate_close` conserva su nombre de contrato y contiene la
cotización diaria de mediodía. En Gold, `close` es la última cotización H.10
observada del mes. Ninguno representa un cierre bursátil. El promedio utiliza
únicamente valores observados. `ND` queda
explícito, con valor numérico nulo; nunca se convierte en cero.
[Definición oficial](https://www.federalreserve.gov/releases/h10/about.htm),
[histórico de México](https://www.federalreserve.gov/releases/h10/hist/dat00_mx.htm).

Se comparan todas las fechas, valores decimales y estados entre CSV y HTML.
Son dos representaciones de la misma institución, no dos proveedores
independientes. Fechas duplicadas, faltantes, valores invertidos, unidades o
metadatos incompatibles bloquean la certificación antes de escribir Silver o
Gold. Deben estar todas las fechas de lunes a viernes, incluso las que contienen
`ND`; no se inventan filas. K.8 aporta contexto para un `ND` que ambas fuentes
ya reportan. Distingue la observancia del Board y de los Federal Reserve Banks;
no prueba la causa del faltante ni define un calendario universal de divisas.
Un `ND` en otro día requiere evidencia y revisión adicionales.
[K.8](https://www.federalreserve.gov/aboutthefed/k8.htm),
[definición de ND](https://www.federalreserve.gov/releases/h10/current/default.htm).

La captura oficial del 19 de octubre respondió HTTP 200 en los seis originales.
El histórico HTML declara versión del 13 de octubre y observaciones hasta el
9 de octubre; el CSV consultado termina el 30 de septiembre. Esa versión no
demuestra la primera publicación de septiembre: su fecha y rezago permanecen
nulos. Las revisiones futuras se capturan en otro candidato, sin sustituir los
originales aceptados. Una diferencia entre versiones bloquea el cruce; no se
atribuye automáticamente a un error del proveedor. Los releases archivados no
se revisan, mientras el histórico puede incorporar revisiones.

La alternativa HTML está comprobada para este cruce, con límite de 2 MB
decodificados por respuesta. No se activa como sustitución automática. El aviso
anuncia retirar «Build Your Package» en la semana del 9 de noviembre de 2026 y
una transición posterior; no demuestra que este endpoint CSV deje de responder
ese día. Debe revalidarse antes de otra captura.
[Aviso oficial](https://www.federalreserve.gov/data/data-download-fred-information.htm).

```bash
uv run python -m src.source_updates h10 --period 2026M09 --as-of 2026-10-19T12:00:00-06:00 --workspace tmp/source-updates/h10-prueba --dry-run
uv run python -m src.source_updates h10 --period 2026M09 --as-of 2026-10-19T12:00:00-06:00 --workspace tmp/source-updates/h10-prueba --execute --check-at-completion
uv run python -m src.source_updates h10 --period 2026M09 --as-of 2026-10-19T12:00:00-06:00 --workspace tmp/source-updates/h10-prueba --check
```

La vista previa declara seis GET públicos, hasta 30 solicitudes contando
redirecciones, cero pagadas y cero escrituras. `--from-collection <id>` sustituye
`--execute` para certificar una captura local existente sin red. `--check`
reconstruye sin red y verifica hashes de originales, recibo de captura y las seis
tablas candidatas: dos Silver, `fact_macro`, `dim_period`,
`dim_source_artifact` y `bridge_record_lineage`. Gold contiene solo dos registros
mensuales, promedio y última cotización, con seis artefactos y 12 enlaces
documentales exactos. No construye un trimestre a partir de un mes.

Esta certificación corresponde únicamente al comando dedicado, al producto y
al mes comprobados. La receta genérica `recipe --product h10` y el parser
histórico no adquieren por ello esa certificación; tampoco queda certificada
la familia macro ni una ronda del coordinador. Los recibos locales conservan
commit y hashes del código, originales, corte, faltantes y salidas. La revisión
humana sigue pendiente antes de publicar datos o activar cualquier ejecución.

Para una captura nueva, `round --execute --check-at-completion` registra el
corte de comprobación al terminar. Conserva también el corte pedido en la
receta. Sin esa opción respeta el corte histórico: una captura posterior queda
rechazada. La opción no autoriza la captura ni modifica las fechas observadas. Se probó
la cadena CLI completa con una [reimportación offline del XLS EIA real](referencias/source-updates-20261019/offline-round.json):
21 filas Silver de septiembre, sin nueva petición de red. Eso acredita la
orquestación; no equivale a revalidar la URL de origen.

Para BMV o catálogos AFAC/aeroportuarios soportados:

```bash
uv run python -m src.source_updates recipe --product bmv_xbrl --output selection --catalog-file <catalogo-preservado.html> --period 2026Q2 --ticker AERO
uv run python -m src.source_updates recipe --product aicm_traffic --output selection --catalog-file <catalogo-preservado.html> --period latest
```

La selección exige enlaces presentes y periodo no ambiguo. Una URL enlazada
puede fallar al descargar. No se generan nombres de próximos reportes.

### Captura y comprobación

El tráfico mensual IR de Aeroméxico usa una cadena dedicada. Primero se captura
el índice y se elige un único enlace que identifica el mes. Después se captura
el PDF; el nombre de la URL no demuestra su periodo. La extracción verifica
título, entidad, orden de columnas y años dentro del documento. Las 12 cifras
del mes y sus 12 comparativos del año anterior quedan separados de los
acumulados. No se suman meses para crear un trimestre desde este comando.

```bash
uv run python -m src.source_updates recipe --product am_traffic_ir --output selection --catalog-file <indice-preservado.html> --period 2026M09 > tmp/am-seleccion.json
uv run python -m src.source_updates collect --selection tmp/am-seleccion.json --workspace tmp/source-updates/am-septiembre --dry-run
uv run python -m src.source_updates collect --selection tmp/am-seleccion.json --workspace tmp/source-updates/am-septiembre --execute
uv run python -m src.source_updates.am_traffic_candidate --workspace tmp/source-updates/am-septiembre --period 2026M09 --as-of <corte-ISO-con-zona> --collection <id-del-recibo> --dry-run
uv run python -m src.source_updates.am_traffic_candidate --workspace tmp/source-updates/am-septiembre --period 2026M09 --as-of <corte-ISO-con-zona> --collection <id-del-recibo> --execute
uv run python -m src.source_updates.am_traffic_candidate --workspace tmp/source-updates/am-septiembre --period 2026M09 --as-of <corte-ISO-con-zona> --collection <id-del-recibo> --check
```

`collect` declara un GET público por PDF, hasta cinco solicitudes con
redirecciones y cero pagadas. El comando dedicado solo lee originales locales;
su vista previa no escribe y su certificación/reproducción no usa red. Preserva
SHA-256, captura UTC, token, extracto, página y fecha de publicación del PDF.
Un candidato aceptado no se sustituye: una nueva captura o revisión requiere
otra carpeta. La comparación de revisiones queda sin acreditar cuando no hay
un candidato anterior. Los hashes de archivos no prueban revisiones de cifras.

Pasajeros se escala de miles a personas; ASM y RPM de millones a millas.
Ocupación se escala de porcentaje a fracción. Pasajeros, ASM y RPM incluyen
itinerario y fletamento; la ocupación reportada cubre itinerario. No se calcula
esa ocupación como RPM/ASM con universos distintos. Su dimensión Gold conserva
esa advertencia. El documento declara cifras no auditadas; eso no basta para
llamarlas preliminares. Se admiten diferencias de suma de hasta 1,5 unidades
publicadas por el redondeo de dos componentes y un total.

La revisión de fórmula del 21 de octubre corrigió su definición a RPM/ASM de
itinerario, equivalente a RPK/ASK, ponderada por distancia. Se recertificaron
offline los PDF reales de julio, agosto y septiembre: 24 filas y siete tablas
por mes, con replay idéntico y sin cambiar las cifras reportadas. Solo cambia
`load_factor_total.formula`. Los candidatos históricos conservan la definición
anterior como evidencia; no se sobrescriben ni sustituyen a los corregidos.
La [comprobación agregada](referencias/source-updates-20261021/verification.json)
registra el commit de código, cortes, hashes y rutas de los candidatos nuevos.

Se conservan **39 archivos locales de revisión**, bajo
`tmp/source-updates/am-traffic-formula-correction-20261021/`, para revisar esta
corrección; no se publicaron ni se añadieron al respaldo histórico de 512
archivos. La recuperación usa los Bronze y recibos de colección ya respaldados
en el privado #38 y el código `579628ba`, con los cortes exactos registrados.
La certificación en una carpeta nueva y su `--check` son los comandos descritos
arriba. La revisión de un lote sigue siendo previa a cualquier publicación.

El candidato Silver `aeromexico_ir_monthly_metrics` aplica el grano y linaje
estructural existente de observaciones operativas, más reglas de dominio IR.
No se rotula como SEC ni se registra automáticamente en el warehouse productivo.
Gold aplica los contratos existentes, tres dimensiones y puente de linaje
documental exacto. La cadena genérica `build/check` no adquiere este adaptador:
se usa el comando dedicado. La certificación de un producto y mes no completa
la familia corporativa ni autoriza publicación o calendario. No cambia tesis.
[Índice oficial](https://ir.aeromexico.com/news-events/traffic-reports).

La captura oficial del 19 de octubre conservó los PDF de julio, agosto y
septiembre de 2026, todos con HTTP 200. Cada mes aporta 24 registros Silver y
24 Gold: 12 actuales y 12 comparativos. Sus documentos están fechados el 3 de
agosto, 3 de septiembre y 6 de octubre, respectivamente; el rezago desde el fin
del mes es de 3, 3 y 6 días. La hora de publicación y la primera disponibilidad
en el portal no se conocen y permanecen nulas. Los tres originales suman
1.025.796 bytes. Estos candidatos no certifican finanzas, otros emisores,
otros formatos ni cobertura de las tres aerolíneas.

Aerocivil tiene una cadena candidata propia. `python -m
src.source_updates.aerocivil recipe --period 2026M07` emite una selección con
tres GET: conteo, datos y conteo posterior. El límite es 1.000 filas de un solo
mes para los designadores de explotador AMX/SLI, hasta 15 solicitudes con
redirecciones y cero pagadas. No usa el descargador histórico completo.
La misma receta con `--metadata` produce la selección del diccionario oficial.
Ambas selecciones se capturan con `collect`. Se importa por hash el original
OurAirports retenido, para códigos y países; esa referencia no se vuelve a
descargar en el piloto.

```bash
uv run python -m src.source_updates.aerocivil certify --workspace <candidato> --period 2026M07 --as-of <corte-ISO-con-zona> --collection <id-de-las-tres-consultas> --dry-run
uv run python -m src.source_updates.aerocivil certify --workspace <candidato> --period 2026M07 --as-of <corte-ISO-con-zona> --collection <id-de-las-tres-consultas> --execute
uv run python -m src.source_updates.aerocivil certify --workspace <candidato> --period 2026M07 --as-of <corte-ISO-con-zona> --collection <id-de-las-tres-consultas> --check
```

La certificación y su reproducción solo leen originales locales, sin red. El
primer modo no escribe. Se rechazan conteos discordantes, truncación, grano
duplicado, mes u operador distinto, aeropuerto sin referencia y dirección
incompatible. Los candidatos aceptados son inmutables. Que ambos conteos sean
iguales no demuestra una versión transaccional del proveedor.

La consulta oficial del 19 de octubre para AMX/SLI en 2026 devolvió meses de
enero a julio. No acredita agosto/septiembre ni demuestra ausencia global de
otros datos. Julio devolvió diez filas; ocho cumplen los códigos literales
S/I y suman **347 movimientos**. Otras dos filas con código N suman tres
movimientos y se conservan como exclusiones, sin llamarlas chárter. No hay
filas SLI en ese resultado; eso no convierte su actividad en cero.

El [diccionario oficial](https://www.datos.gov.co/api/views/jh8x-n6h6.json)
define la medida como movimientos aeroportuarios. Advierte que empresa y
explotador se derivan del callsign y la matrícula. El candidato conserva ese
origen y el designador comercial reportado; no afirma un comercializador
codeshare. La leyenda de S/N/I no quedó comprobada: la aceptación de su
interpretación sigue pendiente. Se mantienen nulos pasajeros, asientos,
despegues y ocupación, y `agent_eligible=false`.

Silver y Gold candidatos conservan ocho observaciones, cuatro artefactos y
24 enlaces exactos. Se aplica la validación de rutas existente y se declara
el grano local del registro al validador de linaje. La tabla heredada no forma
parte del catálogo general de contratos Gold; este comando no cambia ese
catálogo ni acredita su validación completa. La fecha de publicación, su
rezago y comparación de revisiones siguen sin acreditar. La metadata declara
actualización trimestral del proveedor; aquí no se activa ninguna ejecución.
No se cambia Gold de Vuelos, su cohorte, M11 ni datos publicados.

`collect` acepta GET público, exportación CSV pública de Banxico mediante POST,
importación manual con SHA-256 y BTS por año
explícito (GET del formulario + POST). `purpose=catalog` preserva el catálogo y
descubre enlaces; no descarga los documentos encontrados. Una segunda selección
explícita captura documentos nuevos y revisiones. Revalida las URLs elegidas,
incluidos catálogos `current` y años BTS históricos. No inventa futuros enlaces.
SEC y Aena requieren importaciones manuales aquí; no se leen credenciales.

`build` reutiliza parsers y transformaciones permitidas en otro proceso, sin
red y con rutas del candidato. Un bloqueo exclusivo evita escritores simultáneos
del mismo lote. No ejecuta analítica, modelos, aprobaciones ni publicación.
Necesita sus insumos completos: no restaura automáticamente el respaldo privado.
Los pasos disponibles aparecen en `python -m src.source_updates build --help` y
en `src/source_updates/build.py`; se solicitan de forma explícita y ordenada.

`check` verifica hashes Bronze, contratos Silver/Gold, grano, fuente, entidad,
periodo real y valores faltantes. El último periodo del archivo no demuestra
completitud: la skill debe comprobar meses, días y universos requeridos.
`baseline_file`, `revision_keys` y `value_columns` permiten comparar altas,
bajas y cifras revisadas. No se rellenan faltantes con cero. Se distingue edad
del dato de rezago de publicación; este último queda nulo sin fecha conocida.
El periodo publicado por Tracker permanece sin inferir hasta consultar el
expediente autorizado. Un hash Gold agregado exige el gate de linaje existente;
no pasa por tener una cadena de hash. Los controles solo acreditan su alcance.

`round` encadena captura → construcción → controles y se detiene ante fallos.
`retry` calcula propuestas puntuales: +2 hábiles tras fecha oficial, siguiente
hábil tras fallo técnico, o un intento dentro de siete días/siguiente mensual
sin fecha. Máximo dos reprogramaciones por lote; después, decisión del dueño.
No instala ningún horario ni seguimiento automático.

### Certificación de originales retenidos

Los comandos nuevos trabajan con originales públicos que ya estaban guardados.
**No son capturas nuevas ni una comprobación de la última publicación disponible.**
Conservan SHA, alias, URL y fecha original de captura; la fecha de retención va
en otro campo. El último disponible y el último publicado por Tracker siguen
sin inferirse. No se consultó AeroDataBox, no se cambió una credencial y no se
activó ningún calendario, dato, noticia o tesis.

El flujo dedicado está en [`retained.py`](../src/source_updates/retained.py).
Su [coordinador offline](../src/source_updates/retained_round.py) ejecuta
retención → comprobación Bronze → Silver → Gold candidato/linaje → reproducción
sin conexión. Cada producto tiene carpeta y recibo propios. Un fallo detiene
los productos siguientes, conserva los anteriores y deja etapa, objetivo y
error exactos. Los candidatos aceptados son inmutables. Estas tablas tienen
contratos locales explícitos; no se registran en el warehouse publicado.

| Producto | Roles exactos | Alcance del original revisado |
|---|---|---|
| `ryanair_sec` | `html`, `submissions`, `index` | Seis conceptos IFRS consolidados en EUR del ejercicio 2025-04-01–2026-03-31; 14 hechos inline repetidos consistentes y balance verificado. Presentación SEC 22 de junio; no cifras trimestrales. |
| `am_financials` | `pdf` | 20 cifras preliminares/no auditadas de 2T26; unidades ASM/CASM por milla y dos identidades contables. Fecha impresa 13 de julio; primera publicación y rezago desconocidos. |
| `afac_airports` | `workbook` | 2.730 filas enero–julio, 65 nombres de aeropuerto y 173 cruces visibles. Sin aerolínea. |
| `afac_margins` | `routes`, `carriers` | 23.331 filas, 28 reconciliaciones entre marginales y 120 controles de totales; conserva cinco celdas estimadas por AFAC. |
| `afac_countries` | `pdf`, `routes` | 116 cifras acumuladas actuales/comparativas, 29 países y 29 cruces de pasajeros. No mensual desde gráficas redondeadas. |
| `anac` | `json` | 201.483 registros originales consumidos; 36 métricas seleccionadas de enero–junio. Compañía literal y México–Brasil regular. |
| `caa` | `csv` | Seis valores en junio: cotejados, no cotejados y cancelados, por llegada/salida. No pasajeros ni cobertura mundial. |
| `aena` | `company_operations`, `company_passengers`, `market_operations`, `market_passengers` | 54 cifras enero–julio; compañía×aeropuerto y mercado de todas las compañías separados. Dos faltantes de pasajeros BCN siguen N/D. |
| `oma_traffic` | `pdf` | Julio: 168 cifras, 13 aeropuertos/grupo, tres mercados y 80 reconciliaciones. Mensual/acumulado y comparativos separados. |
| `aicm_slots` | `pdf` | Verano 2026: 2.836 asignaciones únicas, 61 páginas y conteos por frecuencia verificados. UTC y designador AM; no vuelos realizados. |
| `iasa` | `pdf` | 84 categorías literales por país o autoridad; documento 2025-04-18. Captura posterior no actualiza su fecha ni prueba vigencia actual. |
| `dictionary` | `csv` | 86.553 palabras por SHA; años con signo, 22 secuencias cero y tres huecos. `NA` literal se comprueba con un caso sintético; no aparece en esta copia. No calcula tono. |
| `am_routes`, `oma_routes`, `colima`, `aifa_roster` | `document` por producto | Seis pasajes fechados, oficiales o secundarios según fuente. No son filas de tráfico ni prueba de operación continuada. |

La fecha de un documento se conserva como tal. El nombre del archivo y la
captura no prueban cuándo se publicó por primera vez. Publicación y rezago
siguen nulos cuando esa evidencia falta. El boletín de países incluye vuelos
con un universo distinto del total O-D: solo pasajeros acumulados actuales se
reconcilian; no se armonizan silenciosamente ambas cifras de vuelos.

Los ceros numéricos reportados se conservan. No prueban ausencia operativa.
Los ceros posteriores al mes de un XLSX acumulado son plantilla y se excluyen.
Sin baseline se declara que no se compararon revisiones. Con uno explícito,
se fija su SHA y se comparan claves naturales, valores y campos de significado
como notas/marcas de estimación o categorías del diccionario. Cada replay
vuelve a comprobarlo. Una edición nueva fuera del formato/cobertura revisado
se bloquea para adaptar y probar; no se declara éxito por haber descargado.

Ejemplo individual, usando una ruta real del manifiesto retenido:

```bash
python -m src.source_updates.retained retain --product afac_airports --source-root <ruta-Bronze-retenido> --workspace tmp/source-updates/afac-aeropuertos --original workbook=domestic_routes_research/afac_airports_2006_2026_july_2026M07_20260913T004755Z.xlsx --dry-run
# Si el lote candidato está autorizado, repetir retain con --execute y conservar su run_id.
python -m src.source_updates.retained certify --product afac_airports --workspace tmp/source-updates/afac-aeropuertos --period 2026M07 --as-of 2026-10-19T12:00:00-06:00 --retention <run_id> --dry-run
# --execute construye el candidato; --check lo reproduce sin red ni escrituras.
```

Una receta del lote declara `version=1`, `source_root`, `as_of` y una lista
`items` con `product`, `period` y `originals` (roles → rutas exactas del
manifiesto). No debe inventar rutas ni versiones. El periodo de FAA/diccionario
es el periodo de revisión: las filas siguen siendo snapshots. Slots conserva
la temporada, países conserva acumulados y pasajes conserva fecha documental.
Usar `YYYYMmm` en productos mensuales; `YYYYQn` es revisión para FAA,
diccionario y slots, y trimestre documental para `am_financials`. Ryanair usa revisión `2026Q2`,
pero conserva `RYANAIR_FY2026` y fechas fiscales dentro de sus filas. El lote no
acepta baseline implícito; prepararlo con el comando individual.

```bash
python -m src.source_updates.retained_round --recipe <receta.json> --workspace tmp/source-updates/mi-lote-retenido --dry-run
# --execute solo tras revisar la selección; nunca instala cron ni llama a red.
```

La prueba en seco del lote principal muestra `products: 14`, `network_requests: 0`,
`paid_requests: 0`, `new_source_capture: false` y `activation: none`.
Ese lote produjo 115.920 registros. Un lote separado de finanzas 2T26 añadió
20, y otro de Ryanair SEC añadió seis: son **16 productos y 115.946 registros**
de esta ampliación local. Los tres lotes se reproducen sin conexión y reciben
revisión independiente. [Evidencia por producto](referencias/source-updates-20261019/retained-verification.json).
El recibo de cada producto distingue sus filas comprobadas, alcance, hash de
salidas y original, revisión del código y resultado del replay. No certifica
un trimestre completo, una familia completa ni frescura frente al proveedor.

La validación completa del código local `0096e2d` pasó **2.204 pruebas y 29
subpruebas**, con 78 omisiones: warehouse local ausente (71), insumos Stage 4
no versionados (5), vista previa Pages sin fijar (1) y propuesta independiente
ausente (1). Los 16 candidatos reales pasaron reproducción offline y revisión
independiente de originales, código y salidas. La primera ejecución de la suite
falló en navegador por los enlaces de dependencias locales; se corrigió esa
copia y la suite final pasó. No se cambió código de la web para resolverlo.

### Alcances históricos y condiciones restantes

La revisión histórica adicional copió 836 archivos públicos y sus sidecars,
conservando los 837 registros del manifiesto: uno es un alias de contenido, no
una descarga adicional. Dieciséis controles verificaron ocho productos en
Silver y Gold, con periodo y entidad exactos. Por ejemplo, Viva y Volaris
aportan una fila financiera Silver y ocho Gold cada uno; eso no certifica el
reporte completo ni una captura nueva. Los 1.766 derivados Stage 6 conservan
113 N/D y 3.713 enlaces a padres con 99 archivos documentales ancestrales. Se
conservaron las fórmulas registradas y se comprobó la ascendencia; no se
recalcularon fórmulas ni modelos.

Estado de aquellas condiciones tras la continuación del 21:

- **Viva tráfico:** el bloqueo inicial se conservó como evidencia. La aprobación
  específica de BMV permitió capturar y comprobar septiembre: 24 filas nativas.
  S3 sigue fuera de la política. El candidato nuevo no se activó.
- **Aerocivil:** la recaptura y comparación numéricas pasaron; la leyenda
  primaria del mismo conjunto y la atribución siguen pendientes.
- **GDELT:** los dos intentos nuevos de septiembre y consulta actual devolvieron
  503. Sus recibos no acreditan noticias ni ausencia; no se siguen repitiendo.

`news_errors` es una exclusión intencional, con frecuencia `never`. Conserva
fallos para auditoría y no necesita implementarse como fuente de noticias.

El auditor RSS leyó siete capturas retenidas y verificó 700 contribuciones
válidas. El corte de septiembre de 2026, en `America/Mexico_City`, contiene
12 URLs fechadas en seis días: 1, 2, 3, 21, 28 y 30. Los otros 24 días no se
observaron en esas capturas; eso no demuestra ausencia de noticias. Conserva
las consultas exactas de las capturas, centradas en Aeroméxico; no acredita
cobertura equivalente de Viva y Volaris. Fecha declarada en RSS, evento,
primera disponibilidad y captura permanecen separados. No visita artículos.

El corte de PR142 contiene 11 candidatos no aprobados, con publicaciones
seleccionadas de junio a octubre y octubre incompleto. Se verificaron
identidades, hashes del contenido candidato y orden de fechas. Sus cuerpos
originales no están disponibles localmente para una nueva comprobación.
La afirmación de lectura del emisor se conserva como metadato del responsable,
sin convertirla en una verificación local nueva ni activar el índice.

La revisión de perfiles abarca cinco perfiles del parser y las mismas cinco
entradas de aerolínea: 100 evaluaciones, 60 localizadores y diez originales
primarios retenidos. Ryanair reporta ASM y etapas en millas pese a su indicador
global `metric`. Viva distingue matriz financiera y operadora, moneda USD desde
octubre de 2022 y pasajeros reservados que pueden no haber volado. Los códigos
IATA/ICAO por entidad y las decisiones de comparación se tratan por separado:
la continuación verificó cuatro referencias literales IATA/FAA sin unirlas a
los totales consolidados ni inferir la equivalencia jurídica Ryanair DAC.
No se corrigieron perfiles ni cifras de producción a partir de estas evidencias.
[Mapa por atributo](referencias/source-updates-20261019/peer-primary-review.json).

El mapa de los 21 eventos usa 24 originales y 54 localizadores. Hay respaldo
acotado para 20 eventos y parcial para uno. La URL DOT de octubre respondió
404; un documento posterior del emisor respalda fecha y acción, pero no las
13 rutas ni su cobertura MEX/NLU. La orden DOT de julio respondió 200 y queda
como original de revisión sin registro activo en el catálogo; no usa el alias
FAA. Los documentos retrospectivos no prueban publicación contemporánea.
El tráfico de febrero conserva el 5 de marzo del documento y el 6 de marzo del
archivo del emisor; 1T26 conserva el 21 de abril del informe y el 23 de abril de
presentación SEC. Impacto, categoría y confianza siguen siendo decisiones
curadas sin aprobación nueva.
[Mapa de eventos](referencias/source-updates-20261019/event-primary-review.json).

Los dos auditores son de lectura y no escriben Silver ni Gold:

```bash
python -m src.source_updates.news_cut rss --root <bronze-publico> --month 2026-09 --as-of 2026-10-19T12:00:00-06:00
python -m src.source_updates.news_cut candidate --file <corte-upstream-no-aprobado.json>
python -m src.source_updates.primary_review --bundle docs/referencias/source-updates-20261019/peer-primary-review.json --root old_public=<bronze-publico>
# Para eventos, añadir --root para context_primary, context_extra, am_july y dot_review.
```

Cada raíz es una carpeta local de originales seleccionados. El mapa contiene
rutas relativas y hashes; no descarga faltantes ni acepta documentos fallidos.
El mapa de eventos exige además tres recibos bajo `tmp/`, declarados en
`local_inputs`. El respaldo privado separado los conserva en
`review/operacion/20261019/source-updates/payload/`. Después de materializar y
verificar ese paquete según su README, restaurarlos en este checkout aislado:

```python
from pathlib import Path
import hashlib, json

package = Path("../aeromexico-tracker-data/review/operacion/20261019/source-updates")
bundle = json.loads(Path("docs/referencias/source-updates-20261019/event-primary-review.json").read_text(encoding="utf-8"))
receipts = {
    "tmp/primary-events-result.json": "payload/proofs/primary-events-result.json",
    "tmp/primary-extra-result.json": "payload/proofs/primary-extra-result.json",
    "tmp/source-updates/dot-primary-review-20261019/capture-results.json": "payload/diagnostics/dot_review/capture-results.json",
}
for target, source in receipts.items():
    content = (package / source).read_bytes()
    assert hashlib.sha256(content).hexdigest() == bundle["local_inputs"][target]
    destination = Path(target)
    if destination.exists():
        assert destination.read_bytes() == content, "Conservar el recibo distinto e investigar"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(content)
```

Para `old_public`, `context_primary`, `context_extra` y `am_july`, usar las
carpetas homónimas bajo `payload/originals/`; para `dot_review`, usar
`payload/diagnostics/dot_review/`. Los candidatos completos viven en
`payload/candidates/` y conservan sus rutas internas y recibos. No copiar esos
Gold a producción ni interpretar el respaldo como una aprobación nueva.
Para reproducir un candidato con `--check`, copiar primero su carpeta completa
a una carpeta nueva bajo `tmp/source-updates/` de este checkout. Ese límite
de escritura y lectura de candidatos se conserva; no se amplía al respaldo
privado ni se sustituye con enlaces simbólicos.
Un pasaje localizado no aprueba la interpretación del revisor. Se conservan
`agent_eligible=false`, `silver_gold_certification=false` y `activation=none`.
[Muestra verificable de los auditores y fallos](referencias/source-updates-20261019/curation-news-verification.json).

El código de esta continuación, `b5def06`, pasó **2.224 pruebas y 29
subpruebas**, con las mismas 78 omisiones por insumos locales o vistas previas
ausentes descritas arriba. La revisión independiente repitió las 20 pruebas
focalizadas y los mapas reales con red bloqueada, sin hallazgos abiertos.
Treinta y tres originales documentales conservaron hash, tamaño y fecha de
modificación durante la reproducción. Estas pruebas no certifican Silver/Gold
para los mapas ni aprueban decisiones curadas. Los commits posteriores solo
actualizan documentación y muestras; no cambian esos insumos de código.

Estas condiciones no se sustituyen por una prueba de frescura de Gold ni por
una aprobación inventada. El calendario aprobado no aprueba tesis, datos nuevos
o publicación.

La vista previa combinada enumera 48 operaciones para 41 productos distintos.
El producto número 42 es `news_errors`, excluido deliberadamente de ejecución
por su frecuencia `never`; sigue en el inventario de auditoría. Siete productos
aparecen en mensual y trimestral. La vista previa declara cero solicitudes de
red o pago, ninguna escritura ni ejecución programada.

### Integración y permisos

PR137 y PR141 ya están integrados; la certificación local H.10 parte de
`dfa207c` y permanece en una rama separada. Vuelos (PR134 y su contraparte
privada33) fue integrado por sus responsables. PR142 se fusionó en `194ff92c`
el 19 de octubre de 2026, con [CI](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/39282317455)
y [workflow Pages](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/39282317699) correctos; no se hizo una
verificación funcional de Pages o Railway desde esta continuación. Privada35
se fusionó a las 17:20 UTC del mismo día. La base local probada
`03a06b8` se conserva; los adaptadores retenidos están en una rama local
distinta, sin push, PR nuevo, merge ni activación durante la preparación local.
La autorización de preparación permitió el PR borrador y su CI. La autorización
posterior permite integrar técnicamente las skills y su respaldo, con revisión
y CI del head final, sin activar calendario, fuentes ni noticias. El trabajo
M11 de PR140 y la publicación 3T26 de PR149 conservan sus responsables. La rama de revisión ya incorpora
PR142 y conserva sus correcciones de fechas GDELT y de noticias. Los commits
locales anteriores y sus recibos mantienen su fecha y alcance históricos.
PR142 no es un PR pendiente ni una razón para dar por exhaustivo RSS.
PR144 y su contraparte privada37 también están integrados; se conservan sus
cierres de documentación y su verificador de lifecycle. No se modifica el
sitio publicado. El respaldo nuevo de candidatos se mantiene separado del
snapshot privado y no modifica expedientes activos ni datos de producción.

Viva, Volaris e Industria siguen requiriendo aprobación exacta de entidad,
periodo y versión para **nuevas** tesis. Las tres tesis 2T26 ya aprobadas y
publicadas se conservan. Captura y pruebas verdes no aprueban otra versión.
Tampoco se activan noticias candidatas, cron, Pages, Railway o auto-merge.
El cron trimestral antiguo de `refresh.yml` sigue siendo una comprobación de
frescura/Gold; no implementa este calendario ni captura fuentes.

### Referencia técnica del inventario aprobado

La auditoría inicial del 18 fue de solo lectura: registró 124 Markdown
públicos, 50 relacionados con chat y siete candidatos a archivo (13.025 bytes).
Esos conteos conservan su corte histórico. La continuación integrada en PR144
archivó tres instrucciones reemplazadas con enlaces a sus originales en Git;
conservó cuatro candidatos por su utilidad y evidencia. No se repiten esos
retiros en este PR de fuentes. El [inventario](referencias/source-updates-20261018/lifecycle-audit.json)
y el [cierre canónico](chat/README.md#cierre-documental-del-19-de-octubre)
registran las disposiciones. La convención de audiencia vive en `AGENTS.md`.

El resto de este documento conserva el inventario y las observaciones de la
fase 1 del 13 de octubre. Sus fechas de disponibilidad y sus brechas son de ese
corte; no prueban una consulta nueva. La aprobación del calendario y el estado
ejecutable de esta entrega se describen arriba.

El objetivo es actualizar Airline Tracker en lotes mensuales y trimestrales,
agrupando publicaciones cercanas. Se reutilizan las ingestas y contratos
existentes. Este documento no autoriza publicar datos nuevos, activar evidencia,
reentrenar modelos ni consumir proveedores pagados.

## Alcance y cómo leer el inventario

El catálogo técnico vigente sigue en [`config/source_catalog.yaml`](../config/source_catalog.yaml);
las definiciones siguen en [`docs/diccionario-datos.md`](diccionario-datos.md)
y [`config/gold_schema_contracts.yaml`](../config/gold_schema_contracts.yaml).
No se sustituyen sus contratos con este plan.

Los archivos de [referencia de esta revisión](referencias/actualizacion-fase1-20261013/)
enumeran **29 claves de fuente, 99 métricas de la dimensión —34 seleccionadas
para el dashboard—, 93 métricas presentes en `fact_carrier_metrics` y 43 tablas
Gold públicas versionadas**. Son metadatos de `ea88008`; no contienen cubos
privados, credenciales ni observaciones nuevas:

- [`fuentes.csv`](referencias/actualizacion-fase1-20261013/fuentes.csv): todas las
  claves/alias, institución, método, frecuencia declarada, límites y vínculo con
  métricas de aerolínea.
- [`metricas.csv`](referencias/actualizacion-fase1-20261013/metricas.csv): las 99
  definiciones, unidad, consolidación, fuentes, entidades y cobertura por grano.
- [`tablas-publicas.csv`](referencias/actualizacion-fase1-20261013/tablas-publicas.csv):
  las 43 tablas, contratos, fuentes y campos métricos. Los extremos léxicos de
  periodo son un inventario, **no certifican cobertura completa ni frescura**;
  una tabla de pronósticos puede tener fechas futuras.
- [`inventario.json`](referencias/actualizacion-fase1-20261013/inventario.json):
  alcance, commit y conteos verificables.

`activa` en el catálogo significa que una fuente está declarada para consumo;
no demuestra que se consulte periódicamente. Una fuente sin filas en
`fact_carrier_metrics` puede alimentar rutas, macro, noticias u otra tabla.
El catálogo agrupa instituciones; Aeroméxico/Volaris/Delta/Ryanair dentro de SEC
y ANAC/Aerocivil/CAA requieren subentradas operativas independientes.
AeroDataBox es una dependencia privada adicional, tratada en
[su plan de salida](plan-salida-aerodatabox.md), fuera de esas 29 claves.

El anexo añade a `derived_gold` el alias documental
`afac_od_exclusive_market_inference`, usado en la tabla pública de inferencias
de mercados nacionales. No figura todavía en el catálogo técnico: se registra
esa brecha sin modificar configuración ni datos. Su atribución combina AFAC
con evidencia fechada de presencia/operador; **es inferencia, no observación
empresa×ruta ni exclusividad actual garantizada**. El `*` de la tabla de
prioridades es un comodín de política, no otra fuente descargable. Todos los
identificadores de fuente de las tablas inventariadas quedan mapeados en el
anexo, con esa excepción de metadatos distinguida.

Las fórmulas unitarias del anexo se contrastan con `stage6_facts.py` y las
definiciones de parseo: SLA aplica `métrica × sqrt(etapa_km / 1834)` y conserva
N/D si falta etapa; CASM usa ASM-milla y Yield reportado RPM-milla. Las
derivaciones por kilómetro explicitan el factor 1,609344 y ×100 para centavos.
`inventario.json` registra las correcciones documentales frente a fórmulas
genéricas de la dimensión; **no se modifican Gold, código, cifras ni unidades
reportadas**. Comparar siempre definición y denominador de la fuente.

`procedencia_fuentes` distingue fuente materializada de herencia verificada.
El resumen `fact_route_traffic_summary` hereda BTS de `fact_route_traffic`
según `src/dashboard/prepare.py`, aunque no guarda `source_system`. En otras
tablas sin esa columna, el campo vacío indica fuente no materializada y obliga
a consultar generador/linaje; **no significa tabla sin dependencias ni fuente
libre**. Este inventario documental no sustituye el grafo de ejecución del
pipeline ni declara completa la lista de padres de cada tabla.

Se distinguen cuatro fechas: **periodo del dato, publicación del documento,
captura y aceptación/publicación del tracker**. Un anuncio o una llamada de
resultados no es el estado financiero. Una fecha de modificación del portal
no prueba cuándo se publicó por primera vez un archivo.

## Fuentes centrales y cobertura realmente incorporada

La columna «incorporado» conserva la cobertura de la base examinada. Los
candidatos locales posteriores se distinguen expresamente: no significan
publicación, activación ni actualización del dashboard.

| Fuente / producto | Métricas y grano | Incorporado al corte | Disponibilidad oficial observada / adquisición | Dependencias y brecha |
|---|---|---|---|---|
| Aeroméxico IR, resultados | Pasajeros, capacidad, ocupación, ingreso/costos unitarios, finanzas, notas y expectativas; trimestre del grupo | PDFs 2021Q1–2026Q2; operación IR histórica 2021Q1–2024Q2 y finanzas IR heredadas 2021Q1–2025Q2; candidato retenido 2T26 separado con 20 cifras; otros periodos recientes por SEC | [Resultados IR](https://ir.aeromexico.com/financial-information/quarterly-results); `src/ingest/aeromexico_ir.py` usa 22 URLs registradas y descarga ausentes | Descubrir links de periodos nuevos y sus estados financieros; no revisita URLs existentes. Los límites históricos de los dos parsers son deliberados, no un parser genérico de futuros releases |
| Aeroméxico tráfico IR / SEC 6-K | Pasajeros, ASM/RPM y ocupación total/nacional/internacional; mes del grupo | Serie mensual SEC hasta junio 2026, trimestral hasta 2T26; candidatos IR dedicados julio/agosto/septiembre | [Tráfico IR](https://ir.aeromexico.com/news-events/traffic-reports) ya muestra septiembre; SEC preserva anexos y presentación regulatoria | Parser SEC busca anexos HTML `ex99*.htm`; selección IR mensual y candidato PDF dedicados permiten comprobar un mes real por separado. No inferir finanzas de tráfico |
| Volaris IR / SEC | Operación y estados financieros; trimestre/mes; grupo y subsidiarias según reporte | Trimestrales hasta 2T26 | [IR](https://ir.volaris.com/news-events/press-releases/), [eventos](https://ir.volaris.com/news-events/events-and-presentations/); SEC CIK 1520504, perfiles existentes | Catálogos `current` se reutilizan por URL en `ingest/peers/stage5.py`; añadir revalidación de catálogos. Pasajeros reservados/transportados y universo geográfico deben conservar definición |
| Viva IR / BMV GVIVA | Operación, finanzas y tráfico; mes/trimestre | 2023Q1–2026Q2 financiero/operativo | [BMV GVIVA](https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD), PDFs InvestorCloud; `ingest/peers/stage5.py` | Plantilla de URLs limitada explícitamente a 2026Q2; descubrir producto mensual y futuros trimestres. Mantener preliminar/no auditado y reconciliaciones H1−Q2 |
| SEC Aeroméxico | Formularios 6-K, 20-F, F-1 y anexos; artefacto/presentación | Índice local hasta presentación 14 agosto; financieros hasta 2T26 | [SEC](https://www.sec.gov/edgar/browse/?CIK=1561861&owner=exclude); submissions/companyfacts, `ingest/sec/discover.py` | Identificación `SEC_USER_AGENT` existente en entorno; discovery refresca catálogos, reutiliza documentos existentes. Un formulario disponible no asegura XBRL financiero |
| BMV AERO/VOLAR | XBRL por concepto, moneda, duración/instante y periodo; respaldo/revisión contable | Paquetes hasta 2T26, con comparativos y TTM | [Catálogo XBRL](https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl); `ingest/bmv/download.py` descubre ZIP/miembro | Catálogo se refresca; paquetes iguales por URL se cachean. Evitar sumar duración trimestral, acumulada y TTM o tratar balance como flujo |
| AFAC, resumen por aerolínea / DATATUR | Pasajeros por operador/mercado y servicio regular/fletamento; mes | Histórico 2015–2025; base canónica examinada hasta junio y candidato julio/agosto separado | [DATATUR](https://datatur.sectur.gob.mx/SitePages/afac.aspx), [PDF agosto](https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_2026_08.pdf); HTTP + descarga asistida cuando gob.mx bloquea | Landing rezagada dice julio, pero PDF del reporte mensual contiene agosto. El parser heredado limitaba enero–junio; el adaptador candidato verifica la edición y el mes hasta agosto. Fecha exacta de publicación agosto no verificada; no usar fecha de captura como publicación |
| AFAC aeropuertos | Pasajeros/operaciones/carga del aeropuerto completo; mes | Adaptador candidato del XLSX retenido enero–julio 2026; 173 cruces visibles | [Estadísticas AFAC](https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404) | Producto independiente del resumen por aerolínea; no atribuir total del aeropuerto a Aeroméxico. Última disponibilidad nueva no verificada; el fallo HTTP de un catálogo no invalida el original retenido comprobado |
| AFAC países | Cajas exactas acumuladas por país; gráficas mensuales redondeadas | Adaptador candidato del boletín julio: 116 valores, 29 países; sin convertir acumulado en mes | Mismo catálogo AFAC; `data/bronze/afac_research/` y selección explícita | No convierte país en ruta u operador. Conservar fuente/edición propia |
| AFAC origen–destino y marginal por aerolínea | Totales por par de ciudades y totales por empresa, granos separados | Referencias para estimación hasta julio 2026; candidato retenido 23.331 filas con 28 reconciliaciones | `ingest/afac/margins.py`, `international_margins.py`; originales `sase-*` y `resumen-*` | Usar misma edición acumulada para reconciliar; disponibilidad de edición agosto de ambos XLSX sigue sin verificar. Totales/marginales **no observan empresa×ruta** |
| BTS T-100 International Segment All Carriers | Pasajeros, asientos, vuelos realizados/programados, distancia, carga/correo; operador×segmento MX↔US×mes×aeronave/clase | 2015M01–2026M05; 2T26 local tiene abril y mayo | [Descarga](https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FJE&QO_fu146_anzr=Nv4%20Pn44vr45), [historial](https://www.transtats.bts.gov/ReleaseInfo.asp); GET formulario + POST México/año/todos los meses/ZIP | Historial anuncia julio añadido 9 octubre y junio 14 septiembre; el ZIP retenido capturado el 19/oct contiene enero–julio, comprobados en el lote BTS descrito abajo; esto no verifica disponibilidad actual ni cobertura completa por operador. Se omiten años anteriores al corriente en caché: perdería revisiones históricas. Segment no es Market ni destino final del boleto |

El [historial BTS](https://www.transtats.bts.gov/ReleaseInfo.asp) registra además
revisiones de diciembre 2023 en octubre y febrero 2024–mayo 2026 en septiembre.
Hay que refrescar los años afectados y comparar celdas, no limitarse a anexar
el mes nuevo. La [política de datos restringidos](https://www.bts.gov/topics/airlines-and-airports/restricted-data)
no permite deducir automáticamente un mes disponible para este filtro.

## Fuentes complementarias y referencias

| Fuente / claves del catálogo | Métricas, cobertura y adquisición actual | Ronda y límite |
|---|---|---|
| OMA (`oma_ir`), GAP/ASUR vía `sec_edgar` | Pasajeros nacionales/internacionales/total por aeropuerto/grupo; Gold hasta julio. [OMA](https://ir.oma.aero/en/traffic-reports/), [GAP](https://www.aeropuertosgap.com.mx/es/material-events.html), [ASUR](https://www.asur.com.mx/comunicados-1); `ingest/airports/groups.py` | Mensual central. Los tres publicaron septiembre en octubre; ASUR es multinacional: separar México, países y adquisiciones, no sumar todo como mercado mexicano |
| AICM (`aicm`) | Tráfico del aeropuerto hasta julio; slots estacionales preservados. [Estadísticas](https://www.aicm.com.mx/estadisticas-del-aicm/17-09-2013), PDFs | Mensual central; índice observado ofrece agosto, sin fecha de primera publicación. Slots son programación, no vuelos realizados ni pasajeros |
| AIFA (`aifa`) | Tráfico aeroportuario hasta julio; [numeralia/normateca](https://aifa.aero/normateca), XLSX | Mensual central; último enlace observado julio, fecha de publicación no expuesta. No usar como tráfico de una aerolínea |
| Banxico (`banxico_sie`) | FIX USD/MXN, INPC y tasa objetivo en series separadas; último dato local 20 agosto. Exportación pública CSV, `ingest/macro/banxico.py`; [SIE](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?accion=consultarSeries) | Capturar historia hasta corte en la ronda mensual/trimestral. FIX por día bancario; INPC y decisiones de tasa tienen su calendario propio. No asumir mismo ritmo para las tres series |
| Reserva Federal H.10 (`federal_reserve_h10`) | Respaldo FX explícitamente rotulado, original preservado en agosto; [H.10](https://www.federalreserve.gov/releases/h10/) | Consulta durante la ronda si falta FIX. Observaciones diarias publicadas semanalmente lunes 16:15 ET, martes por festivo. Cambios anunciados al DDP desde noviembre requieren comprobar el endpoint; no declararlo roto sin prueba |
| EIA (`eia`) | Combustible jet US Gulf Coast; último dato local 18 agosto; XLS histórico, `ingest/macro/fuel.py`; [serie](https://www.eia.gov/dnav/pet/hist_xls/EER_EPJK_PF4_RGC_DPGd.xls) | Mensual/trimestral con promedio y días cubiertos. Referencia de mercado, no costo contratado ni cobertura de combustible de la aerolínea |
| Yahoo Finance (`yahoo_finance`) | Cierre/ajustado/volumen/retornos/volatilidad AERO, VLRS, DAL, RYAAY, ICAGY hasta 20 agosto; `ingest/market/prices.py` | Mensual/trimestral; proveedor secundario, no regulador. Control de identidad AERO e IPO 6 noviembre 2025; no empalmar antiguo ticker con nueva acción |
| ANAC / Aerocivil / CAA (`international_route_authorities`) | Observaciones seleccionadas: Brasil hasta junio, Colombia hasta julio, Reino Unido junio. Aerocivil usado aporta operaciones, no pasajeros. HTTP/selección explícita en `ingest/international_routes.py` | Complementaria en ronda trimestral. [ANAC](https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas), [Aerocivil](https://www.datos.gov.co/resource/jh8x-n6h6.json), [CAA puntualidad 2026](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/uk-flight-punctuality-statistics/2026/). El adaptador usa Flight Punctuality, catálogo hasta julio sin fecha de primera publicación; Airport Data es otro producto. ANAC acceso desafiado, disponibilidad nueva no verificada. No cobertura mundial uniforme |
| Aena (`aena_spain`) | Exportaciones seleccionadas enero–julio; compañía×aeropuerto y par de aeropuertos separados. [Consultas](https://www.aena.es/es/estadisticas/consultas-personalizadas.html); CSV autenticado mediante navegador | Trimestral opcional. Boletines públicos ya hasta septiembre; no sustituirlos por el cruce empresa×ambos aeropuertos, que no existe en las capturas seleccionadas |
| Ryanair (`ryanair_ir`) y Delta SEC | Comparables trimestrales hasta 2T26; Ryanair página mensual capturada en agosto; perfiles parser existentes | Ronda trimestral secundaria. Año fiscal Ryanair y US-GAAP Delta requieren comparabilidad explícita. Actualizar catálogos `current`, sin bloquear las tres entidades mexicanas |
| OurAirports (`ourairports`) | Códigos, ubicación y país de aeropuertos; captura agosto; [catálogo](https://ourairports.com/data/) | Trimestral o cuando falla un código. Referencia comunitaria, no observación de vuelos; crosswalk versionado |
| FAA (`faa_iasa`) | Categoría IASA y eventos; original capturado agosto; [FAA IASA](https://www.faa.gov/about/initiatives/iasa) | Trimestral o evento conocido; no inferir efecto causal en pasajeros de la categoría |
| Google News RSS (`google_news`), GDELT (`gdelt`) | Titulares, URLs, fecha/consulta y tono; capturas agosto. RSS y API metadatos `ingest/news/rss_gdelt.py` | Ronda mensual/trimestral contextual; no noticias completas ni fuente primaria de cifras. Sin barrido diario ni promesa de recuperar todo lo ocurrido entre rondas |
| Errores RSS (`news_http_error`) | Respuestas fallidas preservadas; fuente declarada inactiva | Evidencia de fallo; nunca noticias válidas ni ausencia de noticias. Reintento puntual, no vigilancia |
| Loughran–McDonald (`loughran_mcdonald`) | Diccionario 1993–2025, versión marzo 2026; original agosto; [referencia académica](https://sraf.nd.edu/loughranmcdonald-master-dictionary/) | Revisar trimestral o anual; no un KPI de desempeño. Cambio de diccionario invalida comparación de tono sin versión |
| Comunicados Aeroméxico/OMA (`aeromexico_route_press`, `oma_route_newsroom`) | Frecuencias/presencia anunciada en documentos concretos; preservados septiembre | Complemento trimestral/evento fechado. Separar programación, presencia y vuelos realizados |
| Colima / Expansión (`colima_route_statement`, `expansion_aifa_roster`) | Investigación puntual, artículos/mirrors; preservados septiembre | Fuentes secundarias, no oficiales. Apoyan presencia/inferencia limitada, no volumen atribuible por operador |
| `peer_profile`, `curated_primary_sources`, `derived_gold` | Perfiles curados, fuentes primarias seleccionadas y fórmulas internas; sin endpoint propio | Se reconstruyen con insumos validados; no son tres descargas adicionales. Mantener fórmula, padres, versión y límites |

## Familias de métricas y dependencia de actualización

| Familia | Fuente y reglas de aceptación |
|---|---|
| Operación por grupo: pasajeros, ASK/ASM, RPK/RPM, ocupación, flota | Reporte corporativo / SEC; mes o trimestre según publicación. Conversión millas/km explícita, ocupación ponderada por capacidad. No sustituir pasajeros transportados por reservados sin rotular |
| Finanzas: ingresos, costos, utilidad operativa/final, EBITDAR, caja, deuda, balance, arrendamientos | SEC/IR/BMV; moneda, escala, IFRS/US-GAAP, instante/duración, trimestre/H1/TTM y preliminar/auditado preservados |
| Economía unitaria: RASK/CASK, ex combustible, spread, márgenes y puentes | Reportado o derivación congelada de finanzas + capacidad; fórmulas y redondeo verificables. Descomposición contable no prueba causalidad ni permite aislar FX sin insumos |
| Mercado/mezcla: pasajeros AFAC, participación y cambios | Mes y mercado con denominador homogéneo; mismo vintage cuando se comparan rutas y aerolíneas. Trimestre solo con meses requeridos, ausencia N/D |
| Rutas MX-US: vuelos, pasajeros, asientos, ocupación | BTS observado, segment/dirección/operador/clase. Mes realmente presente, comparativo misma cobertura; trimestre incompleto rotulado, sin inflarlo |
| Rutas fuera de MX-US | Observación parcial de autoridades y programación separada; futura salida de estimaciones AeroDataBox descrita en el plan correspondiente. No asignar totales AFAC a un operador por ruta |
| Macro/mercado y lenguaje | Series independientes de empresa; corte y días cubiertos, ticker y versión de diccionario. Notícias como contexto, no como sustituto de fuente oficial |
| Forecasts, anomalías, clusters, estudios y calidad | Resultados internos (`src/analytics`, `data/quality`), dependientes del lote aceptado. Mantener entrenamiento/corte; no reentrenar o activar automáticamente con una descarga |

El inventario métrico es más amplio que las tarjetas visibles. Una columna
presente en Gold no concede publicación ni significa que el frontend la use.
La revisión de fase 1 no cambia ninguna cifra, fórmula o aprobación.

## Evidencia de fechas: hechos frente a ventanas estimadas

Esta tabla conserva los ejemplos y el corte de disponibilidad de la propuesta
del 18 de octubre. No es una comprobación nueva del estado de 3T26 al 21 de
octubre. La publicación de ese trimestre se trabaja por separado; este
coordinador solo calcula una fecha con los releases reales que se le suministren.

| Producto | Periodo → publicación oficial observada | Implicación |
|---|---|---|
| Aeroméxico tráfico | Junio→2 julio; julio→3 agosto; agosto→3 septiembre; septiembre→6 octubre 2026; [archivo](https://ir.aeromexico.com/news-events/traffic-reports) | Suele llegar temprano el mes siguiente; cuatro ejemplos no fijan día universal |
| Volaris tráfico | Junio→7 julio; julio→5 agosto; agosto→3 septiembre; septiembre→6 octubre; enero→9 febrero y febrero→10 marzo; [archivo](https://ir.volaris.com/news-events/press-releases/) | Esperar a mediados de mes agrupa con Viva y feriados |
| Viva tráfico | Junio→10 julio; julio→12 agosto; agosto→11 septiembre; septiembre→9 octubre; otros ejemplos 11 febrero/12 marzo/10 abril/12 mayo/8 junio; [BMV](https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD), [septiembre](https://investorcloud.s3.amazonaws.com/VivaAerobus/InformacionFinanciera/SalaPrensa/2026-10-09-Trafico-septiembre-2026.pdf) | La muestra reciente llega hasta el día 12; no asegurar que futuros meses cumplan |
| OMA tráfico | Mayo→4 junio; junio→6 julio; julio→5 agosto; agosto→4 septiembre; septiembre→7 octubre; [archivo](https://ir.oma.aero/en/traffic-reports/) | Se agrupa en ronda mensual con las aerolíneas |
| GAP tráfico | Mayo→5 junio; junio→6 julio; julio→5 agosto; agosto→4 septiembre; septiembre→6 octubre; [archivo](https://www.aeropuertosgap.com.mx/es/material-events.html) | Misma ronda; México y Jamaica separados |
| ASUR tráfico | Julio→5 agosto; agosto→8 septiembre; septiembre→7 octubre; [archivo](https://www.asur.com.mx/comunicados-1) | Misma ronda, con alcance multinacional explícito |
| BTS release | Historial: junio→14 septiembre; julio→9 octubre; próximo release de tráfico anunciado 12 noviembre, [aviso](https://www.bts.gov/newsroom/july-2026-us-airline-traffic-data-down-18-same-month-last-year) | Agrupar revisión del catálogo desde el 15; anuncio no certifica el máximo mes MX-US descargable ni futuras fechas |
| AFAC agosto | PDF agosto accesible al 13 octubre; fecha de publicación primera no verificada | No fijar día. Recibir último vintage disponible en la ronda y registrar lag por producto |
| CAA Airport Data, producto separado | [Mayo](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/airports/uk-airport-data/uk-airport-data-2026/may-2026/) completo 9 septiembre; [junio](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/airports/uk-airport-data/uk-airport-data-2026/june-2026/) 22 septiembre; [julio](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/airports/uk-airport-data/uk-airport-data-2026/july-2026/) 23 septiembre | Fechas de completitud, no primera publicación; no prueban disponibilidad del CSV Flight Punctuality que usa el adaptador. Rezago irregular, sin día futuro fijo |
| EIA | [Serie usada](https://www.eia.gov/dnav/pet/hist/EER_EPJK_PF4_RGC_DPGD.htm): release 7 octubre, siguiente 15 octubre; [calendario](https://www.eia.gov/petroleum/supply/weekly/schedule.php) ajusta feriados | Frecuencia de publicación no obliga a adquirir semanalmente; recuperar periodo cerrado durante ronda |
| FIX / H.10 | [FIX](https://www.banxico.org.mx/tipcamb/tipCamMIAction.do?idioma=sp) por día bancario, con fechas distintas de DOF/pago; [H.10](https://www.federalreserve.gov/releases/h10/) semanal | Captura mensual de historia diaria. Calendarios específicos INPC/tasa y días inhábiles operativos futuros deben comprobarse, no inferirse de FIX |
| Aeroméxico 3T26 | **19 octubre después del cierre**, conferencia 20 octubre; [anuncio 30 septiembre](https://ir.aeromexico.com/static-files/30ea3e8d-0097-44f2-909b-e6601f9cdd59) | Fecha confirmada de release; 3T26 aún no publicado al corte |
| Volaris 3T26 | Llamada **27 octubre** confirmada en [eventos](https://ir.volaris.com/news-events/events-and-presentations/); release 26 octubre anunciado secundariamente, primario pendiente | No etiquetar el 26 como fecha oficial confirmada |
| Viva 3T26 | Sin fecha adelantada confirmada. [3T25](https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2025-3T25.pdf) fue 28 octubre; 1T26 30 abril, 2T26 24 julio | Ventana histórica de finales de octubre; requiere documento real |
| Trimestral, contraejemplos | Aeroméxico [3T25](https://ir.aeromexico.com/static-files/3dcc7a4f-a5fa-433f-8033-fd25360c6de3) fue 11 noviembre; Volaris 1T26 27 abril/2T26 21 julio/4T25 24 febrero; Viva 1T26 30 abril/2T26 24 julio | No hay día fijo universal. Q4 necesita ventana febrero/marzo, no enero |

Estos ejemplos prueban una ventana útil de trabajo, no un SLA de los emisores.
Los boletines de aeropuertos/CAA pueden señalar fecha de completitud o revisión
sin exponer la primera publicación. El expediente registra ese tipo de fecha.

## Calendario propuesto: dos tipos de ronda, sin vigilancia permanente

**Mensual: primer día hábil en o después del 15.** En una sola sesión revisar
tráfico de las tres aerolíneas y grupos aeroportuarios, últimos productos AFAC,
historial/disponibilidad BTS, macro y mercado hasta el corte y contexto público.
El objetivo corporativo es el mes previo; AFAC/BTS pueden cubrir meses más
antiguos. Registrar `ultimo_periodo_disponible`, `ultimo_periodo_validado` y
`ultimo_periodo_publicado` por producto. No alinear artificialmente sus meses.

**Trimestral: dos días hábiles después de la última publicación central
confirmada**, con previsión inicial en finales de abril/julio/octubre y
febrero/marzo para Q4. Para 3T26, **2 noviembre es una ventana provisional**,
condicionada al release de Viva y a los otros documentos realmente disponibles.
La fecha se traslada al primer hábil aplicable tras comprobar el calendario;
no se afirma aquí que el 2 de noviembre sea hábil bancario. Preparar un lote de las tres entidades y comparables secundarios sin exigir
que AFAC/BTS ya cubran ese mismo trimestre. Si la ronda trimestral queda a
**siete días naturales o menos** de la mensual, agrupar ambas en la fecha
posterior; si esa espera afectaría materialmente una entrega, decidir el alcance
con el dueño. Ninguna fecha de esta sección está programada.

El calendario aprobado calcula los días en America/Mexico_City con calendario
bancario mexicano. Las capturas se registran en UTC; las horas de anuncio
conservan su zona original (incluidas ET y sus cambios de horario).

### Espera, revisiones y reprogramación puntual

1. En la ronda, consultar catálogos y descargar solamente novedades/revisiones
   del alcance definido. Un 403, timeout o certificado inválido significa
   acceso fallido, no ausencia de publicación. Conservar la última versión
   válida y un pendiente de acceso; nunca saltar TLS ni ampliar permisos.
2. Fecha oficial futura: mover únicamente ese pendiente a dos días hábiles
   después de la publicación anunciada. Sin fecha: permitir un reintento
   puntual dentro de siete días o trasladarlo a la siguiente ronda mensual.
   Máximo dos reprogramaciones por lote; después registrar bloqueo para
   decisión, sin convertirlo en sondeo diario/semanal indefinido.
3. Fallo técnico transitorio: reintento acotado según el cliente HTTP existente;
   si persiste, una revisión puntual siguiente día hábil. No descargar toda
   la historia como respuesta automática al fallo.
4. Fuentes centrales trimestrales incompletas: preparar paquetes independientes
   de entidades disponibles; el agregado Industria espera sus tres insumos
   compatibles. Aprobar/publicar sigue siendo una decisión separada. Fuentes
   complementarias pendientes no bloquean automáticamente un reporte financiero.
5. Cambio de contenido: conservar original y revisión por hash, comparar filas
   y recalcular dependientes afectados. AFAC acumulado puede revisar meses
   previos; BTS puede revisar años anteriores. Conservar el vintage de cada
   cifra, la condición preliminar, filas faltantes/estimadas y corte histórico.
6. Trimestre incompleto: no sumarlo como completo ni rellenar meses con cero.
   Mostrar último mes validado/rezago; comparar con el mismo número de meses
   del año previo. Datos posteriores al corte de un análisis requieren paquete
   nuevo, no cambiar retrospectivamente el aprobado.

## Reutilización y brechas para una fase posterior

Existen `src/pipeline/{registry,runner,model}.py` (41 pasos), ingestas por fuente,
`common/http.py` (límites/reintentos), `common/storage.py` (SHA/versiones),
contratos Silver/Gold, SCD2, linaje y prioridad de fuentes. `src/rebuild.py`
reconstruye offline en checkout aislado; también ejecuta analítica/modelos, por
lo que un refresco de datos necesita alcance de pasos explícito.

Faltan descubrimiento IR por producto, revalidación de catálogos/URLs móviles,
parametrización de límites AFAC/Viva y periodos de cápsulas de análisis,
comprobación de mes BTS real, selección de años revisados, recibo de lote por
fuente/periodo y consolidación con único escritor. La existencia de un archivo
no prueba que la corrida incorporó el periodo solicitado.

El futuro coordinador puede asignar adquisición por fuente y recibir artefactos
aislados; el consolidador valida y escribe el lote una sola vez. El bloqueo de
Bronze actual es por proceso, insuficiente para varios agentes escribiendo
manifiestos en paralelo. El analista recibe evidencia/cálculo congelados y el
auditor independiente verifica la misma versión. No implementar esos agentes
ni sus schedules durante fase 1.

La entrega del 18 de octubre añade el coordinador candidato descrito en el
apéndice inicial. Conserva esas brechas por producto, sin activar schedules.

`refresh.yml` solo valida frescura/Gold, con cron trimestral; no ingiere ni
construye el sitio. Noticias del chat es manual y consume metadatos ya
comprometidos. Pages despliega `site/` revisado sin regenerarlo; Railway atiende
el chat. La cadena futura sigue siendo detección → captura → validación → lote
→ revisión/aprobación → gate → PR → despliegue verificado.

## Antecedente: aceptación de la propuesta de fase 1

Estos criterios describían la propuesta documental aprobada antes de la
implementación local descrita arriba; no son el recibo de pruebas de esta entrega.

- Catálogo legible y anexos completos respecto de las fuentes/métricas públicas
  existentes; cada producto indica grano, cobertura, método, dependencia y brecha.
- Fechas confirmadas separadas de ejemplos históricos/ventanas propuestas;
  máxima disponibilidad BTS y edición XLSX AFAC pendientes se declaran.
- Una ronda mensual propuesta y una trimestral adaptable, con agrupación y
  reintentos limitados; ninguna vigilancia permanente ni automatización creada.
- Propuesta de continuidad sin capturas AeroDataBox recurrentes separada de
  su implementación, licencia y cambios de UI.
- Documentación revisable, sin cambios de datos, código, workflows, dashboard,
  aprobaciones ni despliegues. Validación documental/consistencia de anexos;
  no ejecución de pruebas de producto por un cambio exclusivamente documental.

## Apéndice técnico: certificación aeroportuaria del 23 de octubre

Antes solo había parsers y comprobaciones parciales de tablas para AICM/AIFA.
Ahora el comando `src.source_updates.government_candidate` encadena original
retenido → observaciones nativas → Silver/Gold estándar → dimensiones/linaje
físico → replay sin red. Su integración es independiente del PR152 y conserva
la política global R/C/O de PR151. No cambia datos públicos ni tesis.

- AICM conserva pasajeros comerciales, operaciones comerciales y generales y
  carga en toneladas; compara nacional/internacional/total, meses y acumulados.
  Mantiene el comparativo anual original. Cargo admite solo el margen derivado
  del redondeo a una cifra decimal: 0,15 toneladas por suma de componentes y
  `(meses+1)×0,05` en acumulados. Los conteos se reconcilian exactamente.
- AIFA exige etiquetas físicas comercial/general/carga, unidad kg, meses,
  totales, resumen del aeropuerto y la nota que excluye aerolíneas mixtas de
  operaciones de carga antes de sumar. El archivo julio retenido indica
  `Fecha de validación: 11 Jul. 2026` y `Fecha de actualización: 11 Jul. 2026`,
  aunque declara cifras hasta `31 Jul. 2026`. Se rechaza el candidato y no
  escribe Silver/Gold. No se corrige la fecha a partir del nombre o captura.
- Ambas rutas mantienen aeropuerto, periodo, métrica, mercado, alcance y unidad;
  no atribuyen el agregado a Aeroméxico ni suman mensual y acumulado.
  Las revisiones se comparan en las observaciones nativas, con baseline
  explícito del mismo aeropuerto; una tabla Gold resumida no lo reemplaza.
  Los recibos son inmutables y fijan originales, sidecars, código, contratos,
  corte y salidas. Un escritor activo o una alteración bloquea el replay.

```bash
uv run python -m src.source_updates.government_candidate retain --product aicm_traffic --source-root <Bronze-retenido> --original pdf=<ruta-exacta-del-manifiesto> --workspace tmp/source-updates/<candidato-nuevo> --dry-run
uv run python -m src.source_updates.government_candidate certify --product aicm_traffic --workspace tmp/source-updates/<candidato> --period 2026M08 --as-of 2026-10-23T12:00:00-06:00 --retention <id> --dry-run
```

Usar `--execute` solo para construir y `--check` para reproducir. AIFA usa
`--product aifa_traffic` y rol `workbook`; el original julio actual termina
bloqueado. El lote `retained_round` elige el certificador completo y se detiene
al primer fallo, conservando éxitos previos. El coordinador de revisión usa
`adapter=government`. Ninguno hace una captura nueva, comprueba la publicación
más reciente ni activa el calendario. La fecha de actualización interna no se
convierte en primera publicación o rezago de publicación.

Prueba real offline del código `bb39b6c104abc492d6e03339745d1b7f0aa0a54e`,
confirmado en Git antes de generar candidatos. Se conservaron los originales:

| Original oficial retenido | Observaciones nativas | Silver/Gold de tráfico | Reconciliaciones | Enlaces físicos |
| --- | ---: | ---: | ---: | ---: |
| [AICM julio](https://www.aicm.com.mx/acercadelaicm/archivos/files/Estadisticas/EstadisticasJul2026.pdf) | 189 | 19 / 19 | 90 | 208 |
| [AICM agosto](https://www.aicm.com.mx/acercadelaicm/archivos/files/Estadisticas/EstadisticasAgo2026.pdf) | 198 | 20 / 20 | 93 | 218 |
| [AIFA julio](https://aifa-repositorio.s3.us-east-1.amazonaws.com/PyE/Numeralia-Aeroportuaria-Jul-2026.xlsx) | Rechazado por fechas | Sin salidas | No certificado | Original retenido |

Los 19/20 meses AICM incluyen los doce comparativos de 2025 y siete/ocho de
2026; no son 19/20 meses nuevos ni cifras de una aerolínea. Los originales
SHA-256 son `974c308d2ad975af94c13e493f13d5c87c8ac4ab6a6a961e16719a4f50402a68`
(julio), `8ef46795b2e3b690131b2e38a629aba4271c71f974c92ca25e3201b2503a3273`
(agosto) y `8585dc7bf86a276d3fd2e0d1d2e874dde57bd51057fcc4b8fc53af878b465243`
(AIFA). Capturas conservadas: 21/ago para julio AICM y 19/oct para agosto/AIFA.
No se hicieron consultas nuevas a estas fuentes ni solicitudes pagadas.

El lote de tres tareas se detuvo al certificar AIFA. Conservó los dos
candidatos AICM y su replay idéntico, comprobados además por el verificador
real de la ronda. Una tercera certificación de agosto comparó sus observaciones
nativas contra julio: 171 claves comunes sin cambio, 27 altas y 18 bajas por
mes nuevo/acumulados distintos; cero revisiones de valor en las claves comunes.
Esto compara esas dos ediciones retenidas; no verifica revisiones posteriores.

Muestra de salida del lote probado:

```text
AICM 2026M07: checks_passed; native=189; Gold=19; replay=identical
AICM 2026M08: checks_passed; native=198; Gold=20; replay=identical
AIFA 2026M07: blocked; Esquema Operativo!C4=11 Jul. 2026 < cierre 31 Jul.
network_requests=0; paid_requests=0; activation=none; publication=not_authorized
```

La revisión adversarial independiente del código fijado aprobó 50 casos.
Reprodujo y cerró fallos de unidades/etiquetas, fechas locales, inicio del
periodo, precisión numérica e identidad del aeropuerto. Esas pruebas sintéticas
validan contratos; no resuelven la contradicción del archivo oficial AIFA.
Las 86 pruebas focales y de regresión pasaron, incluido el presupuesto de
archivos y las rutas heredadas. Una ronda global real con solo AICM válido
quedó `blocked_global_policy`: 15 productos mensuales requeridos ausentes,
`core_ready=false` y `ready_for_calendar_incorporation=false`; su replay fue
idéntico y conservó los candidatos. Así se comprueba que cerrar un producto
no declara lista la ronda. El cierre final de CI y la integración se registran
en el PR de esta entrega.
El resumen local, recibos y hashes se conservan bajo
`tmp/source-updates/government-proof-20261023-bb39b6c1-summary.json` y
`government-batch-proof-20261023-bb39b6c1/`; son evidencia regenerable local,
no copias de Bronze publicadas en Git ni aprobación de datos. SHA-256 del
resumen final: `4d9446a4d94dab4118f8407f072d7597f5d38818c47709dc414668e15dcd5a61`.
Los intentos de prueba previos se retienen como evidencia, sin confundirlos con
esta reproducción del código final.

### Finanzas Viva: certificador de las tablas 2T26

El nuevo adaptador está preparado para comprobar el [informe 2T26 retenido](https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-2T26-en.pdf),
con el [1T26](https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-1T26-en.pdf)
solo como soporte de comparación. Ambos originales pasaron la certificación
local, la reproducción sin red y un cotejo independiente de todas sus tablas.
La integración requiere CI y revisión automática del mismo head; el estado
exacto se registra en [PR156](https://github.com/salvamalfa/aeromexico-tracker/pull/156).
No certifica otra edición ni disponibilidad reciente.

La salida separa trimestre, semestre y balances a una fecha. Mantiene USD,
escalas, millas, pasajeros reservados y notas preliminares/no auditadas.
Conserva el contexto macro en Silver, sin usarlo en Gold. Cada dato Gold solo
puede tener su verdadero padre de la edición 2T26. Para vincular un release
trimestral, el coordinador admite solo el PDF que aporta esas cifras Gold:
el soporte 1T26 no puede hacerse pasar por publicación 2T26. La comparación con 1T26
registra diferencias, pero no las presenta como una reexpresión acreditada ni
permite deducir un 1T26 validado restando semestre menos trimestre.

Comando: `python -m src.source_updates.viva_financial_candidate`. Los modos
`retain` y `certify`, los dos roles y la reproducción `--check` están en la
[skill corporativa](../.agents/skills/airline-update-corporate/SKILL.md#finanzas-viva-retenidas-tablas-y-comparación-entre-ediciones).
El contrato propio está en `contracts/source_updates/viva_financial_source.json`;
estas observaciones no se incorporan al warehouse, al sitio ni a perfiles.
No se ejecutó ingesta, calendario ni publicación.

La prueba real del código funcional `b899c3ab` produjo 655 filas Silver,
386 cifras Gold, dos artefactos y 1.427 enlaces de linaje para 1.041 registros.
Conserva 398 observaciones de la edición 2T26 y 257 del soporte 1T26. Las doce
filas de contexto macro de 2T26 no pasan a Gold. Se verificaron 252 identidades
y ratios. Los importes usan intervalos de precisión publicada; los conteos
de aviones exigen igualdad exacta, sin tolerancia de redondeo. No se recalcula la ocupación
de itinerario desde totales distintos. La fecha impresa de 2T26 es 24/jul/2026;
la captura retenida es 24/ago/2026. No se atribuye una primera publicación ni
un rezago conocido. No se hace otra descarga.

El examen entre ediciones conserva 42 diagnósticos. Seis exceden el redondeo,
todos en el 1T26 implícito: H1−Q2 difiere del 1T26 publicado en gastos operativos
(+USD1.212.000), soporte operativo (+USD1.397.000), comercialización
(−USD185.000), costos financieros y su neto (+USD1.212.000 cada uno), y
resultado operativo (−USD1.212.000). No existe aquí evidencia de su causa.
Eso exige revisión antes de armonizar históricos; no bloquea las cifras
directas 2T26 que sí pasan sus propias identidades. Ningún diagnóstico se
publica como un 1T26 validado ni da aprobación a los datos.

Los dos PDF conservan SHA-256 `4fca922642ce3fe06743578064239107539b0546c1519a11abecb0eef098bc7f`
(2T26) y `9ff9a82afff61477908acd10018be79333210b6dcaa90cabb90bffffa04e8ab7`
(1T26). El resumen reproducible y las recetas permanecen locales bajo
`tmp/source-updates/viva-financial-official-b899c3ab-summary.json`, SHA-256
`9c030c92bb3e6e2c5eeeeb60c16162e7b5fdcaeca85fe715d1b74104226d445d`.
Los originales/candidatos y recibos están en las carpetas `viva-financial-official-b899c3ab/`,
`viva-financial-readiness-b899c3ab/` y `viva-financial-global-b899c3ab/` del
mismo directorio. Se conserva el intento anterior bloqueado, sin sobrescribirlo.
La recuperación usa las dos filas Bronze retenidas, sus sidecars/manifiesto y
el código fijado. No se añaden los PDF ni cifras candidatas al repositorio público.

Muestra de ejecución real y comprobación global, sin disparadores:

```text
Viva 2026Q2: checks_passed; Silver=655; Gold=386; artifacts=2; bridge=1427
retained_round: checks_passed; offline_replay_identical=true
readiness: checks_passed; ready_for_calendar_incorporation=false
global combined (junio/2T26): blocked_global_policy; 22 comprobaciones requeridas ausentes
core_ready=false; quarterly_date=null; releases=[]
network_requests=0; paid_requests=0; activation=none; publication=not_authorized
```

Es una muestra acotada de un producto, no una ronda completa. La matriz global
mantiene Aerocivil/GDELT requeridos y bloqueados, disponibilidad reciente sin
acreditar y releases sin suministrar. Las pruebas de contrato son sintéticas;
los conteos anteriores provienen de los dos PDF retenidos reales. Un revisor
independiente reconstruyó todas las columnas, unidades, padres y diagnósticos
sin usar las funciones del producto: no encontró discrepancias. Los 21 casos
adversariales independientes están incluidos en las 51 pruebas focales que
pasaron. La compatibilidad con PR152/154/155 se comprueba en una rama local
separada; sus heads remotos y revisiones pendientes se preservan.

### BTS: originales retenidos, candidato mensual y revisiones (23/oct)

El certificador `src.source_updates.bts_candidate` produce siete tablas en un
candidato aislado: Silver nativo completo, hechos de tráfico del mes pedido,
dimensiones de ruta/aerolínea/periodo, artefactos y puente de linaje. No llama
al parser global que escribe el crosswalk. `retained_round` y `readiness`
requieren el adaptador `bts`; el genérico se rechaza. El archivo puede cubrir
meses posteriores al solicitado, para volver a certificar un mes revisado.

Dos ZIP oficiales de [BTS T-100](https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FJE&QO_fu146_anzr=Nv4%20Pn44vr45)
retienen sus fechas reales de captura, 24/ago y 19/oct/2026. SHA-256:
`590001141ec9907ef392d424bfae910cc7024e8bf6a32fdc5b3948878e2f64a6` y
`99042e468c788d8b22636afba1ac8a4da806ea45f6f3b4e4745b218df6a33754`.
El segundo se recuperó del respaldo ya autorizado, commit privado
`84361b529e93b0e56cd91aae7e1750900c3146a8`, bajo
`review/coverage/20261019/captures/coverage95-20261019/`: solo ZIP público,
sidecar y su fila de manifiesto; no se restauró un snapshot ni se copiaron
insumos privados a este PR. El primer original ya estaba retenido localmente.

Ambos contienen `Documentation.csv`, que acredita pasajeros por tramo,
asientos, libras, millas y minutos, además de identidad DOT. Su hash físico
es `ef7475e8c29e62aba2b5c46caf24dd726019f66977b603aa6db7a1241ae5c342`.
El lector comprueba los 30 campos y definiciones exactas; también conserva
hash del miembro de datos, número de fila y valores literales. El diccionario
no trae leyenda F/G/L/P: los códigos se conservan sin atribuirles regularidad.
Todas las identidades casan con los seis campos exactos del crosswalk;
las referencias `carrier_crosswalk.csv` y `dim_carrier.parquet` se verifican
y sus huellas se fijan en cada recibo. No se actualizan esas referencias.

La prueba real del código funcional `da3f927e` produjo:

| Original / mes pedido | Filas nativas en Silver | Hechos Gold del mes | Filas del puente |
|---|---:|---:|---:|
| Captura agosto / mayo | 9.260 | 1.660 | 12.580 |
| Captura octubre / julio | 12.459 | 1.527 | 15.513 |
| Captura octubre / mayo revisado | 12.459 | 1.665 | 15.789 |

Cada agregado conserva todos sus padres nativos, incluidos entidad y
configuración que no forman parte del grano Gold. ASM/RPM se calculan por
fila antes de sumar; ocupación es RPM/ASM y queda nula con capacidad cero.
La distancia es mediana, nunca suma; libras y millas se convierten con factores
explícitos. Las referencias huérfanas y las identidades ambiguas se rechazan.

Las dos versiones comparten 9.260 observaciones sin cambios de valor ni bajas,
pero octubre añade **cinco observaciones retrospectivas de mayo**, además de
3.194 filas de junio/julio. La proyección Gold de mayo conserva esas cinco
altas: no se declara «sin revisiones» por comparar solo la intersección.
Silver y las revisiones retienen el año completo, separado del mes proyectado.

Existe una incidencia oficial en abril: operador `27Q`, SJD→VNY, clase `L`,
14 pasajeros y 13 asientos. Permanece literal en Silver fuera de las
proyecciones mayo/julio, señalada en sus recibos; no se certifica abril como
válido. Solicitar abril detiene la ejecución antes de Silver/Gold y conserva
Bronze. Realizados superiores a programados se conservan, pues esa relación
no acredita por sí sola un error. Tampoco se acredita cobertura completa:
Aerovías en junio conserva 297 realizados MX→US y 982 US→MX en clase `F`.
Esos códigos no equivalen a una etiqueta de servicio inventada por el lector.

Muestra de ejecución real, con replay idéntico de candidatos y control global:

```text
BTS 2026M05 / agosto: checks_passed; native=9260; Gold=1660
BTS 2026M07 / octubre: checks_passed; native=12459; Gold=1527
BTS 2026M05 / octubre: checks_passed; Gold=1665; historical_added=5
BTS 2026M04 / octubre: blocked; passengers_exceed_seats; no Silver/Gold
global combined: blocked_global_policy; 22 comprobaciones requeridas ausentes en la muestra
core_ready=false; ready_for_calendar_incorporation=false
network_requests=0; paid_requests=0; activation=none; publication=not_authorized
```

Para reproducir con un original explícito ya autorizado:

```bash
python -m src.source_updates.bts_candidate retain --product bts_segments --source-root <Bronze-retenido> --original archive=<ruta-relativa-ZIP> --workspace tmp/source-updates/<candidato-nuevo> --dry-run
# Revisar la selección; repetir retain con --execute y conservar el run_id.
python -m src.source_updates.bts_candidate certify --product bts_segments --workspace tmp/source-updates/<candidato-nuevo> --period 2026M07 --as-of 2026-10-23T12:00:00-06:00 --retention <run_id> --dry-run
# Certificar con --execute; repetir con --check sin escribir ni usar red.
# Para revisiones: baseline explícito bajo baselines/, --baseline baselines/previous-native.parquet.
```

El resumen final y la receta global se conservan localmente bajo
`tmp/source-updates/bts-proof-20261023-da3f927e-summary.json` y
`bts-proof-20261023-da3f927e/`; SHA-256 del resumen:
`d7db69e22ab887d1404bd3130ef4a5e86982bccd3ad0b41aceb78637ac1cd35e`.
Son evidencia regenerable y originales retenidos, fuera de Git público. Los
intentos previos se conservan separados. La fecha de primera publicación y el
rezago siguen nulos; retención no significa captura nueva ni disponibilidad
reciente. El resultado global permanece bloqueado por Aerocivil/GDELT,
productos ausentes y releases comprobados faltantes; no activa el calendario.

Pasaron 302 pruebas focales y de regresión, con 17 casos adversariales
independientes incluidos. Cubren valores/periodos/identidades inválidos,
revisiones retrospectivas, sumas grandes sin desbordamiento, agregación de
configuraciones, unidades, linaje completo, fechas de vigencia, alteración de
originales/salidas/recibos y replay inmutable. Las pruebas sintéticas validan
contratos; la tabla anterior corresponde a extracción de originales reales.
Un revisor independiente cotejó todas las filas nativas, cada agregado de las
tres proyecciones, conversiones, referencias, padres y hashes contra los CSV
oficiales, sin usar las funciones del producto: no encontró discrepancias.
La revisión independiente de código y el cierre remoto se registran en el PR;
la CI y aprobación del head final no se sustituyen por las de otro commit.

### Certificación integral GAP y ASUR: continuación del 23 de octubre

El lote añade `airport_group_candidate` para los originales SEC de tráfico
julio 2026. Es certificación técnica de originales retenidos, no una captura
nueva ni una comprobación de disponibilidad de septiembre/octubre. Los hechos
Gold candidatos son de México; Jamaica, Puerto Rico, Colombia y el total
mundial se conservan separados en la evidencia nativa. No se cambian datos
públicos ni se activa el calendario. PR152 y su revisión pendiente permanecen
intactos; este lote parte del master posterior a PR153.

GAP publica cifras preliminares en miles con un decimal. Se conserva esa
precisión: no son pasajeros exactos. México se calcula sumando doce aeropuertos
redondeados; no se presenta como total mexicano reportado ni se obtiene
restando Jamaica del total mundial. CBX ya está en internacional Tijuana.
ASUR aporta pasajeros enteros y nueve aeropuertos mexicanos que deben
reconciliar exactamente con el resumen México. Su nota de exclusión de tránsito
y aviación general se aplica solo a México y Colombia. Carga y operaciones
ausentes quedan nulas en ambas fuentes.

El lector exige CIK, títulos físicos, unidad, mes completo, comparativos,
acumulado, dominios de aeropuertos y mercados y reconciliaciones. Rechaza
acumulados inferiores al mes fuera de su precisión; enero debe ser igual a su
acumulado. GAP admite solo la cota matemática del redondeo, sin ajustar cifras;
ASUR exige igualdad entera. El linaje de cada hecho conserva precisión y
alcance; el total México calculado de GAP declara sus doce contribuyentes.

Usar el [procedimiento de la skill](../.agents/skills/airline-update-airports/SKILL.md#certificación-integral-gap-asur).
La importación selecciona rol `html`; `certify` requiere producto, mes, corte
con zona y recibo de retención. Mostrar `--dry-run`, construir `--execute` y
reproducir `--check` sin sobrescribir. `retained_round` despacha este lector;
la ronda usa `adapter=airport_group`. El plan `--family airports` incluye GAP y
ASUR por producto, aunque la institución sea SEC; los financieros SEC siguen
en empresas. El lector genérico se rechaza para estos
productos. Cada candidato contiene nueve tablas verificadas: dos Silver,
dos hechos Gold, tres dimensiones, artefactos y puente físico.

La comparación de revisiones usa el grano nativo y también unidad, precisión,
país, definición, preliminar y estado reportado/calculado. La copia previa
debe ser explícita, del mismo grupo y bajo `baselines/`; no se puede comparar
solo Gold y omitir cambios del acumulado o de países. Sin copia se registra
`not_compared_no_baseline`. La fecha declarada del reporte sigue separada de
primera publicación y retraso de publicación; estos últimos siguen nulos.

Referencias físicas revisadas: [GAP, 6-K de agosto con tráfico julio](https://www.sec.gov/Archives/edgar/data/1347557/000117184326005269/f6k_080526.htm),
SHA-256 `dca6191444514e1f6686e661041f4b4d85dd21f9ff9c8a341259cf64ba87207c`,
y [ASUR, tráfico julio](https://www.sec.gov/Archives/edgar/data/1123452/000110465926091204/tm2622355d1_ex99-1.htm),
SHA-256 `d6cbec01f6e095752d4ad5af25a4d48cdd4c3ec06179ee3caf1662f4d82e1cc5`.
Ambos originales fueron capturados el 21 de agosto; declaran fecha del reporte
5 de agosto. La prueba reutiliza los bytes y fechas originales. No llama a SEC
ni configura identidad/credenciales.

Los originales de junio se probaron solo en lectura y quedan fuera del formato
revisado de este lote: GAP usa otra representación de fecha y ASUR otra
cabecera. Se rechazan antes de producir Silver/Gold; no se afirma completitud
histórica ni aceptación automática de cualquier edición.

La prueba real offline quedó fijada en código `24a18edb`: GAP produjo
192 observaciones nativas, 26 filas Silver, 24 hechos por aeropuerto y dos de
grupo, con 72 reconciliaciones y 434 filas de linaje. ASUR produjo 156 nativas,
20 Silver, 18 hechos por aeropuerto y dos de grupo, con 88 reconciliaciones y
176 filas de linaje. Cada candidato pasó contratos, dimensiones y hashes
físicos; el lote ejecutó y reprodujo ambos productos sin red. En julio 2026,
México GAP suma 5.333.600 pasajeros redondeados y calculados; ASUR reporta
3.473.501 enteros. Son totales aeroportuarios, no tráfico de una aerolínea.

Una copia explícita del mismo original usada como baseline resultó en
192/156 observaciones sin cambios; no prueba que el emisor no haya revisado
otras versiones. Las pruebas independientes sí introducen cambios en YTD,
país, definición y preliminar para comprobar que se detectan. El replay
comprueba tablas, bytes, contratos, corte y huellas del código sin escribir.
La ronda limitada a esas dos tareas pasó; la ronda global combinada siguió
`blocked_global_policy`, con `core_ready=false` y calendario no listo. Faltan
los demás productos requeridos, incluidos Aerocivil/GDELT y releases del
trimestre; una prueba local de dos fuentes no levanta esos bloqueos.

Pasaron 263 pruebas focales/regresión; dos verificaciones del almacén local se
omitieron porque ese checkout no tiene `warehouse.duckdb`. No se restauró ni
modificó el almacén público para convertirlas en aprobadas. La revisión
adversarial independiente aprobó 43 casos y ocho controles adicionales de la
ruta genérica cerrada. Después del arreglo de selección por familia pasaron
dos casos nuevos del plan y 128 regresiones de catálogo/política/plan; la
revisión independiente añadió cinco pruebas, incluida la CLI sin HTTP.
Son 56 casos independientes en total. El hallazgo de YTD/enero quedó atendido. Ruff, diff y
presupuesto de módulos pasaron. CI y revisión Codex del head final se cierran
en el PR; los resultados de un head anterior no sustituyen los nuevos.

Evidencia local regenerable, fuera del Git público:
`tmp/source-updates/airport-group-proof-20261023-24a18edb-summary.json`,
SHA-256 `32d199d7ac03d5f5a08c4863584db82ea624b710097a59aebc3c2fb5ad7d5476`.
Los originales, candidatos, baselines, recibos de lote/ronda y fallos de
harness previos se conservan en los workspaces `airport-group-proof-*`.
El harness inicial invocó por error `readiness.run`, que no existe; se corrigió
a `execute` y se retomaron los candidatos por replay, sin reconstruirlos ni
sobrescribir. Tras acortar el guard genérico para cumplir el presupuesto de
600 líneas se emitió la prueba final en workspaces nuevos con su nueva huella.
No se afirma que los recibos antiguos pertenezcan al código final. Una colisión
de nombre en el harness de resumen se corrigió con una importación explícita;
los recibos ya escritos se retomaron por `--check`, sin repetir escrituras.

Muestra resumida del plan real al corte `2026-10-23T10:00:00-06:00`: antes
mostraba tres productos de aeropuertos y ahora muestra cinco, todos con
objetivo septiembre. Esta selección no certifica septiembre desde julio:

```json
{"mode":"dry_run","products":["gap_traffic","asur_traffic","oma_traffic","aicm_traffic","aifa_traffic"],"target_period":"2026M09","network_requests":0,"writes":[],"activation":"none"}
```

La salida completa vive en `family_plan` del resumen local. SEC mantiene su
identidad institucional y sus financieros conservan familia/cadencia. La
política global no cambia: la prueba combinada con dos fuentes conserva 21
requisitos ausentes y fechas de releases sin verificar.

### Compatibilidad local preparada con PR153

El merge normal de PR153 fijó `master` en
`7a1b1b1ce3d51478a40bd42b4cc72e48838f9012`. El head remoto de PR152 sigue
`3a89c6dc`, con su revisión adicional pendiente: no se ha sustituido ni se ha
relanzado. La nueva base produce cuatro conflictos en la guía, registro y
despachos de adaptadores. La resolución se preparó en un checkout temporal
sin rama y **no se publicó**: commit de código
`33597e02bf93155a38924311de0fef8503a4fcb5`, con ambos heads como padres.
Conserva ambos registros y recibos, rechaza adaptadores equivocados y mantiene
los bloqueos de disponibilidad/calendario y las rutas heredadas.

Validación local de esa propuesta: 355 pruebas de regresión y 41 independientes,
Ruff y lifecycle de 15 archivos sin errores. Un lote de originales oficiales
retenidos recorrió EIA `2026Q3` (64 observaciones, ocho hechos Gold) y AICM
`2026M08` (198 observaciones nativas, 20 hechos Gold); comprobó los dos despachos
y el replay conjunto sin red ni escrituras en los candidatos aceptados.
`ready_for_review=true` solo corresponde a esas dos tareas, no a la ronda
completa ni al calendario. Resumen local
`tmp/source-updates/compatibility-mixed-proof-33597e02-summary.json`, SHA-256
`7f91cbecf5205359be329d643b04a6b0eb50dc3d2d7ac3f4aac5409a487a4235`.
El arnés inicial esperaba por error el estado textual `ready_for_review`;
el protocolo usa `status=checks_passed` y un booleano aparte. Se corrigió esa
aserción y pasó el replay de lectura; no hubo reconstrucción o sobrescritura.

Esta evidencia no es CI ni revisión Codex de un head nuevo de PR152. Mientras
su revisión vigente siga pendiente, la propuesta permanece local. Después de
resolver ese proceso, cualquier actualización del PR necesita CI y revisión
sobre su head exacto y la base entonces vigente. Las pruebas de heads anteriores
no sustituyen esos controles.

## Apéndice técnico: certificación integral RSS retenido

El nuevo certificador candidato usa los XML Google News retenidos, sin visitar
artículos ni activar noticias. Comprueba la captura física y todos sus items,
no solo la frescura de una tabla Gold. La prueba real del código
`906a829b` verificó siete capturas con sus sidecars: 700 registros nativos,
12 grupos Gold del mes, siete artefactos y 724 vínculos. Los 688 registros
fuera de septiembre se conservan en Silver. Son seis días observados
(1, 2, 3, 21, 28 y 30) y 24 sin observaciones, sin afirmar ausencia de noticias.
Un revisor independiente reconstruyó las cuatro salidas desde los XML,
sin importar funciones del producto: no encontró discrepancias. Las
57 pruebas RSS incluyen 28 casos independientes; junto con regresiones de
readiness, política global, noticias y presupuesto pasaron 202 casos.
La suite completa, CI y revisión del head final tienen su evidencia vigente
en [PR157](https://github.com/salvamalfa/aeromexico-tracker/pull/157).

`python -m src.source_updates.rss_candidate batch --recipe <receta.json>
--workspace tmp/source-updates/<lote-nuevo> --dry-run` muestra la selección y
el plan sin escribir. `--execute` encadena retención, Bronze, Silver, Gold y
reproducción. La receta declara `version: 1`, `as_of` con zona, `source_root`,
`period` (`YYYYMmm`) y `originals` (rutas explícitas del manifiesto). El hijo
`rss-<period>` conserva originales y recibos; un fallo deja etapa y motivo en
el recibo del lote. Para repetir sin escrituras usar `certify --workspace
<hijo> --period <mes> --as-of <corte-original> --retention <id> --check`.

El contrato `rss-declared-metadata.schema.json` comprueba cuatro salidas JSON
aisladamente: observaciones nativas, metadatos Gold del mes, artefactos y
puente de trazabilidad. Silver conserva todos los items y sus posiciones,
incluso repetidos y fuera del mes. Gold agrupa por URL canónica y día de
México, preservando todas las contribuciones y variantes. No presta el título,
fecha o medio de una captura a otra. Los enlaces Google opacos no se resuelven.

Se exige HTTP 200, hashes/tamaños y manifiesto/sidecar coherentes, RSS 2.0,
canal Google correspondiente a consulta/región, y fechas con zona anteriores
a la captura. Un item inválido bloquea antes de escribir Silver/Gold. Se
rechazan entidades/DOCTYPE, cambios de formato, omisiones, padres prestados,
recibos alterados y cortes incompatibles. Los candidatos son inmutables.

`--baseline baselines/<gold-previo.json>` compara metadatos del mismo mes y
consultas. Una recaptura idéntica no es revisión; cambios de título u otras
declaraciones se conservan sin acreditar una corrección del medio. El baseline
queda fijado por SHA y su procedencia interna debe ser consistente.

Las fechas son declaraciones RSS del agregador. No verifican la publicación
del cuerpo del medio, fecha del evento ni primera disponibilidad. Estas
últimas y el rezago permanecen nulos. No se infieren idioma ni compañía del
artículo. Las consultas históricas seleccionadas buscan Aeroméxico: no
acreditan cobertura de Viva/Volaris ni el mes completo. Días no observados
no significan ausencia de noticias. `readiness` usa `rss_retained`; la política
global conserva GDELT requerido y la disponibilidad actual sin acreditar.
No se modifica el archivo mensual aprobado, el warehouse ni el sitio.

Evidencia local y recetas: `tmp/source-updates/rss-official-906a829b-summary.json`,
SHA-256 `cade40a032b637cd5f7a5558736c381d67644f13e4bdd7e4652800c6d4a8db4c`.
Originales/candidato y recibo de lote: `rss-official-906a829b/`; reproducción
de ronda: `rss-readiness-906a829b/`; control global: `rss-global-906a829b/`,
todos bajo `tmp/source-updates/`. El verificador independiente se conserva
junto al lote, fuera del hijo candidato. Recuperación: los siete XML originales,
sus sidecars/manifiesto y el commit fijado. No se suben al repositorio público.

```text
RSS 2026M09: checks_passed; native=700; Gold=12; artifacts=7; links=724
batch: checks_passed; offline_replay_identical=true; article_requests=0
readiness: checks_passed; ready_for_calendar_incorporation=false
global monthly: blocked_global_policy; core_ready=false
network_requests=0; paid_requests=0; scheduled_executions=0
activation=none; publication=not_authorized
```

Esta prueba conserva las consultas históricas exactas, distintas de las
consultas actuales de tres aerolíneas. La captura no verifica disponibilidad
reciente, cobertura de las otras compañías ni publicación de sus medios.
Los candidatos y baselines no aprueban contenido ni tesis. Las compatibilidades
con los lotes pendientes se comprueban por separado antes de integrar;
los heads en revisión no se modifican.

## Apéndice técnico: dossiers Volaris SEC y AFAC por aerolínea

El lote siguiente prepara dos certificadores integrales aislados con contrato
`carrier-source-observation.json` y tablas de observaciones propias. No cambia
el warehouse ni datos públicos. `carrier_source_candidate retain` conserva los
roles explícitos; `certify` valida el dossier completo antes de escribir cuatro
salidas: nativo Silver, observaciones Gold, artefactos y puente Stage 9.
`--check` reconstruye originales, contratos, selección y linaje y compara
archivos/recibo sin escribir. `retained_round` encadena ambas fases; readiness
requiere `carrier_source` y rechaza reemplazarlo por `retained` o Gold heredado.
Los comandos y roles están en las skills corporativa y tráfico enlazadas arriba.

AFAC usa el PDF mensual y `DB_AFAC.zip` de igual edición. Valida las seis
columnas de conteos de ambas páginas y los meses/servicios de la base completa
2024/2025/2026. Gold mensual conserva regular del PDF con soporte de todas las
filas DB que lo justifican y cada fila charter actual única; un duplicado
charter bloquea. Preserva nombres literales, `World 2 Fly`, desconocidos sin
mapeo, y Aerovías/Connect separados. La declaración preliminar debe existir;
los estimados aplican solo por nombre y periodo declarados. El boletín advierte
información internacional incompleta; conciliar cifras reportadas no acredita
la totalidad de operaciones. No se reparte un total entre rutas.

Volaris se limita al dossier SEC `0001292814-26-003836`, sus cuatro roles y
11 tablas revisadas. Q2, H1 y saldos se conservan separados. Pasajeros reservados
no se renombran transportados, millas no se renombran kilómetros, y los guiones
siguen desconocidos. Fecha impresa 21/jul y aceptación SEC no prueban primera
publicación; el rezago de presentación SEC es 21 días, otro concepto.
**La fuente real está bloqueada**: CASM H1 2025 de 7,97 centavos no concilia
con gastos 1.403 millones y ASM 17.622 millones. Con ±0,5 de cada unidad impresa,
el máximo es 7,964702210368…, inferior al mínimo 7,965 que redondearía a 7,97.
La definición y la nota (2) tienen igual alcance de itinerario/chárter; no se
halló precisión retenida del total de gastos operativos o ASM que resuelva
la relación. El mismo anexo sí contiene precisiones parciales en miles de USD
(depreciación, arrendamientos, pérdida neta e ingresos); no acreditan un
numerador alternativo para CASM ni una regla para ampliar tolerancias.
El control también concilia EPS básico/diluido con resultado neto y acciones
promedio, y ADS con diez CPO. Para fijar el release financiero solo sirve el
anexo financiero verificado; índices/submissions/portada 6-K apoyan la identidad
pero no sustituyen el reporte central. No se omite el comparativo ni se emiten
Silver/Gold aceptados. Falta aclaración
o evidencia oficial suficiente para resolverlo. Un contrato sintético positivo
no certifica este original ni tráfico mensual Volaris.

La comparación de revisiones exige baseline nativo completo del mismo producto
y edición, con originales/manifiesto/sidecars/recibo bajo `baselines/`.
Se reconstruye antes de comparar; así cambios históricos o acumulados no se
ocultan cuando Gold mensual permanece igual. Cuenta altas/bajas por cambio de
posición sin presumir equivalencia. Sin baseline explícito, registra ausencia
de comparación; ninguna comparación acredita una revisión oficial.


Prueba real en código funcional `b4320e882e17a2bca7b54fe245bb9044c3517f8d`:

| Producto retenido | Resultado comprobado | Límite real |
|---|---|---|
| AFAC por aerolínea, agosto 2026 | 4.930 nativas (498 celdas PDF + 4.432 filas DB), 112 Gold, 2 artefactos, 5.294 vínculos; 474 conciliaciones exactas. Replay idéntico | El original declara información internacional incompleta; no acredita disponibilidad actual |
| Volaris SEC, 2T26 | Roles y original conservados; certificación bloqueada en tabla 300, fila 23, columna 2 (CASM H1 2025) antes de crear Silver/Gold o recibo aceptado | Falta aclaración/precisión oficial suficiente; tampoco se ha acreditado un original de tráfico mensual |

Los originales AFAC son el [boletín agosto](https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_2026_08.pdf)
y la [base DATATUR](https://datatur.sectur.gob.mx/Documentoscompartidos/afac/DB_AFAC.zip)
retenidos el 19/oct. No se volvieron a descargar. La contradicción Volaris está
en el [anexo oficial](https://www.sec.gov/Archives/edgar/data/1520504/000129281426003836/ex99-1.htm)
retenido el 24/ago: tabla 300, filas 2/23/26, columna 2, y gastos repetidos en
tabla 306, fila 22. La comprobación usa estos bytes, no el estado actual de URL.

Resumen/receta/plan/recibos locales:
`tmp/source-updates/carrier-official-b4320e88-summary.json`, SHA-256
`4fea08adce7934c601de27dbae6df9b2441903f6f5e9924baf01ec8438754d02`.
Auditoría independiente sin importar módulos del producto:
`carrier-official-b4320e88/afac-independent-review.json`, SHA-256
`96065877268e2e61488f0d25beddfb27f40e304b570205da63587192e600869a`.
Reconstruyó los 36 campos nativos, 39 Gold, cada padre/artefacto/vínculo,
las 117 huellas de código físicas/Git y las 474 conciliaciones. Los 24 ceros
explícitos PDF sin observación DB no se imputaron a la base. `World 2 Fly`
conserva 62 observaciones nativas y su nombre literal.

El lote ejecutable terminó `blocked` por Volaris tras validar AFAC. El replay
individual y `carrier-readiness-b4320e88/` pasan; `carrier-global-b4320e88/`
permanece `blocked_global_policy`, con Aerocivil/GDELT y el resto del alcance
obligatorio ausentes/bloqueados. Ninguna ronda completa ni calendario queda
aprobada por este resultado. Muestra literal del dry-run/resultado:

```text
AFAC 2026M08: retain → Bronze → Silver → Gold/lineage → offline_replay
checks_passed; native=4930; Gold=112; artifacts=2; links=5294; reconciliations=474
Volaris 2026Q2: blocked at certify; table 300 / row 23 / column 2
Silver/Gold/accepted receipt: absent; originals retained
network_requests=0; paid_requests=0; activation=none; publication=not_authorized
ready_for_calendar_incorporation=false
```

La pasada final de toda la familia `source_update` y límites del repositorio
pasó **950 pruebas** en 102,16 s. Las pruebas
sintéticas incluyen expediente AFAC físico PDF/ZIP de tres años,
contrato Volaris completo, casos positivos y negativos, baselines físicos y
rechazo de índices/portada como release. Pasan 80 pruebas independientes; la
revisión adversarial cerró todos sus hallazgos sin modificar tolerancias de
Volaris. El CSV de entidades y los JSON de estos módulos usan UTF-8 explícito;
la salida CLI JSON escapa Unicode para terminales ASCII. El dry-run conserva
`latest_validated_period=null`; solo `checks_passed` informa el periodo
realmente certificado. Cuatro casos del límite de medianoche verifican que AFAC
solo acepte un mes cerrado en America/Mexico_City; no basta el cierre UTC.
Dos pruebas en
subprocesos comprueban locale no UTF-8 y stdout ASCII, sin afirmar portabilidad
integral de los helpers compartidos. La prueba física repetida conserva las
cuatro salidas idénticas a las anteriores. La suite completa, CI/revisión del
head final e integración conservan
su evidencia propia en el PR de este lote. La ejecución local de la suite
pública se detuvo por ausencia del pin externo aprobado
`CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256`: la primera pasada llegó a 208
pruebas aprobadas; la diagnóstica reprodujo 2 fallos y 16 errores del mismo pin
tras 235 aprobadas. Ninguna equivale a suite pública completa aprobada.
La lectura del valor por GitHub recibió 403; no se cambiaron variables, permisos
o gates. La CI del head `4c24afeb` falló en el subset público; sus anotaciones
solo informaron salida 1 y la lectura del log del job recibió `Forbidden`,
sin reintentos. Se reprodujo una regresión concreta del lote en el test
`test_repo_budgets.py`: `retained.py` creció a 605 líneas frente al límite 600.
El registro de roles se trasladó al contrato y quedó en 594 líneas, sin ampliar
excepciones. La revisión independiente verificó specs exactos y guards/transformaciones
idénticos por AST. Las 950 pruebas anteriores incluyen los tres límites de módulos
después del arreglo; la CI del head final aún exige su resultado propio.

Compatibilidad de cadenas reales `08eb762d0244e818d6318f8862eba52b26533e9f`: integra
el código de este lote con los cuatro lotes pendientes y RSS en una rama local,
sin cambiar sus heads. Nueve productos reales reconstruidos conservaron las
53 salidas idénticas a sus ramas separadas; Volaris mantuvo el mismo bloqueo
sin Silver/Gold. Resumen `source-batches-official-08eb762d/compatibility-summary.json`,
SHA-256 `60d13e81acddd7df54417f7bddb9e5f0f105157897d875e896233c9b3cdbb743`.
La revisión independiente del código reconciliado inicial y sus 53 salidas fue
favorable. La suite amplia en `c378cf9d` pasó **1.318 pruebas** en 462,18 s
(sin fallos; 44 `FutureWarning` de pandas por concatenaciones vacías). El cierre
UTF-8/ASCII del head final pasó **281 pruebas afectadas** en 97,14 s (ocho avisos
pandas) y repitió las nueve cadenas reales con las mismas 53 salidas. CI y
revisión del head final mantienen su resultado propio en el PR del lote.
El ajuste posterior de metadatos en compatibilidad `3dce54cd177093be9288ed9b589e25574e28f86b`
pasó **282 pruebas afectadas** en 95,38 s. Solo corrige la diferencia entre
planificado y validado; no modifica lectores, escalas, selección ni linaje.
El guard de cierre mensual en compatibilidad `de4e7986b60746a8677bfd819a2971fc0d2c7c51`
pasó **286 pruebas afectadas** en 101,49 s (ocho avisos pandas). Los cuatro
casos adicionales cubren el límite local/UTC; no cambian las transformaciones.
El cierre de roles en compatibilidad `963865e515c39be68c971e82ba97919d1db3173b`
pasó **1.225 pruebas** de fuentes y límites en 381,48 s (44 avisos pandas).
La revisión independiente comprobó specs exactos y restantes registros/despachos
inalterados por AST. La definición se trasladó a `retention_specs()`; la rama
combinada mantiene su registro separado, sin cambiar los heads pendientes.
La prueba real final de AFAC y el bloqueo Volaris se repitieron en `b4320e88`;
las cuatro salidas AFAC siguen idénticas a las del lote de nueve productos.
Los otros ocho productos mantienen sus transformadores y originales sin cambios.
Son ventanas independientes (julio, agosto, septiembre y 2T26), no una ronda
mensual/trimestral completa. La reconciliación real de las ramas pendientes
requiere que terminen sus revisiones y vuelva a pasar CI/revisión del head
resultante antes de integrarlo. No se han relanzado sus revisiones.

Lifecycle manual: conservar originales/candidatos/recibos/resumen/auditor y
su resultado local de `carrier-official-b4320e88*`, readiness/global para
reproducir. Los lotes anteriores `carrier-official-bc5343f4*`,
`carrier-official-d25f4f6d*`, `carrier-official-868232fd*` y
`carrier-official-39b7dc05*`, `carrier-official-bb44fcc9*` y
`carrier-official-a2cfb66b*` se conservan como
pruebas previas a las correcciones, no evidencia final. Auxiliares bajo `/tmp`,
cachés y scratch de pytest son regenerables; no se suben originales, datos
candidatos o informes paralelos al repositorio público. Inventario manual:
185 archivos locales de este checkout y 294 de la compatibilidad, conservados
fuera de Git público; los 24 archivos versionados tienen disposición en el PR.
No hay retiros.

## Apéndice técnico: comprobación oficial del 24 de octubre

Esta continuación investiga evidencia; no cambia parsers, contratos, tolerancias,
calendarios configurados ni datos publicados. La infraestructura Volaris/AFAC
se integró en [PR158](https://github.com/salvamalfa/aeromexico-tracker/pull/158),
merge `d71b683c5c3a77a8aeb98b93657354b600faa587`, con CI antes/después y Codex
sin hallazgos. Las nuevas comprobaciones usan ese código y preservan los heads
pendientes. No convierten verificaciones aisladas en una ronda lista.

| Producto | Evidencia comprobada | Clasificación del límite |
|---|---|---|
| Volaris CASM H1 2025 | El [original 2T25 SEC](https://www.sec.gov/Archives/edgar/data/1520504/000129281425002705/ex99-1.htm), tabla física 290, repite gastos 1.403 millones, ASM 17.622 millones y CASM 7,97; el anexo 2T26 los conserva como comparativo en tabla 300. Se verificaron las etiquetas y la columna H1 2025 en ambos, sin aplicar el layout 2026 al documento 2025 | Conflicto de precisión ya presente en el documento original; no es una columna comparativa mal seleccionada por el parser actual |
| AIFA julio 2026 | El XLSX enlazado actualmente por [Normateca](https://aifa.aero/normateca) volvió a responder 200 y conserva exactamente el SHA de la captura 19/oct. Las fechas y fórmulas problemáticas están en los bytes del libro | Contradicción de metadatos del documento, sin corrección oficial acreditada |
| Aerocivil `jh8x-n6h6` | Metadata actual del mismo ID respondió 200, mantiene definiciones y atribución de la entidad publicadora, pero no una leyenda literal para S/N/I | Publicador identificado; significado de códigos y atribución operativa no acreditados más allá de lo que declara la fuente |
| GDELT septiembre | Una nueva captura mensual, correctamente rotulada, terminó 24/oct 01:55:53 UTC con HTTP 503 y cuerpo de timeout de conexión al upstream | Fallo de acceso/ruta de red antes de obtener artículos; no permite atribuirlo a la aplicación del proveedor ni diagnosticar un parser de artículos |
| Releases 2T26 | Los originales de las tres empresas declaran días de emisión, pero no una hora de publicación con zona explícita para los tres | Evidencia de día del reporte disponible; todavía no una receta de releases que cumpla el contrato vigente |
| Festivos | BMV sigue mostrando 2026; el registro oficial 5775684 corresponde a disposiciones de 2026. No se localizó calendario 2027 en las consultas oficiales realizadas | Año 2027 no verificado; no es una afirmación de que tal publicación no pueda existir en otra ubicación |

**Volaris.** El original 2025 tiene SHA-256
`cd051d052ff6a2e6e008da48b28eefe4895bdcf724f4f4bab14de6c24873cc10`.
Su tabla 290 usa columna 1 y fila 27 para ASM; el comparativo 2026 usa columna
2 y fila 26. Se compararon por etiqueta/periodo, no por posición supuestamente
intercambiable. El máximo compatible sigue siendo 7,964702210368… frente a
7,965, mínimo que redondearía a 7,97. Los índices SEC retenidos de ambos
expedientes solo enumeran portada, anexo e índices/texto; no aportan un segundo
anexo más preciso. La repetición histórica no resuelve la discrepancia ni
acredita tráfico mensual. No se elimina ese comparativo ni se amplía tolerancia.

**AIFA.** El libro nuevo conserva SHA
`8585dc7bf86a276d3fd2e0d1d2e874dde57bd51057fcc4b8fc53af878b465243`.
`Pasajeros!C4/C5` contiene literalmente las fechas 11 Jul. 2026; no es una
fecha serial interpretada en otro idioma. En `Carga!C5` la fórmula es
`=Pasajeros!C10` y su caché contiene el periodo hasta 31 Jul., en lugar de la
fecha de actualización que exige el esquema. El lector actual vuelve a
rechazarlo antes de Silver/Gold.

También se conservaron el [PDF del mismo corte](https://aifa-repositorio.s3.us-east-1.amazonaws.com/PyE/Numeralia-Aeroportuaria-Jul-2026.pdf)
(15 páginas, SHA `5da7350cf10fbc22041425cefee63fec6c7df3ae3a43047ffbbc7807ba45dcf3`),
la [nota metodológica](https://aifa-repositorio.s3.us-east-1.amazonaws.com/PyE/Nota-metodologica-2026.pdf)
y la [nota descriptiva](https://aifa-repositorio.s3.us-east-1.amazonaws.com/PyE/Nota-Descriptiva-2026.pdf).
El PDF muestra cifras de julio y cobertura hasta 31 Jul.; se revisaron texto
completo y páginas renderizadas. No se localizó en esos documentos una aclaración
que corrija las fechas de validación/actualización del libro. La fecha técnica
de creación de un PDF tampoco se toma como publicación. No se declara que los
formatos sean intercambiables ni se utiliza el PDF para saltar el rechazo XLSX.

**Aerocivil.** Captura 24/oct 02:00:45 UTC de
[metadata del ID exacto](https://www.datos.gov.co/api/views/jh8x-n6h6.json), SHA
`5511f718a55ea52792373874d8455e29bcc27017ac4dfe43f4db94a8eb080bcf`.
Identidad declarada: `resourceName=operaciones-aereas-acumulado-2025`,
`tableId=20263639`, `rowsUpdatedAt=1787261265` (20/ago/2026 21:27:45 UTC).
No hay un número de versión semántica declarado: esos metadatos, captura y SHA
identifican el original revisado. `rowsUpdatedAt` no acredita primera publicación
de un mes ni completitud. El publicador declarado es Aerocivil y la metadata
explica que empresa/explotador se derivan de callsign/matrícula; no son una
confirmación independiente de comercializador, AOC o elegibilidad histórica.
El diccionario de columnas no incluye una equivalencia literal S/N/I ni adjunta
un diccionario separado. Descripción, definiciones revisadas, publicador y
`rowsUpdatedAt` no cambiaron respecto al original del 21/oct; esta comparación
no verifica nuevas cifras de movimientos. Las coincidencias con códigos de otro conjunto o una
norma general no atribuyen por sí mismas esa leyenda a este ID.

**GDELT.** La petición usa exactamente la receta mensual existente, desde
`20260901060000` hasta `20261001055959` UTC, no el diagnóstico `timespan=1d`
que recibió 429 el 21/oct. Se realizó después de tres días, sin reintentos y
con el límite del cliente vigente. El cuerpo 503, 91 bytes, se conserva como
fallo no elegible; SHA
`2f85832e31ca57711e6107af6b142363351ae516adb71c69afc643fac26be7f6`.
La [documentación oficial DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
y su [actualización](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/)
no prueban disponibilidad de la API. La respuesta histórica 200 con fechas
fuera del mes permanece rechazada; no se filtraron sus filas para aprobarla.
No se harán más solicitudes de datos GDELT en esta continuación.

**Releases y festivos.** Para 2T26, los documentos centrales declaran:
[Aeroméxico, 13/jul](https://ir.aeromexico.com/static-files/d780da89-7da6-4360-adae-7ad65f49333e),
[Volaris, 21/jul](https://www.sec.gov/Archives/edgar/data/1520504/000129281426003836/ex99-1.htm)
y [Viva, 24/jul](https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-2T26-en.pdf).
La [convocatoria Aeroméxico](https://ir.aeromexico.com/static-files/92dd5926-74d9-4c59-be1e-0110ce42bb93)
prevé publicación el 13 y llamada el 14; ni la convocatoria ni la llamada
sustituyen el reporte central. Se revisaron también el
[índice trimestral Aeroméxico](https://ir.aeromexico.com/financial-information/quarterly-results)
y los [eventos GVIVA en BMV](https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD).
Las horas de eventos de tráfico u otros documentos no se transfieren al reporte
financiero. El contrato ejecutable exige `published_at`
con zona explícita y vínculo al artefacto financiero validado. Los días impresos,
la captura, la aceptación SEC y las propiedades del archivo no se convierten
en ese instante ni en primera disponibilidad. Se conservan las fechas declaradas
como evidencia, sin rellenar medianoche, crear releases confirmados ni fijar
una fecha trimestral. Esta revisión no trabaja Q3.

La [página BMV](https://www.bmv.com.mx/es/grupo-bmv/calendario-de-dias-festivos)
y la [referencia oficial 5775684](https://sidof.segob.gob.mx/notas/5775684)
respaldan 2026. Una coincidencia «2027» en el selector de navegación del portal
no equivale a disposiciones para ese año. La consulta DOF directa tuvo timeout;
no se cambió su URL configurada ni se extrapolaron festivos. El guard de 2027
continúa rechazando el año no verificado.

Comprobación reproducible sin red ni escrituras Silver/Gold:
`tmp/source-updates/evidence-20261024-audit/verify.py`, sobre los originales
retenidos y las capturas de esta continuación. Resultado `verification.json`,
SHA `4f52141dd44564a0e9261ef0bfcc13b98d08aeaecaf57bafd51c3d2ff9efd028`.
Se ejecuta desde la raíz del checkout con dependencias del proyecto y esos
insumos privados preservados. El replay no actualiza fuentes ni sobrescribe el resultado preservado:

```bash
python -c "import runpy; runpy.run_path('tmp/source-updates/evidence-20261024-audit/verify.py', run_name='__main__')" --check
```

El script tiene SHA `3b81b60654e96468773d235744c7f2f9ab8db507705802735ae93800c2d0fb8c`.
Comprueba hashes/sidecars, etiquetas/columnas/periodos en dos anexos SEC,
precisión con Decimal, celdas/fórmulas/caché AIFA y su rechazo real, metadata del
mismo ID Aerocivil, recibo/cuerpo 503 y guards de fechas/2027. Las capturas AIFA
y Aerocivil son `collected_unvalidated`; el recibo GDELT es `incomplete`. No son
certificados de producto. Hay cero Silver/Gold nuevos y preparación global falsa.

Lifecycle de esta continuación: actualizar solo esta guía; conservar los 21
archivos privados de evidencia bajo `evidence-20261024-*` (originales, sidecars,
recibos, inspector y comprobación). No se suben al repositorio público. Los
PNG/logs auxiliares de `/tmp` se regeneran desde los originales. No se retiró
ningún archivo ni se modificaron secretos, permisos, protecciones o las lecturas
auxiliares denegadas. Los pendientes vigentes se mantienen únicamente abajo.

## Apéndice técnico: reconciliación local del 26 de octubre

La propuesta existente `963865e5` se continuó en el mismo checkout y rama
`codex/carrier-all-source-compatibility-20261023`. Incorporó el cierre documental
final de Viva `ce04eb2d` y master `dad0a39b37fbdfe4367396ee4a9b640f3ce857e8`
mediante merges locales. El código funcional resultante es
`be1ed8a663e5e4c34ef1043588b9f7da9c4af5fc`. No hubo push, actualización de los PR,
relanzamiento de revisiones ni modificación de sus heads remotos.

Los dos conflictos restantes fueron el registro de adaptadores y esta guía.
`retained.py` usa el registro extraído, que incorpora los roles de aerolíneas
mediante `carrier_source_contract.retention_specs()`. Se conservaron los
controles de productos dedicados, el prefijo especial de recibos RSS, el
retainer de aerolíneas y ambos despachos de ejecución/reproducción. No se
cambiaron tolerancias, fuentes requeridas, calendarios, permisos o gates.

La nueva búsqueda comprobó comentarios generales e inline, reviews, checks y
artefactos de los runs existentes. No encontró un recibo terminal adicional:
los cuatro comentarios resumen siguen marcados `running`, sin identificador
de ejecución Codex ni un check que permita comprobar su actividad interna.
La antigüedad no prueba que estén fallidos ni activos. PR152 conserva una
revisión anterior sin hallazgos del mismo head; es anterior a su revisión
adicional. PR154 conserva un recibo de otro head. Los auditores manuales
retenidos y la búsqueda local de 626 archivos técnicos tampoco acreditan un
resultado Codex nuevo. Estado: **desconocido**, sin denegación de lectura.

Validación de esta reconciliación:

- 511 pruebas focales y de regresión aprobadas; 44 avisos existentes de pandas.
- 256 pruebas nuevas independientes aprobadas. Cubren 17 productos por once
  adaptadores, roles/alias, rechazo de rutas parciales, prefijo RSS, retainer
  exclusivo de aerolíneas, despacho/replay y detención al fallar.
- Revisión independiente de 21 contratos legado frente a master: conserva
  roles, alias, grano, tablas, controles, parsers y archivos de código. Los
  catorce módulos de fuentes coinciden con los heads exactos de los cuatro PR.
  Las ocho constantes de política global y los prefijos de datos/publicaciones
  no cambiaron. Dictamen de contratos de fuentes favorable; la integración
  permanece bloqueada. No sustituye Codex, CI ni el cruce Claude/dueño exigido
  por AGENTS cuando corresponda.
- Pyflakes y formato exigidos por CI aprobados. Un chequeo exploratorio de
  todas las reglas Ruff encontró 47 incidencias en 25 módulos idénticos a
  master; no se reformató código ajeno ni se modificaron excepciones.
- Suite pública amplia terminada: **4.933 aprobadas, 34 fallidas, 26 errores,
  seis omitidas y 106 deseleccionadas**, 44 avisos y 29 subtests aprobados,
  en 1.538,46 s. Ningún caso fallido es de `source_updates`. No es una suite
  verde ni CI del nuevo head. Log completo: `public-suite.log`.
- Las pruebas de chat/noticias reproducen la exigencia del pin externo
  `CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256` y la discrepancia con la
  proyección de noticias aprobada. No se consultaron variables/logs denegados
  ni se inyectaron valores alternativos para aprobar esas puertas.
- Cuatro errores adicionales de paridad editorial/financiera son un bloqueo
  de integración distinto: `Financial runtime differs from reviewed producer`.
  `entity_adapter.code_version()` liga intencionalmente todo `src/**/*.py`;
  por diseño, código Python ajeno a las finanzas también exige revisión técnica
  nueva. La reconstrucción por objetos Git de master coincide exactamente con
  el productor aprobado; los veinte archivos cambiados del runtime están todos
  en `src/source_updates/`. La huella local cambia, aunque los bytes de las
  publicaciones, sus gates y sus anclas permanezcan intactos. Diagnóstico:
  `financial-runtime-integration-block.json`. Esta dependencia debe resolverse
  con revisión técnica y el procedimiento autorizado de preservación antes de
  integrar; no se cambia una huella aprobada ni se excluyen módulos del control.

### Contraste controlado y procedimiento financiero

Se ejecutaron en un checkout de control detached de master `dad0a39b` los
mismos 60 nodeids fallidos del candidato, con el mismo Python y perfil público,
sin copiar expedientes privados ni introducir pins. El control permanece limpio.
No se ejecutó una segunda suite completa ni se presenta ese subconjunto como tal.

| Grupo comprobado | Candidato | Control master | Clasificación |
|---|---|---|---|
| 54 casos de aprobación de métricas de negocio | Fallan/error | Mismo estado | Condición compartida del entorno; Docker se comprobó directamente en ambos, sin conservar stderr crudo ni valores de pins |
| Dos casos de proyección aprobada de noticias | Fallan | Fallan | Fallo compartido, no una regresión nueva de las skills |
| Cuatro casos de paridad financiera/editorial | Error por huella | Uno pasa y tres se omiten | Regresión de integración del runtime; las omisiones no prueban replay completo de fuentes |

El subconjunto master terminó con 34 fallos, 22 errores, un aprobado y tres
omitidos en 519,58 s. La comparación por nodo y sus límites están en
`control-comparison/control-comparison-summary.json`; el addendum Docker
se conserva aparte. Los 56 estados compartidos no se corrigieron cambiando
configuración de aprobación. Los cuatro errores nuevos no se ocultaron ni se
convirtieron en omisiones.

La continuación local siguió el procedimiento de `src/publish/README.md` y
`financial_sources.py`: su autoridad vincula consentimiento explícito, salida,
fuentes, productor y revisión exactos. Pasaron 67 pruebas existentes de ese
protocolo. El componente de preservación real verificó 803 archivos y las
identidades/bytes publicados; es una comprobación parcial, no aceptación del
gate financiero completo ni auditoría nueva de sus fuentes.

La primera validación de la autorización real se detuvo por **archivo
inexistente**, no por denegación ni rechazo del dueño. Esa ausencia se resolvió
después mediante el respaldo financiero de Library posterior a PR160, sin
reabrir el hilo archivado ni sustituirlo por una edición anterior solo validada.
El ZIP recuperado tiene 5.364.970 bytes y SHA-256
`64dbb9edb6d62c3ec9ab0c6e1b11c12b8122631c994425b08567c596f94315e3`.
La versión de identidad devuelta sigue siendo nula; el atributo de transferencia
indica 0, sin inferir otra versión. Incluye la cápsula editorial v7 de
5.232.749 bytes y SHA-256
`bc44257f0354a2e0d9b396a671eb0d8b06eda37e0ee5a0a65aab523d97ca3c83`.
Se verificaron todos los miembros contra ambos manifiestos: 22 y 286 hashes.

Se restauraron únicamente 178 archivos de `analysis_runs/` y diez originales o
sidecars de Bronze en cada uno de dos checkouts detached aislados: master
`dad0a39b` y candidato `b9cd5d2c`. El registro a470, paquete, cálculos, autoridad
financiera `8e5d1542…` y revisión `b842a729…` coinciden con sus identidades exactas.
La cadena completa recuperada tiene 161 eventos y termina en la aprobación
`ecc7e7fd…` del 24/oct a las 09:02:12 UTC. Su verificación conserva a470 aprobado y
no encuentra una revocación de esa versión en ese snapshot; no acredita eventos
externos posteriores. Los 188 archivos restaurados permanecen idénticos después
del replay en ambos checkouts. No se copió contenido del respaldo sobre código,
configuración, Gold o sitio publicados.

El verificador original `0f6b4dc…` y el productor archivado `45c930f…` reprodujeron
fuentes, aprobación y proyección en ambos checkouts, prohibiendo conexiones de
red. Coinciden los 312.095 bytes del ejecutivo publicado, SHA-256
`cc0b39ad47ad761cda8c5339381c8552be30211d5da915bf3c25ec56f87d614b`,
y la preservación de 803 archivos. Las ejecuciones duraron 40,79 y 42,62 s.
Esto certifica la entrega original y su conservación; no convierte el runtime
actual en un productor aprobado. En esa fase, los cuatro tests de paridad se
repitieron con el expediente recuperado y dieron cuatro errores por huella,
sin omitirse. La continuación local autorizada se describe a continuación.

Se preparó `financial-technical-rebinding-proposal.json` con la misma proyección,
identidades y límites, cambiando solo el productor propuesto. Está marcada como
propuesta no autorizada y no es entrada del gate. No se creó aprobación ni se
modificó el ancla. `financial-local-procedure-progress.json` enumera los insumos
exactos y las comprobaciones realizadas.

El modo financiero existente incorpora por primera vez un trimestre y exige
baseline igual al master confiable; no es una renovación automática de un
trimestre ya publicado. La autoridad recuperada y su revisión cubren exactamente
el productor `45c930f…`, runtime `f286de95…`. Se comprobó que rechazan vincular el
candidato `b9cd5d2c` y su runtime `8c56fe9f…`; también se rechaza volver a añadir
el trimestre ya existente. UI/mapa no se usaron como atajo. No se cambiaron
gates, anclas, digests, consentimiento ni eventos para obtener aceptación.

**Continuidad técnica local autorizada e implementada:** el dueño aprobó el
procedimiento separado el 26/oct. `financial_continuity` conserva inmutables la
autoridad, el productor y el replay originales. La política local comprometida
vincula una revisión independiente del código `2acc2c68`, runtime `553bdace…`,
los **811 archivos** de la publicación completa y los **177 insumos** de fuentes
y aprobaciones. Reproduce la entrega original y verifica la conservación de
803 archivos. La política incorpora únicamente el consentimiento del procedimiento
local; no reemplaza consentimiento, aprobación o revisión de las cifras o tesis.

El control rechaza evidencia ausente, no comprometida, de otro código, alterada
o con hallazgos; también fuentes, ledger, sitio o runtime cambiados antes o
durante la comprobación. Exige el mismo sitio entero que el commit publicado,
incluidos su manifiesto y recibos. Los inventarios se leen desde los blobs de
Git: no admiten omisiones o sustituciones por atributos de exportación. La revisión
independiente encontró y se corrigieron dos defectos: escapes mediante `..` y
efectos de `export-ignore`/`export-subst`. El protocolo tiene 57 pruebas propias,
22 independientes y 67 financieras existentes aprobadas. La confianza del informe
procede del pin Git revisado, no de una firma criptográfica de identidad. No se
afirma conocer revocaciones externas posteriores al snapshot recuperado.

La selección es explícita y solo local. El gate financiero ordinario y Pages
conservan sus controles; no hay fallback hacia este procedimiento ni cambios en
los workflows. La propuesta anterior de sustituir solo el productor sigue sin
ser autoridad ni entrada ejecutable del gate. Para repetir la validación se
requieren el expediente recuperado y el informe privado referenciado por la
política, en un checkout del código final:

```bash
python -m src.publish.financial_continuity site/ --local-only
python -m pytest -q tests/test_editorial_site_parity.py tests/test_financial_site_parity.py --financial-continuity-local --require-local-data
```

Los cuatro errores anteriores dejan de producirse con este procedimiento y el
expediente real: **tres pruebas aprobadas y una omisión explícita por modo
financiero**, en 281,49 s. La omisión conserva el test editorial antiguo porque
la preservación financiera tiene su propio test estricto; no se debe a material
ausente. Sin selección local, el verificador ordinario continúa rechazando la
huella nueva: no se presenta la suite ordinaria ni CI como verdes. Se conserva
la clasificación previa de 56 fallos/errores compartidos con master; no se
introdujeron pins de aprobación para ocultarlos. No se repitió la suite pública
completa como parte de esta validación focal.

La batería afectada terminó con **405 pruebas aprobadas**, incluyendo las 256
de reconciliación y los tres controles de tamaño de módulos. El primer intento
del control de tamaño encontró copias de laboratorio anidadas dentro del árbol;
se trasladaron a directorios hermanos del mismo entorno y se verificaron sus
188 archivos retenidos por copia. No se modificaron el control, sus excepciones
ni los originales para obtener ese resultado.

La verificación agregada posterior de `52912929` sí ejecutó el perfil público
completo con selección local: 5.003 aprobadas, 46 fallos, 22 errores, siete
omisiones y 106 casos fuera del perfil, más 29 subpruebas aprobadas. La comparación
identificó 12 regresiones nuevas: la firma de la fixture editorial había dejado
de admitir sus llamadas directas existentes. Se restauró la interfaz que recibe
solo `request` y se resuelve el verificador de forma perezosa únicamente en la
rama financiera. No se modificaron las aserciones de las pruebas de rechazo.
Se conserva esa ejecución fallida y se repite la agregada sobre el head corregido;
no se presenta el primer resultado como favorable. La evidencia adicional vive en
`aggregate-final-52912929/` y `aggregate-final-fixed-20261026/`, dentro del mismo
directorio técnico; no se crea otro informe narrativo.

La continuación local recuperó y verificó el respaldo privado: 2.261 archivos
iniciales y los 2.322 del commit privado `84361b52`, con Git LFS íntegro y los
once manifiestos derivados correctos. Se restauró en un checkout aislado;
se conservaron los archivos públicos y el expediente financiero posterior.
Los tres registros exactos de las tesis ya publicadas se recuperaron desde el
expediente de Mercado/Noticias, con sus paquetes y cápsulas originales. Las
capturas del 3T26 se materializaron desde los originales y sus recibos retenidos,
sin inventar fechas ni aprobaciones. Esas tres pruebas antes bloqueadas pasaron.

La primera ejecución de las 75 pruebas locales terminó con 64 aprobadas,
seis fallos, tres errores y dos omisiones existentes. Dos fallos identificaron
un defecto real: el contrato `airport_group_native`, exclusivo de candidatos,
se había incorporado al inventario global de Silver sin productor global.
Ahora tiene su catálogo separado y conserva exactamente columnas, grano y
validación. Las 30 tablas globales obligatorias y su inventario estricto siguen
iguales a la base. No se creó una tabla ficticia ni se volvió opcional una fuente.

Por la prioridad de eficiencia aprobada, se consolidaron las dos pruebas
financieras en una que conserva todas sus aserciones y el replay completo.
La fixture editorial comparte su comprobación entre sus dos consumidores
inmutables; el verificador conserva la selección explícita del procedimiento
local y no almacena resultados globales. Se mantienen los controles del modo
ordinario. La matriz de fechas conserva sus vocabularios y clases de límites:
se retiran cuatro llamadas exactamente duplicadas y 56 cruces equivalentes de
dos guardas que rechazan el texto antes de leer esos límites. Las combinaciones
relativas, mixtas y las demás fronteras siguen completas. La revisión independiente
comprobó la equivalencia. La matriz pasa de 240 a 180 casos; su coste previo
fue solo 0,23 s y no se presenta como ahorro material. El ahorro principal se
mide en los replays financieros, antes de unos 280 s en este entorno.
La colección pasa de 5.184 a 5.133 pruebas: 61 duplicaciones retiradas y diez
casos nuevos para el defecto de contrato y el límite del smoke. No hay cuota
de pruebas ni cambios en required checks. El tiempo remoto aún no se ha medido.

El smoke del chat tiene un modo separado `--fixture-only`: comprueba imports,
autenticación, worker y comparación en el entorno mínimo, sin proveedor, y
declara que no valida la publicación. El modo predeterminado sigue comprobando
el snapshot real y falla sin su pin externo. No se sustituyen las 56 pruebas
reales por fixtures. Las seis pruebas del nuevo límite y su revisión adversarial
pasan. Los pins financieros y de noticias no se calcularon desde los archivos
ni se recuperaron por las rutas previamente denegadas; su entrega por un canal
autorizado sigue siendo necesaria para cerrar esas comprobaciones reales.

La reparación de Silver cambió la huella del código. La revisión independiente
real del commit `95e54979`, runtime `83f58bcf…`, volvió a ejecutar el productor
original con red bloqueada y verificó los mismos 811 archivos del sitio,
803 preservados, 177 insumos y 188 archivos restaurados. El vínculo técnico
local se renovó con ese informe real; la autoridad original, sus anclas y sus
revisiones permanecen intactas. Las nueve ventanas se recertificaron sin red
en destinos nuevos y sus 53 salidas siguen idénticas; Volaris conserva su
rechazo documental. Eso no acredita un calendario completo.

El control general de linaje ahora identifica un material adicional ausente:
el ZIP BTS del 17/oct, SHA `bda94a69b9d8430163a96b33521300cf8f76ac6f0aa0761d67ce3250a184d568`,
259.152 bytes. El original retenido del 19/oct tiene otro hash y no se renombra
ni se usa como sustituto. La búsqueda acotada en copias locales, el respaldo
privado actualizado y Library no recuperó ese original. El gate sigue cerrado.

Las nueve ventanas de fuentes se comprobaron otra vez en modo de replay: sus
53 salidas conservan los mismos hashes. Siguen siendo ventanas separadas y no
acreditan una ronda completa ni un calendario preparado para activación.

El material de recuperación, ambos replays y los negativos están en
`financial-library-recovery/`, dentro del directorio técnico de esta continuación.
`preservation-transition-diagnostic.json` documenta la transición propuesta y sus
límites; no es entrada del gate. Se conserva la evidencia anterior para distinguir
la ausencia inicial ya resuelta del bloqueo real de compatibilidad del protocolo.

La prueba real volvió a construir Viva 2T26; Banxico, EIA y cotizaciones de
septiembre; GAP/ASUR de julio; BTS de julio; RSS de septiembre y AFAC de agosto.
Usó los originales retenidos y el código funcional local: **nueve ventanas de
producto separadas**, no una ronda mensual/trimestral coherente. Las 53 salidas
coinciden por SHA con sus candidatos anteriores; las huellas nuevas de código
se comprobaron y los 117 archivos de candidatos anteriores permanecieron
iguales durante la reproducción final. Esta comparación usa los certificadores
del producto; no afirma una nueva extracción independiente de cada original.
Los contratos y el despacho tienen la revisión independiente indicada arriba.

Volaris volvió a rechazarse por `table 300, row 23, column 2` antes de escribir
Silver, Gold o recibo aceptado. El primer arnés esperaba la palabra CASM en ese
mensaje; se conservó su intento y se corrigió solo la aserción del arnés. La
continuación retomó los recibos ya escritos con `--check`, sin repetir ni
sobrescribir los candidatos aceptados. La receta global vacía emitió y reprodujo
`blocked_global_policy`: preparación del calendario y de ejecución automática
siguen falsas, con Aerocivil/GDELT y los demás requisitos ausentes explícitos.
No hubo consultas de fuentes, capturas nuevas, gasto o publicación.

La evidencia de esta continuación vive en
`tmp/source-updates/monday-reconciliation-20261026/`: recetas y planes en seco,
recibos/candidatos nuevos, logs y los arneses conservados. Resultado de originales
`official-reproduction.json`, SHA-256
`c44a47139cc08ed5c2eb898f536e5a11c64afb913e7732b6d48138ee9652aea4`.
Dictamen `independent-conservation-review.json`, SHA-256
`d3716ae7dcf1c59115a537dedd8209d9d32dfc1019f0639b2ee5f111625083e1`.
La receta `combined-replay-recipe.json` reúne las nueve ventanas con sus cortes
originales. Su despacho conjunto y replay pasaron; resultado
`combined-replay-result.json`, SHA-256
`58991465baaa61289a30861d576d78e068ff50188267b9775642956f33ff9f97`.
`ready_for_review=true` se limita a esas nueve tareas; calendario y ejecución
automática siguen falsos. Con los candidatos conservados, se comprueba sin red:

```bash
python -m src.source_updates.readiness --recipe tmp/source-updates/monday-reconciliation-20261026/combined-replay-recipe.json --workspace tmp/source-updates/monday-reconciliation-20261026/combined-replay --check
```

Se conserva toda esa evidencia local y la anterior; no se sube Bronze ni Gold
candidato. El inventario/disposición del diff local se comprueba contra
`dad0a39b` con el lifecycle canónico. Esta guía consolida el resultado y sus
pendientes; no se crea otro informe paralelo.

## Pendientes

- La política está aprobada e implementada; no falta volver a aprobarla.
  AICM tiene certificación integral de las ediciones retenidas de julio/agosto;
  AIFA tiene el certificador preparado pero su archivo julio sigue rechazado
  por la contradicción de fechas. Falta material oficial coherente o aclaración
  oficial de la edición; no basta una prueba sintética o el control de Gold.
- PR152 añade `banxico`, `fuel` y `equities` y conserva el head `3a89c6dc`.
  La revisión adicional iniciada el 22/oct a las 16:05 UTC sigue sin resultado
  terminal verificable; su actividad interna es desconocida. Su CI y revisión
  manual previas no sustituyen ese resultado.
  No se ha integrado ni se ha relanzado la revisión.
- PR158 integró la certificación técnica de los dossiers Volaris/AFAC;
  Volaris real permanece bloqueado por la discrepancia CASM documentada arriba;
  el original 2T25 confirma que no nace de seleccionar mal el comparativo 2026.
  La prueba de agosto AFAC conserva la advertencia internacional de la fuente.
  Las pruebas reales y revisión independiente constan arriba; CI/revisión del
  head final e integración se registran en PR158.
  RSS añade aquí el certificador retenido, probado sobre originales;
  su suite completa, CI, revisión e integración se registran en
  [PR157](https://github.com/salvamalfa/aeromexico-tracker/pull/157). BTS ([PR155](https://github.com/salvamalfa/aeromexico-tracker/pull/155)),
  GAP/ASUR ([PR154](https://github.com/salvamalfa/aeromexico-tracker/pull/154)) y Viva
  ([PR156](https://github.com/salvamalfa/aeromexico-tracker/pull/156)) están preparados
  en ramas separadas y conservan sus heads/revisiones remotos. La reconciliación
  local de los cuatro PR ya está preparada y probada; falta resolver el estado
  de las revisiones existentes y validar cualquier futuro head remoto con CI y
  revisión exactas, sin duplicar ejecuciones a ciegas. Además, el gate de la
  publicación financiera requiere una revisión técnica nueva de la huella del
  runtime. La conservación de sus bytes no sustituye ese control; falta
  coordinar esa continuidad con el procedimiento de publicación vigente. La
  continuación controlada confirma cuatro errores nuevos del runtime. El
  expediente a470 exacto ya está recuperado y su replay original pasa en ambos
  checkouts aislados; no falta conseguir fuentes del 3T26. El bloqueo restante
  se trata ahora mediante el procedimiento local separado, aprobado por el dueño
  e implementado con revisión y conservación exactas. Su aceptación local no
  equivale a aceptación del gate ordinario, integración o publicación; ese flujo
  sigue rechazando el runtime nuevo. No falta otra aprobación editorial.
  Los heads remotos no se modifican y no se activa nada. Los resultados reales
  y las limitaciones del procedimiento se conservan en la evidencia técnica.
  Los restantes adaptadores conservan sus límites de edición y periodo;
  finanzas IR retenidas de Aeroméxico certifica 2T26, sin aprobar otra edición.
- Aerocivil requiere la leyenda literal aplicable al ID exacto; su entidad
  publicadora ya está identificada, pero la atribución operativa sigue siendo
  derivada. GDELT requiere una captura mensual válida: el intento acotado del
  24/oct terminó en 503 de conexión al upstream y no se vuelve a solicitar en
  esta continuación. Se conservan también el 429 y los rechazos históricos.
  Ambos permanecen **requeridos y bloqueados** por decisión del dueño. No hay
  autorización para declararlos opcionales ni para rebajar sus validadores.
  Obtener aclaración documental del proveedor es otra vía; contactar a terceros,
  añadir hosts o contratar servicios requiere instrucción aparte.
- Completar evidencia temporal y vínculo a payload financiero validado antes
  de suministrar los tres releases al coordinador. Los días declarados de 2T26
  están identificados; no se acreditaron para los tres los instantes de
  publicación con zona que exige el contrato. La primera disponibilidad es
  otro dato que tampoco se infiere. No se rellenan horas ni se traslada esta
  evidencia a Q3. La muestra
  sin releases elegibles no fija fecha; el 2 de noviembre no es una fecha aprobada.
- Las comprobaciones de originales retenidos no acreditan última disponibilidad.
  Para una edición nueva, seleccionar el documento real y revisar su formato,
  cobertura y revisiones antes de incorporarlo. Países no aporta una serie
  mensual exacta desde las gráficas del boletín; Aerocivil conserva su leyenda pendiente.
- PR142/privada35, PR144/privada37 y Vuelos PR134/privada33 ya están integrados. M11 PR140
  conserva su responsable. La integración de infraestructura conserva esas
  salidas y el lifecycle vigente. La propuesta local parte de master `dad0a39b`
  y conserva íntegramente las publicaciones PR149/160, sin volver a publicarlas.
- Resolver las decisiones curadas de perfiles y eventos descritas arriba antes
  de cambiar su significado o elegibilidad. Las pruebas no las aprueban.
- Verificar el calendario bancario de 2027 antes de calcular rondas de ese año.
- Revisar y aprobar cada lote según su alcance antes de publicar o activar una
  ejecución automática. La integración técnica ahora autorizada no aprueba
  datos nuevos ni activa calendario, noticias o nuevas versiones de tesis.
  La disponibilidad y validez de cada fuente se comprueban por lote; cualquier
  producto obligatorio bloqueado impide declarar lista una ronda completa que lo requiera.
