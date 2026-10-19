# Noticias: intención de aerolínea y precisión diaria (15 octubre 2026)

Se atienden los dos hallazgos de `b6bea60`. El argumento de compañía se canonicaliza y debe coincidir con todas las aerolíneas explícitas de la consulta; no reemplaza una ni reduce una petición múltiple. Las variantes AMX/Aeroméxico y Viva Aerobus/VIVA_AEROBUS conservan la intención. Una consulta sin compañía explícita mantiene el filtro estructurado válido y el contrato genérico del índice.

«15 de julio de 2026» se resuelve como 2026-07-15..2026-07-15, nunca como julio entero. Dos extremos completamente expresados conservan su rango; los formatos de día ambiguos o no implementados piden fechas ISO. Un día semanal solo se acepta con fecha exacta concordante. Las horas no están documentadas en las fechas de publicación y no se convierten en ventanas de día/año.

Validación focal: 417 pruebas de compañía/calendario, fecha/límites, API, índice, redirecciones y capturas. La API rechaza un caller que sustituye Aeroméxico por Volaris. El navegador desktop/móvil pregunta por el día 15 y abre únicamente esa ficha, además de los casos anteriores; los cuatro smoke exactos dan 16 aprobadas y una omisión de Mercado independiente. La interfaz, fuentes y datos permanecen iguales.

El parser conserva una gramática acotada de fecha de publicación; esto no califica la inferencia de un modelo real. Se comparan los siete ejemplos offline de la preview para conservar sus resultados e identidad v4. Se regenera la evidencia de paridad desde el nuevo código y se repiten CI/revisión. No se activan candidatas, recibos/pins, nuevas tesis, cron ni publicación.
