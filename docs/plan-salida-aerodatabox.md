# Continuidad de Airline Tracker sin capturas AeroDataBox recurrentes

Este plan conserva la decisión del **15 de octubre de 2026**, aprobada mediante el
[PR #133](https://github.com/salvamalfa/aeromexico-tracker/pull/133).
La procedencia de la
[ampliación posterior de cobertura](etapas/cobertura-vuelos-20261015.md)
se conserva en su bitácora. Para el estado publicado, consultar el
[README](../README.md) y el manifiesto del sitio; esta guía no sustituye las
aprobaciones de cada entrega.
El dueño sustituyó la propuesta de retirar el histórico: **se conserva todo el
snapshot publicado y el mapa muestra únicamente vuelos**. Las tarjetas
oficiales, pasajeros agregados, finanzas y cuatro tesis permanecen iguales.
El chat conserva el histórico con su procedencia y tipo de cifra. No hay
capturas AeroDataBox recurrentes, contrataciones ni activación automática de
modelos o actualizaciones programadas.

## Cobertura aceptada del mapa · 2T26

El 19 de octubre se aceptó la cobertura alcanzada y se canceló perseguir el
95 %. La entrega autorizada representa Grupo Aeroméxico 43.484 / 46.716
(93,08 %), Viva 39.838 / 45.308 (87,93 %) y Volaris México 45.752 / 46.304
(98,81 %). El numerador suma observados regulares y frecuencias estimadas
retenidas; no acredita que toda estimación sea un vuelo realizado. El
denominador conserva VLOSREG AFAC, abril–junio, nacional más internacional.
Connect se mantiene separado en las celdas de operador y se agrega al Grupo;
Volaris excluye los operadores extranjeros Q6/N3.

El mini indicador «Cobertura del mapa», junto al volumen del panel derecho, sigue las aerolíneas y el
periodo del mapa. Varias aerolíneas usan razón de sumas, nunca media simple de
porcentajes. La red completa de las tres representa 129.074 / 138.328 =
93,31 %. El tooltip declara nacional más internacional: los recortes
geográficos, la capa Nacional/Internacional y las doce rutas destacadas no
redefinen ese universo total. Una selección de meses usa los mismos meses en
ambos ámbitos. Sin todas las cifras comparables se muestra «No disponible»;
la capa de programación tampoco acredita cobertura. Los valores estimados
que superen una marginal AFAC no se recortan artificialmente a 100 %.

La proyección `src.web_export.flight_projection` parte de los 766 JSON
congelados del sitio auditado y de `config/flights/2026Q2-accepted.json`.
Comprueba la edición completa y el valor anterior de cada sustitución
colombiana, incluidos deltas negativos y ceros explícitos; mantiene faltantes
como tales. ANAC acredita regularidad sin sumar vuelos nuevos. BTS conserva
solo clases F/G para este numerador y CAA queda fuera mientras no pruebe el
operador efectivo. Las celdas son únicas por operador, sentido y mes; los
slots permanecen separados. Industria se reconstruye desde las tres redes
resueltas. Cada mes, trimestre y ámbito se concilia contra el expediente
aceptado antes de exportar.

`python -m src.publish --flights-only --record <registro-aprobado> ... --out site`
verifica las cuatro aprobaciones originales con su implementación publicada,
conserva sus identidades y todos los datos ajenos a vuelos byte por byte,
y vuelve a comprobarlos antes del reemplazo. No renueva consentimientos ni
recalcula tesis, News, pasajeros, Gold o modelos. El contrato anterior se
conserva por su hash exacto; no se sustituyen contratos de privacidad o
aprobación. El candidato y el despliegue requieren sus propios checks y
verificación; la autorización no activa periodos nuevos ni calendarios.

## Qué sabemos de AFAC y de la semilla

AFAC publica vuelos y pasajeros por **mes × par direccional de ciudades,
todas las aerolíneas** (`REG NAC`/`REG INT`), y marginales separadas por empresa.
Falta la celda **ruta × aerolínea × mes**. El workbook O-D de julio de 2026
conservado se reparseó con el adaptador: sus 4.263 filas de 2026 coinciden
exactamente con el CSV público. Fuente: [AFAC, Excel O-D julio 2026](https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx).

El IPF actual ajusta **pasajeros**, usando marginales de pasajeros. Ese share
no es participación de vuelos: los tamaños de avión y la ocupación difieren.
Las frecuencias históricas publicadas vienen de conteos/muestras AeroDataBox,
expandidas según el calendario y sujetas a los filtros de cobertura de la
capacidad; no se obtienen convirtiendo pasajeros IPF en vuelos. Ver
[método canónico](estimacion-pasajeros-ruta-aerolinea.md),
`src/ingest/aerodatabox/{flights,__main__}.py`,
`src/analytics/{international_capacity,fleet_capacity}.py`.

Técnicamente es posible estimar una celda futura con **marginales de vuelos**
y una semilla congelada de oferta. No queda identificada como observación.
El prototipo calcula `vuelos AFAC de la ruta × share de frecuencias de abril`
por aerolínea, sin usar pasajeros. El expediente histórico detectó en junio
37.064 vuelos por rutas y 36.672 en la selección de empresas utilizada
(392 de diferencia, 1,06 %). Ese contraste describe aquella selección, no un
bloqueo vigente de AFAC: en los workbooks de septiembre recapturados ambas
marginales de junio suman **37.064**, y las 36 conciliaciones mensuales de
vuelos/pasajeros y nacional/internacional enero–septiembre son exactas.
La conciliación permite investigar operaciones con el universo completo;
no identifica por sí misma cada celda ruta×aerolínea ni valida su estimación.

La semilla nacional conservada abarca marzo–agosto de 2026, la internacional
abril–agosto; no septiembre. Los ajustes de pasajeros llegaron a julio.
Una semilla antigua no informa nuevas rutas, cierres, cambios de operador,
frecuencia o mezcla competitiva. Los ceros estructurales y faltantes se
mantienen explícitos; la masa no soportada no se reparte como si se observara.
Las diferencias entre semillas alternativas son sensibilidad, no intervalos
de confianza de vuelos realizados. Con los insumos actuales no se activan
estimaciones para meses nuevos.

## Qué se puede comparar con AICM

AICM conserva fechas, números y horarios UTC de **slots asignados con número AM**;
no confirma ejecución ni identifica por sí solo al operador efectivo.
AeroDataBox conserva agregados mensuales por ruta/operador; no quedan filas
individuales con fecha, hora, número y estado. El adaptador excluyó cancelaciones
explícitas y `IsCodeshared`, pero aceptó estados no confirmatorios y códigos
compartidos desconocidos. No es posible rehacer una deduplicación por vuelo,
alinear zonas horarias o dar una tasa de coincidencia vuelo a vuelo.
En la captura internacional agregada abril–julio, 38,9–41,7 % del peso tiene
estado no confirmatorio. Ese porcentaje no es una tasa de cancelación ni
una medición del histórico nacional.

El contraste disponible es mensual y direccional en MEX, como **proxy de marca
AM frente a Aerovías + Connect**, con los límites anteriores:

| Mes 2026 | Direcciones comunes | Slots en esas direcciones | Semilla expandida | Suma de diferencias absolutas por dirección |
|---|---:|---:|---:|---:|
| Abril | 89 | 10.245 | 10.572 | 2.261 |
| Mayo | 90 | 10.531 | 9.759 | 1.676 |
| Junio | 88 | 10.094 | 8.521 | 1.915 |

No se eliminaron duplicados de slots: ya eran únicos por fecha, dirección,
número, sufijo y horario. Las diferencias de conteo no permiten decidir qué
vuelos individuales coincidieron, se cancelaron o se operaron.

## Ensayo temporal retrospectivo: utilidad de AICM como covariable

Calibración en **abril**; validación en **mayo** contra salidas realizadas BTS
T-100, clase regular de pasajeros `F`, operador Aerovías. Se eligieron por
reglas previas las celdas MEX–EE. UU. con fuentes disponibles y ciudad AFAC
sin ambigüedad de aeropuerto: **12 direcciones/mes de 38 candidatas de abril**,
619 salidas BTS en mayo. AICM se usa como covariable de marca/programación,
no como prueba del operador de cada vuelo.

| Estimación retrospectiva de mayo | Error absoluto ponderado (WAPE) | Error absoluto medio por dirección/mes |
|---|---:|---:|
| Semilla de abril × vuelos agregados AFAC de mayo | 2,80 % | 1,44 vuelos |
| Slots AICM de mayo × razón BTS/slots aprendida en abril | 16,06 % | 8,28 vuelos |
| Combinación fija 50/50 de ambas | 9,37 % | 4,83 vuelos |

No se usaron celdas BTS de mayo para calibrar ni elegir el peso 50/50. El AFAC
del mes objetivo ya publicado es un insumo para desagregar; no se está
pronosticando un mes sin datos. El ensayo no muestra mejora al añadir AICM.
Es un ensayo retrospectivo, no una campaña prospectiva intocada: la semilla y
los crosswalks ya existían antes de este ensayo y su desarrollo tuvo contrastes
T-100. Es un solo mes, seis mercados, cobertura seleccionada y roles de fuente
parcialmente diferentes; no valida México completo, Volaris/Viva, rutas
nuevas ni la estabilidad de una semilla envejecida varios meses.

**Recomendación:** conservar el histórico etiquetado; explorar AFAC + semilla
como estimación de operaciones, con revisión de cobertura/universo, sensibilidad
y validación temporal adicional. Si se desarrolla, declarar periodo/edad de la
semilla, fracción de vuelos AFAC sin soporte y bandas de escenarios entre
semillas históricas estrictamente anteriores; no llamarlas intervalos de
confianza. Mantener AICM como programación y contraste
local en MEX. No añadirlo como una corrección validada de vuelos realizados.
Antes de reutilizar la semilla tras cancelar, revisar la
[frontera contractual documentada](cloud-development.md#proveedores-pagados-y-github).

## Auditoría de fuentes y uso de Gold

La meta de representación se comprueba con un denominador fijo de vuelos
regulares AFAC. Se muestran por separado observaciones, estimaciones y
programación. Una estimación conserva ese nombre aunque el total supere el
umbral. No se activa el calendario por completar una captura: faltan la
validación de capas, la revisión de cobertura y la aprobación de cifras nuevas.
El inventario general sigue en el
[catálogo de fuentes y calendario](catalogo-fuentes-calendario.md); esta sección
solo precisa su uso para vuelos.

- `fact_international_route_observations` ya aporta observaciones al mapa.
  Antes de ampliar operadores, se comprueban operador efectivo, servicio
  regular, dirección, mes, original y precedencia. Colombia puede sustituir una
  estimación existente; se conservan también las sustituciones que reducen el
  conteo. Una fila ausente no se convierte en cero.
- Para ANAC Brasil, verificar `GRUPO_DE_VOO=REGULAR`, `NATUREZA=INTERNACIONAL`
  y `DECOLAGENS` en el original permite revisar la clasificación de una
  observación ya contada. No añade vuelos al total amplio. Se conserva el
  calendario nativo descrito por la
  [metodología de ANAC](https://www.anac.gov.br/acesso-a-informacao/dados-abertos/areas-de-atuacao/voos-e-operacoes-aereas/dados-estatisticos-do-transporte-aereo/48-dados-estatisticos-do-transporte-aereo).
- Los datos de puntualidad CAA requieren cautela: sus
  [notas metodológicas](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/uk-flight-punctuality-statistics-notes/)
  permiten atribución al responsable comercial y destinos finales con escalas.
  La marca comercial no acredita por sí sola el operador físico de un tramo.
- Aena aporta agregados por aerolínea y aeropuerto, o por mercado de todas las
  aerolíneas. No se cruzan para inventar una celda de operador y ruta. Una
  columna de salidas completamente nula sigue siendo no disponible.
- AICM y OMA aportan programación; AIFA y AFAC aportan márgenes o presencia
  cuando falta el cruce de operador y ruta. Esos productos sirven para
  contraste, pero no rellenan vuelos realizados sin evidencia adicional.
- Una nueva fuente de movimientos, como
  [ANAC Argentina](https://datos.transporte.gob.ar/dataset/aterrizajes-y-despegues-procesados-por-la-administracion-nacional-de-aviacion-civil-anac/archivo/7b6d0103-0a69-4c67-aed9-33cb58ae12f5),
  requiere comprobar calendario, operador y continuidad física. No se corrigen
  movimientos incompatibles por inferencia ni se toma la fecha de llegada
  extranjera como fecha de salida mexicana.

### Apéndice técnico: comparar candidatos sin activarlos

`scripts.research.flight_gap_options` ejecuta una comparación privada y sin red
con la misma base que `scripts.research.flight_representation`. Comprueba hashes
de capturas, conteo independiente de Colombia, registros originales de Brasil y
coincidencia con las celdas del mapa. Mantiene el denominador y el estimador;
no modifica Gold, el warehouse, exportadores, aprobaciones ni `site/`.

```bash
python -m scripts.research.flight_gap_options \
  --site /ruta/exportacion-retenida \
  --gold data/gold \
  --private-root /ruta/respaldo-privado \
  --bronze /ruta/bronze-retenido \
  --colombia /ruta/captura-colombia.json \
  --colombia-count /ruta/conteo-colombia.json \
  --out /ruta/privada/fuera-del-checkout-publico
```

Ambas capturas colombianas requieren su `.meta.json` con SHA-256. La ejecución
no sustituye la validación de linaje ni la integración del operador en el
exportador: esas tareas preceden a cualquier activación. Los resultados y
originales nuevos se revisan en el respaldo privado. No se copian a este plan.

## Reproducir sin red ni nuevas capturas

```bash
# Desde el respaldo privado; no usar --fix:
python verify_snapshot.py
python scripts/verify_derived.py
# Desde la raíz del repositorio público:
python -m scripts.research.afac_frozen_flights \
  --private-root /ruta/al/respaldo-privado \
  --out analysis_runs/research/afac-flights-20261015.json
```

El script queda versionado; resultados detallados y agregados del proveedor
permanecen ignorados/privados. Registra hashes de inputs públicos, agregados privados y de su código.
No exporta datos al dashboard, no escribe aprobaciones ni consume APIs.

## Veredicto de calidad para nuevas actualizaciones

Las estadísticas agregadas de vuelos **son públicas**. El problema no es una
necesidad general de información confidencial: es la disponibilidad del cruce
exacto de operador, ruta, sentido, servicio y mes. AFAC permite una red oficial
sin estimación cuando se muestran **todas las aerolíneas**; sus marginales no
permiten atribuir automáticamente cada ruta a las tres compañías del panel.

| Zona/producto | Qué podemos sostener | Recomendación de uso actual |
|---|---|---|
| Nacional | AFAC oficial por par direccional de ciudades, hasta septiembre; marginal separada por compañía. AICM ofrece programación AM en MEX, sin prueba de ejecución ni cobertura nacional de todos los operadores. | Mostrar la red AFAC de todas las aerolíneas si se necesita actualidad oficial. Mantener por separado el histórico estimado por compañía. La calidad de una estimación futura nacional por operador **no está demostrada**. |
| Estados Unidos | BTS aporta salidas realizadas por operador/ruta/sentido/mes; el índice y descarga actuales llegan a julio. Un operador ausente de un mes no se convierte en cero. | Mantener observados con mes y alcance visibles. «Estados Unidos» no significa Norteamérica completa: Canadá requiere fuente propia. |
| Brasil | ANAC original completo llega a septiembre; regular internacional AMX comprobado. Q3 tiene 10 celdas direccionales por operador y mes, 184 salidas. | Mantener el alcance observado real, sin extenderlo a otros operadores o países. La captura actualiza el dato; no convierte toda Sudamérica en observada. |
| Colombia | Fuente actual hasta julio: movimientos registrados provisionales bajo los supuestos documentados. | Conservar como producto contextual separado; no sumarlo como salidas realizadas ni usarlo para una tasa de cobertura de vuelos. |
| Reino Unido/España | CAA agosto LHR–MEX tiene límite de atribución comercial; Aena publica septiembre agregado, mientras detalle por compañía requiere acceso registrado y exportación verificable. | Conservar fuente y alcance contextual. No declarar operador físico o ruta×operador a partir de marginales. |
| Resto de Europa, Asia y Sudamérica | La semilla histórica no observa cierres, altas, cambios de operador ni de frecuencias posteriores. No hay validación suficiente de nuevas celdas/meses en esas zonas. | Preferir archivo histórico o estimaciones ocultas por defecto hasta validar su renovación. No se elimina ninguna región mediante este veredicto: la elección de presentación queda al dueño. |

El dueño eligió posteriormente una **segunda fase**, después de publicar y
verificar la versión actual: `Nacional` AFAC de todas las aerolíneas,
`EE. UU.` observado BTS con selector de operador según disponibilidad real,
e `Internacional` AFAC de todas las aerolíneas **sin Estados Unidos**. Este
último admite Canadá, Centroamérica (incluido Caribe), Sudamérica, Europa y
Asia donde existan datos. La nueva familia de mapa por ciudades no está
implementada ni forma parte de la primera publicación. Los KPI financieros y
su universo de tres aerolíneas conservan su significado independiente.

### Qué denominador AFAC es identificable

En **julio–septiembre de 2026**, el producto regular OD reporta 115.587 vuelos
nacionales y 92.212 internacionales de todas las aerolíneas. En el resumen por
empresa, las tres compañías del panel —Aerovías más Connect, Viva y Volaris
México— suman **108.883 nacionales y 32.773 internacionales: 141.656**.
Es posible evaluar un numerador del mismo universo nacional/internacional
contra esas marginales, previa conciliación de servicio, calendario y
operadores; no permite un desglose de compañía por país o ruta.

Por ejemplo, AFAC reporta en Q3 438 vuelos regulares México–Brasil, 3.559
México–Colombia y 906 México–Reino Unido de **todos los operadores**. Dividir las
184 salidas AMX observadas en ANAC entre 438 y denominar el resultado
«cobertura de Aeroméxico» sería incorrecto. Faltaría el denominador AMX de ese
país, con sentidos y calendario comparables. Las hojas `FLET NAC` y `FLET INT`
del original están separadas de `REG NAC` y `REG INT`; no se suman fletamentos
a un denominador regular ni se reemplazan vuelos por pasajeros.

Una tasa de cobertura observada requiere **salidas observadas representadas /
vuelos oficiales del mismo operador, territorio/ruta, meses, sentidos y
servicio**. La representación de una estimación no mide su exactitud. Si ese
volumen comparable no se identifica, mostrar «No disponible» y explicar el
alcance; se pueden informar por separado los meses/celdas soportados o la
presencia de rutas sobre un universo explícito, sin llamarlo cobertura de
tráfico de las tres compañías. Los faltantes no son ceros.

### Diagnóstico temporal adicional de la semilla fija

Se ejecutó un nuevo ensayo offline con semilla de **abril** fija y los totales
AFAC publicados de cada mes como insumo. La referencia independiente fueron
salidas realizadas BTS, clase regular de pasajeros `F`, México–EE. UU., en
**mayo, junio y julio**. No se ajustaron shares ni se eligieron parámetros con
celdas operador×ruta del mes objetivo. Se excluyeron ciudades multiaeropuerto
sin asignación identificada, faltas de crosswalk y rutas/operadores sin soporte.

Sobre **247 celdas y 7.679 salidas** comparables, el WAPE fue **5,47 %**, con
sesgo agregado **+2,65 %**. El WAPE mensual fue **4,04 % en mayo, 5,78 % en junio
y 6,91 % en julio**. Estos resultados corresponden solo al **37,8 % de las
20.301 salidas observadas** del universo de referencia seleccionado; no son
precisión ni cobertura del mapa completo. Aerovías no aparece en julio en la
edición BTS capturada, por lo que no se fabricó una observación nula ni se
evaluó su error de ese mes.

Las muestras mensuales cambian. En el control de las **mismas 70 celdas**
presentes en los tres meses, sin Aerovías por faltar su reporte de julio, el
WAPE fue 4,62 %, 5,29 % y 5,85 %, respectivamente. El resultado muestra utilidad
de corto plazo en el subconjunto probado, pero no aísla un efecto causal de
edad frente a cambios de mercado ni establece una ley de error o bandas de
confianza. Es **desagregación retrospectiva** con AFAC del mes
objetivo, no pronóstico de un mes sin publicar. Se usan ediciones revisadas,
no el conjunto de información disponible en tiempo real de cada mes; el
desarrollo previo de semilla/crosswalk no fue una campaña prospectiva ciega.
No valida nacional, otros continentes, septiembre, nuevas rutas ni celdas
ausentes. El ensayo previo de 12 direcciones AMX/MEX en mayo y sus resultados
con AICM conserva sus propios límites; no se reemplaza por este diagnóstico.

El método reproducible está en
`scripts/research/frozen_seed_temporal_validation.py`; entradas, desgloses,
exclusiones, hashes y resultado completo permanecen privados. No activa un
estimador, modifica Gold, produce aprobaciones ni publica cifras.

## Actualización pública y consumidores

El corte de revisión del **1 de noviembre de 2026, hora de México**, distingue
captura nueva, certificación de un original retenido, proyección local y sitio
publicado. Los recibos de esta ronda conservan horas reales, originales,
consultas, hashes y reconciliaciones en el respaldo privado; un replay sin red
no renueva la fecha del original. La fecha de un trimestre o de una captura
tampoco acredita tres meses observados en todos sus bloques.

Las alternativas públicas estaban identificadas, pero no constituían una
migración automática completa. Había adaptadores de originales retenidos,
consultas y programación con granos diferentes; varias rondas reprodujeron
esos insumos sin buscar o capturar una edición nueva. En particular, junio era
el máximo de la **captura ANAC conservada**, no un máximo verificado del portal;
el consumidor del mix de Aeroméxico aún leía una serie heredada; y una propuesta
de consultas de Noticias no ejecutaba búsquedas. Estos son huecos de ejecución
y consumo concretos, no una consecuencia necesaria de haber detenido AeroDataBox.

| Bloque visible | Fuente y proceso normal | Exportación y consumidor | Periodo realmente comprobado / estado del corte |
|---|---|---|---|
| Lectura: tesis por entidad y periodo | Expedientes del agente de análisis, ledger privado e identidades aprobadas; skill de análisis y exportador `web_export.analysis` | `analysis/<entidad>/<periodo>.json` o su ruta de compatibilidad; `views/executive/narrative` | Aprobación e identidad exacta se verifican por tesis. Una revisión local no constituye publicación ni permite rellenar otra entidad con el relato de Aeroméxico. Estado editorial vigente en [periodos-dashboard](periodos-dashboard.md). |
| Economía: ingresos, costes, márgenes, unitarios, comparación | SEC/IR Aeroméxico, Viva y Volaris; parsers financieros, Silver y `fact_carrier_metrics`; skill financiero y `executive_summary` | `executive.json`; `views/economy` y tarjetas ejecutivas | Q3 disponible para las tres aerolíneas en los expedientes revisados. La síntesis Industria tiene su propio cálculo/aprobación; no se fabrica por tener las tres fuentes. Esta ronda de fuentes de rutas no recapturó esos estados. |
| Mercado: pasajeros, cuota, crecimiento, ranking y segmentos | Catálogo oficial AFAC → resumen anual XLSX → parser `src.parse.afac.monthly_stats` → Gold y `scripts.build_afac_market_review`; skill tráfico | `market.json`; `views/executive/market`, cálculos de Mercado | Septiembre capturado realmente y procesado en revisión local. El índice Datatur atrasado no invalida el workbook oficial de septiembre. No confundir resumen anual con el boletín base de `afac_carriers`. |
| Vuelos: tarjetas operativas y mix nacional/internacional | Métricas de emisor para tarjetas; AFAC por empresa y segmento para el mix | `executive.json` y `market.json`; `views/flights/carriers` | Tarjetas Q3 por emisor; mix AFAC hasta septiembre para AM, Viva, Volaris e Industria. Se corrigió el consumidor de AM que antes terminaba en agosto. |
| Vuelos: Norteamérica observada | Índice BTS ReleaseInfo + POST T-100 real → `bts_candidate` → Silver/Gold por operador, sentido y mes → resolución `flight_cells` | `flights/**/international/<periodo>.json`; mapas y filtro de observados | Recaptura e índice actuales confirman julio como último mes publicado. Sus 1.527 filas seleccionadas coinciden exactamente con la base previa; agosto/septiembre no se rellenan. Se capturó además la edición revisada de 2023. |
| Vuelos: Brasil observado | JSON completo ANAC por rangos de una misma edición → `scripts.refresh_anac_routes` → retención/certificación → normalizador internacional y `scripts.build_anac_route_review` | Ocho redes generadas para AM e Industria, Q3 y sus meses, y manifiesto de disponibilidad (nueve JSON); consumidor normal del mapa | **Septiembre** verificado en el original completo recién capturado. Q3 contiene julio, agosto y septiembre. Industria conserva las celdas AMX; no se copian a Viva o Volaris. Proyección local comprobada, sin publicación. |
| Vuelos: Colombia | Consulta real de disponibilidad AMX/SLI; conteo/filas/conteo + metadatos → `source_updates.aerocivil`, contratos y linaje | Producto provisional de movimientos, proyección `recorded_movements`, separado de salidas | Consulta actual solo devuelve hasta julio. Captura nueva: 347 movimientos provisionales bajo los supuestos documentados; pasajeros, asientos y salidas siguen nulos. No se declara septiembre ausente por un recibo retenido. |
| Vuelos: Reino Unido | Índice CAA 2026 → CSV Arrival/Departure real → adaptador retenido `caa` | Candidato de observaciones LHR–MEX; no eleva cobertura de operador físico | Agosto es el último enlace mensual comprobado; seis métricas certificadas y replay. La atribución comercial admitida por CAA exige prueba adicional antes de usarlo como vuelos de un operador físico. |
| Vuelos: España | Exportación manual Aena, con originales y grano documentado | Actividad aeropuerto×compañía y mercado agregado; consumidores separados | Captura retenida hasta julio. No se obtuvo una exportación nueva en esta ronda. No unir marginales para inventar aerolínea×ruta; la falta de captura no acredita falta de publicación. |
| Vuelos: programación MEX y presencia | Catálogo AICM → PDF AM verano y páginas históricas semanales → `aicm_slots`; documentos de OMA/AIFA conservan su propio grano | Capa de slots/programación y contexto, separada de `flight_components` observados | AICM recapturado: 2.836 asignaciones en 61 páginas; la edición interna sigue siendo 5 febrero, temporada 29 marzo–24 octubre. Página semanal consultada 27 septiembre–3 octubre. No acredita ejecución ni operador físico. |
| Vuelos: estimación nacional y resto internacional | Márgenes AFAC OD y empresas + semilla histórica retenida; investigación y ajustes de pasajeros permanecen separados de vuelos | Redes estimadas históricas etiquetadas, con periodos reales de cada componente | AFAC septiembre capturado y certificado: 36 reconciliaciones de márgenes exactas. Falta identificación ruta×operador y validación temporal suficiente para estimar vuelos de nuevos meses; no se activó el prototipo ni se prolongó la semilla por calendario. |
| Noticias: archivo y selección mensual | Búsqueda nativa real + lectura del editor → revisión JSON → `source_updates.editorial_news` → circuito editorial; skill Noticias | Paquete de decisión inmutable y preview local por `dashboard.news`; posteriormente `web_export.news`/`news.json` solo con aprobación; `views/news` | Tres fichas antiguas aprobadas hasta julio. Nueva selección agosto/septiembre/octubre: 7/7/9 eventos, 24 procedencias y 28 consultas registradas; tres certificaciones y replay. Son 16 hechos adicionales y siete relecturas. El dueño aprobó el lote exacto de 23 tras la preview; el exportador normal contiene ahora 26 fichas aprobadas y 27 procedencias. Los 23 recibos conservan ese alcance, separado de las aprobaciones analíticas y de la publicación efectiva. |

FX, combustible, acciones, tráfico aeroportuario y productos de demanda
conservan sus tareas y contratos de fuente. Tener un adaptador disponible no
crea una gráfica visible: cada ronda debe demostrar el consumidor que usa el
resultado. El producto auxiliar de demanda retirado de la interfaz no debe
utilizarse para declarar actualizado Mercado o Vuelos.

### Ejecución y límites verificados

La captura nueva ANAC usa el descargador de rangos existente con límites
explícitos de tamaño y solicitudes, continuidad de bytes y ETag/Last-Modified.
El JSON completo se conserva sin filtrar antes de certificar. El script de
revisión compara cada cifra normalizada contra las métricas nativas,
valida 22 registros de linaje directo y resuelve las celdas con el generador
normal, contratos y privacidad. Conserva otros componentes, rechaza periodos
no cubiertos y no publica ni escribe Gold activo. Una segunda generación desde
la proyección local produce exactamente los mismos nueve archivos; se corrigió
la acumulación de notas de cobertura en el generador común.

Para las siguientes rondas, aplicar las skills de
[coordinación](../.agents/skills/airline-update-coordinator/SKILL.md),
[rutas](../.agents/skills/airline-update-routes/SKILL.md),
[tráfico](../.agents/skills/airline-update-traffic/SKILL.md) y
[Noticias](../.agents/skills/airline-update-news/SKILL.md). El inventario de cierre
debe registrar fuente → tarea → captura/ingesta → transformación → exportación
→ consumidor, el último periodo nativo, la última captura real exitosa y el
estado separado de revisión, aprobación y publicación. Si falta un eslabón,
se declara el eslabón pendiente; no se llama «todo actualizado» al conjunto.

Los límites abiertos son concretos: nueva exportación Aena, atribución física
CAA, actualización del producto de programación de otros operadores cuando
exista el cruce necesario, tratamiento de celdas nuevas sin soporte de la
semilla y conciliación de la integración global antes de reconstruir desde un
warehouse anterior. El Gold internacional heredado aún requiere migrar la
semántica colombiana de salidas a movimientos antes de servir como base de una
reconstrucción completa; la proyección revisada conserva esa separación. Las
aprobaciones editoriales/analíticas y la publicación del sitio son estados
posteriores, no fallos de acceso a estas fuentes gratuitas.

## Pendientes

Conservar en cada publicación el mismo universo y las identidades aprobadas;
comprobar también el sitio servido. No continuar la búsqueda de fuentes para alcanzar el
95 %. Futuras actualizaciones, periodos y calendarios requieren su alcance y
validación propios. Conservar las bitácoras enlazadas mientras sean
procedencia del histórico o evidencia de un esfuerzo abierto. No retirar una
fuente por edad ni duplicar el catálogo general en nuevos reportes de estado.

La [decisión del lote de 23 noticias](decisiones/20261102-noticias-23.md) quedó registrada a las 01:33:13 UTC del 2 de noviembre. Preserva íntegros los diez registros anteriores del índice (siete extractos y tres noticias) y añade exclusivamente las 23 noticias revisadas: 33 registros en total. No concede aprobación a las cuatro nuevas lecturas ni al mapa de la segunda fase.
