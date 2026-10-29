# Roadmap

Revisión: 29 de octubre de 2026 (UTC). Pendientes, trabajo en curso y backlog arriba;
trabajos terminados al final, como pidió el dueño. No se activan fuentes ni
calendarios por mover una tarea entre secciones.

## Ahora

- **Prioridad: evidencia de fuentes y calendario operativo.** Las ocho familias
  de skills y el coordinador están implementados e integrados. Falta completar
  la evidencia obligatoria de una ronda; no falta volver a aprobar el calendario.
- **Ronda comprobada con el criterio aprobado:** 20 de 22 tareas obligatorias
  verificadas; 110 salidas de fuentes y cinco eventos editoriales. El recibo
  global se escribió y reprodujo sin red. Una tarea RSS opcional también pasa.
  Aerocivil y Viva financiero3T26 siguen pendientes; no es una ronda completa.
- **Vista mensual comprobada de septiembre:** 15 de15 tareas obligatorias,
  86 salidas, cinco eventos editoriales y replay; lista para incorporar ese lote
  a revisión. Sigue en el mismo calendario general, sin programar ejecuciones
  ni aprobar publicación. No acredita todavía los meses futuros.
- **Calendario preparado, sin activar:** mensual 17/nov y 15/dic de 2026,
  primer hábil bancario mexicano en/después del 15; trimestral a +2 hábiles
  del último reporte financiero real de las tres aerolíneas, agrupado con la
  mensual si distan ≤7 días naturales, en la fecha posterior. Zona
  America/Mexico_City. Falta Viva Q3 para fechar el trimestre. Cero ejecuciones
  programadas. Septiembre/Q3 es el corte probado, no una certificación de los
  datos que necesitarán noviembre o diciembre.

## Bloqueos y siguiente acción

| Pendiente | Estado comprobado | Siguiente acción y criterio de cierre |
| --- | --- | --- |
| Aerocivil | Consulta registrada: radicado 2026190010175977, IdControl 2758656, 28/oct; sin diccionario ni atribución verificados | Incorporar respuesta oficial aplicable a jh8x-n6h6. El registro administrativo no responde las preguntas; no duplicar correo |
| Viva financiero Q3 | La investigación del hilo principal encontró 1T/2T 2026; el tercer trimestre mostrado debajo corresponde a 2025. Sin fecha 2026 confirmada | Incorporar reporte oficial 3T26 y adaptar/verificar esa edición; finales de octubre es solo estimación histórica, no una fecha prometida |

La ronda completa sigue bloqueada por Aerocivil y Viva financiero3T26.
Noticias está dentro del mismo calendario mediante revisión editorial nativa:
GDELT/RSS son descubrimiento opcional y sus fallos históricos permanecen.
Un componente pendiente no cancela las tareas independientes válidas.
Los controles de sesiones de septiembre y trimestre ya pasan para los cinco instrumentos.
GAP/ASUR septiembre pasan por edición validada; sus novedades quedan sin comprobar. Banxico/EIA
mantienen tres advertencias de cobertura observada, sin afirmar calendarios
exhaustivos. Aerocivil conserva su obligación trimestral; Noticias, la revisión
mensual obligatoria. Se conservan fechas reales,
periodos, unidades, faltantes y distinción entre original y reconstrucción.

**Criterio autorizado el 28/oct, 23:15 UTC, preparado en el borrador PR174:**
reutilizar las ediciones verificadas de GAP/ASUR septiembre y Volaris financiero
3T26 conservando sus fechas y hashes. Consultas de novedades y fallos quedan
separados; una edición nueva conocida o un periodo distinto exige otra validación.
No equivale a una descarga actual ni a permiso de activar o publicar. Dos grupos
locales finales, sin casos solapados, pasaron:347 pruebas en11,66s y92 en25,79s.
La CI remota del head final y la integración son controles distintos.

## Backlog

