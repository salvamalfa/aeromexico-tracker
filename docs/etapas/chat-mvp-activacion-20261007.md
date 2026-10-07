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

Para validar el registro aprobado se restauraron en `quantitative.py` dos
imports que habían sido eliminados después de generarse el cálculo. El
fingerprint registra los bytes completos del archivo; la fuente restaurada es
idéntica a la que se usó para el cálculo aprobado. El replay mantuvo iguales
los 372 nodos y sus cifras; no se editó el cálculo, el registro ni la aprobación.

El gate generó 126 archivos con el panel incluido y `src.publish.verify site/`
pasó. Los 112 archivos de `site/data/v1/` y el `analysis_manifest` coinciden
con `origin/master`; esta etapa no publica cifras nuevas. La compilación y la
verificación local están completas. Sigue pendiente confirmar la configuración
y salud de Railway y comprobar el panel tras el deploy de Pages. No se
modificaron prompt ni backend y no se hicieron llamadas pagadas.
