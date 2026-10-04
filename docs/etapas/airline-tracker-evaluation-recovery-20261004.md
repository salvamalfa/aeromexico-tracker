# Recuperación y cierre seguro del chat analítico

## Alcance

Esta etapa documenta la protección del cierre del worker y la reconciliación
del uso de un turno que el proveedor completa después de una cancelación. El
cambio no altera prompts, modelos, presupuestos normales, configuración de
proveedor ni los datos de evaluación. Las validaciones reportadas son offline;
no implican aprobación de calidad, autorización para habilitar el chat ni
llamadas pagadas.

## Admisión y entrada al proveedor

Al iniciar el cierre, el API y el worker dejan de admitir y reclamar turnos
nuevos. El worker espera al turno activo por un máximo de 95 segundos, suficiente
para cubrir el presupuesto normal de 90 segundos más margen de cierre. La
espera del API está acotada y no queda bloqueada por una cancelación remota que
no responda.

El worker serializa el cierre con la autorización inmediatamente anterior a
crear una entrada nueva en el SDK. Si el cierre ya venció, el turno no empieza
una nueva entrada. La protección también cubre sesiones reutilizadas: no cancela
la sesión previa antes de confirmar que la entrada nueva está autorizada. Los
proveedores con la interfaz actual reciben esta autorización; los proveedores
legados que no declaran soporte siguen ejecutándose con su firma existente.

Un turno interrumpido recibe un estado terminal una sola vez. El worker no
reintenta ni reproduce entradas durante el cierre. Si el proveedor entrega una
respuesta tardía, su uso confirmado todavía se registra una sola vez sin
reabrir el turno ni reemplazar su estado terminal.

## Errores y reconciliación del uso

Los errores persistidos exponen únicamente códigos de una lista permitida
(incluidos `tool_call_limit`, `turn_timeout` y `tool_result_limit`) y tipos o
estados seguros. No guardan texto bruto de excepciones del proveedor.

Después de cancelar, el evaluador de comparación puede consultar el turno
existente para reconciliar uso durante un máximo de 30 segundos y seis lecturas
GET, con un límite por lectura. Solo acepta un resultado terminal que coincida
con el turno y la sesión esperados. No crea otra entrada, no reintenta la
consulta como una nueva ejecución y no atribuye uso no confirmado. Si el
resultado sigue sin estar disponible, el uso permanece desconocido y su reserva
se conserva; nunca se convierte en cero por falta de respuesta. En el worker,
una respuesta o excepción tardía con uso conocido se contabiliza de manera
única; el worker no ejecuta este sondeo de reconciliación.

## Validación y estado

Las pruebas focales offline cubren cierre con turno activo, persistencia única
del resultado y uso, bloqueo de nuevos claims, expiración acotada y cancelación
remota bloqueada. La validación del root reportó 105 pruebas focales aprobadas,
736 pruebas públicas aprobadas (1 omitida y 77 no seleccionadas) y formato final
correcto en 37 archivos. El smoke completo de runtime con la
variante local CA verificó healthcheck, `PORT`, autenticación, rechazo de
admisión y persistencia tras reinicio; no hizo llamadas al proveedor. El sondeo
de uso tardío hasta seis lecturas pertenece al evaluador de comparación. No se
ejecutó un turno pagado de 90 segundos para probar el drenaje en Railway: las
pruebas offline sí cubren el límite de cierre, pero el comportamiento del host
remoto sigue sin verificarse. La CI del PR siguiente todavía está pendiente.
No hay aquí una aprobación de calidad de respuestas. Durante el
cierre del servidor se rechazan nuevos claims; esto no cambia la configuración
persistente de admisión. El proveedor permanece en `mock` hasta que se completen
por separado las revisiones y autorizaciones requeridas.