- **Airline Monthly:** el dueño lo dejó en backlog el 28/oct. No es trabajo
  activo ni bloquea fuentes/calendario. Se conserva privado el corte24/oct,
  HTML/PR140, QA estático/funcional (23 afirmaciones, seis fuentes, cuatro hashes;
  dos PDF AM HTTP503), QA visual completo y aprobación editorial final pendientes.
  No publicar, modificar ni enviar correo.

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

- `flight_evidence_v1` sigue siendo un paquete candidato no aprobado; su
  activación, backfill o publicación requieren una decisión explícita del
  dueño, no un criterio técnico.
- Explorar fuentes que permitan resolver pasajeros por tramo (en vez de
  itinerario) en mercados nacionales sin escalas.

- **Acceso y datos:** [dashboard existente](https://salvamalfa.github.io/aeromexico-tracker/)
  respondió HTTP200 con TLS estándar el 27/oct; el navegador cloud tuvo un
  límite de certificados, sin desactivar TLS ni rediseñar. Se preservan alcance
  AFAC/BTS/RSS y AeroDataBox, sin nuevas llamadas pagadas.

## Fuera de alcance

- Otra implementación del dashboard fuera de `web/`: es la única vista
  soportada.
- Reemplazar DuckDB/Parquet por un warehouse externo (BigQuery, dbt): ver
  `docs/decisiones/decision-007-warehouse-bigquery.md`.

## Terminado

- **AFAC aeroportuario septiembre, verificado localmente:** descarga real desde
  Chrome local, original 705.225 bytes/SHA comprobado; 3.510 filas, nueve meses,
  65 aeropuertos y 173 cruces. Julio conserva baseline:780 altas,0 bajas,9diferencias
  escalares registradas; no se sobrescribe el histórico publicado. PR174 en borrador.
- **OTC/ICAGY, controles locales completos:** MHTML nativo oficial 28/oct23:35UTC,
  sin etiquetarlo HTTP ni reconstrucción. Cinco instrumentos:21 sesiones septiembre,
  64 trimestre,187enero–septiembre, ancla e historia previa comprobadas. Suplemento
  vinculado al control global, sin editar los recibos antiguos. PR174 en borrador.

- **Reutilización local comprobada de ediciones cerradas:** GAP/ASUR septiembre
  y Volaris financiero3T26 mantienen fechas, bytes y representación;14 candidatos
  regenerados con salidas idénticas y seis productores reproducidos sin cambios.
  El recibo combinado y su replay verifican110 salidas. No acredita última edición.
- **Noticias, implementación local verificada:** cinco eventos de septiembre,
  seis páginas de origen y siete búsquedas. Resúmenes propios, fechas de publicación
  y hechos separadas, agrupación por evento y trazabilidad; candidatos sin aprobar.
  Una sola vista/calendario, con estados independientes y dependencias reales.
  PR174 pendiente de CI e integración, sin publicación ni activación.

- **Aeroméxico mensual recuperado:** el 28/oct a las 22:09 UTC el recolector
  habitual obtuvo índice y 6-K con HTTP200. Certificación/replay: 24 observaciones
  mensuales/comparativas y siete salidas; disponibilidad vigente aprobada. El
  bucle301 anterior queda como fallo histórico, no como bloqueo vigente.
- **Integración técnica PR170–173:** [PR173](https://github.com/salvamalfa/aeromexico-tracker/pull/173)
  se integró en `62607e869d553b3ebb387404a63b726a8ce17f08` el 28/oct19:52 UTC,
  con árbol idéntico al head autorizado `efc579d8`. [CI posterior](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40758184706)
  aprobada a las 20:24:09 UTC: test/web, runtime aislado y Ruff; 5.363 pruebas
  públicas y 29 subpruebas, nueve omisiones y 106 exclusiones del perfil público,
  cero fallos. Codex independiente favorable del head exacto; cero hilos.
  Se incorporaron OMA, Volaris mensual, GAP manual, ASUR reconstruido y Volaris
  financiero Q3 reconstruido, sin publicar candidatos ni activar nada.

Los registros siguientes conservan sus cifras, hashes y cortes de ejecución
originales. Sus menciones de preparación local o CI pendiente describen esos
cortes anteriores, resueltos por la integración indicada arriba; no son tareas
remotas todavía abiertas ni ejecuciones nuevas atribuidas retrospectivamente.

- **Infraestructura de skills y coordinador:** infraestructura de ocho familias/coordinador y
  contratos PR156/161–170 integrados. [PR169](https://github.com/salvamalfa/aeromexico-tracker/pull/169)
  merge `3cbb765a`, CI/revisión del head aprobadas y
  [CI posterior verde](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40528783248).
  [PR170](https://github.com/salvamalfa/aeromexico-tracker/pull/170), head
  `aff81d0b`, integrado manualmente tras autorización específica del dueño,
  CI y revisión Codex independiente favorables: merge `4780b8da`, 28/oct
  14:30 UTC. [CI posterior](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40706667984)
  aprobada para ese merge: test y web. El bot antiguo sigue `running`, separado del dictamen
  auténtico. La continuación AIFA está en [PR171](https://github.com/salvamalfa/aeromexico-tracker/pull/171),
  head `3ab5af7e`, integrado en `0a99dab0` tras la aprobación específica,
  con árbol idéntico al revisado `43ae2b95`
  y master `4780b8da` incorporado solo a su historia. La CI anterior probó una
  referencia de merge antigua y falló correctamente; se corrigió la ascendencia,
  sin cambiar gates. CI nueva `40713725543` aprobada. Dictamen independiente:
  29 pruebas/replay AIFA y 15 comprobaciones de historia, sin hallazgos.
  [CI posterior AIFA](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40742445009)
  y [CI posterior de la política](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40742533938)
  quedan en seguimiento; su resultado no se confunde con las CI de los heads.
  OMA y los lotes siguientes se preparan juntos sobre master `ba553a54`,
  sin cambiar el runtime local probado.

- **Cierres prácticos:** AM mensual extrae 24 cifras de septiembre/comparativo,
  separadas del anexo financiero Q3 de veinte métricas. Fecha/unidad/linaje
  se conservan, sin nueva publicación. AFAC julio reproduce 2.730 filas y
  173 cruces; los originales de distintos días no crean una captura actual.
  AIFA corrige receta Normateca→Informes: índice y libro septiembre actuales
  verificados, 180 nativas/9 Gold y baseline sin cambios; no relaja fechas de
  julio. 108 pruebas y revisión independiente aprobadas. OMA recupera artículo
  y PDF oficiales septiembre dentro de hosts vigentes: 168 observaciones,
  cuatro salidas, once ataques rechazados y revisión independiente favorable.
  150 pruebas de familias y 203 del coordinador pasan; sin activar. Volaris Q2 mantiene
  la advertencia autorizada de 0,105 %, sin convertirse en Q3.

- **Admisión Volaris autorizada:** contrato local limitado al documento exacto
  y página oficial, sin otros documentos/subdominios. Ambos GET200; candidato
  48 cifras/24 variaciones y cuatro salidas reproducidas; diagnóstico conjunto
  previo de 16 tareas, sin activar. Las 303 pruebas afectadas y la revisión independiente
  fueron favorables. El hilo principal ya envió la consulta Aerocivil
  autorizada (Gmail `SENT`), esperando
  respuesta: no acredita la semántica y no se repetirá. GDELT conserva HTTP503. AFAC aeropuertos necesita acceso actual.
  OMA quedó comprobado con otra ruta oficial, sin repetir IR404/es202. AIFA quedó comprobado e integrado tras corregir la entrada. Faltan dossiers actuales aeroportuarios y
  financieros indicados en la matriz. No son cuatro servicios caídos ni faltan 18 adaptadores por la revalidación temporal.
  GAP septiembre ya cerró con original manual real, 192 cifras/72 conciliaciones,
  nueve salidas y replay integral. Conserva el archivo de 77.223 bytes con script
  no ejecutado, sin fingir igualdad binaria con el listado SEC de 77.102.
  ASUR septiembre ya cerró con cuatro copias reconstruidas autorizadas:
  5 tablas/864 celdas/155 guiones desconocidos, 168 observaciones proyectadas,
  92 conciliaciones, nueve salidas y 752 vínculos. Conserva la etiqueta de
  reconstrucción, enero–agosto CPC ausente y los distintos ámbitos explícitos.

- **Continuidad local GAP:** código `05a0e75b`, runtime `3bb20c57…`, revisión
  independiente favorable; 252 pruebas afectadas y 79 financieras pasan.
  CLI real `8b356124` válida, sin autorización de publicación. Recibo conjunto
  de 17 tareas escrito/reproducido después del binding; no hay cambios remotos.

- **Continuidad local ASUR:** fuente `2f856890`, runtime `52ed9cdd…`, dictamen
  independiente auténtico y binding `919234e0`; CLI real válida en 74,301 s,
  sin autorización de publicación. Global escrito/reproducido: 18 tareas,
  102 salidas, 93 previas idénticas. 284 pruebas afectadas pasaron; la única
  omitida por warehouse en main sí se ejecutó en el aislado y pasó después de
  refrescar solo `dim_source.parquet` con el catálogo vigente de 30 fuentes.
  Otros 79 casos financieros posbinding pasaron. Fuentes/autoridad/sitio/53
  salidas históricas conservados exactamente. No se atribuye suite completa
  ni CI remota aprobada a este lote; falta integración ordenada y sus gates.

- **Volaris financiero Q3:** ZIP reconstruido verificado, 20 tablas/1.198 celdas;
  446 nativas, 364 Gold, 187 conciliaciones sin recurrir al 5 %, cuatro salidas y
  1.174 vínculos; cuatro guiones desconocidos y guía/notas miles no proyectadas.
  Execute/replay/readiness locales reales aprobados. Fuente final `6ea243f3`,
  revisión independiente favorable; binding `11dd5d68`, CLI financiera válida
  en 81,655 s, publicación no autorizada. Se corrigieron presupuesto de módulos
  y contrato de alias sin retirar casos; 83 focales y 63 de revisión independiente
  pasaron. Navegador/cache/npm preparados: otras 23 pruebas recuperadas pasaron.
  La agregada anterior dejó tres fallos, cinco errores y 32 omisiones. La nueva
  de `11dd5d68`, con datos locales/navegador y sin exclusiones nuevas, terminó:
  **5.474 pruebas y 29 subpruebas aprobadas**, cero fallos/errores y cuatro
  omisiones explícitas; 41:52 de proceso local. De las 75 pruebas `local_data`,
  73 pasaron y dos son las omisiones por draft actualmente aprobado ausente;
  no se inventó autoridad para ejecutarlas.
  El recibo conjunto conserva las diferencias de fecha, no las oculta.

- **Política de revisión:** decisión del dueño 28/oct: solo revisión independiente
  adversarial Codex, sin obligación Claude. Integrada en [PR172](https://github.com/salvamalfa/aeromexico-tracker/pull/172),
  head `b0f31cea`, merge `ba553a54`, CI `40695705610` y revisión del mismo
  head aprobadas. La compatibilidad sobre AIFA fue limpia: solo dos documentos.
  CI, hilos, protecciones y autoridad originales permanecen exigidos.

- **Eficiencia:** la agregada local anterior aprobó 5.129 casos; el total
  comparable pasó de 39:47 a 36:33 (8,1 % local). No se promete ese ahorro
  remoto ni se atribuye aquella suite a los heads posteriores.

- **Publicación conservada:** lectura e indicadores Aeroméxico 3T26 de PR149/160
  y tesis 2T26 siguen exactos; no se publican los nuevos candidatos. La CLI de
  continuidad usó el checkout aislado con el expediente completo; main conserva
  el fallo por ledger ausente. No se reconstruyó autoridad ni se alteraron pins.
