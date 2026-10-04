# Airline Tracker — revisión del PR y validación real

Fecha: 4 de octubre de 2026 UTC (los primeros intentos ocurrieron el 3 de
octubre por la noche en Ciudad de México). Continúa la
[remediación de Claude](airline-tracker-remediacion-20261004.md) en el PR #81.
Los cambios de programación y la revisión se delegaron a GPT-6 Luna.

## Correcciones revisadas

- El modo local rechaza cualquier cabecera `X-Forwarded-*`, además de
  `Forwarded` y `X-Real-IP`. La fábrica de API también exige contraseña para
  OpenAI, aunque la configuración se construya directamente en Python.
- El adaptador cierra el stream y recupera el uso del turno por hasta cinco
  lecturas oficiales cuando falta en el evento final, con esperas de dos
  segundos y dentro del tiempo restante. Un uso ausente permanece
  desconocido; no se reenvía el mensaje.
- La evaluación guarda checkpoints privados y reportes atómicos. Un agregado
  desconocido queda `null`, con subtotal conocido aparte. El reporte final se
  guarda antes de marcar el progreso completo. Las sesiones con uso desconocido
  se conservan para reconciliación.
- Los argumentos inválidos de herramientas regresan al modelo como error de
  función, igual que en el worker del producto. Las observaciones de consulta,
  comparación y serie conservan argumentos y filas reales; no se sustituyen
  por los valores o el plan del fixture.
- La rúbrica reconoce coma decimal, espacios antes de `%` y nombres
  equivalentes de trimestre. Rechaza números diferentes, signos incorrectos y
  periodos distintos. No se cambiaron los valores golden.
- El panel libera observers, listeners y stream al desmontarse. Se elimina
  el error de teardown de jsdom. El máximo de herramientas pasa a cinco,
  consistente con la sonda y el holdout. El contexto descarta tarjetas de otra
  pestaña y el diálogo móvil declara su modalidad, aísla el fondo y devuelve
  el foco al CTA que lo abrió, incluso sin autofocus del navegador.

## Evidencia de la integración

La comprobación segura confirmó `OPENAI_API_KEY` disponible, sin mostrar ni
copiar su valor. El dueño había autorizado US$10 acumulados para una sonda y
40 preguntas con tres candidatos. Los archivos con respuestas del proveedor,
sesiones y diagnósticos permanecen bajo `.state/`, ignorados por Git.

| Intento | Resultado | Entrada | Salida | Estimación a tarifa normal sin caché |
|---|---|---:|---:|---:|
| Sonda Luna | Respuesta, plan, cifra y fuentes correctos; 28,47 s y cinco herramientas. Uso reconciliado por el dueño desde Platform: 46.986 tokens y cuatro requests. | 46.623 | 363 | US$0,0048438 |
| Primer caso del holdout Luna | Error antes del resultado; cancelación confirmada. Uso recuperado mediante GET del turno conservado. | 111.635 | 607 | US$0,011467 |
| Segundo caso del holdout Luna | Respuesta, plan y fuentes correctos; 20,51 s y cuatro herramientas. Uso tardío recuperado por GET. | 45.400 | 343 | US$0,0047115 |

Consumo conocido antes de la continuación: **204.971 tokens**; estimación
acumulada **US$0,0210223** y saldo operativo **US$9,9789777**. El segundo intento reportó
98.249 tokens de entrada en caché y 202 de razonamiento, incluidos en los
contadores anteriores. El cálculo usa precios normales sin descuentos de caché ni créditos; las
escrituras de caché no observadas y la factura pueden diferir. No se atribuyó costo cero por Data Sharing.

La primera sonda se calificó inicialmente mal por `84,9 %` y `2T26`; reevaluar
el mismo reporte con la rúbrica corregida dio un caso correcto, sin repetir la
llamada. El evaluador anterior había solicitado borrar esa sesión antes de
reconciliar el uso; una lectura devolvió 404. Esto se corrigió para los intentos
siguientes. El intento del holdout no guardó los argumentos de la herramienta
que falló, por lo que no se afirma una causa retrospectiva exacta.

