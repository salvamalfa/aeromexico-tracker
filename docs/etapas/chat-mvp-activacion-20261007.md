# Activación del panel MVP del chat

Este reporte separa el build y gate preparados el 7 de octubre de la activación
operativa comprobada el 8 de octubre. El build del 7 habilitó el panel en la
compilación de Pages con `VITE_CHAT_ENABLED=true` y pasó `src.publish.verify`;
por sí solo no comprobaba que Railway estuviera conectado al proveedor real ni
que una sesión de usuario pudiera acceder.

El dueño eligió `gpt-6.1-sol`, con topes diarios de US$3 por usuario y US$3
global. El estado comprobado el 8 de octubre es Railway por HTTPS, autenticación
con contraseña, proveedor OpenAI y admisión habilitada; el panel está visible
en [Pages](https://salvamalfa.github.io/aeromexico-tracker/). Salud reportó
HTTPS 200 y estado `ok`, con worker y proveedor habilitados. Una conversación
anónima recibió 401; CORS permitió el origen de Pages. Se comprobaron una vez
el login y la lectura del historial desde Pages con las credenciales del dueño.

La pregunta original del historial quedó `provider_error` sin mensaje de
asistente. No se reenvió ni recuperó y no hay una respuesta nueva validada. La
causa no está demostrada; no se atribuye a los límites de 8 llamadas o 180
segundos. La prueba desde el teléfono con la computadora apagada sigue
pendiente. El uso del turno fallido y su costo deben preservarse.

La evidencia histórica disponible para Sol registró 31 respuestas correctas
de 31 respuestas disponibles; el conjunto soportado fue 10 de 12 preguntas y
dos quedaron sin respuesta correcta. Esa evidencia no valida el prompt actual
y no se declara como gate de calidad superado. El dueño aceptó el MVP con ese
límite conocido; fase 2 no ha comenzado y solo se inicia si el dueño la pide.

PR [#102](https://github.com/salvamalfa/aeromexico-tracker/pull/102),
[#103](https://github.com/salvamalfa/aeromexico-tracker/pull/103) y
[#104](https://github.com/salvamalfa/aeromexico-tracker/pull/104) están
fusionados. CI [37792230297](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/37792230297)
y Pages [37792230531](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/37792230531)
terminaron correctamente. La fuente publicada es `5e5d024`. Los 112 archivos
de `site/data/v1/`, contratos y `analysis_manifest` permanecen iguales; no se
publicaron datos nuevos.

El monto de **US$2.72 gastados**, reportado el 7 de octubre, no está reconciliado
contra el ledger y no debe tratarse como saldo contable ni como consumo actual
verificado. S14 sigue `NULL`/desconocido, nunca cero. No importes ese valor
como uso medido ni borres o reprocese el turno fallido para alterar costos.

La comprobación del DOM del 8 de octubre mostró en la pregunta histórica el
error seguro guardado para el turno fallido sin respuesta. Se asocia al turno
en el cliente, se inserta como texto y no reenvía la pregunta al abrir el
historial. Si una actualización autoritativa cambia el estado, la etiqueta se
elimina. La prueba desde el teléfono con la computadora apagada sigue pendiente.

La siguiente comprobación es el acceso desde el teléfono con la computadora
apagada, sin reintentar la pregunta fallida. Si el dueño decide enviar una
pregunta nueva, su resultado será una observación independiente, no una
validación del prompt. Para detener admisiones, usar
`CHAT_ADMISSION_ENABLED=false` mediante cambio de configuración y despliegue
controlado, preservando historial y costos registrados.

Para validar el registro aprobado se restauraron en `quantitative.py` dos
imports que habían sido eliminados después de generarse el cálculo. El
fingerprint registra los bytes completos del archivo; la fuente restaurada es
idéntica a la que se usó para el cálculo aprobado. El replay mantuvo iguales
los 372 nodos y sus cifras; no se editó el cálculo, el registro ni la aprobación.
El chequeo Ruff F401 queda exceptuado solo para este archivo por esos dos
imports; las demás reglas F y el resto de `src/` y `scripts/` siguen cubiertos.

El gate de compilación generó 126 archivos con el panel incluido y
`src.publish.verify site/` pasó. El encendido final se realizó por
configuración, después de las correcciones operativas de PR #103 y visuales de
PR #104. No cambiaron el prompt, el esfuerzo ni los límites de 8 llamadas y
180 segundos; no se hicieron nuevas evaluaciones pagadas.
