# Cuotas y preparación de hosting del chat

Continuación del 4 de octubre de 2026 después de integrar el
[PR #81](https://github.com/salvamalfa/aeromexico-tracker/pull/81).
El dueño pidió continuar inmediatamente y anticipó las aprobaciones para
terminar la implementación. La programación pendiente quedó desactivada.

## Cambio entregado

El backend aplica valores predeterminados de **200.000 tokens diarios por
usuario y globales** y reserva al menos **150.000 por turno OpenAI**, conservando
estimaciones dinámicas mayores. Suma entrada y salida y mantiene las cuotas
monetarias a tarifas normales. El proveedor simulado conserva su reserva
habitual para permitir la demo sin consumo de OpenAI.

El nuevo CLI `import-usage` incorpora contadores privados de evaluaciones u
otros procesos en la misma base del chat. Su modo predeterminado valida el
archivo y muestra la propuesta sin abrir ni modificar SQLite; `--apply` valida
conflictos y escribe atómicamente. El esquema admite solo identidad contable,
propietario, fecha UTC y contadores/costo o reservas. Rechaza datos crudos,
fechas futuras, duplicados, booleanos como tokens y valores fuera de rango.

Los registros idénticos son idempotentes; los conocidos no se reescriben.
La validación transaccional también considera las sumas existentes por día y
las reservas de todos los días para evitar desbordamientos de SQLite o de costo.
Conciliar un desconocido reemplaza su reserva una vez. El uso conocido se suma
a las cuotas de su día y los desconocidos bloquean admisiones globalmente,
incluso después del cambio de día o la retención del historial. Un desconocido
también pausa turnos que estuvieran en cola antes de la importación, conservando
su identidad hasta conciliarse. Importar no descubre Usage automáticamente:
los procesos externos deben compartir o
importar su contabilidad antes de reabrir el piloto.

Para un único usuario de 09:00 a 17:00 entre semana, con actividad intermitente
y tolerancia al arranque, se preparó la
[evaluación de Railway Free/Hobby y VPS](../chat/hosting-options.md).
El grupo bloqueado `chat-runtime` contiene seis dependencias directas, sin
dependencias del pipeline, analítica o navegador. No cambia versiones del lock.
CI instala el perfil en un entorno aislado y prueba snapshot, contraseña,
worker, SSE y una comparación simulada con datos publicados.

## Verificación

- Suite local de chat y límites de módulos: **142 pruebas aprobadas**, incluidas
  cuotas, importación, almacenamiento, API, worker, enteros grandes y rechazo
  de lotes sin escritura parcial.
- Perfil aislado instalado: 25 paquetes y aproximadamente 40 MiB; smoke real
  de autenticación, worker y `compare_metrics` aprobado sin llamadas OpenAI.
  Máximo local de memoria durante ese smoke: 122,9 MiB. No mide capacidad de
  turnos reales ni asegura los límites de Railway Free.
- Ruff y comprobación de diff sin errores. La entrega requiere `test` y `web`
  del último commit y seguimiento de las revisiones según AGENTS.md.
- Las dos observaciones de revisión tienen correcciones y regresiones:
  configuración monetaria incompatible rechazada antes de crear proveedor o
  SQLite, y sumas del lote/estado existente validadas antes de confirmar.
  La verificación posterior de API, cuotas, importación, almacenamiento, worker
  y límites aprobó **67 pruebas**, además del smoke del perfil aislado.

## Límites pendientes

La lectura acotada del turno fallido existente sigue indicando `failed` y
sesión `idle`, sin contadores completos. El dueño aportó contadores diarios
por modelo; el expediente distingue esos agregados del uso por intento, sin
atribuir cero al fallo. No se repitieron casos ni se reanudó una corrida con
uso individual desconocido; el tope acumulado de US$10 permanece vigente.

El acceso al dueño ya está preparado fuera de Git. No se creó una cuenta
Railway, no se contrataron servicios ni se modificó DNS/hosting. El chat público
sigue apagado hasta completar calidad, revisión semántica, política de retención
y prueba HTTPS desde Pages. Ningún dato, catálogo o aprobación del Analysis
Agent se modificó.
