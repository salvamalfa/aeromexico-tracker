# Preparación operativa del calendario único

## Resumen

**Preparado para activación**, con estado privado y disparo puntual calculado.
No hay una automatización operativa. La autorización específica de activación
sigue pendiente. La aprobación de las reglas del calendario ya existe y no se
pide otra vez. Las reglas y las dependencias de fuentes siguen en el
[catálogo canónico](catalogo-fuentes-calendario.md).

El [registro operativo](../scripts/source_update_coordinator.py) añade solo la
persistencia que faltaba entre turnos. Reutiliza `calendar`, `plan`, `retry` y
el bloqueo exclusivo del recolector. No adquiere fuentes, envía mensajes,
crea automatizaciones, ejecuta recetas ni publica. No modifica el pipeline ni
las huellas de sus productores. Los candidatos y `global_readiness` conservan
sus controles y su límite `ready_for_automatic_execution=false`.

## Qué cambia para ti

El próximo mensual conocido es **17 de noviembre de 2026**, para `2026M10`.
El siguiente es **15 de diciembre**, para `2026M11`. Ambos se calculan con
los [festivos bancarios verificados](../config/source_update_holidays.json).
La mañana se representa a las 08:00 en `America/Mexico_City`, con
`timing_mode=flexible_schedule`: no es una hora de publicación de fuente.
No se genera una regla diaria o semanal ni se extrapola 2027.

El trimestre conserva fecha nula mientras falte el financiero de Viva.
El responsable del monitor ya existente aportará su confirmación junto con
los registros de Aeroméxico y Volaris. `refresh_reports` reutiliza el cálculo
de dos hábiles y agrupa a siete días naturales o menos. Una fecha ya fijada
o una ronda empezada no se cambia silenciosamente. Aerocivil sigue pendiente
de respuesta; no se envía otra consulta.

Noticias es una tarea mensual del mismo plan, con búsqueda nativa y lectura
de fuentes. RSS/GDELT permanecen opcionales. El registro selecciona por defecto
el núcleo requerido de la política vigente y Noticias. Enumera los demás
productos sin programarlos. Si se usa contexto adicional, la receta y el
control global existentes deben validar ese producto y sus dependencias.

## Apéndice técnico

### Un estado privado y un coordinador

La ruta canónica es la que consta en `state.workspace`; el identificador es
`airlines-tracker-source-calendar`. El estado vive bajo
`tmp/source-updates/<coordinador>/`, ignorado por Git, fuera de datos públicos.
No copiarlo al PR ni crear otro ledger para el mismo calendario. Una copia en
otra ruta se rechaza. El despliegue futuro debe conservar este mismo entorno
y ruta o restaurar el último estado privado verificado antes de operar. Si no
se puede recuperar, bloquear; no interpretar su ausencia como primera ejecución.

`state.json` comienza con `activation_authorized=false`, `automation_id=null`
y `publication_authorized=false`. Conserva zona, fechas mensuales y trimestral
conocidas o nulas, eventos por fecha y miembros, y claves
`cadence:period:product`. Cada tarea tiene `planned`, `running`, `completed`,
`retry_pending` o `blocked_for_decision`; recibos, SHA-256, mensajes y turnos
permanecen separados. `completed` describe el cierre operativo de un despacho;
`certification` sigue nulo. Un nuevo periodo nunca hereda una certificación.

La escritura usa el `writer` existente y sustitución atómica del JSON tras
`fsync`. Una intención de despacho guarda el dueño antes del envío externo.
El bloqueo persistente `active_task` impide otro escritor entre comandos,
incluso si el proceso desaparece. Las adquisiciones independientes pueden
preparar candidatos en sus espacios aislados; la consolidación del registro
común tiene un solo escritor. Nunca se comparte el Bronze de un lote entre
varios escritores.

Preparar una sola vez con un JSON privado que declare `as_of`, `start`,
`months`, `quarter` y `releases`. Los releases tienen la forma del CLI
`calendar`; sus confirmaciones son revisiones explícitas de documentos reales,
no una inferencia del nombre de archivo. Conservar la referencia de revisión
en ese JSON. La preparación no vuelve a consultar las fuentes.

```bash
python -m scripts.source_update_coordinator --workspace tmp/source-updates/calendar-coordinator --prepare <solicitud-privada.json> --now 2026-10-29T04:00:00Z
python -m scripts.source_update_coordinator --workspace tmp/source-updates/calendar-coordinator
```

El primer comando escribe el plan privado; repetir la misma solicitud conserva
los bytes. Otra solicitud no puede sustituirlo ni reiniciar contadores. El
segundo solo lee y emite `next_trigger.payload`. El payload contiene título,
prompt, `schedule` VEVENT sin RRULE, zona y modo flexible. **Mostrarlo no lo
crea ni autoriza ejecutarlo.** Si está vencido o hay un escritor sin resolver,
el payload es nulo y exige reconciliación. No se mueve a mañana por defecto.

### Activación futura y recuperación de su creación

La capacidad nativa conocida crea tareas habilitadas y no admite crearlas
apagadas. Por eso no se invoca durante esta preparación. Tras la autorización
específica del dueño, el coordinador realiza estos pasos una sola vez:

1. Comprobar el estado canónico y las tareas nativas existentes. Conservar la
   referencia exacta de la autorización. Registrar `activation_intent` antes de
   llamar a la herramienta nativa.
2. Crear una tarea con el payload puntual revisado. No crear otro monitor de
   Viva. Un resultado incierto deja `automation_creation.outcome=uncertain`.
