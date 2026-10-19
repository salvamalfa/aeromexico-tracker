# Noticias: recorrido del chat y decisión conjunta (15 octubre 2026)

Esta continuación mantiene el PR draft independiente y las tres fichas aprobadas. No habilita las once candidatas, no cambia el prompt ni sus recibos, no publica y no programa tareas.

## Preguntas completas y destinos verificables

La herramienta existente `search_news` resuelve entidades, meses/años o intervalos explícitos de publicación y temas en español; las palabras restantes ordenan coincidencias. No infiere fechas relativas ambiguas. El botón de Noticias lleva los filtros al chat; la búsqueda se ejecuta en su API y worker. Los resultados llevan referencias y un payload de navegación generado exclusivamente por la herramienta ejecutada, persistido y recuperable por historial/SSE. El texto del proveedor no crea destinos de navegación.

La interfaz verifica corpus, hash de índice, ID, identidad del relato, título, fecha, URL, editor y hash de fuente antes de abrir una ficha. Un ID desconocido, una fuente alterada o una candidata en el build de producción no navegan. Cada llamada conserva el máximo existente de cinco resúmenes; devuelve el total y hasta 50 IDs verificados para abrir el conjunto completo en Noticias. No se interpreta falta de coincidencias como ausencia de noticias.

Las pruebas recorren preguntas completas como «¿Qué noticias de combustible de Aeroméxico se publicaron en abril de 2026?» y «¿Qué publicó Viva sobre tráfico en septiembre de 2026?». La segunda devuelve cero en el corpus aprobado. La simulación candidata aislada encuentra el tráfico de Viva publicado en septiembre (hecho de agosto), el crédito, la alianza Delta y tráfico de Volaris publicado en octubre. «Muéstrame todas las noticias publicadas entre junio y octubre de 2026» permite abrir las 13 fichas del intervalo, con cinco resúmenes y total explícito.

## Cobertura y aprobación

Las tarjetas marcan «Buscable hoy» o «No buscable en producción». Un filtro y un botón muestran exactamente las tres actuales. Las once candidatas se reúnen en [un paquete de decisión](../noticias-aprobacion-conjunta-20261015.md): resúmenes originales, publicación/hecho/captura, fuentes y hashes de registros normalizados. SHA-256 del paquete `64e30adc58e1a72b302190ebeb5c43ea287bba79337a9b8bd1f92ebdbd05dc56`. El dueño puede decidir una vez sobre todas; los recibos internos se prepararían después de esa decisión. No se escriben recibos aquí.

La preview de Library ejecuta siete ejemplos offline claramente rotulados, mediante el mismo panel y navegación reales. El candidato usa un flag exclusivo de revisión y un módulo que no se importa en el runtime de producción. No se fingen respuestas de un modelo, no se generan aprobaciones falsas y no se cambia el índice real.

## Validación y límites

Se probó API real → worker → herramienta → historial/SSE → navegación en Chromium a 1440 y 390 px con proveedor simulado, además de inyección, referencias inventadas y fuentes alteradas. Los cuatro smoke de CI dieron 16 aprobadas y una omisión por la pestaña Mercado independiente; TypeScript y 194 pruebas de Vitest pasaron. Runtime aislado, Ruff y formato migrado pasan. La suite pública detectó exclusivamente un texto generado desactualizado de la matriz F2.9: las 55 llamadas offline pasan de 108601 a 108893 bytes por los metadatos de navegación. Se regeneró la matriz; no se alteran perfiles, presupuestos, recibos ni resultados históricos de campaña. Los checks remotos corresponden al HEAD del PR.

**Inferencia de modelo real no verificada.** Existe clave en el entorno (no se muestra ni copia); faltan el opt-in y la configuración local efectiva del runtime de producción. Se reutiliza la integración y el prompt existentes, sin nueva clave, presupuesto ni aprobación. No se hizo una petición pagada ni se afirma que el modelo ya elija la herramienta en todos estos casos.

La [paridad de presentación](../paridad-presentacion-20261015.md) conserva un fallo y un error de fixture en los dos controles locales, ambos por la misma huella técnica heredada que también falla en master. Datos numéricos, cuatro tesis y 68 afirmaciones permanecen iguales. Tres nuevas versiones técnicas requieren revisión/aprobación independiente antes de exportar. No se declara presentación verificada.

## Entregables y pendientes

Preview actualizada conservando identidad: `oai-library://libfile_3e22fcada01c8191a8a4ef18b047093a/Noticias-preview.html`. Capturas adicionales del chat: `oai-library://libfile_65925ad27c4881919a25ee8d2b34042b/Noticias-chat-desktop.png` y `oai-library://libfile_56ec0d2f2bbc81918fee90555b1fdd29/Noticias-chat-mobile.png`.

Pendientes: skills por fuente; coordinador mensual/trimestral; corte mensual de Noticias con cobertura declarada; decisión sobre las once candidatas; prueba autorizada del modelo real y calificación de su comportamiento; revisión/aprobación técnica de presentaciones; aprobaciones independientes de integración/publicación; limpieza futura según auditoría Gold, sin borrar datos ahora. Cron permanece apagado.
