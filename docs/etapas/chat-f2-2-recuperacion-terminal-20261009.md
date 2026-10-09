# F2.2 · Reconciliación local de una corrida terminal

Fecha: 9 de octubre de 2026.

## Alcance y evidencia

La campaña stage 1 conserva sus dos prompts, sus 58 casos por prompt, el límite
configurado de 16 llamadas de herramienta y la reserva total de US$3. El informe
privado de Luna medium/current terminó con 53 filas: 50 turnos de modelo
completados, dos rechazos de contexto antes del proveedor y N24 detenido por el
límite local `tool_call_limit`. Los 51 turnos iniciados tienen uso y costo
conocidos por fila; el total del informe y la suma de filas son US$0.281405875.
N24 es un error terminal controlado, no una respuesta ni una aprobación.
Quedaron pendientes N25–N28 y N30.
El SHA-256 del informe local comprobado es
`eec6473ced6c7706a933f52521b5eafa4d90e9e65702775d22a51fc8f43e5681`; el
informe permanece en almacenamiento privado y no forma parte del PR.

El reconciliador comprueba el hash exacto del informe, la identidad del plan y
campaña, el prompt y herramientas, versiones de datos y semántica, tarifas,
presupuesto, prefijo único de casos, estados, uso y conciliación de costos. Solo
acepta esos dos rechazos de contexto cuando el fixture actual también confirma el
rechazo y la evidencia prueba cero llamadas, sin sesión, uso ni costo. Errores
HTTP, uso desconocido, costos ausentes, filas duplicadas o fuentes parciales
bloquean el resume antes de admitir proveedor.

`scripts/chat/reconcile_terminal_campaign_report.py` reconstruye el plan desde
el fixture y prompt aprobados, valida el snapshot y catálogo actuales, y exige el
SHA-256 esperado. Su modo predeterminado solo valida y muestra una vista previa.
`--apply` escribe el checkpoint indicado, crea antes un respaldo privado 0600 y
registra el hash; no llama al proveedor. Reanudar después envía solo los IDs
faltantes. El caso terminal queda guardado y nunca se repite.

Al completar las 58 filas se escribe un informe privado nuevo, con cada fila de
origen intacta y sus hashes de partes. Se suma el costo una vez por case ID;
los tokens conocidos incluyen cada caso iniciado con uso completo, N24 incluido.
Las latencias solo incluyen turnos de modelo completados. El `turn_count`
heredado cuenta casos con llamada iniciada; `planned_user_message_count` cuenta
mensajes de usuario planeados, y no afirma cuántas solicitudes API hizo el
proveedor. La calidad y la rúbrica humana siguen pendientes; cerrar técnicamente la campaña no aprueba
respuestas ni reconcilia una factura.

## Validación

Las pruebas usan stubs offline y cubren el caso real de 53 filas más cinco
pendientes y el composite de 58 filas, además de identidad cambiada, gasto
incompleto, error HTTP, costo ausente, duplicados, prefijo parcial y alteración
de fuentes. El ensayo del CLI sobre una copia temporal del checkpoint y el
informe original confirmó exactamente cinco IDs faltantes y US$0.281405875; la
copia no cambió en modo dry-run. No se hicieron llamadas API ni se alteró el
checkpoint original, el informe original, los prompts, fixtures, tarifas o
aprobaciones.
