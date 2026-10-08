# Evaluaciones y presupuesto del chat

## Conjunto holdout y pruebas offline

`tests/fixtures/chat_evals/holdout.json` contiene 40 preguntas en español e
inglés, aparte de `config/chat/question_examples.yaml`. Cubre entidades y alias,
ambigüedad de pasajero de compañía frente a AFAC, métricas, trimestre no
publicado, desgloses por ruta, cambios relativos frente a puntos porcentuales,
ponderación, contexto por tarjeta, causalidad, faltantes y prompts que intentan
obtener datos privados. Doce consultas soportadas guardan valores exactos,
incluida una fila `missing` que nunca se convierte en cero, del snapshot público
y planes estructurados esperados.
El fixture fija `data_version` y `semantic_version`; el auditor falla cuando
cualquiera cambia hasta regenerar y revisar los valores esperados.

La auditoría offline ejecuta esos doce planes fijos con la herramienta
allowlisted contra `site/`, compara valores y exige referencias HTTPS. Registra
las versiones de datos y semántica. No llama a modelos, no fabrica respuestas
en lenguaje natural y no califica los otros 28 casos: ambigüedad, seguridad y
calidad de respuesta aparecen como pendientes live, con denominador de calidad
cero. Para reproducirla:

```bash
uv run python -m src.conversational_analytics.evaluation --dry-run
uv run python -m src.conversational_analytics.evaluation --audit-snapshot
uv run pytest -q tests/test_chat_evaluation.py
uv run python -m src.conversational_analytics.evaluation --dry-run \
  --models gpt-6-luna gpt-6.1-sol gpt-6-astra \
  --model-price gpt-6-luna=0.10:0.50 \
  --model-price gpt-6.1-sol=2:10 \
  --model-price gpt-6-astra=10:50
```

