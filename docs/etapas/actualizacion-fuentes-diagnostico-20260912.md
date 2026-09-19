# Diagnóstico de actualización de fuentes

Fecha: 12 de septiembre de 2026. Alcance: inventario del proceso **existente**, previo al diseño de skills de ingesta y de una tarea programada. No se ejecutaron descargas ni se creó un programador con este diagnóstico.

## Estado real del proyecto

El [registro del pipeline](../../src/pipeline/registry.py) define 14 pasos de ingesta y el encadenamiento principal de parseo, validación, Gold y dashboard. `python -m src.ingest` ejecuta esa fase y emite un comprobante por paso. El [catálogo de fuentes](../../config/source_catalog.yaml) describe procedencia y políticas de enlaces. Solo existe una skill de proyecto, [aeromexico-tracker-analysis](../../.agents/skills/aeromexico-tracker-analysis/SKILL.md); todavía no hay skills operativas por fuente. El registro principal tampoco incluye la extensión de rutas internacionales ni Aena.

| Familia | Punto de entrada existente | Estado para actualización futura |
|---|---|---|
| SEC/EDGAR Aeroméxico y pares | `src.ingest.sec.discover`, `src.ingest.peers.stage5` | Descarga programática y descubrimiento de filings. Requiere validar cambios de documentos y cierre de periodos. |
| BMV XBRL | `src.ingest.bmv.download` | Catálogo y paquetes descubiertos por código; conservar y validar respuestas. |
| Aeroméxico IR | `src.ingest.aeromexico_ir` | Descarga por código **solo de URLs registradas**, actualmente hasta 2026Q2. Un trimestre nuevo exige descubrir y registrar su URL. El método actual omite una URL ya presente en Bronze, por lo que no detecta revisiones bajo esa misma URL. Existe importación de PDF local. |
| AFAC/DATATUR | `src.ingest.afac.download` | Descubrimiento y descarga por código; algunos adjuntos pueden topar con desafío de CDN y requerir navegador. El propio resultado registra fallos y cobertura. |
| BTS T-100 | `src.ingest.bts.t100` | Descarga por año hasta el actual; valida ZIP. La publicación de meses del año vigente debe comprobarse por separado. |
| Banxico/Fed H.10, EIA | `src.ingest.macro.banxico`, `src.ingest.macro.fuel` | Descarga programática; Fed es respaldo explícito de FX. Requieren controles de vigencia y revisiones. |
| Precios de mercado | `src.ingest.market.prices` | Consulta mediante `yfinance`; la instantánea normalizada queda en Bronze. Necesita control de cobertura y fallos del proveedor. |
| OurAirports, grupos aeroportuarios, FAA | `src.ingest.airports.reference`, `src.ingest.airports.groups`, `src.ingest.regulatory.faa` | Código existente. Los grupos combinan SEC, OMA y publicaciones AICM/AIFA; el PDF FAA usa URL fija y debe revisarse cuando cambie. |
| Noticias RSS/GDELT | `src.ingest.news.rss_gdelt` | Código existente con fuentes opcionales y registro de fallos. |
| Viva, Ryanair y diccionario NLP | `src.ingest.peers.stage5`, `src.ingest.nlp.loughran_mcdonald` | Código existente; Viva está acotada hasta 2026Q2, Ryanair usa la página actual y el diccionario es un archivo de referencia de baja frecuencia. |
| ANAC Brasil | `src.ingest.international_routes` | Descarga programática del original completo por rangos; la etiqueta de selección actual está fijada al incremento de septiembre de 2026. |
| Aerocivil Colombia | `src.ingest.international_routes` | API programática, pero filtro 2025–2026 fijo. |
| CAA Reino Unido | `src.ingest.international_routes` | El código apunta al CSV concreto de junio de 2026; no descubre meses nuevos. |
| Aena España | `src.ingest.international_routes:import_aena_exports` | Cuatro exportaciones de navegador que se importan desde archivos locales. El importador exige enero–julio de 2026 y todavía no es una actualización parametrizada. Requiere sesión autenticada. |

Los hallazgos de Aena y la separación entre compañía por aeropuerto y mercado por ruta están en [su integración](vuelos-espana-integracion-20260912.md). La [evidencia de exportación](aena-exportacion-20260910/README.md) conserva un recorrido de «Informes detallados», mientras que la integración activa usó cuatro consultas personalizadas. Falta un recorrido reproducible de esas **cuatro** consultas con filtros, clics, nombre de archivo, comprobación posterior y recuperación ante cambios de interfaz; el documento actual no debe presentarse como skill operativa completa. Las rutas de [Brasil, Colombia y Reino Unido](vuelos-integracion-internacional-20260908.md) también tienen comandos de reconstrucción, pero el código debe dejar de fijar ventanas y versiones para una ejecución periódica.

## Implicaciones para una tarea programada

1. La mayor parte de los pasos repetitivos puede quedar en scripts deterministas. Las skills deben indicar parámetros, precondiciones, señales visibles y criterios de fallo; el agente interviene en descubrimiento, navegador y excepciones.
2. Los subagentes pueden consultar fuentes en paralelo, pero no conviene que varios procesos escriban simultáneamente `data/bronze/_manifest.jsonl`, `selection.json`, Silver, Gold o DuckDB. El candado de `save_bronze` es un `threading.Lock` local al proceso. Cada trabajador debería entregar archivos y un recibo aislados; un coordinador único validaría y promovería las versiones en orden, reconstruiría Silver y luego Gold.
3. Un recibo por fuente debe indicar `new`, `unchanged`, `partial`, `auth_required` o `failed`, periodo realmente publicado, archivos, URL, fecha verificable, SHA-256, conteos y límites. Una fuente opcional faltante no debe parecer actualizada; una fuente indispensable incompleta debe impedir la promoción dependiente.
4. Bronze se conserva localmente fuera de Git. Una tarea de escritorio sobre un worktree aislado no debe asumir que encuentra los originales; para la arquitectura actual habría que ejecutar sobre el proyecto local con exclusión mutua o configurar un almacén compartido antes de escoger worktrees.
5. La actualización de datos actuales y la elegibilidad para un análisis histórico son decisiones diferentes. Una descarga de hoy no prueba disponibilidad al corte pasado. Tampoco debe publicarse análisis nuevo sin su aprobación versionada.

## Acceso Aena

La sesión de Chrome con usuario y contraseña guardados puede facilitar el inicio de sesión si el perfil está disponible y desbloqueado. No está comprobado que una ejecución programada en segundo plano pueda reutilizar ese autocompletado, ni que tenga acceso al correo que recibe el código. El procedimiento futuro debe identificar la cuenta y el destino Aena autorizados sin escribir usuario, contraseña ni códigos en la skill, el log o Bronze. Si la sesión expira, el código no llega, el navegador exige intervención o la interfaz cambia, el resultado correcto es `auth_required`/`partial` y continuar con las demás fuentes elegibles.

La siguiente fase de trabajo sería convertir este inventario en contratos por fuente, probar una ejecución manual completa y solo entonces configurar la programación. Este archivo documenta el estado y las brechas; todavía no es el plan de implementación.
