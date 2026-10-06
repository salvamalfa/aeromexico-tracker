# Verificación de Data Sharing y cobertura

**Consulta de fuentes: 4 de octubre de 2026.** Esta nota distingue la oferta
pública de OpenAI de lo que podemos confirmar en este repositorio. No se
consultó el panel privado de la organización ni se hicieron llamadas de
inferencia para esta verificación.

## Lo que dice la documentación pública

OpenAI indica que por defecto no usa entradas ni salidas de clientes API para
mejorar sus modelos. Compartir tráfico requiere que una persona propietaria de
la organización active explícitamente Data Sharing. La elegibilidad para tokens
complementarios también se confirma en esa página: debe aparecer el texto de
elegibilidad y, después de activar el uso compartido, el texto de inscripción.
El propietario declaró que la organización está inscrita en Data Sharing y
confirmó nivel de uso 1 en Platform Limits a las 20:12 UTC del 4 de octubre de
2026. Es una declaración del propietario, no una lectura independiente del
panel. La inscripción no demuestra por sí sola que los créditos se hayan
aplicado a estos turnos.

La oferta publicada agrupa cuotas diarias por modelos: para niveles de uso 1–2,
250 mil tokens en el grupo principal y 2.5 millones en el grupo mini; para los
niveles 3–5, los topes publicados son 1 millón y 10 millones, respectivamente.
Entrada y salida cuentan. Las cuotas se comparten por grupo, no por aplicación.
La página dice que evals, uso de herramientas, entrenamiento y modelos
afinados quedan fuera. Si una solicitud individual excede el saldo diario, se
cobra completa a tarifa normal; el contador reinicia a las 00:00 UTC. No
asumimos que esta integración con Agents API y funciones propias califique para
el incentivo: la exclusión de “tool use” está publicada, pero su alcance exacto
para este flujo no queda definido allí. La oferta también indica que OpenAI
puede terminar el programa con aviso de 30 días; no publica una fecha fija de
expiración.

Los expedientes de evaluación incluyen `gpt-6-luna`, `gpt-6.1-sol` y
`gpt-6-astra`. La oferta de incentivo lista exactamente `gpt-6-astra`,
`gpt-6-sol` y `gpt-6-luna` en el grupo principal; no lista `gpt-6.1-sol`, por
lo que la similitud de nombre no acredita elegibilidad de Sol 6.1. Luna y Astra
sí coinciden con IDs listados. Tier 1 corresponde a los topes públicos de
250 mil / 2.5 millones. No se consultó la cuenta mediante API ni se verificó
que se hayan aplicado créditos a tráfico de Agents con herramientas.

La página propone verificar los créditos comparando Usage (entrada y salida,
agrupado por service tier) con Costs: la categoría debe aparecer como “data
sharing incentive tier” en Usage y no como costo en Costs. Hasta observar esa
evidencia de la cuenta, el costo del proveedor y la factura permanecen sujetos
a los cargos normales. Los precios públicos estándar consultados son por
millón de tokens: Luna $0.10 entrada / $0.50 salida, Sol 6.1 $2 / $10 y Astra
$10 / $50. Los cálculos locales con esos precios son estimaciones de control,
no una factura ni garantía de límite de gasto.

## Qué miden los reportes locales

El adaptador registra los totales `input_tokens` y `output_tokens` que recibe
en el uso terminal agregado del turno. El reporte marca `cached_tokens` como
`unknown`; el esquema de resultado no tiene campos para `cached_tokens` ni
`reasoning_tokens`, y el parser solo conserva los dos totales de entrada y
salida. Aunque el proveedor exponga detalles adicionales, este adaptador no los
extrae ni persiste en el reporte de ejecución. Sí existen reconciliaciones
privadas posteriores para cinco turnos raíz únicos de `gpt-6-luna` con uso
terminal confirmado y totales consistentes. Sumados una sola vez por turno,
registran 367,346 tokens de entrada, 4,945 de salida, 294,173 en caché y 2,943
de razonamiento. Cada valor de caché es menor o igual a su entrada y cada valor
de razonamiento es menor o igual a su salida; la suma de entrada y salida
coincide con el total reportado. Cuando una reconciliación repite el mismo uso
en los objetos de turno y sesión, se cuenta una sola vez. Este denominador de
cinco turnos es solo el subconjunto reconciliado con detalle válido, no el
denominador completo de la evaluación. No permite imputar valores a los demás
turnos ni inferir estadísticas de `gpt-6.1-sol`. Un campo ausente o `unknown`
en reportes sin reconciliar no equivale a cero ni prueba que el proveedor no
los haya contado.

