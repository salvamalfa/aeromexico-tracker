# Noticias: prioridad explícita, contexto y dirección temporal (15 octubre 2026)

Se atienden los tres hallazgos de `4a0ed2f`. En MockProvider, una petición explícita del catálogo o de una métrica/fuente se resuelve antes de recurrir a la pestaña Noticias como pista. Una petición explícita de noticias mantiene su herramienta. La suite recorre API, worker, herramientas y eventos para catálogo, RASK, sus fuentes y noticias desde esa pestaña. No se evalúa un modelo real.

El selector Connect no se transforma en Industria ni en Aeroméxico. El contexto canónico de métricas aún no admite ese operador, por lo que se omite la entidad en ese caso (el API ya admite la omisión); el panel lo indica. El botón sigue enviando el nombre explícito de Connect en la pregunta. No se amplía el catálogo de entidades de métricas ni el universo de datos.

«Antes/después», y equivalentes direccionales, se rechazan de forma explícita y piden fechas de inicio y fin. No se estrechan al mes mencionado ni se presentan como cero noticias. Cuarenta combinaciones prueban texto y límites nullable del caller; otro caso recorre la aclaración por API/historial sin fichas. Se conservan desde/hasta y fechas admitidas.

Pasan 639 pruebas focalizadas con los pins de CI (sin forzar otro prompt global), TypeScript, 198 Vitest y navegador desktop/móvil; se regenera el diagnóstico de paridad desde el commit de código y se solicita CI y revisión final. Previews recompiladas; el envío a Library sigue bloqueado por HTTP 401. Índice, corte candidato, recibos/pins, Gold, tesis, cron y publicación no cambian.
