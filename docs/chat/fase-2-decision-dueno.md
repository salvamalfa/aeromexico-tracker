# Fase 2 del chat · decisiones pendientes del dueño

El código está preparado para recibir decisiones; nada de esta lista activa
contenido o cambia la versión de producción por sí solo. R1 y Sol low siguen
siendo la selección preparada. No hace falta volver a aprobar el modelo, las
preguntas, la rúbrica ni R1.

| Decisión | Material para revisar | Acción disponible |
|---|---|---|
| Prompt R2 | [Texto propuesto](../../config/chat/prompt_candidates/system_prompt_r2-proposed.txt) · SHA-256 efectivo `68961bc7a2dc7d0c79988352b56b2ded2ef7b55e515ce824dba3b2cf516a9edf` | Aprobar ese hash exacto para futuras capacidades o mantener R1. R2 solo se selecciona con un recibo de aprobación owner válido, ligado al hash y a sus capacidades. |
| Métricas financieras | [Definiciones y límites candidatos](../../config/chat/metrics-candidates.json) · [propuesta técnica y cobertura](f23-metricas-detalle-tecnico.md) | Revisar los siete indicadores y su proyección pública preparada; aprobar solo las definiciones y filas expresamente seleccionadas. Las puertas permanecen cerradas mientras falte el recibo ligado al contenido y definiciones. |
| Pasajes de reportes | [Siete pasajes candidatos con fuente, página y sección](../../config/chat/evidence/candidates/reports-candidate.json) | Aprobar o rechazar cada pasaje. Los dos pasajes de Volaris cuya captura difiere de Gold están identificados como discrepancia de bytes pendiente de revisión, no como restatement. |
| Noticias | [Tres fichas candidatas de FlightGlobal](../../config/chat/evidence/candidates/news/) | Aprobar o rechazar cada ficha; son metadatos y resúmenes breves, sin cuerpo de artículo. |
| Evaluación final | [Campaña y preflight Stage 3](../../config/chat/f2_9_final_campaign.json) · [instrucciones offline](fase-2-agente-analitico.md#f29--stage-3-offline) | Decidir si se autoriza y fondea la corrida Sol low tras regenerar el preflight con todas las dependencias integradas. La cifra preliminar de US$6.58 no es una autorización ni reemplaza el cálculo nuevo. |

Al aprobar contenido, la decisión debe identificar los registros exactos; la
implementación genera recibos verificables y el índice de evidencia solo
acepta registros con recibo válido. El código, las vistas y el prompt quedan
integrados, pero la fase 2 no se declara cerrada hasta que se resuelvan las
decisiones de contenido y presupuesto, se ejecute la verificación autorizada y
se compruebe la publicación correspondiente.