El total de entrada del turno no es un conteo de la pregunta visible: el
adaptador suministra instrucciones de sistema, historial/contexto y esquemas
de herramientas además del mensaje del caso; las herramientas también pueden
producir resultados dentro del turno. La fuente local conserva el total que
reporta el proveedor, pero no una descomposición tokenizada por mensaje,
herramienta o iteración. No hay base para asignar una cantidad fija de
“prompt interno” (por ejemplo, 20 mil tokens). La reserva de 140 mil tokens de
entrada por caso usada en el plan de evaluación es un supuesto preventivo de
capacidad, no una medición del prompt ni del uso real.

OpenAI documenta el cruce de cuota por solicitud, pero no aclara en esta oferta
si un turno Agents con varias iteraciones de modelo y herramientas se considera
una solicitud completa o varias para el contador y el cargo. Tampoco la
documentación local demuestra que el total agregado de turno coincida con la
unidad de facturación del proveedor. Ese punto requiere respuesta de soporte o
reconciliación con Usage y Costs de la cuenta.

## Verificación propuesta, aún no ejecutada

Prueba futura propuesta, aún no autorizada ni ejecutada: usar el mismo proyecto
inscrito, sin otras llamadas de chat o benchmark durante la ventana, y solo
después de una decisión separada del dueño y autorización explícita para la
prueba. Si se aprueba, hacer dos o tres preguntas nuevas, sencillas y de solo
lectura a `gpt-6-luna` en días UTC separados; no reutilizar preguntas de
holdout intentadas. Presupuestar hasta US$0,10 de costo normal acumulado,
separado de cualquier supuesto de incentivo. El piso metodológico de reserva
Luna de la propuesta revisable es 170 mil tokens; con 200 mil operativos y un
consumo ilustrativo de 40 mil, solo cabe una solicitud típica por día. No
reactivar el servicio con la reserva configurada de 150 mil basándose en el
plan anterior. Antes de cada solicitud, verificar que consumo medido, reservas
pendientes y nueva reserva quepan en el límite operativo de 200 mil. Los 50 mil
de diferencia entre la cuota principal Tier 1 de 250 mil y el límite operativo
de 200 mil no son un saldo seguro ni una reserva adicional. Estos son límites
preventivos, no una garantía de facturación ni un máximo contractual. Al día
siguiente, leer Usage y Costs para el intervalo/proyecto: entrada, salida,
service tier y cargos. Incentivo positivo solo si la categoría aparece allí;
tarifa/costo normal si no aparece; estado ambiguo sigue siendo desconocido,
nunca cero. No reintentar llamadas ni reutilizar sesiones. Preguntar a soporte
si sigue sin aclararse el tratamiento de Agents API, tool calls, caché y turnos
con errores.

## Fuentes

- [OpenAI: compartir feedback, evaluaciones y datos API](https://help.openai.com/en/articles/10306912-sharing-feedback-evaluation-and-fine-tuning-data-and-api-inputs-and-outputs-with-openai) — opt-in, elegibilidad, modelos, cuotas, tools y verificación en Usage/Costs.
- [OpenAI API: controles de datos](https://developers.openai.com/api/docs/guides/your-data) — tratamiento de datos y controles API.
- [OpenAI API: precios](https://developers.openai.com/api/docs/pricing) — tarifas estándar por modelo.
- Implementación inspeccionada: [adaptador Agents API](../../src/conversational_analytics/providers/openai.py), [esquema de resultado](../../src/conversational_analytics/providers/base.py), [parser de uso](../../src/conversational_analytics/providers/_openai_helpers.py) y [reportes live](../../src/conversational_analytics/evaluation_live.py).
