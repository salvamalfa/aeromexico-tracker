# Roadmap

Propuesta — el dueño decide prioridades.

## Ahora

- Fase 2 del chat (`docs/chat/fase-2-agente-analitico.md`), empezando por
  F2.0 (modelo y esfuerzo explícitos), F2.1 (prompt) y F2.2 (conjunto de
  evaluación de negocio), con los puntos de decisión del dueño que marca el
  documento. El MVP está activo desde el 8 de octubre de 2026.
- Ciclo de análisis de 3T26 con el Analysis Agent (evidencia, cálculo,
  revisión y aprobación) una vez publicados los reportes trimestrales de
  Aeroméxico.
- Refresco manual de AFAC (rezago típico 27–36 días tras el cierre de mes);
  agosto de 2026 se esperaba entre el 28 de septiembre y el 2 de octubre.
- Mantener la cobertura internacional de Vuelos (AeroDataBox) al día, con la
  ventana histórica de captura y las marginales AFAC ajustadas mes a mes.

## Siguiente

- Fase 2 del chat, paquetes F2.3–F2.9 (glosario y métricas totales, rutas,
  índices de reportes y noticias, explicaciones atribuidas, presentación por
  referencia y evaluación comparativa de Luna y Sol), en el orden y con los
  puntos de decisión del documento de fase 2.
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
