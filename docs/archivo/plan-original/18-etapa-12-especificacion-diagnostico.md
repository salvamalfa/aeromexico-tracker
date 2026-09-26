# Etapa 12 — Especificación y diagnóstico

Estado: IMPLEMENTACIÓN LOCAL PARA REVISIÓN HUMANA; aceptación pendiente.

## Alcance autorizado

1. Guardar el plan acordado y los contratos documentales de evidencia, análisis,
   auditoría, versiones y publicación.
2. Diagnosticar cada trimestre de 2021Q1 a 2026Q2 desde el warehouse existente.
3. Distinguir presencia de datos, integridad de archivos y elegibilidad temporal.
4. Generar una maqueta autocontenida, con contenido editorial claramente ilustrativo.
5. Verificar datos, reproducibilidad, seguridad y presentación.
6. Presentar resultados y detenerse antes de la Etapa 13.

No se extraen nuevas cifras financieras, se modifican datos ni se ejecuta un
analista. Tampoco se implementan estados productivos, aprobación ni publicación.
Los controles de la maqueta son simulaciones sin persistencia.

## Entregables

- `docs/plan/17-analysis-agent-plan.md`: plan completo por etapas.
- `docs/analysis-agent/contratos-v1.md`: contrato documental y criterios editoriales.
- `docs/referencias/etapa-12/diagnostico.json`: matriz completa, faltantes, artefactos,
  candidatos SEC, cobertura contextual y hashes de insumos.
- `docs/referencias/etapa-12/cobertura.csv`: resumen tabular exportable.
- `prototypes/etapa-12/analysis_agent.html`: maqueta y diagnóstico navegables.
- `src/analysis_agent/stage12.py`: generador diagnóstico, con fuentes de solo lectura.
- `docs/etapas/etapa-12-reporte.md`: evidencia y estado de aceptación.

## Definición de cobertura

Grano: Grupo Aeroméxico, trimestre calendario, segmento total, métrica seleccionada
por `v_carrier_default`. Cinco métricas operativas, seis financieras y ocho de
costos/consumo declaradas en el generador. Se cuentan valores finitos y no nulos,
rechazando claves seleccionadas duplicadas; no se confunde falta de extracción con
falta de publicación. Los KPI de la maqueta reutilizan `build_executive_payload`.

Macro: meses distintos con agregación `average`, nunca contar promedio y cierre
como dos observaciones. AFAC: pasajeros AM, total, vigente, meses distintos.
Aeropuertos/grupos: meses con algún valor, sin prometer cobertura completa de
entidades. Peers: presencia de ingreso de al menos una aerolínea, no comparabilidad.

Archivos: últimas versiones IR registradas por trimestre; comprobar existencia y
SHA-256. Un archivo ausente o alterado queda marcado, no aprobado. Fechas de filing
SEC se obtienen por relación explícita documentos–índice–texto de resultados; no
se adivinan a partir del nombre ni se adoptan como fecha de primera publicación IR.

La ausencia actual de un contrato de publicación/versiones impide certificar
cualquier corte desde este diagnóstico. `not_verified` NO significa que el reporte
no existiera entonces. La Etapa 14 resolverá esa evidencia.

## Aceptación

- 22 filas únicas; conteos reconciliados contra consultas independientes.
- Archivos locales comprobados contra hashes; candidatos y brechas visibles.
- Regeneración idéntica con mismos insumos; originales y Gold sin cambios.
- Maqueta identifica toda prosa editorial como ilustrativa y usa KPI reales de la
  serie actual, sin aparentar verificación histórica o aprobación.
- Selección trimestral, pestañas, detalles y simulaciones funcionan con teclado.
- Sin red en runtime, HTML remoto ejecutable, secretos o rutas privadas.
- QA de escritorio, 736 px y 360 px documentada con sus límites.
- Pruebas enfocadas y regresión del prototipo previo verdes.
- Reporte entregado y comentarios incorporados. La aceptación visual/formal solo
  se marca cuando el usuario la conceda.

## Reproducción

```powershell
just stage12-prototype
just stage12-validate
```

No requiere dependencias nuevas. El diagnóstico necesita el warehouse y los
archivos locales; una copia pública sin Bronze mostrará faltantes de archivos,
no una falsa comprobación de integridad.

## Ajuste de presentación solicitado

Identificar en azul claro Lectura ejecutiva y sus ventanas como alcance del
dashboard. Mantener dentro de ese bloque los accesos al análisis completo y a la
evidencia, con ventanas modales cerrables. Identificar expresamente diagnóstico,
simulaciones y revisión/aprobación como UI de comprobación. Esta corrección no
constituye aceptación de la etapa ni autorización para iniciar la siguiente.
