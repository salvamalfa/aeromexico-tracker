---
name: airline-update-routes
description: "Actualizar candidatos de la familia autoridades y evidencia de rutas de Airline Tracker; usar para capturar, validar y revisar esas fuentes sin activar ni publicar."
---

# Autoridades y evidencia de rutas

Leer y aplicar [el contrato común](../source-updates-common.md).
Familia ejecutable: `routes`. Alcance: ANAC, Aerocivil, CAA, Aena y evidencia fechada de Aeroméxico, OMA, Colima y Expansión.

Decisión del dueño del 29/oct: Aerocivil sigue requerido, utilizable con los
supuestos S/I y atribución AMX/SLI documentados en el catálogo. La espera de la
respuesta oficial no bloquea por sí sola; no afirmar leyenda oficial ni cambiar
`agent_eligible=false`. `readiness` adjunta la política operacional solo tras
replay positivo de datos, conteos, periodo, originales y linaje y huellas
semánticas revisadas. Disponibilidad desconocida, filas ausentes, definiciones
cambiadas u otros códigos no se sustituyen con supuestos. Conservar advertencia
y originales; una respuesta contradictoria exige nueva versión de los cálculos.

Seleccionar documentos reales; no ejecutar el descargador histórico con URLs fijas como refresh universal. ANAC puede bloquear acceso; Aerocivil necesita paginación acotada y reconciliar cantidad de registros. CAA Flight Punctuality no es Airport Data. Aena requiere exportación manual; compañía×aeropuerto y mercado entre aeropuertos no producen compañía×ambos extremos. Comunicados y listados permiten presencia/programación/inferencia limitada, no pasajeros o vuelos observados. Conservación del original no autoriza activar inferencias ni estimaciones.

## Ejecución

```bash
python -m src.source_updates plan --round monthly --as-of 2026-10-18T12:00:00-06:00 --family routes
```

Si la familia es trimestral, usar `--round quarterly --quarter 2026Q3`.
La fecha del ejemplo solo reproduce el corte; cambiarla deliberadamente.
Pasos existentes disponibles: comandos dedicados para snapshots retenidos y Aerocivil; no se añade un parser universal de novedades al build genérico.

Consultar `src/source_updates/catalog.py` para subproductos y brechas.
No confundir esos pasos disponibles con un adaptador aprobado para cualquier
formato o periodo nuevo. Entregar recibos y periodos realmente comprobados.

## Adquisición por producto

La entrada exacta y el procedimiento están en el [catálogo operativo](../../../config/source_update_acquisition.json), enlazado al [catálogo de instituciones](../../../config/source_catalog.yaml). El comando resuelve la URL o API desde su configuración canónica; no hay que inventarla.

```bash
python -m src.source_updates recipe --product anac
```

Consultar cada producto de esta familia:

- `anac` — adaptador offline de JSON completo retenido. Entrada canónica: `constant:src.ingest.international_routes:ANAC_URL`. Formato: JSON 2021–2030 con rangos HTTP.
- `aerocivil` — candidato numérico dedicado; interpretación de códigos pendiente. Entrada canónica: `constant:src.ingest.international_routes:CO_URL`. Formato: Socrata JSON de movimientos.
- `caa` — adaptador offline de Flight Punctuality retenido. Entrada canónica: `url:https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/uk-flight-punctuality-statistics/2026/`. Formato: HTML → CSV Flight Punctuality.
- `aena` — adaptador offline de cuatro exportaciones retenidas; nueva exportación manual autorizada. Entrada canónica: `constant:src.ingest.international_routes:AENA_URL`. Formato: cuatro CSV UTF-16 exportados.
- `am_routes` — selección/importación manual. Entrada canónica: `catalogue:aeromexico_route_press`. Formato: comunicado HTML fechado.
- `oma_routes` — solo descubrimiento. Entrada canónica: `catalogue:oma_route_newsroom`. Formato: sala de prensa → PDF.
- `colima` — selección/importación manual. Entrada canónica: `catalogue:colima_route_statement`. Formato: republicación HTML fechada.
- `aifa_roster` — selección/importación manual. Entrada canónica: `catalogue:expansion_aifa_roster`. Formato: artículo/listado secundario fechado.

### Procedimiento verificable

1. Ejecutar `recipe --product <producto>` y leer su procedimiento, URL resuelta, formato y bloqueo.
2. Para un índice HTML admitido, emitir la selección con `recipe --product <producto> --output selection > tmp/seleccion.json`. Revisarla con `collect --selection tmp/seleccion.json --workspace tmp/source-updates/<lote> --dry-run`. Capturar solo dentro del alcance autorizado.
3. Leer los enlaces y el contexto del catálogo preservado. Elegir el documento real y comprobar su periodo dentro del contenido. No transformar una plantilla histórica en una URL futura. Para importación manual, colocar el original en `imports/` del candidato, calcular SHA-256 y declarar URL, entidad, periodo, formato y directorio que espera el parser.
4. Revalidar documentos/URLs seleccionados en la ronda. Conservar original y revisión por hash. Comparar filas contra una copia previa explícita; sin baseline, registrar que no se compararon revisiones.
5. Ejecutar solo el paso de construcción que el plan declare y cuyos insumos estén presentes. Aplicar `check` al producto, tabla, fuente, entidad y periodo solicitados; compartir institución no permite intercambiar productos.
6. Acreditar éxito solo en la capa comprobada: hash Bronze, contrato/grano/linaje Silver y controles Gold/meses/días/reconciliaciones que correspondan. Si no existe adaptador, terminar en captura o descubrimiento y declarar ese límite. No llenar faltantes ni activar/publicar.

