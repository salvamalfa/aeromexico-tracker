# Noticias: matriz de límites y procedencia HTTP (15 octubre 2026)

Se atienden los dos hallazgos de `f0dc124` con validación por significado y una matriz amplia; no se vuelve a descargar ni modificar el corte real.

## Fechas y argumentos nullable

La consulta se valida siempre, antes de combinar límites. Una frase relativa pide fechas explícitas aunque el caller envíe inicio, fin o ambos. Un periodo absoluto expresado en la pregunta determina su ventana; un límite ausente se completa únicamente de ese texto. Los argumentos contradictorios se rechazan. Una consulta solo por palabras conserva los filtros estructurados válidos, incluidos intervalos abiertos explícitos. «Desde» y «hasta» tienen límites inclusivos; no se añade un extremo opuesto no expresado.

La matriz de 128 casos cruza consultas relativas, precisión mixta/inválida, mes/día/año, rangos entre años, intervalos abiertos, argumentos nulos/parciales/completos y contradicciones. Incluye llamadas a EvidenceIndex; otras siete pruebas de API/worker/historial emulan un caller que envía fechas: cuatro variantes relativas no crean tarjetas, dos meses absolutos completan el límite explícito faltante y una contradicción pide aclaración. No se usa un modelo real.

## Redirecciones y bytes efectivamente descargados

Se mantienen cuatro peticiones máximas por fuente. Un último 3xx agota el límite y falla antes de hashes, Bronze o candidato. Cada destino se valida antes de pedirlo; un Location ausente falla. Solo HTTP 200 representa un documento completo. La URL atribuida al hash proviene de la respuesta recibida; nunca de un Location que quedó sin descargar.

La matriz de 55 casos prueba estados 301/302/303/307/308 con cero a cinco redirecciones; destinos HTTP, autenticados o no aprobados en cada salto permitido; Location ausente/vacío; 201/202/204/206/304 y errores; y un lote donde la segunda fuente falla. Los casos exitosos cotejan hash y bytes Bronze con la respuesta final 200. Los fallidos no crean candidato ni captura de HTML de redirección; una captura 200 válida anterior permanece conservada.

El httpx instalado ya rechaza 3xx en raise_for_status(): no se observó corrupción del corte existente, cuyas once fuentes se verificaron con respuesta final 200. El nuevo rechazo explícito deja la garantía independiente de ese comportamiento y evita atribuciones ambiguas; rechazar 206 también impide etiquetar contenido parcial como verificado 200.

## Resultado y límites

285 pruebas focalizadas pasan: 128 fechas/límites, 55 HTTP/redirecciones, 66 flujo natural/API, 29 índice y siete capturas históricas. Los siete ejemplos de la preview siguen coincidiendo exactamente con el resolver actualizado; su HTML/JS, datos e identidad v4 no cambian. CI y revisión se ejecutan de nuevo sobre el HEAD.

Índice, recibos/pins, once candidatas, Gold, tesis, cron y publicación conservan su estado. La gramática es acotada y usa fechas de publicación; no equivale a calificar un modelo real. El diagnóstico de paridad se regenera con la procedencia del código evaluado y conserva el bloqueo técnico sin aprobar ninguna versión.
