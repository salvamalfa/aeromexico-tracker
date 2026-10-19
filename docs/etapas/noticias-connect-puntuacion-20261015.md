# Noticias: nombre compuesto con puntuación (15 octubre 2026)

Se corrige el hallazgo de revisión de `32e71dd`: Aeroméxico (Connect), Aeroméxico/Connect y variantes con guiones Unicode deben seleccionar únicamente el operador Connect. La normalización resuelve el nombre compuesto antes de reconocer la marca matriz, tanto en el texto como en el argumento de compañía. Una conjunción explícita conserva las dos entidades. No se incorporan noticias de la matriz a una consulta de Connect.

Las 531 pruebas focalizadas pasan, incluidas 27 regresiones nuevas de puntuación, argumentos contradictorios y conjunciones. Los siete ejemplos preparados del preview permanecen idénticos byte a byte. El cambio es del resolver; UI, capturas, fuentes, índice aprobado, paquete candidato y recibos no cambian. No se ejecutó un modelo real. Se regenera el diagnóstico de paridad y se solicita CI y revisión del HEAD final; la presentación sigue bloqueada sin aprobación independiente.
