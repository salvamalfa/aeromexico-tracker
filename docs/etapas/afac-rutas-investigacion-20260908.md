# Investigación de cobertura de rutas AFAC

> **Método canónico:** el procedimiento completo y verificado de estimación
> de pasajeros por ruta y aerolínea está en
> [`../estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md).
> Este documento es un reporte de su etapa, no la especificación.

Fecha: 8 de septiembre de 2026. Alcance: investigación y preservación de fuentes. No se integraron datos en Silver/Gold, no se cambió la UI ni se activó evidencia del Analysis Agent.

## Resultado

AFAC permite ampliar el análisis de mercados a rutas nacionales y a otras regiones del mundo. Los libros de origen–destino inspeccionados publican tráfico del mercado por par de ciudades, dirección, mes y servicio, sin identificar aerolínea. El resumen por empresa sí separa Aeroméxico y Connect, pero carece de origen–destino. No existe una clave con la cual unir ambas tablas y obtener el tráfico de Aeroméxico en cada ruta.

El boletín por país aporta otra dimensión útil: participación de aerolíneas en mercados internacionales. ANAC Brasil es una alternativa oficial cuyo esquema y muestra descargada sí incluyen operador y aeropuertos. La cobertura mundial de Aeroméxico requiere combinar fuentes de forma explícita y verificar periodos; no está resuelta por una única tabla AFAC de las inspeccionadas.

## Investigación previa y acceso

Se revisaron `docs/etapas/vuelos-reporte.md`, `docs/afac-inventario.md`, `docs/decisiones/decision-005-acceso-afac.md`, el descargador AFAC y las convenciones de `src/common/storage.py`. No se encontraron AGENTS.md en la raíz de AMEX ni en el proyecto mediante la búsqueda realizada. Hay cambios anteriores de otras sesiones; se conservaron.

La investigación previa documentaba únicamente la ausencia de rutas en el AFAC integrado. En esta entrega se abrió el catálogo oficial con Computer Use y se observaron los enlaces vigentes. Se intentó un clic normal sobre el Excel de origen–destino; no se confirmó un archivo en Descargas. Después, HTTP directo a las URL observadas entregó archivos válidos (200, firmas ZIP/XLSX y PDF correctas). Los artefactos se registraron como `httpx`, sin atribuirles una descarga por Computer Use. No hubo CAPTCHA ni elusión de controles. Los 403 de consultas anteriores no se interpretaron como ausencia de datos.

## Matriz de fuentes

| Fuente | Cobertura y periodo verificados | Grano / identificación | Métricas | Uso y límites |
|---|---|---|---|---|
| [AFAC origen–destino julio 2026](https://www.gob.mx/cms/uploads/attachment/file/1100280/sase-julio-2026-27082026.xlsx) | México doméstico e internacional; enero–julio 2026. Tablas regulares: 609 pares direccionales nacionales y 979 internacionales; 37 etiquetas de país incluyendo México en REG INT | Ciudad origen/destino, país en internacional, mes, regular/fletamento. Sin empresa ni códigos de aeropuerto | Vuelos, pasajeros, carga kg. Sin asientos | Mapa y tendencias del mercado. No permite pasajeros ni cuota de Aeroméxico por ruta, ocupación por ruta o identificación inequívoca de aeropuertos |
| [AFAC origen–destino 2025](https://www.gob.mx/cms/uploads/attachment/file/1055167/sase-diciembre-2025-05022026h.xlsx) | Libro anual 2025 descargado e inspeccionado; misma estructura de cuatro tablas de servicio | Par de ciudades direccional y mes; sin operador | Vuelos, pasajeros y carga | Base candidata para comparar abril–junio 2025 con abril–junio 2026. La validación exhaustiva de cifras del libro 2025 queda para la integración |
| [Catálogo histórico origen–destino](https://www.gob.mx/afac/acciones-y-programas/estadistica-mensual-operativa-monthly-traffic-statistics) | Enlaces visibles 1992–2025; se descargó una muestra 2025, no todos los años | Libros anuales con datos mensuales; formatos antiguos aún no inspeccionados en esta investigación | Por confirmar por familia histórica | Permite planificar histórico de mercados; no afirmar cobertura validada de todos los años |
| [AFAC resumen por empresa julio 2026](https://www.gob.mx/cms/uploads/attachment/file/1100279/resumen-julio-2026-27082026.xlsx) | Enero–julio 2026; empresa nacional/extranjera, servicio nacional/internacional y regular/fletamento | Aeroméxico (Aerovías de México) y Aeroméxico Connect (Aerolitoral) separados. Sin rutas | Pasajeros, vuelos, carga; OPREG/OPFLET incluyen horas, correo y equipaje | Operación de la compañía y subsidiaria, reconciliaciones agregadas. No cruzar con O-D para repartir tráfico |
| [AFAC boletín por país julio 2026](https://www.gob.mx/cms/uploads/attachment/file/1100282/stats-por-pais-es-jul2026-27082026.pdf) | 37 páginas; gráficas mensuales recientes, acumulado enero–julio, series anuales y participaciones de julio. Diferente ventana según gráfico | Mercado México–país; participaciones por aerolínea y principales ciudades en gráficos separados | Pasajeros, vuelos, PLF agregado, cuota por compañía | Contexto regional y competencia. Las participaciones de julio no son cuotas de 2T26 ni de cada ciudad. Preservar la etiqueta publicada; no asumir consolidación de Connect |
| [AFAC metodología](https://www.gob.mx/cms/uploads/attachment/file/843705/descripcion-variables-metodologia-24072023.pdf) | Documento de 19 páginas enlazado desde la página metodológica | Terminología general OACI | Definiciones | Ayuda conceptual; no contiene un diccionario operativo que resuelva la equivalencia OFOD/segmento BTS ni ciudades/aeropuertos |
| [ANAC Brasil: metadatos](https://www.anac.gov.br/acesso-a-informacao/dados-abertos/areas-de-atuacao/voos-e-operacoes-aereas/dados-estatisticos-do-transporte-aereo/48-dados-estatisticos-do-transporte-aereo) | Actualización mensual; compañías extranjeras con operaciones vinculadas a Brasil. Archivo por bloque 2021–2030 anunciado en el directorio | Empresa operadora, aeropuertos ICAO, año, mes y tipo de vuelo; muestra de registros reales inspeccionada | Pasajeros pagados/gratis, asientos, salidas, ASK/RPK, carga y otras variables | Mejor candidato acotado para extender tráfico propio a Brasil. Requiere descarga completa, control de revisiones y validación de definiciones |
| [Aerocivil Colombia](https://www.aerocivil.gov.co/analitica/Paginas/Pasajeros_Carga.aspx) | Portal anuncia datos desde 2014 y filtros de operador, origen–destino y tipo de tráfico | Detalle anunciado por autoridad; archivos no inspeccionados | Pasajeros y carga; otras métricas por confirmar | Siguiente alternativa regional. La consulta automatizada de la página de bases devolvió 403; no se certifica contenido de sus archivos ni cobertura 2026 |
| [Aeroméxico, rutas y comunicados](https://www.vuela.aeromexico.com/rutas-y-comunicados-oficiales/) | Fuente comercial/oficial candidata; no se descargó una red versionada de 2T26 | Rutas/destinos según publicación; requiere verificar operador y fechas de inicio/fin | Presencia de ruta, anuncios y contexto; no tráfico observado por ruta | Útil para una red documentada de la compañía con métricas N/D donde no existan. Las páginas comerciales pueden incluir conexiones/codeshare; no equivalen a segmentos operados |

## Ejemplos verificables de mercados

Cálculos Python: suma de abril, mayo y junio de 2026 en la versión del Excel de julio. **Una dirección, todas las aerolíneas del mercado.** Los nombres de ciudad se conservan como en la fuente. Estas cifras no deben rotularse como tráfico de Aeroméxico ni considerarse prueba de vuelo sin escala.

| Origen → destino | Pasajeros 2T26 | Vuelos 2T26 | Localizador de pasajeros |
|---|---:|---:|---|
| MEXICO → MONTERREY | 414,835 | 2,680 | REG NAC!S282:U282 |
| MEXICO → MADRID | 141,526 | 581 | REG INT!U516:W516 |
| MEXICO → PARIS | 73,807 | 269 | REG INT!U528:W528 |
| MEXICO → TORONTO | 45,409 | 313 | REG INT!U550:W550 |
| MEXICO → SAO PAULO | 37,979 | 180 | REG INT!U544:W544 |
| MEXICO → BOGOTA | 89,400 | 637 | REG INT!U493:W493 |
| MEXICO → TOKYO | 29,013 | 181 | REG INT!U549:W549 |

El archivo denomina sus tablas OFOD y usa pares de ciudades. No se ha demostrado que sean intercambiables con los segmentos sin escala de T-100. El caso de Tokio requiere especial cuidado con escalas y dirección. No convertir automáticamente MEXICO en MMMX ni una ciudad con varios aeropuertos en un único aeropuerto.

El boletín por país muestra para **julio 2026** participaciones de Aeroméxico de 39.3% en México–España (página PDF 8, folio impreso 7), 45.2% en México–Brasil (PDF 18), 11.1% en México–Canadá (PDF 3) y 57.4% en México–Japón (PDF 36). La página de España se verificó también visualmente: [captura](afac-rutas-evidencia-20260908/espana-julio-2026.png). Son cuotas del mercado bilateral de pasajeros, no cuotas por ruta. Connect aparece expresamente en otros mercados (páginas PDF 28–30), por lo que deben preservarse las identidades publicadas.

## Disponibilidad temporal

- Los archivos AFAC de julio contienen datos posteriores al corte de 2T26. Sus nombres indican `27082026`; el libro O-D tiene fecha interna de modificación 25 de agosto de 2026. Son señales de versión posterior, no prueba independiente del momento exacto de publicación. La fecha de 2022 del catálogo no fecha los adjuntos actuales.
- El 2T26 puede calcularse completo desde abril–junio de esta copia para una retrospectiva actualizada. No se autoriza su uso en el expediente histórico congelado al 13 de julio sin recuperar una versión acreditada disponible entonces.
- El libro 2025 tiene nombre con fecha 5 de febrero de 2026 y modificación interna del 4 de febrero. Es candidato a comparable previo, pero esas fechas por sí solas no prueban que los bytes descargados hoy estuvieran disponibles al corte.
- En el Excel 2026 las columnas agosto–diciembre contienen ceros de plantilla. Convertirlas en N/D con base en el periodo del producto; no tratarlas como ausencia de operación. 3T26 solo dispone de julio en esta copia. Comparar enero–julio o abril–junio contra los mismos meses; no contra años o trimestres completos cuando falten meses.
- El directorio ANAC muestra modificación del archivo el 9 de agosto de 2026. La regulación de remisión mensual a la autoridad no prueba fecha de publicación pública. Los metadatos advierten revisiones. Su uso histórico al corte permanece sin acreditar.

## Muestra verificable de tráfico propio: Brasil

Se inspeccionaron fragmentos originales del [JSON oficial ANAC 2021–2030](https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/Dados%20Estat%C3%ADsticos%20do%20Transporte%20A%C3%A9reo/Dados_Estatisticos_2021_a_2030.json). La descarga completa de 208,844,798 bytes no terminó dentro del presupuesto acotado de aproximadamente cuatro minutos y se detuvo. Luego el servidor atendió peticiones HTTP Range normales con estado 206: prefijo de 1 MiB y sufijo de 8 MiB, ambos conservados como archivos parciales identificados expresamente. No son copias completas ni versiones sucesivas del conjunto; no deben usarse sus diferencias como reexpresiones.

El prefijo permitió leer 1,012 objetos JSON completos de la muestra y verificar el esquema y la presencia de Aeroméxico en enero de 2021. El sufijo contiene registros de abril de 2026 y dos observaciones regulares con empresa `AEROVÍAS DE MÉXICO S.A DE C.V - AEROMÉXICO`:

| Periodo | Operación | Pasajeros pagados | Asientos | Salidas |
|---|---|---:|---:|---:|
| Abril 2026 | MMMX → SBGR | 6,635 | 7,825 | 30 |
| Abril 2026 | SBGR → MMMX | 7,131 | 7,800 | 30 |

Los objetos completos y el rango de bytes están en [anac-tail-inspection.json](afac-rutas-evidencia-20260908/anac-tail-inspection.json); el esquema en [anac-sample-inspection.json](afac-rutas-evidencia-20260908/anac-sample-inspection.json). Localizar por empresa, ANO=2026, MES=4, GRUPO_DE_VOO=REGULAR y aeropuertos de cada dirección. `EMPRESA_SIGLA` está vacío en estas filas: el futuro parser deberá resolver el operador desde su razón social verificada. No convertir ese vacío en ausencia de Aeroméxico.

Esta muestra confirma disponibilidad de cifras específicas del operador para esa ruta y mes. No certifica cobertura completa de abril, máximo histórico del archivo, mayo–junio ni un 2T26 completo. Los ceros de combustible de una empresa extranjera tampoco deben interpretarse como consumo nulo: la metodología limita esa variable a empresas brasileñas.

## Validación y evidencia conservada

Los originales están en `data/bronze/afac_research/`, `data/bronze/route_research/` y las muestras ANAC en `data/bronze/anac_research/`. Cada archivo conserva sidecar de metadatos y entrada en `data/bronze/_manifest.jsonl`, con URL, SHA-256, fecha de descarga y método. El directorio de investigación está separado de los prefijos de ingesta normal.

El [resultado de inspección](afac-rutas-evidencia-20260908/inspection.json) contiene inventario de artefactos, hashes verificados, encabezados, localizadores, fórmulas de los ejemplos y texto extraído por página. El [script de inspección](afac-rutas-evidencia-20260908/inspect_sources.py) puede ejecutarse desde la raíz con `.venv/Scripts/python.exe docs/etapas/afac-rutas-evidencia-20260908/inspect_sources.py`.

Controles ejecutados para el O-D 2026:
- Cuatro tablas: 609 registros REG NAC, 979 REG INT, 239 FLET NAC y 418 FLET INT. Son registros direccionales de la tabla, no conteos de rutas activas de Aeroméxico.
- Sin duplicados de las claves ciudad/país/dirección dentro de cada tabla.
- Sumas de las filas reconciliadas con todos los totales publicados; diferencias máximas inferiores a 0.000001 atribuibles a aritmética de coma flotante en carga.
- Se inspeccionaron las cinco hojas del libro; no hay hojas ocultas que aporten operador. Encabezados de rutas sin empresa ni asientos.
- En PAXREG del resumen por empresa, filas 10/11 separan Aeroméxico/Connect nacional y 24/25 internacional; se conservaron localizadores.

No se ejecutó una batería de regresión del dashboard porque no hubo cambios de implementación. La comprobación realizada valida la evidencia de investigación, no certifica un parser productivo.

## Propuesta del siguiente incremento

1. **Mercados AFAC 2025–julio 2026** (esfuerzo medio): parser separado con ciudad/país/dirección/servicio, máscara de meses disponibles, conciliaciones y capa de mapa etiquetada como tráfico total del mercado. Evitar sumarlo al tráfico propio de T-100. Revisión humana de la equivalencia geográfica antes de dibujar.
2. **Contexto por país** (esfuerzo medio): extraer cuotas y métricas por gráfico con periodo explícito; empezar por mercados relevantes y una edición mensual. Puede alimentar Competencia y una lectura retrospectiva fechada. El PDF exige revisión visual de las cifras y del alcance de las etiquetas.
3. **Piloto de tráfico propio México–Brasil** (esfuerzo medio/alto): completar y versionar ANAC, identificar Aerovías de México, filtrar servicio regular, conservar pagados/gratis y validar asientos/salidas por dirección. Los metadatos advierten que algunas variables de demanda de empresas extranjeras proceden de etapas combinadas: no calcular ocupación de ruta por RPK/ASK sin comprobar compatibilidad.
4. **Red mundial documentada de Aeroméxico** (esfuerzo alto): construir catálogo de rutas operadas por fecha desde fuentes de la compañía/autoridades. Mostrar presencia documentada con métricas N/D donde falte tráfico específico. Anuncios y codeshare requieren estados distintos. Ampliar por país con fuentes verificadas, empezando por Brasil y después Colombia.

Para el Analysis Agent, estos avances permitirían explicar qué mercados crecen, qué peso tiene Aeroméxico por país y cómo evoluciona su operación donde exista desglose de operador. No respaldan rentabilidad por ruta, causalidad sobre ingresos ni identificación de la ruta global más importante de la compañía.

**Estado: diagnóstico entregado para revisión. La integración, cualquier cambio del análisis aprobado y la publicación requieren la siguiente autorización del usuario.**
