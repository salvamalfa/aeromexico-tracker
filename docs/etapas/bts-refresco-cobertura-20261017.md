# BTS: refresco para auditar cobertura de vuelos

Corte: 17 de octubre de 2026. Candidato sin integración ni publicación; no
consulta AeroDataBox, no reajusta modelos y no cambia las tesis aprobadas.

## Fuente y procedimiento

El calendario oficial de BTS (`https://www.transtats.bts.gov/releaseinfo.asp`)
registra junio de T-100 International Segment All Carriers el 14 de septiembre
y julio el 9 de octubre. Eso no acredita que cada operador esté completo.

Se ejecutó `src.ingest.bts.t100.download_year` para 2026: formulario oficial,
geografía México, todos los meses y los 30 campos documentados por `FIELDS`.
La respuesta HTTP 200 `application/zip` se conserva sin reformatear, con
metadatos y evento de restatement. El ZIP nuevo contiene 12,459 filas y meses
enero–julio, frente al original retenido de enero–mayo. No se borra el original.

- Anterior: 2026-08-24T03:16:56.016705Z, 193,316 bytes,
  SHA-256 `590001141ec9907ef392d424bfae910cc7024e8bf6a32fdc5b3948878e2f64a6`.
- Nuevo: 2026-10-17T18:33:40.420808Z, 259,152 bytes,
  SHA-256 `bda94a69b9d8430163a96b33521300cf8f76ac6f0aa0761d67ce3250a184d568`.

`scripts/research/audit_bts_refresh.py --old <ZIP> --new <ZIP> --out <directorio>`
produce conteos por operador, mes, clase, ruta y sentido, además de comparar
las ediciones sin convertir celdas ausentes en cero. Usa `DEPARTURES_PERFORMED`;
las salidas conservan la clase original. F/G son regulares; L/P se informan
aparte. No se usa pasajeros ni `DEPARTURES_SCHEDULED` como vuelos realizados.

## Conteos confirmados en el CSV

| Operador BTS | Abril F | Mayo F | Junio F | Q2 F | Q2 L |
|---|---:|---:|---:|---:|---:|
| Aeromexico, AM, ID 19534 | 2,239 | 2,207 | 1,279 | 5,725 | 51 |
| Aerolitoral, 5D, ID 20250 | 460 | 408 | 361 | 1,229 | 0 |
| Aeroenlaces, VB, ID 21342 | 1,221 | 1,081 | 1,345 | 3,647 | 41 |
| Volaris México, Y4, ID 21351 | 3,648 | 3,568 | 3,813 | 11,029 | 0 |

No hay filas G/P de esos cuatro operadores en Q2. La suma regular AM + 5D es
6,954 y requiere agregación explícita como Grupo Aeroméxico; el parser conserva
ambos operadores separados. Aerolitoral sí reporta a BTS: el mapeo anterior
lo mantenía bajo la clave genérica `BTS_AIRLINE_ID_20250`, no dentro de AM.
El candidato corrige su identidad a `AEROMEXICO_CONNECT`, IATA 5D, ICAO SLI.

Abril/mayo de los cuatro operadores son idénticos entre ediciones al grano
operador–ruta–sentido–mes–clase. Para todas las aerolíneas hay cinco celdas nuevas
de mayo: AC NLU–DFW G (3), AC NLU–ORD G (5), E7 MEX–MIA G (21), E7 MIA–MEX G
(21) y RV CUN–PIT F (1); ninguna pertenece al objetivo de las tres aerolíneas.

## Límites y validación

Junio de AM tiene solo 297 regulares MX→US frente a 982 US→MX. Connect registra
180/181, Viva 672/673 y Volaris 1,906/1,907. La fuerte asimetría de AM debe
exponerse; no permite declarar el mes completo ni fabricar vuelos de regreso.
BTS cubre México–EE. UU., no toda la red internacional. Actualizarlo no acredita
por sí solo alcanzar el objetivo de cobertura del 95% contra AFAC.

La conciliación del ZIP anterior con Silver y Gold vigentes confirma AM 4,446 F
más 5 L y Connect 868 F en abril/mayo. Los 5,474 observados del mapa anterior
incluyen otras autoridades y no son un total BTS. La transformación conserva
los conteos: Silver nuevo 193,053 filas y fact candidato 193,008, tras agregar
configuraciones al grano contractual. Todas las sumas por operador–mes–clase
coinciden exactamente; los años 2015–2025 usan los originales retenidos.

Pruebas focalizadas: cuatro aprobadas, incluidas identidad AM/5D, conservación
de clase y vuelos realizados frente a programados. Contrato del fact validado,
Ruff y `git diff --check` correctos. No se ejecutó la suite completa ni CI en
esta rama auxiliar; la entrega funcional debe verificarlos en el head integrado
del PR de vuelos. No se activa ningún dato con este refresco.
