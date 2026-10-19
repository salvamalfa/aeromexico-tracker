# Catálogo de fuentes, métricas y rondas de actualización

Revisión: 19 de octubre de 2026. **Calendario aprobado; skills y coordinador
preparados para pruebas. Sin nuevas ejecuciones automáticas ni publicación.**

## Resumen

Ya hay una herramienta ejecutable para preparar las actualizaciones por fuente.
Incluye ocho skills por familia y un coordinador. Primero muestra qué haría.
Después puede capturar y comprobar un lote candidato en una carpeta separada.
La aprobación del calendario ya está recibida. La revisión del contenido y su
publicación conservan sus permisos separados.

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
pasos de cada fuente. Este es el alcance comprobado por familia:

| Familia | Alcance actual |
|---|---|
| Empresas | BMV: catálogo y ZIP oficiales capturados; parseo offline acotado implementado. SEC preservado reconstruido; Ryanair FY2026 tiene un lector XBRL retenido separado, sin convertirlo a trimestre. Tráfico mensual y finanzas 2T26 IR de Aeroméxico tienen candidatos dedicados desde PDF; véase alcance abajo. Otros periodos nuevos IR/SEC siguen condicionados. |
| Tráfico AFAC y BTS | AFAC: aeropuertos y marginales de julio tienen adaptadores offline; países conserva cajas acumuladas exactas. Boletines/base julio–agosto y BTS conservan su evidencia previa. La retención no es una captura nueva. |
| Aeropuertos | AICM agosto y AIFA julio conservan sus comprobaciones. OMA julio y slots AICM verano 2026 tienen adaptadores de originales retenidos. OMA septiembre enlazado falló; no se acredita septiembre completo. |
| Macro y mercado | EIA, tres series Banxico y cinco series bursátiles verificadas hasta Gold para septiembre. H.10 tiene una cadena dedicada de certificación mensual aislada; véase su alcance y evidencia abajo. La familia completa no está certificada. |
| Rutas | ANAC junio, CAA junio y Aena enero–julio tienen adaptadores retenidos con ámbitos separados. Cuatro documentos aportan pasajes fechados. Aerocivil conserva comprobación numérica; falta su leyenda de códigos. No representan una red mundial uniforme. |
| Referencias y contexto | OurAirports conserva 9.051 referencias verificadas. FAA y diccionario tienen snapshots candidatos por SHA: 84 categorías y 86.553 palabras, sin inferir seguridad de aerolínea ni tono empresarial. |
| Noticias | PR142 ya está integrado. Corte RSS retenido de septiembre: 12 URLs fechadas en seis días observados. Los 11 candidatos de PR142 pasan controles de metadatos; no se releen sus cuerpos aquí. GDELT devolvió 503 en un intento sin reintentos. Sin cobertura universal ni activación. |
| Derivados y curación | Sin descarga propia. Mapas documentales ejecutables para cinco perfiles y 21 eventos; conservan discrepancias y decisiones pendientes. No aprueban perfiles, impacto ni confianza de los eventos. |

El [inventario de los 42 productos](referencias/source-updates-20261019/product-coverage.json)
separa las capas comprobadas. Hay **35 alcances acotados comprobados**:
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
La siguiente revisión útil será un lote candidato con sus datos y faltantes.

## Riesgos

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

Las condiciones de fuente o atribución restantes son:

- **Viva tráfico:** el host S3 del PDF seleccionado no está permitido por la
  política existente; se bloqueó antes de HTTP y no se reintentó por otra ruta.
- **Aerocivil:** las ocho filas numéricas están comprobadas, pero falta la
  leyenda primaria de códigos del mismo conjunto y la revisión de atribución.
- **GDELT:** el intento normal de septiembre de 2026 devolvió HTTP 503, 91
  bytes, sin reintentos. El original y el recibo están retenidos como fallo;
  no acreditan noticias ni ausencia de ellas.

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
IATA/ICAO por entidad y las decisiones de comparación siguen pendientes.
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
La aprobación posterior permite ahora un PR borrador para revisión y CI. Su integración y el
trabajo M11 de PR140 conservan sus responsables. La rama de revisión ya incorpora
PR142 y conserva sus correcciones de fechas GDELT y de noticias. Los commits
locales anteriores y sus recibos mantienen su fecha y alcance históricos.
PR142 no es un PR pendiente ni una razón para dar por exhaustivo RSS. No se modifican esas ramas,
el sitio publicado ni el respaldo privado desde esta certificación.

Viva, Volaris e Industria siguen requiriendo aprobación exacta de entidad,
periodo y versión para sus tesis. Captura y pruebas verdes no la sustituyen.
Tampoco se activan noticias candidatas, cron, Pages, Railway o auto-merge.
El cron trimestral antiguo de `refresh.yml` sigue siendo una comprobación de
frescura/Gold; no implementa este calendario ni captura fuentes.

### Referencia técnica del inventario aprobado

La auditoría documental inicial fue de solo lectura. Encontró 124 Markdown
públicos, de los que 50 están relacionados con chat. La política existe y ya se
ha aplicado; quedan cierres históricos por revisar. Algunos documentos son
entradas de pruebas o generadores y deben conservarse. Los siete candidatos
concretos para archivo suman 13.025 bytes: el beneficio principal sería claridad,
no espacio. [Inventario y referencias](referencias/source-updates-20261018/lifecycle-audit.json).
No se retiró ningún documento. La convención de audiencia vive en `AGENTS.md`.

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
| BTS T-100 International Segment All Carriers | Pasajeros, asientos, vuelos realizados/programados, distancia, carga/correo; operador×segmento MX↔US×mes×aeronave/clase | 2015M01–2026M05; 2T26 local tiene abril y mayo | [Descarga](https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FJE&QO_fu146_anzr=Nv4%20Pn44vr45), [historial](https://www.transtats.bts.gov/ReleaseInfo.asp); GET formulario + POST México/año/todos los meses/ZIP | Historial anuncia julio añadido 9 octubre y junio 14 septiembre; **máximo mes efectivamente descargable MX-US pendiente de verificar en archivo** por contradicción con política genérica de rezago. Se omiten años anteriores al corriente en caché: perdería revisiones históricas. Segment no es Market ni destino final del boleto |

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

## Pendientes

- Confirmar los tres reportes financieros de 3T26. La fecha trimestral permanece
  sin fijar al corte de la muestra; el 2 de noviembre no es una fecha aprobada.
- Las comprobaciones de originales retenidos no acreditan última disponibilidad.
  Para una edición nueva, seleccionar el documento real y revisar su formato,
  cobertura y revisiones antes de incorporarlo. Países no aporta una serie
  mensual exacta desde las gráficas del boletín; Aerocivil conserva su leyenda pendiente.
- PR142/privada35 y Vuelos PR134/privada33 ya están integrados. M11 PR140
  conserva su responsable. Integrar este cambio sobre la base vigente y
  conservar sus controles; esta rama no hace esos merges ni altera sus salidas.
- Resolver las decisiones curadas de perfiles y eventos descritas arriba antes
  de cambiar su significado o elegibilidad. Las pruebas no las aprueban.
- Verificar el calendario bancario de 2027 antes de calcular rondas de ese año.
- Revisar y aprobar cada lote según su alcance antes de publicar o activar una
  ejecución automática. El dueño aprobó subir esta ampliación como PR borrador
  para revisión y CI el 19 de octubre. Esa aprobación no autoriza merge,
  publicación de datos, calendario ni activación de noticias o tesis.