El dry-run no hace llamadas ni escribe archivos y no elige modelo. La shortlist
que se evaluó fue `gpt-6-luna`, `gpt-6.1-sol` y `gpt-6-astra`. Tarifas
estándar de contexto corto revisadas el 3 oct 2026 (zona horaria del dueño), en
USD por millón de tokens (fuente: [página de tarifas de OpenAI](https://developers.openai.com/api/docs/pricing)):

| Modelo | Entrada | Entrada en caché | Escritura de caché | Salida |
|---|---:|---:|---:|---:|
| `gpt-6-luna` | 0.10 | 0.01 | 0.125 | 0.50 |
| `gpt-6.1-sol` | 2.00 | 0.10 | 2.50 | 10.00 |
| `gpt-6-astra` | 10.00 | 1.00 | 12.50 | 50.00 |

Contexto largo cambia las tarifas; los modelos deben tener acceso confirmado en
la cuenta antes de pedir la prueba. Las cifras son una referencia de plan, no
un quote ni una medición. Por candidato se imprimen preguntas, ventanas de
hasta diez, llamadas planeadas, tokens de entrada/salida aproximados, precios
ingresados y destinos. El CLI acepta el precio sin caché con
`--model-price MODEL=INPUT:OUTPUT` (USD por millón); no aplica una tarifa de un
candidato a los demás. Sin precio registrado el costo queda `null`; la tabla
debe volver a comprobarse el día de una prueba live. Una proyección de tokens
es solo orientativa, no una tarifa por pregunta: una pregunta enviada puede
originar varios turnos del modelo, llamadas de herramientas y contexto
acumulado. Consulta el [reporte de validación con mediciones reales](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/airline-tracker-validacion-real-20261004.md)
para revisar consumo por pregunta; el cálculo suma todos sus turnos, incluidos
los que terminan con error, cancelación o sin respuesta útil. Las escrituras de
caché, créditos y otros ajustes de factura pueden ser desconocidos; no se les
atribuye costo cero.

El destino live configurado es `.state/outputs/chat-evaluations/`, dentro de
datos locales ignorados por Git. El dry-run informa esa ruta como destino
hipotético y confirma que no escribe nada.

No se publica una proyección multiplicando un tamaño fijo de pregunta: el
número de turnos y tokens varía entre casos, incluso cuando fallan. El reporte
de la etapa registra el costo estimado a tarifas normales según el uso
recuperado y separa cualquier uso desconocido. El hosting del backend es un
costo aparte, no incluido en los precios por tokens.

## Ejecución live y continuidad

El harness live usa el adaptador de producción y un registro real de
herramientas sobre el snapshot público. La continuidad por fases conserva un
presupuesto acumulado compartido. Cada pregunta crea su propia sesión, y su
consumo totaliza todas las llamadas internas a modelo, no solo la respuesta
final. Esto incluye contexto acumulado, iteraciones de herramientas,
aclaraciones y turnos fallidos o cancelados cuyo uso se recupere.
El SDK deshabilita reintentos automáticos y no se repiten preguntas ya enviadas.
Una respuesta fallida sigue siendo consumo facturable. El comando
offline `--dry-run` planifica sin llamadas; no reproduce las fases live.

La comparación de modelos ya terminó. Su permiso cubrió únicamente las fases
autorizadas hasta un umbral operativo acumulado de US$10, sin reiniciar el saldo
entre fases; esa autorización está cerrada. Para revisar uso y estado, consulta
el reporte de la etapa enlazado arriba. Las evaluaciones nuevas y su
presupuesto se definen en la [fase 2](fase-2-agente-analitico.md). Si el uso de un turno no se confirma, su costo permanece desconocido:
no se vuelve a enviar la pregunta para reconstruirlo ni se presenta un subtotal
conocido como total.

Los reportes live detallados y checkpoints se conservan localmente, fuera de
Git y con permisos privados. Los tokens totales de un turno son desconocidos si
el proveedor no confirma su uso completo. Las métricas del SDK o caché que no
se hayan recuperado también se mantienen como desconocidas. El costo reportado
es una estimación con las tarifas ingresadas, no una factura. La reserva
operativa puede detener casos posteriores, pero no limita los tokens de una
llamada ya iniciada ni garantiza un techo exacto. No se inventan resultados ni
costos faltantes.

Usar el mismo holdout, snapshot, semántica, prompt de sistema, límites y
configuración de herramienta por modelo. No incluir la pregunta y su respuesta
de oro como instrucción al modelo. Revisar outputs sin nombres de modelo antes
de calcular calidad; las rúbricas exactas por caso deben poder reproducirse.
Reportar cobertura por idioma, métrica, ambigüedad y riesgo, además del
resultado global. No promediar casos de aclaración/privacidad como si fueran
consultas numéricas.

## Criterio de decisión y coste

El gate de calidad propuesto es al menos 95% de casos soportados correctos y
cero fallos críticos, especialmente conversión de faltante a cero, cifras sin
referencia, exposición de datos privados, rutas inventadas, confusión de puntos
porcentuales, o ejecución contra otro snapshot. Los casos no soportados deben
declarar la limitación; las ambigüedades materiales deben pedir precisión. Un
modelo que no alcance estos gates no se elige por tener menor costo o menor
latencia.

El [reporte final de validación real](https://github.com/salvamalfa/aeromexico-tracker/blob/747808228103f3d30afc582b42480ce4e5d05713/docs/archivo/chat-mvp/airline-tracker-validacion-real-20261004.md)
es la fuente de mediciones por pregunta y candidato: latencia, resultado de
calidad con denominador, tokens de todos los turnos, errores y costo estimado
a tarifas vigentes. Sus escenarios mensuales deben partir del uso medido y
declarar sus supuestos; el hosting se presenta por separado. Ni la estimación
del harness ni un presupuesto propio prometen un tope de factura. Tras la
comparación, el dueño eligió `gpt-6.1-sol` para el MVP; no se aprobó un gate
de calidad ni se fijó un objetivo mensual. La comparación de Luna y Sol con
distintos esfuerzos, el conjunto de evaluación de negocio y cualquier gate
nuevo se definen en la [fase 2](fase-2-agente-analitico.md). Un incentivo o
una escritura de caché no se contabiliza como crédito confirmado. Ver
[cobertura y propuesta de límites](data-sharing.md)
antes de atribuir costo cero a una llamada.
