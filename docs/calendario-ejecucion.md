# Preparación operativa del calendario único

## Resumen

**Preparado para activación**, con estado privado y disparo puntual calculado.
No hay una automatización operativa. El dueño autorizó condicionalmente activar
el único calendario después de comprobar Viva, los datos requeridos y el
despacho nativo. No se pide otra vez esa decisión: se comprueban sus condiciones.
La preparación inicial de PR175 ya está integrada y tiene CI posterior aprobada.
Las reglas y las dependencias de fuentes siguen en el
[catálogo canónico](catalogo-fuentes-calendario.md).

El [registro operativo](../scripts/source_update_coordinator.py) añade solo la
persistencia que faltaba entre turnos. Reutiliza `calendar`, `plan`, `retry` y
el bloqueo exclusivo del recolector. No adquiere fuentes, envía mensajes,
crea automatizaciones ni publica. El agente coordinador invoca realmente los
subagentes con el [mapa de despacho](../scripts/source_update_dispatch.py);
los candidatos y `global_readiness` conservan
sus controles y su límite `ready_for_automatic_execution=false`.

## Qué cambia para ti

El próximo mensual conocido es **17 de noviembre de 2026**, para `2026M10`.
El siguiente es **15 de diciembre**, para `2026M11`. Ambos se calculan con
los [festivos bancarios verificados](../config/source_update_holidays.json).
La mañana se representa a las 08:00 en `America/Mexico_City`, con
`timing_mode=flexible_schedule`: no es una hora de publicación de fuente.
No se genera una regla diaria o semanal ni se extrapola 2027.

