# Noticias: recencia singular e intervalos de años (15 octubre 2026)

La segunda revisión de búsqueda añadió dos casos de lenguaje ordinario. «¿Cuál es la última noticia de Aeroméxico?» y «Muéstrame la noticia más reciente de Aeroméxico» eliminan formas singulares de recencia y cópulas del vocabulario buscable; devuelven primero la ficha de publicación más reciente, sin términos espurios. No se afirma que haya una sola noticia ni cobertura exhaustiva.

«Muéstrame noticias de Aeroméxico entre 2025 y 2026» aplica los límites completos 2025-01-01..2026-12-31. Una regresión con noticias de 2024 a 2027 prueba que solo devuelve 2025 y 2026; los intervalos invertidos o con más de dos años distintos se rechazan expresamente. No se elimina un filtro temporal silenciosamente.

Las 22 pruebas del flujo natural pasan, incluidas API/worker, citas inventadas y candidatas cerradas. La suite pública de CI vuelve a ejecutarse sobre el HEAD; no hay inferencia de modelo real. El índice aprobado, las fuentes, el paquete de once candidatas y los recibos/pins permanecen iguales. Las correcciones no cambian el HTML de la preview ni sus datos: continúa en el mismo archivo de Library v4.