El intento fallido de Luna se conserva como incidencia de infraestructura;
no se cuenta como respuesta correcta ni se repite silenciosamente. La
continuación cubre los 38 casos de Luna todavía no intentados y los 40 de
Sol y Astra; el caso completado de Volaris se conserva una sola vez,
con el saldo acumulado y pausa ante uso desconocido, error o reserva
insuficiente. La reserva de evaluación se calibra a 140.000 tokens de entrada
y 10.000 de salida como piso estimado, sin prometer una cota de API.

La fase siguiente de Luna completó 15 preguntas y registró un error de la
aplicación en otra pregunta. El turno remoto de ese error terminó y su uso se
reconcilió sin repetirlo. Antes de continuar los 22 casos todavía no intentados
de Luna y los candidatos restantes, el gasto acumulado conocido es
**US$0,0900575 a tarifas normales**. La calidad provisional del holdout es
**7/8 casos soportados puntuados**; cuatro de los doce todavía no tienen score.
Los 28 casos de ambigüedad y seguridad requieren revisión ciega. El expediente
privado incluye textos disponibles y campos humanos vacíos; no utiliza la sonda
como respuesta del holdout. Ningún resultado parcial elige un modelo.

## Piloto y límites diarios

El cupo principal de Data Sharing de 250.000 incluye Luna y Astra; Sol
`gpt-6.1-sol` no aparece en la lista. Agents API con funciones propias no tiene
cobertura inequívoca en la documentación, que excluye “tool use”. El
[documento de cobertura](../chat/data-sharing.md) conserva las tarifas normales
y propone 200.000 tokens diarios para el proyecto y el dueño, con una reserva
estimada de 150.000 por turno. Esa política del piloto aún no está adoptada.
Se suman entrada y salida, incluida caché, y chat más evaluaciones; el día
reinicia a las 00:00 UTC, 18:00 de Ciudad de México. El incentivo no cambia RPM,
TPM ni el presupuesto autorizado de US$10.

Hostinger **Hosting Web Empresarial / Business** no admite este backend
Python. La [guía de VPS](../chat/hostinger-vps.md) prepara una instancia separada
con systemd, SQLite persistente, Nginx y HTTPS en un subdominio. No se contrató
ni modificó hosting o DNS. Una contraseña aleatoria del dueño y su hash están
preparados en un archivo local privado, fuera de Git y del frontend.

## Validación y estado

- Python: 58 pruebas focalizadas de API, evaluación, adaptador y límites de
  módulos aprobadas tras los cambios finales; pruebas adicionales de worker,
  borrado durable y conversaciones Mock también aprobadas.
- Suite pública: 653 aprobadas, una omitida y 77 deseleccionadas; después se
  agregaron regresiones de límites y diagnóstico. La CI del último commit es
  la validación autoritativa de entrega.
- Typecheck, 91 Vitest y build aprobados; nueve smokes de navegador aprobados.
  Tras las correcciones del panel se repitió el smoke del chat y pasó.
- Auditoría del snapshot: 12/12; `src.publish.verify site/` válido. Ruff y
  diff sin errores; módulos dentro de los límites del repositorio.
- Con el chat desactivado, HTML y assets compilados siguen idénticos a `site/`.
  Los datos, el manifiesto y las aprobaciones humanas no cambiaron.

El fallo local preexistente del hash del warehouse en el diagnóstico de etapa
12 sigue documentado en la [entrega original](airline-tracker-implementacion-20261003.md).
No se modificó ese diagnóstico ni se declaró verde la suite privada completa.
H3 tiene una sonda real correcta; H4 requiere completar y revisar el holdout.
H5 requiere servidor, retención y pruebas HTTPS desde Pages. No hay modelo
elegido ni piloto publicado.
