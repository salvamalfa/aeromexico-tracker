# Stage 3 · corrección del contrato de herramientas Agents API · 13 oct 2026

El reintento N01 devolvió HTTP 400 con parámetro rechazado
`agent.tools[0].strict` y tipo `invalid_request_error`, antes de crear sesión.
El catálogo enviaba un campo de Responses API que el contrato de funciones de
Agents API no admite.

Se omite únicamente `strict` del objeto enviado. Se conserva la normalización
de JSON Schema: objetos cerrados, todas las propiedades requeridas y nulabilidad
para argumentos opcionales; también se conserva el rechazo de declaraciones
explícitas `strict=False`. No cambian modelo, prompt, contenido ni fixture.

Una prueba offline captura el POST del SDK oficial mediante transporte mock y
comprueba los trece nombres, campos admitidos por el SDK y esquemas completos,
sin modificar los insumos. Otra prueba confirma la validación semántica de
`strict`. Las pruebas focalizadas de proveedor, herramientas y campaña se
ejecutan con el pin financiero autorizado existente: **149 pasaron**. Esta corrección no consume
API, no acredita respuestas nuevas ni determina el consumo de intentos previos.
