# Traspaso: activación del MVP del chat

Documento operativo de continuidad, actualizado el 8 de octubre de 2026. Resume
la decisión del dueño, el estado comprobado y los límites del MVP. Las reglas
de `AGENTS.md` siguen vigentes. La siguiente etapa es la
[fase 2 del chat](fase-2-agente-analitico.md), que comienza cuando el dueño
envíe la solicitud.

**Orden de lectura:** este traspaso, luego el [estado del chat](README.md) y el
[reporte de activación](../etapas/chat-mvp-activacion-20261007.md).

## Estado operativo comprobado al 8 de octubre

- El dueño eligió `gpt-6.1-sol`. Los topes diarios vigentes son **US$5 por
  usuario y US$5 global**: eran de US$3 hasta el 8 de octubre, cuando a pedido
  del dueño se subieron y `CHAT_MAX_TOOL_CALLS` pasó de 8 a 16 (ver
  [diagnóstico](../etapas/chat-limite-herramientas-presupuesto-20261008.md)).
  El backend real usa autenticación con contraseña, proveedor OpenAI y
  admisión habilitada. El panel está visible en
  [Pages](https://salvamalfa.github.io/aeromexico-tracker/).
- Se comprobó HTTPS 200 y estado `ok`; worker, autenticación con contraseña,
  proveedor OpenAI y admisión reportaron estado habilitado. Una visita anónima
  recibió 401 en conversaciones; CORS permitió el origen de Pages.
- Se comprobaron el login y la lectura del historial desde Pages con las
  credenciales del dueño. La pregunta original del 7 de octubre aparece como
  `provider_error`, sin respuesta de asistente; no se reenvió ni recuperó.
- La causa original no está demostrada, pero el turno terminó con 8 resultados
  de herramienta. La segunda pregunta real, del 8 de octubre (`0fc9308d…`),
  falló por `tool_call_limit`, así que es muy probable que la causa haya sido
  la misma. El uso del turno del 7 de octubre ya está contabilizado en el
  estado privado; conserva ese costo y el historial. El turno `0fc9308d…`
  conserva una reserva de US$1.50 sin conciliar.
- El 8 de octubre, con los límites nuevos, el dueño obtuvo respuestas reales
  correctas en producción: una pregunta de aclaración y la respuesta de market
  share 2026 con tabla. Las tablas se renderizan en el chat desde
  [#108](https://github.com/salvamalfa/aeromexico-tracker/pull/108), y un turno
  detenido por un límite local cancela el turno del proveedor y registra su uso
  real desde [#107](https://github.com/salvamalfa/aeromexico-tracker/pull/107).
  Son observaciones de uso, no una validación de calidad del prompt.
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

- **Dueño:** eligió modelo y topes, decide cuándo inicia la fase 2 y realiza
  las comprobaciones de uso desde su sesión. No se guardan aquí contraseñas,
  tokens, claves ni identificadores privados del proveedor.
- **Agente:** mantiene código y documentación conforme a una solicitud
  explícita, revisa el estado público permitido y reporta claramente límites
  de evidencia. La fase 2 empieza con la solicitud del dueño; no se infiere de
  la autorización general de cambios rutinarios.

El backend consume únicamente el snapshot público y mantiene versiones de
datos y semántica por turno. Los valores `missing`, `NULL` o desconocidos se
preservan; no se convierten en cero. No se reingresa ni reintenta una pregunta
fallida de forma automática. No recuperes una respuesta del proveedor ni
vuelvas a enviar el turno salvo que el dueño lo pida explícitamente y se
compruebe antes su elegibilidad y costo.

La reserva de costo, los usos conocidos y los usos desconocidos deben
preservarse en el ledger. No borres ni reproceses el turno fallido para ocultar
el cargo. El límite diario monetario es el control operativo. El 8 de octubre
el límite de llamadas pasó de 8 a 16 por la falla comprobada por
`tool_call_limit`; el de 180 segundos no cambió. Un turno fallido con uso
desconocido conserva su reserva hasta que se concilia, incluso en días
posteriores.

## Versiones del holdout

El holdout congelado conserva `data_version de3c4d…` y el `semantic_version`
anterior a la aprobación del catálogo en PR #87. Con la regla de versión
vigente, los datos de ese corte producen `d9c4e56d04ad…`, igual al snapshot
actual; los archivos de datos, contratos y `analysis_manifest` publicados no
cambiaron. No reescribas el holdout ni atribuyas una diferencia de semántica a
un cambio de datos.

## Comprobación opcional y rollback

Si el dueño lo desea, puede comprobar el acceso desde el teléfono con la
computadora apagada: login y estado del historial. No reenviar las preguntas
fallidas. Cada pregunta nueva es una observación separada, no una validación de
calidad del prompt.

Si hace falta detener admisiones, usar `CHAT_ADMISSION_ENABLED=false` mediante
un cambio de configuración y despliegue controlado. Esto debe preservar
historial y costos ya registrados. El rollback no implica borrar turnos ni
cambiar datos aprobados.
