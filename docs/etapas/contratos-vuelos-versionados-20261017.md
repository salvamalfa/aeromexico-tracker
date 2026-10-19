# Compatibilidad estricta de contratos de Vuelos

17 de octubre de 2026. La ampliación de Vuelos añade `flight_components` al
contrato vigente. Leer el snapshot aprobado anterior con ese contrato nuevo
rompía la comparación de SHA-256, aunque sus datos permanecían idénticos.

Se conserva el contrato original de `4caae0f7` bajo su SHA-256
`17fb7e131da94435190bea925fe9733e298754d04e9b9c5e76fbbea8bef119a7`, el mismo
que declara producción `40a63d1905`. El lector del chat y el verificador de
publicación validan cada archivo de vuelos con los subesquemas derivados de
la versión exacta que pide su manifiesto. Un manifiesto antiguo no admite los
componentes nuevos. El generador de manifiestos continúa usando hashes vigentes.

Solo esa versión histórica de vuelos está registrada. No se archivan reglas
de privacidad ni aprobaciones; se rechazan modificaciones de los bytes
seleccionados, hashes desconocidos, enlaces simbólicos y rutas inseguras.
La explicación permanente y las pruebas están en
[`contracts/web/README.md`](../../contracts/web/README.md#evolucionar-el-contrato).

Se verificó la identidad de los bytes archivados y la ausencia de cambios en
`site/`, manifiestos y recibos de producción. Pruebas focalizadas: contratos,
Snapshot/chat, publicación y sus negativas; resultados concretos en la entrega
del PR. Esta migración no activa datos, tesis, aprobaciones ni una publicación.
