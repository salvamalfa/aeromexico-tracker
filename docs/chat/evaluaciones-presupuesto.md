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
de evaluación propuesta es `gpt-6-luna`, `gpt-6.1-sol` y `gpt-6-astra`. Tarifas
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
debe volver a comprobarse el día de una prueba live. La proyección de tokens es
orientativa e incluye contexto/herramientas, respuesta y hasta una consulta de
herramienta por caso soportado. Reintentos, contexto acumulado, más
herramientas, descuentos de caché y formato alteran el uso real.

El destino live configurado es `.state/outputs/chat-evaluations/`, dentro de
datos locales ignorados por Git. El dry-run informa esa ruta como destino
hipotético y confirma que no escribe nada.

Escenario de planificación con el supuesto actual de 1 200 tokens de entrada y
350 de salida **sumados entre todas las llamadas de cada pregunta**, tarifas
estándar cortas sin caché y hosting excluido:

| Modelo | 100 preguntas | 1 000 preguntas | 10 000 preguntas |
|---|---:|---:|---:|
| `gpt-6-luna` | US$0.03 | US$0.30 | US$2.95 |
| `gpt-6.1-sol` | US$0.59 | US$5.90 | US$59.00 |
| `gpt-6-astra` | US$2.95 | US$29.50 | US$295.00 |

Son importes ilustrativos, no sustituyen mediciones de tokens/latencia ni una
cotización. Iteraciones del agente, respuestas largas, historial, caché y
tarifas de contexto largo los pueden cambiar.

## Comparación live futura

El bridge usa el `OpenAIProvider` de producción con un `ToolRegistry` real,
sesión nueva por pregunta y callbacks que capturan plan, filas, referencias e
IDs de proveedor. El modo de sonda admite un candidato; el holdout exige 2–3.
`--run` requiere `--budget-usd` positivo (máximo US$10 de umbral operativo),
`--models`, `--model-price` por candidato y `--opt-in`. El mismo permiso del
experimento puede cubrir una sonda y luego la comparación si la sonda resulta
válida. Se ejecutan como fases separadas para inspeccionar el reporte de la
sonda; cada proceso empieza su contador de presupuesto en cero. No se ejecutó
`--run`.

Comandos previstos solo después de autorización específica:

```bash
uv run python -m src.conversational_analytics.evaluation --run --probe-only \
  --budget-usd 10 --models gpt-6-luna --model-price gpt-6-luna=0.10:0.50 --opt-in
```

Antes de la segunda fase, revisar el reporte de la sonda: detenerse si
`models[0].spent_unknown` es verdadero, si los totales de tokens son nulos o si
`token_totals.usage_complete_case_count` no coincide con `token_totals.turn_count`.
Con uso completo, fijar `REMAINING_USD` a **10 menos
`models[0].estimated_cost_usd`** y continuar solo si es positivo. No reiniciar
el presupuesto a US$10 para la comparación. Mantener los mismos precios al
calcular el saldo; la caché no observada puede alterar la factura.

```bash
uv run python -m src.conversational_analytics.evaluation --run \
  --budget-usd "$REMAINING_USD" --models gpt-6-luna gpt-6.1-sol gpt-6-astra \
  --model-price gpt-6-luna=0.10:0.50 \
  --model-price gpt-6.1-sol=2:10 \
  --model-price gpt-6-astra=10:50 --opt-in
```

La variable de entorno
`OPENAI_API_KEY` está presente en el entorno de esta sesión; su valor no fue
leído ni reportado y acceso a Agents API sigue sin verificar.

Cada corrida escribe un reporte local en `.state/outputs/chat-evaluations/`;
Git ignora ese directorio porque puede contener texto del proveedor. El informe
guarda plan, filas, respuesta, referencias, `call_id`, sesión, turno y eventos.
Los tokens totales de un turno quedan `null` si el proveedor no confirma uso
completo; conteo HTTP interno del SDK y caché quedan `unknown` hasta que el
adaptador los devuelva. Costo es una estimación con precios ingresados, no
factura. Una reserva operativa aproximada frena el siguiente caso cuando no
alcanza el saldo, pero no limita los tokens de una llamada ya iniciada ni
garantiza un tope exacto. La evaluación no inventa los resultados faltantes.

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

El experimento que se presentará al dueño cubre una sonda de una consulta con un
candidato y, si la sonda funciona, las 40 preguntas con tres candidatos (120
casos de modelo). El umbral operativo propuesto es US$10 para el alcance
completo, con reservas conservadoras y pausa entre casos cuando el saldo
estimado no cubra el siguiente. La autorización de ese alcance puede cubrir la
sonda y el holdout sin pedir otra confirmación entre ambas fases. El umbral no
garantiza factura máxima: el uso del proveedor puede llegar tarde y un turno ya
iniciado puede exceder el saldo.

El reporte H4 comparará 2–3 candidatos y expresará p50/p95 de latencia, calidad
con intervalo/denominador, tokens de todas las llamadas, tasas de error y costo
medido con precios vigentes y supuestos de caché. Incluir escenarios de 100,
1 000 y 10 000 preguntas al mes; separar tokens de entrada/salida, llamadas de
herramientas y costos de hosting. Uso reportado por la API puede estar atrasado
o incompleto, por lo que ni las estimaciones ni un presupuesto propio prometen
un tope de factura. No se eligió un modelo, objetivo mensual, precio del
proveedor ni presupuesto para live evaluation.
