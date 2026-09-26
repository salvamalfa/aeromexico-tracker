# Aeromexico Tracker Analysis Agent — plan acordado

Estado: plan autorizado para implementación por etapas; Etapa 12 aceptada por el usuario el 2026-09-05; Etapa 13 aceptada; Etapa 14 aceptada; Etapa 15 implementada y pendiente de revisión.
La autorización del plan NO autoriza saltar las aprobaciones entre etapas.

## Objetivo y decisiones

Crear una lectura trimestral de negocio específica, trazable y aprobada por el
usuario para el HTML local del resumen ejecutivo. Operación asistida desde Codex,
sin API propia, servicio permanente ni generación desatendida. Streamlit,
publicación remota y otras páginas quedan para un plan posterior.

El histórico 2021Q1–2026Q2 se reconstruye con la información disponible en la fecha
de primera publicación del comunicado de cada trimestre. Se completará la
extracción financiera histórica de lo publicado; un faltante nunca se rellena con
cero. Contexto complementario ausente permite un análisis acotado. La ausencia de
evidencia esencial bloquea la tesis.

El usuario revisará un HTML local de borrador y comentará/aprobará versiones en
Codex. Resumen visible de aproximadamente 150–250 palabras y 3–5 hallazgos cuando
haya evidencia; detalle en una ventana modal abierta desde Lectura ejecutiva, de 600–1,000 palabras o menos si corresponde.

## Arquitectura

Datos y documentos → elegibilidad temporal → paquete cerrado → cálculos Python →
analista → validación y auditor independiente → revisión humana → HTML.

- Coordinador: skill del proyecto, selección explícita de trimestre y gestión del
  flujo. Se implementa en Etapa 16, no se instala una skill en Etapa 12.
- Python: selección temporal, comparaciones, identidades, validaciones, versiones y
  exportaciones. Se reutilizan DuckDB, Parquet, contratos y linaje existentes.
- Analista: solo recibe el paquete; pedir más evidencia crea una nueva versión del
  paquete. No calcula ni accede libremente a datos posteriores.
- Auditor: contexto separado, referencias verificables y observaciones
  estructuradas; no concede aprobación humana ni altera datos.
- Modelos: heredan la configuración de Codex; metadata no expuesta queda nula y
  explicada. No se inventan modelo, costo o tokens.
- Consumo: solo texto precomputado y aprobado; abrir el HTML no llama modelos.

La persistencia autoritativa de ejecuciones y eventos será local y separada de los
directorios que reconstruye el pipeline. `fact_quarterly_analysis` será una
materialización; solo versiones autorizadas para consumo se exportarán a Gold.
Los borradores y comentarios privados nunca entrarán al HTML de consumo.

Los contratos, políticas y transiciones se especifican en
[contratos-v1](../analysis-agent/contratos-v1.md). Son especificaciones para etapas
posteriores, no interfaces productivas ya implementadas.

## Etapas

| Etapa | Desarrollo | Entrega revisable | Aceptación |
|---|---|---|---|
| 12 | Especificación, cobertura, disponibilidad temporal y reglas editoriales | Matriz de 22 trimestres y maqueta explícitamente ilustrativa | Brechas clasificadas; formato, alcance y criterios aceptados |
| 13 | Extracción histórica de ingresos, resultados, costos y componentes publicados | Antes/después y fichas cifra–reporte | Campos extraídos o ausencia documentada; diferencias materiales explicadas |
| 14 | Paquete cerrado, prueba de publicación/versión, localizadores y huellas | Dossiers 2026Q2 y un trimestre histórico | Sin evidencia posterior; referencias resueltas; limitaciones visibles |
| 15 | Comparaciones y descomposiciones parametrizadas por trimestre | Cálculos e identidades inspeccionables | Tolerancias documentadas, faltantes y residuales explícitos |
| 16 | Skill y primer borrador 2026Q2 | HTML con resumen, detalle y referencias por afirmación | Tesis específica, cifras trazables y cambios editoriales incorporados |
| 17 | Auditor, revisión, aprobación y versiones | Observaciones, correcciones y diferencias | Sin bloqueantes; imposible incorporar una versión no aprobada |
| 18 | Integración en el resumen ejecutivo local | HTML con navegación, detalle y fuentes | Sincronía trimestral y QA en escritorio, 736 px y 360 px |
| 19 | Backfill cronológico 2021Q1–2026Q1; reutilizar piloto 2026Q2 vigente | Un trimestre por entrega | Aprobación individual o bloqueo documentado; esperar antes del siguiente |
| 20 | Pendientes, cambios de fuentes, reanudación y recuperación | Manual y simulaciones | Sin duplicados, pérdida de versiones ni publicación automática |

