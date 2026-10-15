# Noticias: calificadores abiertos adicionales (15 octubre 2026)

Se atiende el hallazgo de `9fa26ed`: «a partir de» y «en adelante» no se convierten en una búsqueda limitada al mes mencionado. Se rechazan y piden inicio y fin explícitos; lo mismo aplica a las variantes «a partir del», «a contar de» y «en lo sucesivo». La validación corre antes de extraer términos y no depende de que el caller envíe uno o ambos límites.

Se añaden cuarenta combinaciones de texto/límites, más dos regresiones API/worker/historial. Las consultas piden aclaración sin fichas ni resultados cero engañosos. Se conservan fechas explícitas, desde/hasta y los siete ejemplos preparados. La gramática es acotada y no se declara comprensión universal del lenguaje natural.

Pasan las 681 pruebas de la suite focal completa y se regenera el diagnóstico de paridad desde el commit de código. No cambia la interfaz: se conservan las pruebas desktop/móvil, 198 Vitest y la resolución temporal conjunta (203 Vitest, 18 browser). Se solicita CI/revisión del HEAD final. No se cambia evidencia, Gold, recibos/pins, tesis, cron o publicación. Library sigue bloqueado por HTTP 401; los archivos finales quedan en el workspace.
