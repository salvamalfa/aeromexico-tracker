# Noticias: cantidades relativas y límites del parser (15 octubre 2026)

El hallazgo de `877ac05` reproduce «noticias de hace 3 meses sobre combustible»: un tema coincidente no puede ocultar un intervalo sin resolver. Se detectan cantidades numéricas/escritas tras «hace», y formas de pasado/futuro. Una unidad temporal sin corte absoluto pide aclaración; semanas/trimestres/otros intervalos no implementados requieren extremos de fecha explícitos. Ayer/anteayer/anoche/mañana tampoco se convierten en una consulta abierta.

La regla es conservadora: una consulta ambigua recibe una petición de fechas de publicación, no resultados de todo el archivo ni una interpretación del periodo del hecho. La fecha ISO, mes con año o año explícito siguen funcionando; un plazo de crédito en años puede coexistir con un año de publicación expresado. «Última noticia» conserva orden de recencia sin inventar un intervalo.

Validación: 59 pruebas naturales/temporales y 29 del índice. El recorrido API/worker/historial prueba tanto «último mes» como el caso «hace 3 meses sobre combustible» y exige una aclaración sin destinos de tarjetas. Las reglas son una gramática acotada, no una validación de inferencia de un modelo real. UI, siete ejemplos offline y archivo de Library v4 no cambian.

El nuevo HEAD vuelve a pasar por CI y revisión. Datos, índice, recibos, candidatas y bloqueos de publicación permanecen iguales; se regenera la prueba de paridad con su procedencia.
