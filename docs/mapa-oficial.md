# Mapa de vuelos regulares

## Resumen

El candidato mantiene el trimestre global de Mercado. Nacional e Internacional
usan pares de ciudades AFAC de todas las aerolíneas. Internacional excluye
Estados Unidos y permite Canadá, Centroamérica y Caribe, Sudamérica, Europa y
Asia. EE.UU. usa tramos observados de BTS para Grupo Aeroméxico (Aerovías y
Connect, operadores separados), Volaris y Viva. La selección inicial suma
esos tres grupos; no equivale al total del mercado estadounidense.

Servicio regular incluye pasajeros y carga exclusiva: BTS F/G, sin L/P.
AFAC no separa vuelos de pasajeros/carga en rutas mixtas. Cada sentido se suma
una vez. No se ejecuta estimador ni se incorpora programación. La primera
exposición requiere autorización del paquete exacto conforme a `AGENTS.md`.
Preparar no activa fuentes, aprueba análisis ni publica el sitio.

## Fuentes y cobertura

- [SASE diciembre 2025](https://www.gob.mx/cms/uploads/attachment/file/1055167/sase-diciembre-2025-05022026h.xlsx)
  y resumen anual retenido: doce meses, 48 reconciliaciones exactas de vuelos y
  pasajeros. La nota Sunwing/WestJet cambia el reportante; no estima celdas.
- [SASE septiembre 2026](https://www.gob.mx/cms/uploads/attachment/file/1112830/sase-septiembre-2026-27102026.xlsx)
  y [resumen de la misma edición](https://www.gob.mx/cms/uploads/attachment/file/1112829/resumen-septiembre-2026-27102026.xlsx):
  enero–septiembre, 36 reconciliaciones exactas. Las marginales separadas de
  empresa no observan empresa por ruta.
- [BTS T-100](https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FJE&QO_fu146_anzr=Nv4%20Pn44vr45):
  2025 completo y enero–julio 2026. La [guía oficial](https://www.bts.dot.gov/sites/bts.dot.gov/files/docs/explore-topics-and-geography/topics/airlines-and-airports/219466/t100-guide-april-2007.pdf)
  define las clases. El replay privado conserva DOT, reportante, configuración,
  sentido, mes y clase. Tres meses acreditan soporte temporal, no cobertura total
  de operadores/rutas/celdas. 3T26 BTS muestra julio: 1 de 3 meses.

YoY requiere los mismos meses, operadores y sentidos en ambos años. Una celda
ausente produce N/D. Una base explícita cero conserva cero sin porcentaje. No
se añaden periodos anteriores a 2025. PR/VI geográficos pertenecen al Caribe,
aunque BTS los reporte como US; el código original permanece en el expediente.

## Geografía y contrato

`data/reference/official_route_cities.csv` contiene sólo 146 lugares afectados:
etiqueta AFAC, identificador propio, país, GeoName ID, división administrativa,
coordenadas, método y procedencia. Se reproduce contra el original
[GeoNames cities500](https://download.geonames.org/export/dump/cities500.zip)
retenido por hash, CC BY 4.0. Del Bajío conserva su etiqueta regional y usa Silao
como punto representativo explícito, sin repartir tráfico entre aeropuertos.
México, Santa Lucía y Toluca permanecen separados. Homónimos se resuelven por
país, nombre y división administrativa. Una etiqueta nueva sin resolver conserva
coordenadas nulas; no se elige un aeropuerto por semejanza. BTS usa OurAirports.

La superficie nueva `data/v1/official-routes.json` usa
`contracts/web/official-routes.schema.json`, versión `official_route_network_v1`.
`dataset_version` es SHA-256 del contenido canónico excluyendo ese campo.
Incluye 7 combinaciones de las tres aerolíneas para EE.UU. y agregado AFAC por
trimestre. El helper comprueba ámbitos, regiones, grano, meses, DOT y sumas
de ruta/sentido/mes. Los consumidores históricos permanecen separados.

## Apéndice técnico

Preparación offline desde una selección por ruta y SHA con originales y sidecars
físicos. La selección no descarga fuentes. Crear siempre un workspace nuevo.

```powershell
python -m scripts.prepare_official_routes --inputs tmp/<seleccion>/selection.json --out tmp/<revision-nueva>
python -m scripts.prepare_official_routes --inputs tmp/<seleccion>/selection.json --out tmp/<revision-nueva> --execute
python -m src.source_updates.official_routes --selection tmp/<revision-nueva>/selection.json --check
```

Salida: payload, certificado, selección y perfil que fija originales, geografía,
crosswalk, contrato y productor. No reescribir certificados. `--check` reproduce
originales y compara bytes. No copiar Gold candidato al warehouse ni alterar
`flight_evidence_v1`. Los crudos permanecen privados; el CSV de puntos es público.

El coordinador existente conserva por defecto la evaluación de dependencias
`afac_margins`/`bts_segments`. La [continuación explícita del mapa
oficial](calendario-ejecucion.md#continuación-explícita-para-el-mapa-oficial)
selecciona `conditional_products=["afac_margins"]` y
`consumers=["official_routes"]` en un checkpoint con `run_id` nuevo, ligado al
mismo ID de automatización y al estado anterior por hash. Conserva horizonte,
pendientes, fechas e historia; no repite tareas ya completadas.
`official_routes_consumer.consumer_plan` identifica ámbitos, preparador y gate.
El handoff exige los originales verificados de AFAC/BTS, el perfil completo y,
para cerrar una publicación, autoridad exacta, gate y QA servida. Cada llegada
reutiliza el último original aceptado de la otra fuente y sus meses reales.
La equivalencia reproduce el JSON oficial completo y su baseline; nunca usa el
mapa histórico. Preparar esta continuación no modifica la tarea nativa.

`src.publish.official_routes_projection` reproduce el perfil completo, producto
`official_routes`. El gate compartido sólo añade/reemplaza el JSON nuevo y su
contrato; preserva datos históricos, ocho lecturas, noticias, manifiesto editorial
y aprobaciones. La inspección fija baseline, productor, fuentes, interfaz compilada
y archivos exactos. Su autoridad exige ese scope y el consentimiento auténtico.
Inspección, preparación y publicación requieren siempre los originales privados
y su replay completo. La verificación posterior del sitio usa únicamente el
JSON público ya fijado: contrato, semántica, identidad, hash, vínculo del perfil
y los 14 pins numéricos. No es una opción para publicar sin originales ni copia
los crudos al repositorio público.

```powershell
python -m src.publish.source_data_update --inspect tmp/<request-revisable>.json
# Tras revisión y autorización exacta, conservar el consentimiento auténtico.
python -m src.publish.source_data_update --prepare tmp/<request-autorizado>.json
python -m src.publish.source_data_update --request tmp/<request-autorizado>.json --out site/
python scripts/check_pages_publication.py site/
```

## Pendientes

Web, chat, datos y continuación mensual están integrados y cuentan con revisión
independiente. La inspección Linux K2 reprodujo el candidato y su continuidad
histórica sin publicar; el productor final requiere su propia inspección y
scope. Siguen pendientes la autoridad exacta, publicación y QA de los datos
servidos, y después la actualización de la misma tarea nativa con su
configuración actual verificada. El código no acredita esa activación operativa.
La aprobación del plan no se registra como aprobación de cifras ni hashes.
