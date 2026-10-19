# Noticias: correcciones adversariales de búsqueda (15 octubre 2026)

Se atendieron cinco hallazgos de la revisión de `2daac63` con regresiones concretas:

- El botón envía únicamente aerolínea, mes y término/tema elegido. Las instrucciones sobre citas/cobertura ya no contaminan las palabras buscables. «Busca noticias de Aeroméxico publicadas en 2026-07 sobre unicornios» devuelve cero también a través de API/worker/historial.
- El filtro explícito de empresa usa el intent canónico: `Viva Aerobus` y `Viva` encuentran el mismo corpus aprobado. No se conserva un segundo filtro contradictorio.
- Los empates de relevancia ordenan por publicación descendente; una regresión con ocho historias prueba que las cinco devueltas son las más recientes.
- «De diciembre de 2025 a enero de 2026» conserva ambos años explícitos; la API procesa la frase completa sin inferir un único año.
- El exportador y el runtime comparten una proyección pura de historias, sin dependencias del pipeline. El resultado de una segunda fuente conserva su cita original, pero la navegación usa la identidad de la tarjeta agrupada. El conjunto deduplica historias y sus IDs. Pruebas de backend y navegador unitario verifican el origen secundario y sus hashes.

La proyección compartida no importa Bronze/Silver/pandas ni se alimenta de candidatas en producción. El índice real, recibos y pin externo permanecen iguales. El parser de RSS reutiliza la misma canonicalización de URLs. El contrato de búsqueda conserva sus límites originales; el filtro de las tres empresas de la pestaña no reduce el contrato genérico de empresas del índice.

Validación focal: 117 pruebas Python; TypeScript y 196 Vitest. Se repiten los cuatro smoke exactos de CI y la suite pública sobre el HEAD. Los checks remotos y sus logs son la evidencia final. El modelo real sigue sin verificarse; ninguna prueba convierte la simulación en inferencia real o activa las once candidatas.

El reporte de paridad se regenera después de estos cambios. Su versión v2 identifica el commit/árbol evaluados y el hash del generador; guardar un artefacto crea necesariamente un commit documental posterior. Se comprueba igualdad del código evaluado, sin auto-referencia circular al commit que contiene el propio JSON. La presentación sigue bloqueada; no se modifican aprobaciones.
