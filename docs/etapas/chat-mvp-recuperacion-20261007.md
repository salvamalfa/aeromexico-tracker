# Recuperación operativa del turno del MVP

Una solicitud de activación terminó como `failed/provider_error` en la app,
aunque el turno correspondiente quedó completado en el proveedor. La consulta
posterior del mismo turno confirmó una respuesta final y uso conocido. La causa
precisa de la interrupción original no quedó registrada; no se atribuye al
límite de herramientas ni al tiempo máximo sin evidencia.

El adaptador recupera resultados terminales del turno exacto tras errores
recuperables, sin reenviar entradas. Rechaza resultados de otros turnos,
sesiones o subagentes y conserva las guardias locales. La lectura del historial
recupera solo la respuesta final, sin incorporar mensajes intermedios.
La lectura recorre cursores oficiales hasta delimitar los elementos del turno,
con un máximo de 10 páginas, 1.000 elementos y 30 segundos. Detecta páginas
superpuestas y conserva la recuperación cuando el resto del historial contiene
turnos anteriores. La CLI comparte ese lector.
La reconciliación también conserva el orden de las respuestas finales divididas
en varios mensajes y excluye los mensajes intermedios. Su modo de vista previa
declara las lecturas previstas, las ventanas y el destino local; al aplicar,
informa el número de solicitudes de lectura realizadas.

La CLI privada permite reconciliar un turno existente fallido mediante lecturas
del proveedor y una transacción local. Conserva el evento de fallo anterior y
registra la respuesta y el consumo una sola vez. Rechaza cancelaciones,
timeouts, guardias conocidas, cambios de identidad y conversaciones con turnos
posteriores. Su modo predeterminado no escribe ni llama al proveedor; no hay
un endpoint público de administración.
El contexto de Docker incluye explícitamente el archivo de la CLI y mantiene
excluidos los demás scripts de chat e insumos privados.

Esta corrección mantiene el modelo, el prompt, el esfuerzo y los límites del
MVP. No introduce evaluaciones nuevas ni cambios de fase 2. Las respuestas y
credenciales permanecen en el almacenamiento privado; el expediente histórico
y los consumos desconocidos se conservan.

La validación offline cubre identidad, recuperación sin reenvío, contenido
final, contabilidad idempotente y rechazo de operaciones incompatibles. El
despliegue y la verificación de la conversación existente se registran por
separado en el checkpoint privado; no se declara una aprobación de calidad.
