# Activación del panel MVP del chat

El 7 de octubre de 2026 se habilitó el panel del chat para el build de Pages
con `VITE_CHAT_ENABLED=true`; se conservó la URL pública de la API configurada
en `web/.env.production`. La selección del dueño para el backend es
`gpt-6.1-sol`, con topes diarios de US$3 por usuario y US$3 global. La
configuración de Railway y la publicación del sitio se realizan por separado.

La evidencia histórica disponible registró 31 respuestas correctas de 31
disponibles. El conjunto soportado fue 10 de 12 preguntas; Q07 y Q34 fallaron.
Esa evidencia no valida el prompt actual. El dueño decidió activar el MVP con
ese límite conocido; no se creó un gate de aprobación ni se cambió el estado
de aprobaciones. Evaluaciones nuevas, esfuerzo de respuesta y ajustes de estilo
quedan para fase 2.

La validación pendiente incluye confirmar la configuración y salud del servicio
de Railway, compilar el sitio mediante el gate de publicación aprobado y
comprobar el panel publicado. Esta etapa no modifica prompt, backend, datos ni
aprobaciones y no ejecuta llamadas pagadas.