Un 403, TLS, timeout o archivo inválido es un fallo de acceso/contenido; no prueba ausencia de publicación. Registrar pendiente y conservar el dato aceptado. Las fechas de publicación desconocidas siguen nulas.

## Candidato Aerocivil por mes

`python -m src.source_updates.aerocivil recipe --period YYYYMmm` produce tres GET públicos: conteo, filas y conteo posterior. Un solo mes, operadores de fuente AMX/SLI, hasta 1.000 filas y 15 solicitudes contando redirecciones; sin paginación implícita. La misma receta con `--metadata` emite el diccionario oficial. Capturar ambas selecciones mediante `collect` y conservar sus recibos. El conteo debe coincidir antes/después y con todas las filas. Esto no demuestra aislamiento transaccional de versiones del proveedor.

Importar además un original público OurAirports retenido, por URL y SHA-256, para mapear ICAO/IATA y país; no reutilizar solo la frescura de Gold. `python -m src.source_updates.aerocivil certify --workspace <candidato> --period <mes> --as-of <corte-con-zona> --collection <id-del-recibo-de-tres-consultas> --dry-run` muestra la construcción. `--execute` escribe el candidato offline y `--check` reproduce sin red ni escrituras. Usar una carpeta por mes. Se preservan originales, diccionario, referencia y hashes del código/recibo/salidas.

El producto selecciona literalmente `tipo_vuelo=S` y `trafico=I`. Falta una leyenda oficial comprobada: no traducir N como chárter ni certificar S como regular. Los campos empresa y explotador son derivados del callsign y matrícula por el proveedor. Conservar el designador comercial reportado en su propia columna; `marketing_carrier` queda nulo. El AOC de fuente no establece elegibilidad histórica ni codeshare.

La cifra mide movimientos aeroportuarios reportados en Colombia. Pasajeros, asientos, despegues y ocupación permanecen nulos; no son cero. Verificar aeropuerto colombiano que registra y dirección, país de ambos extremos, grano nativo, códigos IATA únicos y faltantes. Conservar exclusiones por código y ceros que sí reporta la fuente. Silver y Gold candidatos usan la validación de rutas existente y una declaración local explícita del grano de linaje. No se añade esta tabla al catálogo general ni al warehouse publicado. La comprobación numérica/linaje no cierra la interpretación de códigos, la familia, la cobertura de tres aerolíneas ni un trimestre.


La continuación del 21 de octubre recapturó metadata y conteo/filas/conteo con
HTTP 200: diez filas crudas, ocho bajo S/I, 347 movimientos, comparación con
ocho filas iguales y replay sin cambios. `recipe --availability --period
2026M07` emite la consulta acotada del máximo mes AMX/SLI del año; el modo
`availability --workspace <candidato> --period 2026M07 --as-of <corte>
--collection <id>` comprueba su recibo sin escribir. El máximo obtenido fue
2026M07; no certifica completitud ni publicación inicial. `certify --baseline
baselines/<anterior.parquet>` fija hash y grano de revisiones, repetidos en
`--check`. La metadata del conjunto exacto sigue sin leyenda literal; la portada
con desafío fue rechazada. No transferir una leyenda de otro conjunto ni
contactar al proveedor sin autorización expresa.

### Autoridades y documentos retenidos

Aplicar el [flujo común](../source-updates-common.md#originales-retenidos-y-lote-offline).
ANAC exige `json`, consume todos los arrays y conserva compañía literal, par
dirigido, servicio regular y métricas separadas. La edición retenida llega a
junio: meses/operadores ausentes no son cero ni prueba de cobertura completa.
CAA exige `csv`; separa vuelos cotejados, no cotejados y cancelados por llegada/
salida, sin renombrarlos como todos los vuelos realizados.

Aena exige `company_operations`, `company_passengers`, `market_operations` y
`market_passengers`. No unir compañía×aeropuerto con totales de mercado para
atribuir compañía×ruta. Dos filas de pasajeros de Barcelona en enero/febrero
faltan en la fuente y siguen N/D, aunque operaciones de otro CSV sean cero.

Los productos `am_routes`, `oma_routes`, `colima` y `aifa_roster` exigen rol
`document`. Solo normalizan pasajes literales y sus fechas; distinguen
comunicado oficial, republicación y listado secundario. El periodo se refiere
al documento, no a vuelos del mes. No expanden programación a fechas futuras,
no demuestran operación continuada, no aportan pasajeros/asientos y no activan
noticias ni evidencia. La leyenda Aerocivil continúa pendiente: la leyenda de
un dataset diferente no puede transferirse a los códigos S/N/I usados aquí.
