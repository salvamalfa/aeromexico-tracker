# Límites de turno y cierre del chat

## Cambio

El runtime anterior permitía cinco llamadas de herramienta y 90 segundos de
ejecución. En la validación del chat, una consulta multifuente agotó el límite
de llamadas antes de obtener todas sus referencias; otro caso agotó el límite
de 90 segundos. Un turno remoto completado sin uso inmediato conservó estado
terminal y reserva hasta que una consulta posterior confirmó el consumo. Estos
fallos permanecen fallos: recuperar uso no convierte una respuesta fallida en
éxito ni vuelve a enviar la pregunta.

El perfil sube el máximo a ocho llamadas de herramienta y 180 segundos de
ejecución. Para un turno terminal cuya respuesta no incluya uso, el proveedor
puede hacer una ventana de hasta 30 segundos de lecturas GET del turno ya
completado; no envía entradas nuevas ni cambia el resultado terminal. El worker
reserva además 10 segundos para finalizar estado local y SQLite. Con el máximo
de ejecución, espera 220 segundos; Railway debe permitir 230 segundos en total:
5 segundos para conexiones, 220 para el worker y 5 de margen. Un límite de
ejecución hosted menor reduce el drenaje calculado; valores mayores de 180 se
rechazan al arrancar.

Los límites de llamadas y ejecución siguen produciendo un error terminal. Si
no se confirma el uso durante la ventana acotada, la reserva continúa retenida.
Al vencer el plazo de ejecución, una respuesta tardía no reabre el turno ni
produce una respuesta de usuario. Solo uso completo y conocido puede conciliar
su contabilidad; uso ausente, incompleto o todavía desconocido conserva la
reserva. La extensión de cierre permite finalizar el registro y conciliar
consumo; no prueba la calidad de una respuesta.

## Evidencia y estado

Pasaron 61 pruebas focales de proveedor, límites, contabilidad y cierre. Una
revisión independiente final también pasó sus 53 pruebas focales. La cobertura
usa dobles locales y no realiza llamadas a la API. Los checks obligatorios
`test` y `web` del PR verifican la entrega antes del merge; no prueban calidad
del modelo.

El corte privado anterior conserva 74 respuestas disponibles. Un corte privado
posterior tuvo 11 intentos, 8 respuestas completadas y 3 fallos. Son cortes
separados: sus conteos no se suman ni se usan como un mismo denominador de
calidad. La revisión de respuestas y la decisión humana sobre calidad siguen
pendientes; no hay modelo ganador.

El proveedor hosted continúa en `mock`, la admisión continúa deshabilitada y el
acceso usa contraseña. El panel público permanece apagado. Railway ya muestra
230 segundos de drenaje y los límites no secretos de 8 llamadas y 180 segundos
para el próximo deploy. El runtime de esa configuración aún no se ha verificado
después de desplegar; no hubo cambio de API key ni se habilitó OpenAI.
