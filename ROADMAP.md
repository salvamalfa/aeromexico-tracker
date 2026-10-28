# Roadmap

Propuesta — el dueño decide prioridades.

## Ahora

- **Skills y calendario:** infraestructura de ocho familias/coordinador y
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
- **Preparación comprobada local:** 19 candidatos y 106 salidas compatibles,
  con las 102 previas idénticas y cuatro nuevas Volaris financiero Q3. El último
  snapshot de 18 éxitos es del 27/oct local. La revalidación real del 28/oct
  deja **16 tareas vigentes**, sin cambiar reglas: 14 candidatos nuevos,
  AIFA capturado hoy y Volaris Q3 observado hoy. Tres siguen sin disponibilidad
  actual: AM tráfico (bucle301 en su índice), GAP/ASUR (observados27/oct). No equivale a ronda completa lista. Quedan cuatro productos sin
  evidencia válida y dos controles bursátiles. La [matriz operativa](docs/catalogo-fuentes-calendario.md#cierre-operativo-de-la-ronda)
  desglosa las once del snapshot PR169: AM mensual, AIFA, OMA, Volaris mensual
  y GAP cerraron con originales reales; ASUR y Volaris financiero Q3 con
  reconstrucciones específicas autorizadas;
  AFAC aeropuertos tiene lector/contrato histórico; su acceso actual HTTP403 sigue abierto,
  separado de AFAC por aerolínea que respondió200 hoy.
  Banxico/EIA conservan tres advertencias de cobertura observada: su
  reclasificación anterior no equivale a calendarios exhaustivos comprobados.
  Aerocivil/GDELT siguen obligatorios según su cadencia; cotizaciones requiere
  sesiones verificadas para rendimientos y volatilidad.
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
- **Calendario probado, sin activar:** mensual 17/nov y 15/dic de 2026, primeros
  hábiles bancarios mexicanos en/después del 15. Trimestral: +2 hábiles tras el
  último reporte real del trimestre; agrupar si dista ≤7 días naturales de la
  mensual, en la fecha posterior. Día oficial explícito admite hora nula.
  Dry-run real con cero ejecuciones programadas. La prueba de fuentes actual
  es septiembre/Q3; noviembre/diciembre necesitarán sus ediciones posteriores.
  AM y Volaris Q3 están detectados; falta Viva para fechar. Avisar es independiente
  de incorporar cifras/aprobar tesis; Volaris ya fue avisado el 27/oct 13:09 UTC.
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
- **Cotizaciones:** auditor local `ee04531a` verifica calendarios y precios
  reales de cuatro instrumentos en ambos periodos: 187 sesiones acumuladas,
  21 de septiembre y 64 del trimestre; incluye ancla anual e historial para
  volatilidad. 99 pruebas y 22 ataques independientes pasan. ICAGY sigue
  pendiente: OTC entregó página dinámica y su contenido público HTTP403.
  Faltan fuente interpretable, lector OTC y conexión final con el flujo global.
  Los dos controles conservan su bloqueo; no es otra ronda aceptada.
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
