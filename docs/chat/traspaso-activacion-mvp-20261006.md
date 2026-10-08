# Traspaso: activación del MVP del chat

Documento operativo de continuidad, actualizado el 8 de octubre de 2026. Resume
la decisión del dueño, el estado comprobado y los límites del MVP. Las reglas
de `AGENTS.md` siguen vigentes. La fase 2 no está iniciada y solo comienza
cuando el dueño la solicite expresamente.

**Orden de lectura:** este traspaso, luego el [estado del chat](README.md) y el
[reporte de activación](../etapas/chat-mvp-activacion-20261007.md). Para una
solicitud expresa de fase 2, consulta [fase 2 del chat](fase-2-agente-analitico.md).

## Estado operativo comprobado al 8 de octubre

- El dueño eligió `gpt-6.1-sol`, con topes diarios de **US$3 por usuario y
  US$3 global**. El backend real usa autenticación con contraseña, proveedor
  OpenAI y admisión habilitada. El panel está visible en
  [Pages](https://salvamalfa.github.io/aeromexico-tracker/).
- Se comprobó HTTPS 200 y estado `ok`; worker, autenticación con contraseña,
  proveedor OpenAI y admisión reportaron estado habilitado. Una visita anónima
  recibió 401 en conversaciones; CORS permitió el origen de Pages.
- Se comprobaron una vez el login y la lectura del historial desde Pages con
  las credenciales del dueño. La pregunta original aparece como `provider_error`, sin respuesta de asistente.
  No se reenvió ni recuperó. No hay una respuesta nueva validada y queda
  pendiente probar el acceso desde el teléfono.
- La causa original no está demostrada. No se atribuye a límites de 8 llamadas
  ni de 180 segundos. El uso del turno fallido ya está contabilizado en el
  estado privado; conserva ese costo y el historial.
- PR [#102](https://github.com/salvamalfa/aeromexico-tracker/pull/102),
  [#103](https://github.com/salvamalfa/aeromexico-tracker/pull/103) y
  [#104](https://github.com/salvamalfa/aeromexico-tracker/pull/104) están
  fusionados. CI [37792230297](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/37792230297)
  y Pages [37792230531](https://github.com/salvamalfa/aeromexico-tracker/actions/runs/37792230531)
  terminaron correctamente. La fuente publicada es `5e5d024`; los 112 archivos
  de datos, contratos y `analysis_manifest` no cambiaron.

## Calidad y evidencia

La evidencia histórica de Sol registró 31 respuestas correctas de 31
respuestas disponibles; el conjunto soportado fue 10 de 12 preguntas y dos
quedaron sin respuesta correcta. Es evidencia histórica que no valida el
prompt actual. El dueño aceptó activar el MVP con esos límites conocidos; no
hay un gate de calidad aprobado ni debe reportarse como superado.

El saldo de OpenAI de **US$2.72 gastados** es el monto reportado al 7 de
octubre, no está reconciliado contra el ledger de uso. No lo presentes como un
saldo contable verificado ni como el costo total actual. S14 conserva su estado
`NULL`/desconocido; desconocido nunca significa cero y no se importa como uso
medido.

## Roles y operación

- **Dueño:** eligió modelo y topes, puede decidir si se inicia fase 2 y realiza
  las comprobaciones de uso desde su sesión. No se guardan aquí contraseñas,
  tokens, claves ni identificadores privados del proveedor.
- **Agente:** mantiene código y documentación conforme a una solicitud
  explícita, revisa el estado público permitido y reporta claramente límites
  de evidencia. La fase 2 no está autorizada por inferencia ni por la antigua
  autorización general de cambios rutinarios.

El backend consume únicamente el snapshot público y mantiene versiones de
datos y semántica por turno. Los valores `missing`, `NULL` o desconocidos se
preservan; no se convierten en cero. No se reingresa ni reintenta una pregunta
fallida de forma automática. No recuperes una respuesta del proveedor ni
vuelvas a enviar el turno salvo que el dueño lo pida explícitamente y se
compruebe antes su elegibilidad y costo.

La reserva de costo, los usos conocidos y los usos desconocidos deben
preservarse en el ledger. No borres ni reproceses el turno fallido para ocultar
el cargo. El límite diario monetario es el control operativo; los parámetros
históricos de 8 llamadas y 180 segundos no explican por sí solos el fallo y no
se cambian como parte de este traspaso.

## Versiones del holdout

El holdout congelado conserva `data_version de3c4d…` y el `semantic_version`
anterior a la aprobación del catálogo en PR #87. Con la regla de versión
vigente, los datos de ese corte producen `d9c4e56d04ad…`, igual al snapshot
actual; los archivos de datos, contratos y `analysis_manifest` publicados no
cambiaron. No reescribas el holdout ni atribuyas una diferencia de semántica a
un cambio de datos.

## Próxima comprobación

La próxima comprobación pendiente es una sesión explícita desde el teléfono,
con la computadora apagada: comprobar login y el estado del historial. No
reenviar la pregunta fallida. Si el dueño decide probar una pregunta nueva,
registrar el resultado como una observación nueva, separada de la pregunta
original; no llamarla validación de calidad del prompt.

Si hace falta detener admisiones, usar `CHAT_ADMISSION_ENABLED=false` mediante
un cambio de configuración y despliegue controlado. Esto debe preservar
historial y costos ya registrados. El rollback no implica borrar turnos ni
cambiar datos aprobados.

## Contexto histórico del 7 de octubre

El build de Pages preparado el 7 de octubre activó el panel en la compilación y
pasó su gate local; eso no comprobaba por sí solo que Railway estuviera en modo
real ni que una sesión de usuario funcionara. La activación operativa y el
login/historial descritos arriba se comprobaron después, el 8 de octubre. El
resultado actual de la pregunta sigue siendo un fallo conocido, sin respuesta
validada.

La actualización del catálogo semántico se aprobó para el MVP en PR #87. Las
calificaciones entregadas el 7 de octubre y sus límites están descritos en el
[reporte de activación](../etapas/chat-mvp-activacion-20261007.md). Las notas de
estilo y las evaluaciones nuevas pertenecen a fase 2, solo cuando el dueño la
solicite.