### Ajuste informado por el diagnóstico de Etapa 12

La Etapa 13 debe cubrir 2021Q1–2024Q2, y revisar también la procedencia
contemporánea de 2024Q3–2025Q2: sus ingresos en la vista vigente proceden de
comparativos en reportes posteriores. No hay cuatro trimestres adicionales sin
cifras actuales; hay cuatro cuya procedencia actual no demuestra el corte original.
La certificación temporal sigue correspondiendo a la Etapa 14.

## Reglas analíticas

- Python calcula variaciones absolutas/porcentuales, pp y centavos por ASK, contra
  periodos calendario exactos. Base nula/cero/negativa no produce un porcentaje
  engañoso; se conserva cambio absoluto y motivo de indisponibilidad.
- Usar definiciones, unidades, alcance y denominadores compatibles. Ratios y
  márgenes no se suman. Promedio y cierre macro son agregaciones distintas.
- RASK no equivale automáticamente a tarifa. El spread no es margen operativo ni
  EBITDAR. Reportado, derivado y ajustado mantienen identidades separadas.
- El puente de spread separa RASK, gasto de combustible por ASK y residual no
  explicado cuando existan insumos. No etiqueta el residual como eficiencia.
- Costo efectivo por litro no equivale al precio de mercado. FX, coberturas y mezcla
  solo se cuantifican si están identificados. Se conservan alternativas y límites.
- Clasificar afirmaciones como hecho observado, descomposición contable,
  explicación atribuida a la compañía o hipótesis. Correlación no es causalidad.
- La narrativa usa referencias a cifras formateadas por Python; cualquier cifra
  nueva sin respaldo se rechaza. Riesgos/catalizadores solo conocidos al corte.

## Protocolo humano

Antes de cada etapa: presentar acciones. Después: pruebas, artefacto visible,
reporte, límites y comentarios del usuario. Corregir dentro de esa etapa y
DETENERSE. No avanzar sin autorización explícita.

Aceptar desarrollo y aprobar contenido son dos actos distintos. `approved` requiere
autorización de trimestre, versión y huella exactos. `published` significa incorporado
al HTML local, no despliegue público. Editar requiere nueva versión y aprobación.

## Pruebas y condición de aceptación final

Casos: primeros comparables ausentes, base cero/negativa, FX y unidades históricas,
reportado/derivado/ajustado, duplicaciones, grano y meses faltantes, versiones
posteriores al corte, fechas desconocidas, causalidad espuria, contradicciones con
fuentes, referencias falsas, instrucciones incrustadas en documentos, cambios tras
aprobar, interrupciones y reconstrucción del warehouse, escape de HTML, ausencia
de red/datos privados y sincronía móvil.

Evaluaciones editoriales con expedientes congelados de 2026Q2, 2021Q1 y
2022Q3–2022Q4, además de casos adversariales. Evaluar fidelidad, especificidad,
claridad y prudencia; no igualdad literal entre generaciones.

Se completa cuando el usuario pueda solicitar, revisar, corregir y aprobar un
trimestre que aparezca correctamente en el HTML con su historial conservado. Los
22 trimestres tendrán estado explícito; rellenar huecos con texto genérico no es
éxito. Cada ejecución deja comprobante de paso alcanzado, faltantes y acción próxima.

## Referencias técnicas consultadas durante la planificación

- [Skills de Codex](https://learn.chatgpt.com/docs/build-skills)
- [Subagentes y contexto separado](https://learn.chatgpt.com/docs/agent-configuration/subagents)

La configuración exacta se verificará nuevamente al implementar la skill.