3. Consultar la tarea nativa por intención, título, prompt y momento. Cuando
   se conoce el ID, registrar `bind_authorized_automation` con ese mismo
   `intent_id` y la referencia del resultado. Nunca repetir `create` por
   ausencia de respuesta. `activation_not_created` requiere prueba positiva
   de que la creación no ocurrió; una búsqueda sin resultados no basta.
4. Tras cada resultado reconciliado, actualizar **el mismo `automation_id`**
   al próximo payload. Registrar la intención de actualización en el
   expediente; ante respuesta incierta, leer su horario antes de repetir.
   Una actualización al mismo ID no justifica crear un reemplazo.

El registro acepta afirmaciones del operador autorizado; no demuestra por sí
solo que el usuario haya dado permiso ni que el proveedor haya completado una
acción. Las referencias a conversaciones y recibos son evidencia retenida,
no aprobaciones fabricadas. La publicación nunca se habilita en este registro.

### Contrato de acciones y recibos

Cada acción se pasa en un JSON privado con `--record <acción.json>`, un
`operation_id` estable y `at` con zona. Repetir el mismo ID y argumentos es una
lectura idempotente; cambiar argumentos con ese ID falla. `at` no puede ser
posterior al corte `--now`. Campos adicionales por acción:

| Acción | Campos y efecto |
|---|---|
| `refresh_reports` | `releases`; confirma fechas antes de activar o despachar, sin certificar cifras. |
| `activation_intent` | `activation_authorized=true`, `authorization_reference`, `owner_turn_id`; guarda intención incierta, sin llamar a la herramienta. |
| `bind_authorized_automation` | `intent_id`, `automation_id`, `reconciliation_reference`; liga el resultado real de aquella creación. |
| `activation_not_created` | `intent_id`, `confirmed_not_created=true`, `reconciliation_reference`; solo tras probar que no se creó. |
| `dispatch_intent` | `automation_id`, `task_key`, `event_id`, `owner_turn_id`; exige fecha y miembros exactos, y persiste `running` antes del envío. |
| `acknowledge` | `automation_id`, `task_key`, `owner_turn_id`, `message_id`, `worker_turn_id`; registra el acuse real. |
| `complete` | Mismos tres primeros campos de acuse, `receipt_file`, `receipt_sha256`; conserva y liga un recibo, sin aprobar sus datos. |
| `retry` | Mismos tres primeros campos, `confirmed_stopped_or_not_sent=true`, `reconciliation_reference`, `reason` y, para `announced`, `announced_date`; usa el cálculo existente. |
| `uncertain` | Mismos tres primeros campos y `reconciliation_reference`; bloquea la decisión y conserva el escritor hasta probar resultado o parada. |

El recibo operativo es un JSON privado físico dentro del workspace, con
`task_key`, `intent_id` y `receipt_id`. Puede adjuntar referencias a recibos
nativos y a sus verificaciones existentes. La clave y la intención deben
coincidir; el hash debe corresponder a todos sus bytes. No se cambia la fecha
ni el hash del original para asociarlo al registro. La incorporación a un
periodo nuevo sigue necesitando sus candidatos y comprobaciones reales.

Los contadores de `retry` se comparten por lote `cadence:period`: cambiar de
producto no los reinicia. Máximo dos reprogramaciones; después queda bloqueado
para decisión. Un envío incierto no es reintentable hasta probar que terminó
o que no se envió. Conservar los resultados independientes que ya terminaron.

### Caída o bloqueo huérfano

Conservar `.source-update.lock`, `state.json` y `.state.pending`, si existe.
Comprobar proceso, dueño, mensajes/turnos y recibos antes de retirar un bloqueo
huérfano. Un PID ausente, una edad o un timeout no prueban que un envío externo
no haya ocurrido. Preservar el archivo anterior y reconciliar bajo escritor
único. Nunca promover `.state.pending` a autoridad sin cotejarlo contra el
último JSON completo y los resultados reales. Si falta evidencia, mantener el
bloqueo y devolver acción, destino, motivo y resultado incierto.

### Validación y conservación

Las pruebas operativas usan autorizaciones y releases **sintéticos**. Cubren
fechas, festivos, 2027 bloqueado, corte México, clave por periodo, identidad
del evento combinado tras cierres parciales, exclusión mutua, operaciones
repetidas, recibo ajeno o alterado, creación/envío inciertos y dos reintentos
compartidos. No prueban disponibilidad de fuentes ni ejecutan una automatización.

```bash
python -m pytest tests/test_source_update_coordinator_state.py tests/test_source_update_calendar.py tests/test_source_update_calendar_adversarial.py -q
```

Cierre documental: conservar el script y sus regresiones como contrato de
operación; conservar esta guía como referencia única del estado/recuperación;
actualizar solo su enlace en `REPO_MAP.md`. Los JSON privados y sus recibos se
conservan fuera del diff y no se suben al repositorio. No hay retiros ni cambios
de originales, Gold, sitio, aprobaciones, Noticias o workflows.

## Pendientes

- Integrar esta preparación sobre `master` tras el PR174 y completar CI y
  revisión Codex del head final, coordinando el merge con el hilo principal.
- Recibir la autorización específica para activar la única tarea. Esta guía y
  el estado preparado no constituyen esa autorización.
- Recibir Viva 3T26 y la respuesta Aerocivil por sus responsables existentes.
  El mes nuevo exige evidencia propia; septiembre no certifica octubre.
- Verificar el calendario bancario 2027 antes de fechar ese año.
