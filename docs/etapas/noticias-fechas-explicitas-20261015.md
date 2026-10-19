# Noticias: fechas explícitas y rechazos seguros (15 octubre 2026)

La revisión de `4515e61` detectó dos consultas que podían perder una restricción temporal. Se corrigen sin inferir fechas:

- «Último mes», «últimas dos semanas», «últimos 30 días», «este mes», «mes anterior», «año pasado» y «hoy» solicitan fechas explícitas. Se distinguen de «última noticia», que sí puede ordenar el corpus por recencia sin inventar un intervalo. La prueba de API/worker/historial devuelve la aclaración y ningún destino de ficha.
- Un año sin asociar a los meses/fechas del intervalo se rechaza: «diciembre de 2025 a 2026», «diciembre de 2025 y 2026» y equivalentes ISO mixtos no se convierten silenciosamente en diciembre de 2025. Se requieren extremos con la misma precisión.
- Los tokens numéricos malformados o inválidos (por ejemplo `2026-13`, `2026-1-1` o un tercer componente adicional) no caen en una búsqueda de todo el año.

Las 39 pruebas de flujo natural y fechas, más las 29 del índice, pasan. La gramática acotada admite fechas ISO completas, meses ISO o nombrados con año e intervalos de dos extremos; no promete interpretar cualquier formulación temporal. Las fechas resueltas son de publicación, no del hecho. No se prueban inferencias de un modelo real ni se activan candidatas. La preview mantiene sus siete ejemplos offline rotulados y su identidad v4.

Se regenera el diagnóstico de paridad tras el código corregido y se repiten CI/revisión del nuevo HEAD. Se conservan datos, tesis, recibos, pins y los bloqueos de exportación/publicación.
