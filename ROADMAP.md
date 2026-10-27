# Roadmap

Propuesta — el dueño decide prioridades.

## Ahora

- **Skills y calendario:** infraestructura de ocho familias/coordinador y
  contratos PR156/161–169 integrados. [PR169](https://github.com/salvamalfa/aeromexico-tracker/pull/169)
  merge `3cbb765a`, CI/revisión del head aprobadas y
  [CI posterior verde](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/40528783248).
  [PR170](https://github.com/salvamalfa/aeromexico-tracker/pull/170), head
  `aff81d0b`, tiene CI aprobada (Python 20:23, web 1:57); Codex sigue pendiente,
  sin integración. Añade AM mensual/contrato AFAC. La continuación AIFA
  `24366ace` está en [PR171](https://github.com/salvamalfa/aeromexico-tracker/pull/171),
  head `43ae2b95`, en borrador: CI falla por la base PR170 no integrada; no se
  relanza hasta resolver esa dependencia legítima. OMA `472a0528` está local.
- **Preparación comprobada local:** dieciséis tareas del mismo runtime pasan;
  las 80 salidas previas son idénticas y hay cuatro nuevas Volaris IR. Quedan siete
  tareas requeridas y dos controles bursátiles. La [matriz operativa](docs/catalogo-fuentes-calendario.md#cierre-operativo-de-la-ronda)
  desglosa las once del snapshot PR169: AM mensual, AIFA, OMA y Volaris mensual
  son cierres reales;
  AFAC histórico/contrato está probado, pero actualidad HTTP403 sigue abierta.
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
  AM y Volaris Q3 están detectados; falta Viva para fechar. Avisar es independiente
  de incorporar cifras/aprobar tesis; Volaris ya fue avisado el 27/oct 13:09 UTC.
- **Admisión Volaris autorizada:** contrato local limitado al documento exacto
  y página oficial, sin otros documentos/subdominios. Ambos GET200; candidato
  48 cifras/24 variaciones y cuatro salidas reproducidas; diagnóstico conjunto
  de 16 tareas, sin activar. Las 303 pruebas afectadas y la revisión independiente
  fueron favorables. El hilo principal ya envió la consulta Aerocivil
  autorizada (Gmail `SENT`), esperando
  respuesta: no acredita la semántica y no se repetirá. GDELT conserva HTTP503. AFAC necesita acceso actual.
  OMA quedó comprobado con otra ruta oficial, sin repetir IR404/es202. AIFA quedó comprobado localmente tras corregir la entrada; falta
  su integración. Faltan dossiers actuales aeroportuarios y
  financieros indicados en la matriz. No son siete servicios caídos.
  GAP/ASUR septiembre ya tienen documentos SEC exactos identificados; falta
  su original por la importación manual vigente. ASUR además cambia ámbito
  por la adquisición CPC: requiere adaptar la edición, no aplicar tolerancia
  numérica ni rellenar guiones con ceros. Los conteos no cambian por descubrirlos.
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
