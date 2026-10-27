# Roadmap

Propuesta — el dueño decide prioridades.

## Ahora

- **Skills y calendario:** ocho skills por familia y coordinador ejecutable,
  con integración técnica de PR156 y contratos de fuentes PR161–167. El último
  [PR167](https://github.com/salvamalfa/aeromexico-tracker/pull/167) quedó integrado
  en `f35c96b4`, con CI y Codex del head `3a48b763` favorables y CI posterior
  `40504737268` aprobada. El calendario está aprobado y **sin activar**:
  mensual el primer hábil bancario mexicano en/después del 15 (17/nov y 15/dic
  de 2026); trimestral dos hábiles después del último reporte financiero real
  de las tres aerolíneas, todavía sin fecha verificada.
- **Preparación actual:** el ensayo combinado del SRC `4b097b10` verifica once
  tareas del mismo runtime y mantiene doce requeridas no incluidas. Los
  controles pendientes de observaciones bajaron de seis a **cinco**. Ver el
  [desglose operativo](docs/catalogo-fuentes-calendario.md#cierre-operativo-de-la-ronda-doce-tareas-y-cinco-controles-pendientes):
  separa programación, material y decisiones concretas. La ronda completa y
  sus ejecuciones automáticas siguen bloqueadas; no son doce servicios caídos.
- **Banxico mensual:** calendario de septiembre comprobado con tres CSV y el
  original metodológico FIX; 21 fechas FIX, una observación INPC y treinta de
  tasa. El trimestre sigue no certificado frente al universo diario por el
  12/julio no observado, sin inferir error del proveedor ni imputar datos.
  No cambian valores o linaje numérico: 56 de las 58 salidas del ensayo son
  idénticas; las otras dos solo añaden el método como artefacto de referencia.
  Los tres originales sin método conservan el estado no certificado.
- **Siguientes cierres concretos:** tráfico mensual Volaris requiere el host
  ya propuesto; Aerocivil, leyenda/atribución del conjunto exacto y decisión
  sobre contacto al publicador; GDELT conserva HTTP503. OMA y AFAC aeropuertos
  necesitan material oficial accesible. AIFA conserva septiembre histórico,
  pero el índice actual anuncia julio, cuyo libro falla por fechas. Los
  expedientes actuales y calendarios de combustible/bolsas siguen pendientes.
  AM Q3 ya tiene PDF y veinte métricas en el HTML retenido: falta resolver su
  atribución al contrato de fuentes y completar el adaptador, no conseguir
  archivos al dueño. Nada de ello autoriza reducir requisitos o ampliar hosts
  implícitamente.
- **Eficiencia:** la agregada local previa pasó 5.129 casos. La preparación
  optimizada redujo el tiempo comparable de 39:47 a 36:33 (8,1 % local);
  no se promete ese ahorro remoto ni se atribuye aquella suite a otros heads.
  Cada lote posterior conserva sus pruebas, fuentes y límites en la guía.
- **Aeroméxico 3T26:** lectura e indicadores publicados mediante PR149/160;
  publicación, fuentes y autoridad originales preservadas. Las tesis 2T26 ya
  publicadas permanecen visibles; no se activan versiones nuevas.
- **Airline Monthly, corte 24/oct:** revisión estática/funcional realizada
  (23 afirmaciones, seis fuentes y cuatro hashes confirmados); dos PDF de
  Aeroméxico devolvieron HTTP503. Falta revisión visual completa por login y
  aprobación editorial final del dueño. Sigue privado, sin modificar el HTML,
  integrar PR140, publicar o enviar correo.
- **Acceso:** [dashboard existente](https://salvamalfa.github.io/aeromexico-tracker/)
  comprobado con HTTP200 y TLS estándar el 27/oct. La revisión interactiva
  cloud tuvo un límite de certificados; no se deshabilitó TLS ni se rediseñó.
- **Datos retenidos:** preservar la advertencia internacional AFAC y el alcance
  reportado de BTS; no inferir universo completo por operador ni red mundial.
  Se conservan AeroDataBox y sus derivados, sin nuevas solicitudes pagadas.

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
