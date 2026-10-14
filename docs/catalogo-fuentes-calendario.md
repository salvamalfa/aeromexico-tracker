# Catálogo de fuentes, métricas y rondas de actualización

Revisión: 13 de octubre de 2026. Estado: **fase 1 documental; calendario propuesto, sin automatizaciones ni ingestas nuevas**.

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

| Fuente / producto | Métricas y grano | Incorporado al corte | Disponibilidad oficial observada / adquisición | Dependencias y brecha |
|---|---|---|---|---|
| Aeroméxico IR, resultados | Pasajeros, capacidad, ocupación, ingreso/costos unitarios, finanzas, notas y expectativas; trimestre del grupo | PDFs 2021Q1–2026Q2; operación IR histórica 2021Q1–2024Q2 y finanzas IR 2021Q1–2025Q2; periodos recientes se completan por SEC | [Resultados IR](https://ir.aeromexico.com/financial-information/quarterly-results); `src/ingest/aeromexico_ir.py` usa 22 URLs registradas y descarga ausentes | Descubrir links de periodos nuevos y sus estados financieros; no revisita URLs existentes. Los límites históricos de los dos parsers son deliberados, no un parser genérico de futuros releases |
| Aeroméxico tráfico IR / SEC 6-K | Pasajeros, ASM/RPM y ocupación total/nacional/internacional; mes del grupo | Serie mensual SEC hasta junio 2026, trimestral hasta 2T26 | [Tráfico IR](https://ir.aeromexico.com/news-events/traffic-reports) ya muestra septiembre; SEC preserva anexos y presentación regulatoria | Parser actual busca anexos HTML `ex99*.htm`; falta descubridor IR mensual que conecte novedades fuera del archivo SEC existente. No inferir finanzas de tráfico |
| Volaris IR / SEC | Operación y estados financieros; trimestre/mes; grupo y subsidiarias según reporte | Trimestrales hasta 2T26 | [IR](https://ir.volaris.com/news-events/press-releases/), [eventos](https://ir.volaris.com/news-events/events-and-presentations/); SEC CIK 1520504, perfiles existentes | Catálogos `current` se reutilizan por URL en `ingest/peers/stage5.py`; añadir revalidación de catálogos. Pasajeros reservados/transportados y universo geográfico deben conservar definición |
| Viva IR / BMV GVIVA | Operación, finanzas y tráfico; mes/trimestre | 2023Q1–2026Q2 financiero/operativo | [BMV GVIVA](https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD), PDFs InvestorCloud; `ingest/peers/stage5.py` | Plantilla de URLs limitada explícitamente a 2026Q2; descubrir producto mensual y futuros trimestres. Mantener preliminar/no auditado y reconciliaciones H1−Q2 |
| SEC Aeroméxico | Formularios 6-K, 20-F, F-1 y anexos; artefacto/presentación | Índice local hasta presentación 14 agosto; financieros hasta 2T26 | [SEC](https://www.sec.gov/edgar/browse/?CIK=1561861&owner=exclude); submissions/companyfacts, `ingest/sec/discover.py` | Identificación `SEC_USER_AGENT` existente en entorno; discovery refresca catálogos, reutiliza documentos existentes. Un formulario disponible no asegura XBRL financiero |
| BMV AERO/VOLAR | XBRL por concepto, moneda, duración/instante y periodo; respaldo/revisión contable | Paquetes hasta 2T26, con comparativos y TTM | [Catálogo XBRL](https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl); `ingest/bmv/download.py` descubre ZIP/miembro | Catálogo se refresca; paquetes iguales por URL se cachean. Evitar sumar duración trimestral, acumulada y TTM o tratar balance como flujo |
| AFAC, resumen por aerolínea / DATATUR | Pasajeros por operador/mercado y servicio regular/fletamento; mes | Histórico 2015–2025; canónico mensual 2026 hasta junio | [DATATUR](https://datatur.sectur.gob.mx/SitePages/afac.aspx), [PDF agosto](https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_2026_08.pdf); HTTP + descarga asistida cuando gob.mx bloquea | Landing rezagada dice julio, pero PDF del reporte mensual contiene agosto. Parser PDF tiene `range(1,7)` y validación hasta junio. Fecha exacta de publicación agosto no verificada; no usar fecha de captura como publicación |
| AFAC aeropuertos | Pasajeros/operaciones del aeropuerto completo; mes | Consultas y documentos de investigación, no nueva serie automática certificada | [Estadísticas AFAC](https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404) | Producto independiente del resumen por aerolínea; no atribuir total del aeropuerto a Aeroméxico. Disponibilidad y edición por comprobar, acceso HTTP 403 en esta revisión |
| AFAC países | Pasajeros por país/mercado; mes | Boletín de investigación preservado de julio | Mismo catálogo AFAC; `data/bronze/afac_research/` y selección explícita | No convierte país en ruta u operador. Conservar fuente/edición propia |
| AFAC origen–destino y marginal por aerolínea | Totales por par de ciudades y totales por empresa, granos separados | Referencias para estimación hasta julio 2026 | `ingest/afac/margins.py`, `international_margins.py`; originales `sase-*` y `resumen-*` | Usar misma edición acumulada para reconciliar; disponibilidad de edición agosto de ambos XLSX sigue sin verificar. Totales/marginales **no observan empresa×ruta** |
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

Calendario operativo en UTC con zona del emisor en cada evidencia. Para
agrupar días hábiles se usa calendario bancario mexicano; las horas de anuncio
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

`refresh.yml` solo valida frescura/Gold, con cron trimestral; no ingiere ni
construye el sitio. Noticias del chat es manual y consume metadatos ya
comprometidos. Pages despliega `site/` revisado sin regenerarlo; Railway atiende
el chat. La cadena futura sigue siendo detección → captura → validación → lote
→ revisión/aprobación → gate → PR → despliegue verificado.

## Aceptación de fase 1 y siguiente decisión

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

La fase siguiente debe acordar qué lotes de datos y análisis requieren revisión
humana antes de publicación. Preparar este catálogo no altera el límite vigente.
