# Roadmap

Propuesta — el dueño decide prioridades.

## Ahora

- Actualización por lotes: probar el
  [catálogo de fuentes/métricas y calendario](docs/catalogo-fuentes-calendario.md).
  Una ronda mensual desde el 15 y una trimestral según publicaciones reales;
  calendario aprobado y coordinador candidato con skills por familia y pruebas
  en seco. La reconciliación de los cuatro certificadores se reúne en
  [PR156](https://github.com/salvamalfa/aeromexico-tracker/pull/156), integrado
  en `70fb03ec` tras CI y revisión Codex favorables del head `a10c2e69`.
  PR152/154/155 quedaron integrados con sus heads conservados. La
  [CI posterior del merge](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40450942960)
  conserva su resultado verificable. La agregada
  local previa pasó 5.129 casos; preparación optimizada de 39:47 a 36:33
  (8,1 % observado localmente, sin prometer ahorro remoto).
  AIFA septiembre ya tiene extracción oficial, vínculo físico de disponibilidad
  y revisión independiente: código integrado en
  [PR161](https://github.com/salvamalfa/aeromexico-tracker/pull/161), merge
  `6d78cf8f`, con CI y Codex favorables y CI posterior `40455383797` aprobada.
  Sus datos siguen siendo candidatos. Pasaron
  1.680 casos de fuentes y 99 financieros (una omisión histórica). Aerocivil,
  GDELT, tráfico mensual Volaris y fechas verificadas siguen bloqueando la
  ronda completa. No están activados calendario ni nuevas ingestas/noticias.
  [PR162](https://github.com/salvamalfa/aeromexico-tracker/pull/162), integrado
  en `53c9b2a2`, pasó CI y Codex del head `a43725af` y CI posterior
  `40466462847`. AICM y Viva septiembre tienen colección real,
  certificación completa y vínculo físico a los índices del día local 27/oct;
  OMA septiembre conserva HTTP404 del PDF y HTTP202 del índice alternativo.
  Validación: 1.791 casos de fuentes/pipeline/documentación, 142 financieros
  y revisión independiente favorable; continuidad financiera solo local, con
  publicación y autoridad originales exactas. Faltan los contratos físicos
  de las otras familias descritos en la guía; no se declara lista la ronda.

- Aeroméxico 3T26: lectura e indicadores publicados con evidencia y aprobación
  vinculadas, mediante PR149/160. Conservar publicación y autoridad originales
  durante la integración técnica de las skills; no queda una nueva tesis
  pendiente de publicar por este encargo.
- AFAC: conservar el original de agosto y su advertencia internacional;
  la colección del 27/oct confirmó índice, PDF y base ZIP con HTTP200 y los
  mismos hashes. La continuación técnica `1c9b3392` vincula los dos originales
  al dossier completo reproducido: 4.930 nativas, 112 Gold y 474 conciliaciones.
  Conserva la cobertura internacional incompleta; disponibilidad documental
  no equivale a universo completo ni activa la ronda.
- BTS: contrato físico integrado en
  [PR164](https://github.com/salvamalfa/aeromexico-tracker/pull/164), merge
  `e049eb00`, tras CI `40480306782` y Codex favorables del head `36862fb0`.
  CI posterior `40484738784` en curso. Usa la fila FJE del historial y descarga
  México del año actual y del revisado. Extracción real: 12.459 filas en 2026
  hasta julio; 18.081 en 2023, iguales al baseline explícito. Pasaron 236
  contratos afectados y revisión independiente; disponibilidad de julio
  verificada al día local 27/oct. No acredita universo completo por operador,
  ni fechas de primera publicación, ni una ronda global lista. El ensayo
  global real acepta los cuatro productos AICM/Viva/AFAC/BTS y rechaza
  incorporación por las otras 19 tareas requeridas y los reportes centrales
  sin vínculo. Son tareas no incluidas, no 19 fuentes declaradas caídas.
- Tráfico IR Aeroméxico: contrato de índice actual/PDF preparado y probado;
  extracción real del original de septiembre retenido desde 19/oct: 24
  observaciones y siete salidas idénticas. Pasaron 408 casos afectados y
  revisión independiente. Índice del 27/oct HTTP200; falta el PDF actual en
  colección del mismo día. No se confunde ese pendiente externo con una
  implementación ausente ni se afirma disponibilidad nueva desde el retenido.
- Airline Monthly del corte 24/oct: revisión estática y funcional realizada
  por el agente de Pages: 23 afirmaciones, seis fuentes y cuatro hashes de
  originales confirmados; dos PDF de Aeroméxico devolvieron HTTP503. Falta la
  revisión visual completa por login y la aprobación editorial final del dueño.
  La transferencia local HTTP401 no invalida esa revisión ni autoriza modificar
  el HTML. Sin integración de PR140, publicación ni envío por correo.
- [Dashboard existente](https://salvamalfa.github.io/aeromexico-tracker/):
  enlace comprobado con HTTP200 y TLS estándar el 27/oct. El navegador cloud
  no completó la revisión interactiva por su cadena de certificados; no se
  deshabilitó TLS ni se rediseñó la interfaz.
- La [base BTS del 18 de octubre](docs/etapas/bts-refresco-cobertura-20261017.md)
  incorpora los meses retenidos de 2026 y conserva estimaciones declaradas.
  La opción adicional de estimaciones de EEUU sigue pendiente de decisión
  independiente; no se activa con esta base. La [prueba AFAC/AICM](docs/plan-salida-aerodatabox.md)
  documenta la viabilidad condicional de una semilla congelada y sus límites.

## Siguiente

- Ampliar la cobertura internacional de rutas más allá de EE. UU. (BTS
  T-100): candidatos con evidencia parcial en Brasil (ANAC), Colombia
  (Aerocivil), Reino Unido (CAA) y Perú (DGAC); España sigue bloqueada por
  falta de un cruce compañía+ambos aeropuertos+mes en Aena.
- Auditoría de exclusividad de operador en mercados nacionales candidatos
  (p. ej. MEX–CPE, MEX–MAM) antes de tratar un total AFAC como pasajeros de
  Aeroméxico por ruta.
- Actualizar `vite`/`vitest` a sus majors (`vitest@5`, y evaluar `plotly.js@4`
  cuando exista una migración sin romper `web/src/lib/plotly.ts`) para cerrar
  los dos avisos de `npm audit` que no llegan hoy al bundle publicado (ver
  `web/README.md`, sección de dependencias y avisos de seguridad).
- Evaluar activar en el ruleset de rama la opción "Require conversation
  resolution before merging" en GitHub, para forzar en la plataforma lo que
  hoy es una regla de `AGENTS.md`.

## Más adelante

- `flight_evidence_v1` sigue siendo un paquete candidato no aprobado; su
  activación, backfill o publicación requieren una decisión explícita del
  dueño, no un criterio técnico.
- Explorar fuentes que permitan resolver pasajeros por tramo (en vez de
  itinerario) en mercados nacionales sin escalas.

## Fuera de alcance

- Otra implementación del dashboard fuera de `web/`: es la única vista
  soportada.
- Reemplazar DuckDB/Parquet por un warehouse externo (BigQuery, dbt): ver
  `docs/decisiones/decision-007-warehouse-bigquery.md`.
