# Roadmap

Propuesta — el dueño decide prioridades.

## Ahora

- Actualización por lotes: probar el
  [catálogo de fuentes/métricas y calendario](docs/catalogo-fuentes-calendario.md).
  Una ronda mensual desde el 15 y una trimestral según publicaciones reales;
  calendario aprobado y coordinador candidato con skills por familia y pruebas
  en seco. La reconciliación de los cuatro certificadores se reúne en
  [PR156](https://github.com/salvamalfa/aeromexico-tracker/pull/156), con CI del
  head `a10c2e69` en ejecución y revisión remota final pendiente. La agregada
  local previa pasó 5.129 casos; preparación optimizada de 39:47 a 36:33
  (8,1 % observado localmente, sin prometer ahorro remoto).
  AIFA septiembre ya tiene extracción oficial y revisión independiente local;
  falta cerrar su vínculo de disponibilidad y entrega técnica. Aerocivil,
  GDELT, tráfico mensual Volaris y fechas verificadas siguen bloqueando la
  ronda completa. No están activados calendario ni nuevas ingestas/noticias.

- Aeroméxico 3T26: lectura e indicadores publicados con evidencia y aprobación
  vinculadas, mediante PR149/160. Conservar publicación y autoridad originales
  durante la integración técnica de las skills; no queda una nueva tesis
  pendiente de publicar por este encargo.
- AFAC: conservar el original de agosto y su advertencia internacional;
  la siguiente actualización debe comprobar disponibilidad y periodo real.
- Airline Monthly del corte 24/oct: revisión y calidad HTML del borrador
  privado pendientes; no hay aprobación final ni envío por correo.
- Acceso a la interfaz: comprobar y entregar un enlace utilizable al dashboard
  existente, sin rediseñar el producto ni trasladar tareas técnicas al dueño.
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
