# Diagnóstico de Etapa 12

Snapshot generado desde el warehouse local mediante
`python -m src.analysis_agent.stage12`.

- `diagnostico.json`: detalle de grupos, métricas faltantes, contexto, artefactos IR
  comprobados, candidato de filing SEC y hashes de insumos.
- `cobertura.csv`: matriz resumida; fechas de corte vacías deliberadamente.
- La maqueta está en `prototypes/etapa-12/analysis_agent.html`.

## Lectura de resultados

Grupos: operación 5 métricas; finanzas 6; costos/consumo 8. Son las métricas
declaradas en `GROUPS` y exportadas dentro del JSON. El conteo no certifica
comparabilidad histórica. `missing` significa ausente en la selección Gold actual,
no que la compañía haya omitido publicarlo.

`verified_hash` comprueba que el archivo local coincide con el hash del catálogo.
No acredita su fecha de publicación o que sea la versión original.

`sec_candidates` documenta la fuente usada por `total_revenue` en la vista actual,
su periodo de reporte y fecha de filing. No se generaliza a todos los indicadores.

`not_verified` significa que la elegibilidad temporal no fue certificada en esta
etapa. El generador no adopta automáticamente fechas del filing como corte IR.
La inexistencia de evidencia de fecha no se sustituye por una fecha de descarga.

## Brechas

| Código | Interpretación | Etapa responsable |
|---|---|---|
| historical_extraction_missing | Falta modelar finanzas/costos en Gold | 13 |
| financial_values_from_later_comparative | Ingreso actual extraído de un reporte de periodo posterior | 13 para extraer fuente contemporánea; 14 para certificar corte |
| publication_and_version_proof_missing | Publicación y disponibilidad de versión no acreditadas | 14 |
| release_integrity_unresolved | Archivo ausente o hash no coincidente | Resolver antes de usar como evidencia |

Macro usa meses distintos con `average`; `close` es otra agregación, no un
duplicado. AFAC cuenta meses de pasajeros totales AM. Aeropuertos/grupos reportan
meses con algún dato, no completitud de entidades ni participación de AM. Peers
solo señala al menos un ingreso presente. Toda esa cobertura es de la serie
actual, no del corte histórico.

La prosa de la maqueta es estructural e ilustrativa. No se almacena como análisis,
no hay auditoría del contenido y ningún control de la página concede aprobación.
