# Airline Tracker — implementación y comparación parcial

Fecha: 4 de octubre de 2026 UTC. Entrega del [PR #81](https://github.com/salvamalfa/aeromexico-tracker/pull/81),
tras la [remediación de Claude](airline-tracker-remediacion-20261004.md).
La programación y las revisiones independientes se delegaron a GPT-6 Luna.

El backend, las herramientas y el panel están implementados y verificados.
La comparación real **está pausada por un turno cuyo uso no se puede confirmar**.
No hay modelo elegido, aprobación semántica del dueño ni piloto publicado.
El chat público permanece desactivado; los datos y las aprobaciones existentes
no cambiaron.

## Comportamiento entregado

- El chat consulta el snapshot público mediante 11 métricas versionadas y siete
  herramientas de lectura. No abre el warehouse privado ni habilita las ocho
  fichas que permanecen en inventario.
- El acceso OpenAI exige contraseña; el servidor conserva hashes scrypt y
  sesiones temporales revocables. La contraseña no se guarda en el navegador.
  El modo local rechaza cabeceras de proxy, incluidas todas las X-Forwarded-*.
- El adaptador usa el SDK oficial y Agents API sin sandbox. Recupera uso tardío
  mediante lecturas oficiales acotadas, sin reenviar la pregunta. Un contador
  ausente se mantiene desconocido. Si recupera un turno fallido o cancelado con
  uso confirmado, entrega ese uso al worker y al evaluador para contabilizarlo.
- Las cancelaciones explícitas y por timeout esperan al proveedor antes del
  siguiente turno. Si la sesión aparece después de cancelar o borrar la
  conversación, se conserva lo necesario para cancelarla y encolar su borrado.
  Un resultado tardío puede aportar consumo, pero no cambia el estado terminal
  ni publica un mensaje después del cierre.
- Las reservas desconocidas persisten entre días UTC y sobreviven al borrado o
  retención del historial mediante un registro contable sin contenido. El uso
  confirmado se registra una sola vez. No existe conciliación automática de
  ese registro después de borrar las referencias del proveedor: sin evidencia,
  la reserva sigue retenida. La fecha de confirmación es una fecha contable
  operativa, no una garantía sobre la fecha de facturación.
- El panel retoma turnos pendientes, conserva el contexto seleccionado por
  tarjeta y libera streams, listeners y observers al desmontarse. El diálogo
  móvil aísla el fondo y devuelve el foco al botón que lo abrió. Un envío HTTP
  de resultado incierto conserva su identificador, contenido y contexto para
  consultar el mismo envío al reintentar, evitando crear otro turno pagado.
- En el proveedor simulado, una aerolínea nombrada explícitamente prevalece
  sobre el contexto. La consulta AFAC de todas las aerolíneas mexicanas usa
  MEXICAN_CARRIERS, sin sustituirla por las tres compañías del proyecto.
- El evaluador guarda argumentos y observaciones reales, respuestas y
  checkpoints privados. No sustituye observaciones por valores golden.
  Los reportes son atómicos y el SDK no reintenta automáticamente entradas.

Dos contextos soportados del fixture usaban IDs de tarjetas obsoletos. Se
alinearon con los IDs del frontend y se validan todos los contextos soportados;
no cambiaron los planes ni los valores golden. Los rechazos originales de Luna
no se repitieron. La corrección solo se aplica a casos nuevos de los otros
candidatos.

## Método y continuidad

El holdout contiene 40 casos por candidato: 12 consultas soportadas con valores
estáticos, 12 aclaraciones, nueve rechazos y siete preguntas fuera de cobertura.
Hay 26 preguntas en español y 14 en inglés. Se mantiene separado de los ejemplos
del prompt y de la sonda inicial.

Versiones congeladas:

- Datos: de3c4d404837b8c19d306c301cd5647cc955d26215a45bc0c8f8b7bed00db668.
- Semántica: d43faaad53a352cbbfea194c6ffa978ebef8bce6a4d403cc52553158fcb11b2a.

La autorización acumulada de US$10 incluye la sonda, todos los intentos,
errores e interrupciones. No se reinician contadores entre fases. Antes de
admitir cada caso se reserva un piso estimado de 140.000 tokens de entrada y
10.000 de salida; no es una cota de consumo del proveedor. Los límites del
experimento son cinco herramientas, 16.000 bytes por resultado y 90 segundos
por turno.

Se recuperó mediante GET el uso de errores anteriores. Una interrupción de Sol
tiene consumo terminal confirmado, pero carece de reporte de respuesta: queda
sin puntuar y no se repite. La continuación programada se ejecutó el domingo
4 de octubre a las 04:00 de Ciudad de México y admitió únicamente casos nuevos.

La última fase registró nueve casos nuevos de Sol. El último turno quedó
failed, con la sesión idle, sin contadores de uso confirmados. El harness
intentó cancelarlo y conservó la sesión; las lecturas posteriores de esa misma
sesión tampoco recuperaron los contadores ni un código de fallo clasificable.
Se pausó antes de enviar otra pregunta. La conciliación de este único caso
requiere evidencia de Usage; su uso y costo **no se consideran cero**.
Los reportes originales permanecen intactos y las conciliaciones se guardan
como evidencia derivada privada. No se publican textos crudos, identificadores
de sesiones, secretos ni ajustes de cuenta.

## Comparación observada

La sonda confirma acceso, herramientas, referencias y una respuesta real
correcta; su costo se incluye en el expediente acumulado, pero no su calidad
en el holdout. Los intentos fallidos sí cuentan en consumo y cobertura.

| Candidato | Casos con disposición / 40 | Enviados al proveedor | Completados | Errores de aplicación | Interrupciones sin respuesta | Rechazos locales | No admitidos |
|---|---:|---:|---:|---:|---:|---:|---:|
| gpt-6-luna | 40 | 36 | 32 | 4 | 0 | 4 | 0 |
| gpt-6.1-sol | 16 | 16 | 14 | 1 | 1 | 0 | 24 |
| gpt-6-astra | 0 | 0 | 0 | 0 | 0 | 0 | 40 |

Un rechazo de contexto antes de llamar al proveedor no es una respuesta del
modelo. De los cuatro rechazos locales de Luna, dos correspondían a los IDs
soportados obsoletos y dos a contextos inválidos. No se los cuenta como pases
semánticos. Hay 55 pares modelo-caso con reportes finales y una disposición
adicional de Sol sustentada por el checkpoint interrumpido y su conciliación;
son 56 disposiciones y 64 casos no admitidos, sin duplicación.

| Candidato | Soportados correctos / puntuados | Cobertura numérica / 12 | Soportados sin puntuar | Latencia p50 / p95 | Muestra de latencia |
|---|---:|---:|---:|---:|---:|
| gpt-6-luna | 7 / 9 (77,8%) | 9 / 12 | 3 | 22,23 / 32,04 s | 32 completados |
| gpt-6.1-sol | 8 / 8 (100%) | 8 / 12 | 4 | 26,36 / 30,23 s | 14 completados |
| gpt-6-astra | Sin muestra | 0 / 12 | 12 | Sin muestra | 0 |

Los percentiles usan rango más cercano sobre turnos completados; no incorporan
los tiempos de fallos como si fueran respuestas útiles. Los casos de aclaración,
rechazo y cobertura no se mezclan con la exactitud numérica. Los resultados de
la rúbrica original se conservan: la revisión independiente detectó una posible
discrepancia de puntuación temporal en RASK y una atribución ambigua de pasajeros
de Viva, pero no cambió calificaciones ni valores esperados retrospectivamente.

Se preparó una hoja ciega privada con nombres de modelo ocultos y campos humanos
vacíos. La revisión automática de un subagente se registra separadamente; no
constituye aprobación humana ni demuestra ausencia de fallos críticos en los
casos no observados.

En los 84 espacios no numéricos (28 por candidato), esa revisión automática
examinó 29 respuestas: 22 pases, cinco pases con reservas y dos pendientes de
criterio humano. Otros 55 espacios carecen de respuesta calificable. No detectó
fallos críticos en las 29 respuestas revisadas; ese resultado observado no
completa el gate de cero fallos críticos del piloto.

### Cobertura de las muestras

| Grupo del holdout | Casos esperados | Completados Luna | Completados Sol | Completados Astra |
|---|---:|---:|---:|---:|
| Español | 26 | 22 | 9 | 0 |
| Inglés | 14 | 10 | 5 | 0 |
| Consulta soportada | 12 | 9 | 8 | 0 |
| Requiere aclaración | 12 | 10 | 1 | 0 |
| Debe rechazarse | 9 | 8 | 2 | 0 |
| Fuera de cobertura | 7 | 5 | 3 | 0 |

| Métrica de los casos soportados | Casos esperados | Puntuados Luna | Puntuados Sol |
|---|---:|---:|---:|
| ASK | 1 | 1 | 1 |
| CASK | 1 | 1 | 1 |
| Pasajeros de compañía | 2 | 2 | 1 |
| Factor de ocupación | 3 | 1 | 2 |
| Participación | 1 | 1 | 1 |
| Cambio de participación en puntos porcentuales | 1 | 1 | 0 |
| RASK | 1 | 1 | 1 |
| Margen unitario | 2 | 1 | 1 |

El fixture no tiene etiquetas explícitas de nivel de riesgo o tipo de
ambigüedad. Se informa la cobertura de resultados esperados y de idiomas;
no se inventan tasas por categorías inexistentes. Los 28 casos no numéricos
por candidato siguen sin aprobación de una rúbrica humana.

## Tokens y costo a tarifa normal

Las medias suman todas las llamadas internas de cada pregunta, incluidos los
intentos que fallaron. Se excluye la sonda de las medias del holdout. Cada caso
evaluado abre una conversación de un solo turno; el historial de conversaciones
más largas puede incrementar el consumo.

| Candidato | Entrada media | Salida media | Herramientas medias | Base de la muestra |
|---|---:|---:|---:|---|
| gpt-6-luna | 40.104,69 | 524,28 | 3,11 | Los 36 intentos del holdout tienen uso confirmado |
| gpt-6.1-sol | 38.349,60 | 197,73 | 2,87 | Solo 15 intentos con contadores conocidos; no es la media de los 16 |
| gpt-6-astra | Desconocida | Desconocida | Desconocida | No se envió una inferencia |

La caché se registra cuando está disponible, pero no se descuenta de estas
estimaciones. Las escrituras de caché, créditos y ajustes de factura no
observados pueden cambiar el cargo. Las tarifas normales de entrada/salida,
en USD por millón, son Luna 0,10/0,50, Sol 2/10 y Astra 10/50; se conservan como
alternativa al incentivo de Data Sharing. No se atribuye gratuidad a Agents API
con funciones propias ni a gpt-6.1-sol.

| Base de proyección | Costo medio estimado | 100 preguntas/mes | 1.000 | 10.000 |
|---|---:|---:|---:|---:|
| Luna: todos los intentos enviados, incluidos fallos | US$0,00427261 | US$0,43 | US$4,27 | US$42,73 |
| Sol: todos los intentos enviados | Desconocido | Desconocido | Desconocido | Desconocido |
| Sol: solo 14 completados, referencia secundaria | US$0,076889 | US$7,69 | US$76,89 | US$768,89 |
| Astra | Sin medición | Sin medición | Sin medición | Sin medición |

La referencia secundaria de Sol excluye dos intentos sin respuesta útil y
no sustituye una proyección operativa completa. El agregado monetario del
experimento permanece desconocido mientras falte el consumo del último turno;
su subtotal conocido se conserva en el expediente privado, sin presentarlo como
total ni reiniciar el presupuesto. El hosting se presupuesta por separado.

## Gates y entrega

| Hito | Estado y condición pendiente |
|---|---|
| H1 | Catálogo conciliado técnicamente, 12/12 referencias estáticas verificadas; revisión semántica del dueño pendiente. |
| H2 | Backend simulado, herramientas y panel implementados y verificados. |
| H3 | Integración real sin sandbox comprobada; el último uso fallido requiere conciliación externa. |
| H4 | Comparación parcial pausada; no se selecciona modelo. Requiere consumo reconciliado, cobertura suficiente, al menos 95% de soportados correctos y cero fallos críticos revisados. |
| H5 | Sin servidor persistente HTTPS, retención acordada ni prueba desde teléfono con la computadora apagada. Chat público apagado. |

Sol tiene mejor exactitud numérica observada, pero cuatro de doce casos aún
carecen de puntuación y Astra no tiene muestra. Luna queda por debajo del gate
con la rúbrica conservada. La evidencia actual no permite declarar ganador ni
prometer calidad del piloto.

La [política propuesta de Data Sharing](../chat/data-sharing.md), **aún no
adoptada**, limita el proyecto y al dueño a 200.000 tokens diarios con una reserva
estimada de 150.000 por turno. Suma entrada y salida, incluida caché, chat,
evaluaciones y reservas de toda la organización. El cupo principal se reinicia
a las 00:00 UTC, 18:00 de Ciudad de México; no aumenta RPM/TPM. Los límites
predeterminados actuales no se cambian por esa propuesta.

Hostinger **Hosting Web Empresarial / Business** no aloja este backend Python.
La [guía de VPS](../chat/hostinger-vps.md) prepara systemd, SQLite persistente,
Nginx, HTTPS, rollback y comprobaciones desde Pages. No se contrató un servicio
ni se modificaron hosting o DNS. El acceso inicial del dueño y su hash están
preparados fuera de Git; la retención debe decidirse antes de abrir el piloto.

## Verificaciones

- CI del código d948481: test y web aprobados; 675 pruebas Python,
  seis omitidas y 77 deseleccionadas, 91 Vitest y nueve smokes de navegador.
- Verificación local final de almacenamiento, worker, adaptador, semántica y
  límites de módulos: 42 pruebas aprobadas. Ruff, formato y diff sin errores.
- Las correcciones posteriores de revisión tienen regresiones offline de
  recuperación de uso fallido/cancelado, precedencia de entidad, denominador
  AFAC y pérdida de respuesta HTTP. La verificación posterior del adaptador,
  Mock y límites aprobó 19 pruebas; typecheck y los 95 Vitest de la interfaz
  pasaron, incluidos reintentos tras 401 y fallos simultáneos de SSE y GET.
  La entrega exige los checks test y web del último commit, además de resolver
  los hilos de revisión.
- Auditoría del snapshot: 12/12; src.publish.verify site/ válido. Con el
  flag apagado, HTML y assets compilados conservan igualdad con site/.
- No cambiaron site/data/v1/, el manifiesto, las aprobaciones ni el sitio
  público. El fallo local preexistente del hash del warehouse en el diagnóstico
  de etapa 12 sigue descrito en la [entrega original](airline-tracker-implementacion-20261003.md);
  no se declara aprobada la suite privada completa.

El PR entrega código y documentación verificables. Su integración no activa
el chat ni concede las aprobaciones pendientes de H1, H4 y H5.
