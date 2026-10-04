# Incentivo por compartir datos de API

**Revisión: 4 de octubre de 2026.** Esta guía contempla la oferta de 250 mil /
2.5 millones de tokens diarios. La cobertura de esta integración requiere
comprobación separada del saldo bonificado. No modifica ajustes de cuenta.

## Cuotas y modelos

OpenAI cuenta tokens de entrada **y** salida. La oferta confirmada agrupa los
modelos así para los niveles 1–2:

| Grupo | Cuota diaria compartida | IDs usados/relevantes |
| --- | ---: | --- |
| Principal | 250,000 | `gpt-6-luna`, `gpt-6-astra`; la página también lista `gpt-6-sol` |
| Mini/nano | 2,500,000 | No hay candidato de ese grupo en el experimento actual |

La lista pública contiene el ID exacto `gpt-6-sol`, pero no `gpt-6.1-sol`; no
inferir cobertura de otro ID por similitud. Consulta la [lista vigente de
modelos](https://help.openai.com/en/articles/10306912-sharing-feedback-evaluation-and-fine-tuning-data-and-api-inputs-and-outputs-with-openai)
antes de usar candidatos nuevos.

Los cupos se comparten entre los modelos de cada grupo y el uso elegible de los
proyectos habilitados en la organización; no son un saldo separado por
aplicación. El artículo describe cuota diaria de tokens, no un aumento de RPM o
TPM. El contador reinicia a las **00:00 UTC**, que corresponde a las **18:00 de
Ciudad de México**. Si una solicitud rebasa el saldo del cupo, se cobra entera
a tarifa normal. El artículo no publica fecha de expiración y dice que OpenAI
puede terminar el programa con aviso de 30 días.

## Agents API, tools y Evals

La página de OpenAI excluye “tool use” del incentivo de tokens. Este proyecto
usa Agents API con herramientas `function` de la aplicación, y el harness live
custom reutiliza esa misma integración. La documentación pública no precisa si
la exclusión cubre estas funciones, solo herramientas alojadas por OpenAI, o
todas las solicitudes de Agents API. Por eso, la bonificación de esta
integración **no está confirmada**: presupuestar los turnos con tools a tarifa
normal hasta que Usage Dashboard refleje el crédito. No afirmar que todo el
tráfico ya agotó la cuota gratis ni que definitivamente es inelegible.

El harness de este repo no usa provider Evals API: hace llamadas normales por
el adapter Agents API. OpenAI trata los datos compartidos con Evals por
separado y dice que procesa sin costo hasta siete runs por semana; la misma
página excluye evals del cupo diario de tokens. Ese beneficio no vuelve gratis
las llamadas del harness custom ni las del producto.

## Control de costo

El contador operativo debe sumar entrada y salida, incluida la entrada en
caché, de chat y evaluaciones. Debe abarcar todos los proyectos consumidores
de la organización si se agregan otros, y registrar por separado consumo total,
tráfico elegible y crédito efectivamente aplicado. Las lecturas de Platform y
los expedientes locales permiten reconciliar el uso sin publicar información
de cuenta. Una consulta del saldo gratuito no sustituye el registro total.

El almacenamiento del chat conserva reservas con uso desconocido a través de
los cambios de día UTC. Si se borra un turno terminal o vence su conversación,
transfiere la reserva a un registro contable independiente del contenido. Ese
registro no contiene prompts, respuestas, contexto ni identificadores del
proveedor. Cuando se reconcilia uso confirmado, lo contabiliza una vez y libera
la reserva, incluso si el turno ya no existe. Antes de borrar el contenido o
solicitar el borrado remoto, reconcilia el turno del proveedor cuando sea
posible. No hay una consulta automática posterior para resolver tombstones; sin
evidencia confirmada, la reserva permanece retenida y no se reinicia por UTC ni
por retención. Si falla el borrado remoto, la solicitud queda en una cola
durable de reintentos. El uso confirmado se contabiliza en la fecha UTC de
confirmación, como estimación operativa; esa fecha puede diferir de la fecha de
solicitud o de la facturación del proveedor.

Este mecanismo conserva la contabilidad; no adopta la propuesta de 200,000
tokens diarios ni la reserva estimada de 150,000 tokens por turno/caso. Los
límites y valores predeterminados actuales no cambian por esta documentación.

**Propuesta para el piloto, aún no adoptada:** presupuesto de 200,000 tokens
por día tanto para el owner como para el total global; usar **150,000 tokens
como reserva estimada por turno/caso**, con margen sobre los turnos de más de
100 mil tokens observados en la integración. Quedan 50 mil de margen respecto
al cupo principal. Esta reserva no es un máximo duro de API; debe ajustarse con
el historial y las mediciones. El backend del chat aún no aplica esta política;
el evaluador usa un piso de reserva de 140 mil de entrada y 10 mil de salida.
El control propuesto rechaza un turno cuando consumo organizacional más
reservas pendientes más la nueva reserva superen el límite diario, incluso si
el presupuesto monetario todavía permite pagarlo. Con uso desconocido, pausa
y reconcilia. Al cambiar de día, conserva la reserva de turnos en curso hasta
resolver a qué ventana corresponde el uso. La comparación ya autorizada usa
su presupuesto monetario separado; esta propuesta es para el piloto.

La autorización ya vigente de hasta **US$10 para la comparación pagada** se
mantiene bajo las tarifas API normales, sin depender del incentivo y sin pedir
una aprobación nueva. Mantener `CHAT_INPUT_COST_PER_MILLION`,
`CHAT_OUTPUT_COST_PER_MILLION` y presupuestos basados en precios normales; son
estimaciones y controles operativos, no un techo contractual de factura.

## Referencias oficiales

- OpenAI Help Center, [Sharing feedback, evaluation and fine-tuning data, and API inputs and outputs with OpenAI](https://help.openai.com/en/articles/10306912-sharing-feedback-evaluation-and-fine-tuning-data-and-api-inputs-and-outputs-with-openai) (actualizada el 23 de septiembre de 2026): opt-in, cuotas, modelos, tool use, Evals, reinicio y overage.
- OpenAI API, [Agents](https://developers.openai.com/api/docs/guides/agents) y [Function calling](https://developers.openai.com/api/docs/guides/function-calling): tools de función y flujo de ejecución.
- Implementación: [adapter Agents API](../../src/conversational_analytics/providers/openai.py), [harness live custom](../../src/conversational_analytics/evaluation_live.py), [presupuesto de evaluaciones](evaluaciones-presupuesto.md).