Viva 3T26 está incorporado y verificado en [PR177](https://github.com/salvamalfa/aeromexico-tracker/pull/177),
con publicación documental del 28/oct. Falta trasladar y cotejar sus recibos
físicos en el estado canónico, junto con los de Aeroméxico y Volaris; esa
vinculación no equivale a repetir la ingesta ni a confirmar la ronda conjunta.
Hasta entonces, la fecha propuesta es **30/oct**, condicionada a que el último
día confirmado entre los tres siga siendo el 28/oct. La fecha depende de la publicación real,
no del día en que termine la revisión. `refresh_reports` reutiliza el cálculo
de dos hábiles y agrupa a siete días naturales o menos. Una fecha ya fijada
o una ronda empezada no se cambia silenciosamente. El 30/oct dista 18 días del
17/nov, por lo que serían dos eventos dentro del mismo calendario.

Aerocivil queda **utilizable con supuestos operacionales documentados** tras
verificar sus datos reales; la respuesta oficial ya no bloquea por sí sola.
No se cambia el producto requerido, los códigos originales ni la confirmación
oficial pendiente. Datos faltantes o disponibilidad no acreditada siguen
bloqueando el resultado correspondiente. Si la respuesta contradice los
supuestos, se versionan los cálculos afectados. No se repite la consulta enviada.

Noticias es una tarea mensual del mismo plan, con búsqueda nativa y lectura
de fuentes. RSS/GDELT permanecen opcionales. El registro selecciona por defecto
el núcleo requerido de la política vigente y Noticias. Enumera los demás
productos sin programarlos. Si se usa contexto adicional, la receta y el
control global existentes deben validar ese producto y sus dependencias.

| Evento del calendario único | Periodo | Estado de la fecha |
|---|---|---|
| Finanzas, macro/mercado y alcance colombiano trimestral | 3T26 | 30/oct propuesto si se verifica el último financiero del 28/oct; aún no activado |
| Datos mensuales y Noticias, juntos | Octubre 2026 | 17/nov calculado con festivos verificados; aún no activado |
| Datos mensuales y Noticias, juntos | Noviembre 2026 | 15/dic calculado con festivos verificados; aún no activado |

Una publicación es un hecho de la fuente, distinto del evento de ejecución.
Un financiero primario confirmado permite avisar y preparar su paquete
independiente con el alcance autorizado. Las demás novedades se descubren en
la ronda consolidada; no se inventa un día 13 ni se instala un sondeo por fuente.
Los periodos propios y rezagos de AFAC/BTS se conservan.

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
`fsync`; en POSIX también sincroniza el directorio. En Windows la garantía
local cubre caída de proceso; la recuperación de host exige el último respaldo
privado verificado. Una intención guarda el dueño antes del envío externo.
Los bloqueos persistentes `active_tasks` y `active_task` conservan las
intenciones y el dueño entre comandos, incluso si el proceso desaparece.
Varios workers aislados del mismo dueño pueden preparar candidatos en paralelo;
otro dueño o un escritor serial no entra hasta reconciliar los anteriores.
Las rutas de candidatos anteriores siguen reservadas. La consolidación del
registro común tiene un solo escritor; nunca se comparte Bronze entre workers.

`record_conditional_authorization` conserva la decisión recibida y sus
condiciones sin poner `activation_authorized=true` ni asignar una automatización.
Las condiciones registradas como verificadas después son afirmaciones del
operador con referencias reales, no pruebas fabricadas por rellenar booleanos.

### Fuente, skill y subagente responsable

El mapa ejecutable enumera los **43 productos del catálogo y la tarea editorial**.
Cada producto declara fuente, skill exacta/SHA, cadencia de publicación del
proveedor, disparador, fecha oficial conocida o nula, procedimiento/limitación,
agente lógico y destinos. `handoff_eligible` significa que puede asignarse a una
skill; no acredita que exista un adaptador universal o datos completos.

| Familia y fuentes/productos | Skill exacta |
|---|---|
| Empresas: IR Aeroméxico/Volaris/Viva, SEC/BMV y comparables | [airline-update-corporate](../.agents/skills/airline-update-corporate/SKILL.md) |
| Tráfico: AFAC por empresa/aeropuerto/país/marginal y BTS México–EEUU | [airline-update-traffic](../.agents/skills/airline-update-traffic/SKILL.md) |
| Aeropuertos: GAP, ASUR, OMA, AICM y AIFA | [airline-update-airports](../.agents/skills/airline-update-airports/SKILL.md) |
| Macro/mercado: Banxico, H.10 separado, EIA y cotizaciones | [airline-update-macro-market](../.agents/skills/airline-update-macro-market/SKILL.md) |
| Rutas: Aerocivil, ANAC, CAA, Aena y documentos de rutas | [airline-update-routes](../.agents/skills/airline-update-routes/SKILL.md) |
| Contexto: OurAirports, FAA IASA y diccionario | [airline-update-context](../.agents/skills/airline-update-context/SKILL.md) |
| Noticias: búsqueda/lectura nativa y descubrimiento RSS/GDELT opcional | [airline-update-news](../.agents/skills/airline-update-news/SKILL.md) |
| Internos: perfiles, fuentes curadas y cálculos derivados existentes | [airline-update-internal](../.agents/skills/airline-update-internal/SKILL.md) |

El nombre lógico se liga a `cadence:period:product` y al evento. El ID real del
subagente queda nulo hasta recibirlo de la herramienta. El
[coordinador](../.agents/skills/airline-update-coordinator/SKILL.md) registra la
intención y luego invoca `jobs[].native_call` con herramientas nativas reales.
El CLI de despacho solo materializa esos argumentos; no puede fingir un envío.
Si el host no tiene capacidad nativa, el coordinador devuelve un bloqueo.

Cada worker lee y verifica la skill, ejecuta plan/receta y su adquisición o
retención autorizada, conserva evidencia/originales en `evidence/` y
`data/bronze/`, procesa `data/silver/`, construye sus salidas y linaje en
`data/gold/`, y guarda recibos en `receipts/`. Esas son rutas de candidato:
su existencia no demuestra que las capas se hayan producido. El adaptador
dedicado determina los pasos reales. Noticias conserva evidencia editorial y
su candidato propio; internos/derivados pueden reutilizar padres sin Bronze nuevo.

Si falla la vía programática, el agente usa navegación oficial normal mediante
el navegador cloud/local autorizado disponible, o devuelve el handoff al
coordinador si no dispone de él. Los originales se transfieren por Library y
se cotejan en el consumidor. No se amplían permisos ni se eluden accesos,
TLS, CAPTCHA o autenticación; SEC, Aena y reconstrucciones mantienen sus contratos.
El ensayo en seco no demuestra ese fallback ni disponibilidad de una fuente.

El coordinador reúne recibos y resultados independientes y ejecuta los
comprobadores existentes de conteos, periodo, cobertura, revisiones,
Bronze/Silver/Gold y linaje, además de dependencias/readiness global. No vuelve
a transformar todo con un rebuild universal ni publica automáticamente.
El reparto respeta las ranuras reales del host y las dependencias de los
productos derivados. La consolidación implementada es de recibos y candidatos
verificados; no hay una copia automática de todos los Gold candidatos al
dataset activo. Su incorporación y publicación conservan los controles existentes.

Preparar una sola vez con un JSON privado que declare `as_of`, `start`,
`months`, `quarter` y `releases`. Los releases tienen la forma del CLI
`calendar`; sus confirmaciones son revisiones explícitas de documentos reales,
no una inferencia del nombre de archivo. Conservar la referencia de revisión
en ese JSON. La preparación no vuelve a consultar las fuentes.
El estado retiene esa solicitud íntegra y sus releases. El monitor puede
aportar solo Viva: los registros nuevos se añaden por contenido, sin sustituir
ni renovar los días, hashes o referencias anteriores.

```bash
python -m scripts.source_update_coordinator --workspace tmp/source-updates/calendar-coordinator --prepare <solicitud-privada.json> --now 2026-10-29T04:00:00Z
python -m scripts.source_update_coordinator --workspace tmp/source-updates/calendar-coordinator
python -m scripts.source_update_dispatch --source-map
python -m scripts.source_update_dispatch --state <estado-canónico-absoluto.json> --event-id <evento-exacto> --as-of <corte-real-con-zona> --dry-run
```

El primer comando escribe el plan privado; repetir la misma solicitud conserva
los bytes. Otra solicitud no puede sustituirlo ni reiniciar contadores. El
segundo solo lee y emite `next_trigger.payload`. El payload contiene título,
prompt, `schedule` VEVENT sin RRULE, zona y modo flexible. **Mostrarlo no lo
crea ni autoriza ejecutarlo.** Si está vencido o hay un escritor sin resolver,
el payload es nulo y exige reconciliación. No se mueve a mañana por defecto.

### Activación futura y recuperación de su creación

La capacidad nativa conocida crea tareas habilitadas y no admite crearlas
apagadas. Por eso no se invoca durante esta preparación. Una vez verificadas las condiciones de la autorización
ya recibida, el coordinador realiza estos pasos una sola vez:

1. Comprobar el estado canónico y las tareas nativas existentes. Conservar la
   referencia exacta de la autorización condicional. Cotejar los recibos de Viva y sus fechas,
   los datos requeridos con replay/global de la cadencia real y la capacidad nativa
   de despacho. Aerocivil requiere su prueba operacional positiva, no respuesta
   oficial; las fuentes faltantes no pasan por tener supuestos. Registrar
   `activation_intent` con referencias a esos resultados antes de
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
| `record_conditional_authorization` | `authorization_reference`, `operational_policy_id`; conserva la decisión y condiciones; no activa ni crea una tarea. |
| `refresh_reports` | `releases`; confirma fechas antes de activar o despachar, sin certificar cifras. |
| `activation_intent` | `activation_authorized=true`, referencia de autorización y de condiciones verificadas; guarda intención incierta, sin llamar a la herramienta. Con autorización condicional exige booleanos exactos de Viva, datos requeridos, despacho nativo y coordinador único. |
| `bind_authorized_automation` | `intent_id`, `automation_id`, `reconciliation_reference`; liga el resultado real de aquella creación. |
| `activation_not_created` | `intent_id`, `confirmed_not_created=true`, `reconciliation_reference`; solo tras probar que no se creó. |
| `dispatch_intent` | `automation_id`, `task_key`, `event_id` y dueño; exige fecha y miembros exactos y persiste `running` antes del envío. Para paralelo: `execution_mode=isolated_skill_worker` y `worker_workspace` disjunto. |
| `acknowledge` | Tarea/dueño y IDs reales de mensaje/turno, o `native_task_name` con `native_response_sha256` si el host solo devuelve ese identificador; los IDs no expuestos permanecen nulos. |
| `complete` | Mismos tres primeros campos de acuse, `receipt_file`, `receipt_sha256`; conserva y liga un recibo, sin aprobar sus datos. |
| `retry` | Mismos tres primeros campos, `confirmed_stopped_or_not_sent=true`, `reconciliation_reference`, `reason` y, para `announced`, `announced_date`; usa el cálculo existente. |
| `uncertain` | Mismos tres primeros campos y `reconciliation_reference`; bloquea la decisión y conserva el escritor hasta probar resultado o parada. |

El recibo operativo es un JSON privado físico dentro del workspace, con
`task_key`, `intent_id` y `receipt_id`. Puede adjuntar referencias a recibos
nativos y a sus verificaciones existentes. La clave y la intención deben
coincidir; el hash debe corresponder a todos sus bytes. No se cambia la fecha
ni el hash del original para asociarlo al registro. La incorporación a un
periodo nuevo sigue necesitando sus candidatos y comprobaciones reales.

El coordinador conserva el resultado del worker intacto y crea un wrapper
local ligado a la intención real y a sus rutas/hashes. Un `receipt_id` local
se rotula como tal, no como ID nativo. El dueño puede ser `owner_turn_id`
observado o `owner_lease_id=local_lease:<token-local>`; en ese último caso no se
inventa un turno del servicio. El acuse nunca equivale a finalización.

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

- Completar la entrega de la política operacional/despacho con revisión y CI
  del head final y serializar su integración con el hilo principal.
- Vincular los recibos verificados de Viva 3T26 al estado y comprobar los datos
  requeridos de la ronda con la política vigente;
  entonces el coordinador puede ejecutar la autorización condicional ya recibida,
  con una sola automatización. Este hilo de preparación no la crea.
- Conservar Aerocivil como seguimiento de confirmación oficial, sin bloquear
  por esa espera; corregir los cálculos si la respuesta contradice los supuestos.
  El mes nuevo exige evidencia propia; septiembre no certifica octubre.
- Verificar el calendario bancario 2027 antes de fechar ese año.
