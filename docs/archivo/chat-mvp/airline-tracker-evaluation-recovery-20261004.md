# Recuperación y cierre seguro del chat analítico

## Alcance

Esta etapa documenta la protección del cierre del worker y la reconciliación
del uso de un turno que el proveedor completa después de una cancelación. El
cambio no altera prompts, modelos, presupuestos normales, configuración de
proveedor ni los datos de evaluación. Las validaciones reportadas son offline;
no implican aprobación de calidad, autorización para habilitar el chat ni
llamadas pagadas.

## Admisión y entrada al proveedor

Al iniciar Uvicorn el cierre, el API detiene de inmediato los nuevos claims,
antes de esperar las conexiones SSE existentes. Uvicorn permite hasta 5
segundos para cerrar esas conexiones; después, el lifespan da al worker hasta
90 segundos para terminar el turno activo. En el launcher Railway el presupuesto
es 5 + 90 segundos, con 5 segundos de margen frente al drenaje configurado de
100 segundos. La espera del API está acotada y no queda bloqueada por una
cancelación remota que no responda.

El worker serializa el cierre con la autorización que marca una entrada nueva
como iniciada. Si el cierre ya venció, el turno no recibe autorización para una
nueva entrada. La autorización es el punto de linealización: una entrada ya
autorizada cuenta como en vuelo y puede alcanzar el SDK concurrentemente con el
cierre; el worker la trata como uso potencialmente desconocido, nunca como cero.
La protección también cubre sesiones reutilizadas: no cancela la sesión previa
antes de confirmar la autorización para una entrada nueva. Los proveedores con
la interfaz actual reciben esta autorización; los proveedores legados que no
declaran soporte siguen ejecutándose con su firma existente y se marcan como
potencialmente en vuelo antes de invocarlos.

Al escribir el mensaje de usuario en una sesión reutilizada, si la cancelación
llega mientras la llamada síncrona al SDK está en curso, el proveedor intenta
cancelar la sesión al salir de esa escritura y luego propaga la cancelación. No
repite ni vuelve a enviar el mensaje. Si la cancelación remota falla, el worker
mantiene el estado terminal y su límite de espera; el uso queda desconocido
hasta que exista confirmación.

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
única; el worker no ejecuta este sondeo de reconciliación. Al vencer el drenaje,
la cancelación remota se lanza en segundo plano y no se espera ni se garantiza
su aceptación; el estado terminal y la reserva desconocida impiden reproducir
el turno.

## Validación y estado

Las pruebas focales offline cubren cierre con turno activo, persistencia única
del resultado y uso, bloqueo de nuevos claims, expiración acotada, autorización
coordinada con timeout y cancelación remota bloqueada. La validación más reciente
anterior del root aprobó 122 pruebas focales y el formato de 40 archivos. La ejecución
pública previa del commit inicial de PR84 (`a2ab6d8`) aprobó 736 pruebas (1
omitida y 77 no seleccionadas); sus checks `test` y `web` quedaron verdes. Esa
CI corresponde a ese commit inicial. La revisión `04d0afe` también aprobó CI:
742 pruebas Python, 6 omitidas y 77 no seleccionadas, 95 Vitest y 9 de navegador.
La corrección posterior de cancelación durante la escritura en sesiones
reutilizadas aprobó 40 pruebas del adaptador y de límites de módulos. Incluye una
prueba integrada de cierre con la segunda cancelación bloqueada, uso desconocido
y reserva conservada. Sus checks de CI se siguen antes de integrar. El smoke completo de runtime con la
variante local CA verificó healthcheck, `PORT`, autenticación, rechazo de
admisión y persistencia tras reinicio; no hizo llamadas al proveedor. El sondeo
de uso tardío hasta seis lecturas pertenece al evaluador de comparación. No se
ejecutó un turno pagado de 90 segundos para probar el drenaje en Railway: las
pruebas offline sí cubren el límite de cierre, pero el comportamiento del host
remoto sigue sin verificarse. No hay aquí una aprobación de calidad de
respuestas. Durante el
cierre del servidor se rechazan nuevos claims; esto no cambia la configuración
persistente de admisión. El proveedor permanece en `mock` hasta que se completen
por separado las revisiones y autorizaciones requeridas.
