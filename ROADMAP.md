# Roadmap

Propuesta — el dueño decide prioridades.

## Ahora

- **Skills y calendario:** infraestructura de ocho familias/coordinador y
  contratos PR156/161–168 integrados. [PR168](https://github.com/salvamalfa/aeromexico-tracker/pull/168)
  se integró en `24097209`, con CI/Codex del head `336af97e` favorables;
  [CI posterior](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40519239644).
  El cierre pragmático del SRC `d55934f7` está verificado con originales reales,
  revisión independiente y conservación financiera. La integración de cada
  entrega exige CI/revisión del head final, sin bypass.
- **Preparación comprobada:** doce tareas del mismo runtime pasan. Las 58
  salidas previas son idénticas y se añaden cuatro AM 3T26. Quedan once tareas
  requeridas y dos controles bursátiles; ver [matriz operativa](docs/catalogo-fuentes-calendario.md#cierre-operativo-de-la-ronda).
  Banxico/EIA mantienen cobertura y agregados observados; la falta de un censo
  de días no bloquea esos cálculos. Cotizaciones conserva el control de sesiones
  que sí requieren rendimientos y volatilidad. Aerocivil/GDELT siguen obligatorios.
- **Cierres prácticos:** AM 3T26 certifica veinte métricas desde el 6-K oficial,
  con trimestre/unidades/linaje exactos. Volaris Q2 conserva CASM 7,97; su
  conciliación derivada difiere 0,105 % y pasa con advertencia bajo el 5 %
  autorizado. El cambio no admite fuentes ausentes, periodos/unidades erróneos,
  integridad falsa ni convierte Q2 en Q3. Final: 327 afectadas y 80 independientes
  aprobadas; 79 financieras y CLI local con el expediente original favorables.
- **Calendario probado, sin activar:** mensual 17/nov y 15/dic de 2026, primeros
  hábiles bancarios mexicanos en/después del 15. Trimestral: +2 hábiles tras el
  último reporte real del trimestre; agrupar si dista ≤7 días naturales de la
  mensual, en la fecha posterior. Día oficial explícito admite hora nula.
  AM y Volaris Q3 están detectados; falta Viva para fechar. Avisar es independiente
  de incorporar cifras/aprobar tesis; Volaris ya fue avisado el 27/oct 13:09 UTC.
- **Pendientes concretos:** host mensual Volaris y permiso para contactar al
  publicador Aerocivil; GDELT conserva HTTP503. OMA/AFAC necesitan material
  accesible; AIFA conserva septiembre histórico y el índice actual anuncia un
  julio con fecha incoherente. Faltan dossiers actuales aeroportuarios y
  financieros indicados en la matriz. No son once servicios caídos.
- **Eficiencia:** la agregada local anterior aprobó 5.129 casos; el total
  comparable pasó de 39:47 a 36:33 (8,1 % local). No se promete ese ahorro
  remoto ni se atribuye aquella suite a los heads posteriores.
- **Publicación conservada:** lectura e indicadores Aeroméxico 3T26 de PR149/160
  y tesis 2T26 siguen exactos; no se publican los nuevos candidatos. La CLI de
  continuidad usó el checkout aislado con el expediente completo; main conserva
  el fallo por ledger ausente. No se reconstruyó autoridad ni se alteraron pins.
- **Airline Monthly, corte 24/oct:** QA estático/funcional realizado (23
  afirmaciones, seis fuentes, cuatro hashes; dos PDF AM HTTP503). Falta QA
  visual completo por login y aprobación editorial final. Sigue privado;
  sin modificar HTML/PR140, publicar ni enviar correo.
- **Acceso y datos:** [dashboard existente](https://salvamalfa.github.io/aeromexico-tracker/)
  respondió HTTP200 con TLS estándar el 27/oct; el navegador cloud tuvo un
  límite de certificados, sin desactivar TLS ni rediseñar. Se preservan alcance
  AFAC/BTS/RSS y AeroDataBox, sin nuevas llamadas pagadas.

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
