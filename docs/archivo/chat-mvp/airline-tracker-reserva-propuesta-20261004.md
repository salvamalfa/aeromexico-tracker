# Propuesta revisable de reserva de tokens

> **Nota posterior (6 de octubre de 2026).** Las mediciones de este documento
> se obtuvieron con los límites de turno vigentes entonces: 5 llamadas de
> herramienta y 90 segundos. El PR #88 los subió a 8 llamadas y 180 segundos,
> así que el peor caso por pregunta puede ser mayor y no se volvió a medir.
> Para el MVP, la política de admisión pasó a un tope diario en dólares
> configurable en Railway (ver `docs/archivo/chat-mvp/chat-mvp-preparacion-20261006.md`);
> los pisos de reserva propuestos aquí se conservan como registro, no como
> configuración vigente.

Fecha de corte: 4 de octubre de 2026 UTC. El documento presenta estadísticas y
un piso metodológico de revisión; no altera configuración, activa el proveedor
ni autoriza más evaluaciones.

## Unión, estados y método

El corte usa V10 terminal y la unión validada de reportes originales,
checkpoints V3/V4 y disposiciones V6–V10 con conciliaciones exactas. La unión
contiene 40 disposiciones Luna, 40 Sol y 11 Astra; 29 casos Astra no fueron
admitidos. Hubo 36 solicitudes de proveedor para Luna (32 completadas), 38
para Sol (31 completadas) y 11 para Astra (11 completadas). Los errores y la
interrupción se conservan en las métricas de todos los enviados.

Dos rechazos locales de Sol no enviaron solicitud. Su uso de tokens permanece
NULL; el costo atribuible a proveedor es cero solo por evidencia específica de
ausencia de solicitud, no porque se hayan medido cero tokens. Un turno enviado
antiguo de Sol sigue con uso desconocido y tokens NULL. La autorización
operativa de reserva cero cubre solo ese intento; no es una imputación para la
estadística ni una verificación de factura.

Los cuantiles usan rango más cercano y valores no negativos conocidos. La tabla
“todos los enviados” incorpora errores con uso confirmado; los no conocidos
quedan fuera de cada métrica y se cuentan aparte. Los máximos de entrada,
salida y total se calculan de forma independiente: pueden pertenecer a turnos
distintos, así que no se suman entre columnas. El total de una observación solo
se calcula cuando ambas partes están disponibles.

## Distribuciones de tokens por modelo

Cada celda de cuantiles es p50 / p95. `n conocido` indica cuántos valores
entraron al cálculo; la tasa de completados aparece junto a cada total de
envíos. Las cifras se expresan en tokens.

| Modelo y grupo | Enviados; completados | n conocido entrada/salida/total | Entrada p50/p95 | Salida p50/p95 | Total p50/p95 |
|---|---:|---:|---:|---:|---:|
| Luna, todos | 36; 32 | 36/36/36 | 33.909 / 111.635 | 456 / 1.308 | 34.915 / 112.242 |
| Luna, completados | 32; 32 | 32/32/32 | 33.456 / 59.301 | 410 / 875 | 33.939 / 60.030 |
| Sol, todos | 38; 31 | 37/37/37 | 35.207 / 50.271 | 208 / 330 | 35.391 / 50.587 |
| Sol, completados | 31; 31 | 31/31/31 | 34.986 / 49.610 | 201 / 330 | 35.183 / 49.940 |

La estadística de cuantiles/reserva compara Luna y Sol. Astra aparece en el
informe terminal general con 11 envíos y costo/latencia observados, pero no se
usa para esta propuesta de reserva: 29 casos siguen sin ejecutar y la muestra
parcial no ofrece cobertura equilibrada.

## p95 y máximos por cantidad de llamadas a herramientas

En las tablas, cada celda de tokens es `p95 / máximo` por vector. Los
denominadores conocidos corresponden a entrada/salida/total; los grupos se
forman por llamadas observadas del proveedor, no por historial de conversación.

### Todos los envíos conocidos

| Modelo / llamadas | Enviados; con uso conocido | Entrada p95/máx. | Salida p95/máx. | Total p95/máx. |
|---|---:|---:|---:|---:|
| Luna 0–2 | 13; 13 | 111.635 / 111.635 | 607 / 607 | 112.242 / 112.242 |
| Luna 3–4 | 13; 13 | 59.964 / 59.964 | 1.006 / 1.006 | 60.611 / 60.611 |
| Luna 5+ | 10; 10 | 126.456 / 126.456 | 1.853 / 1.853 | 128.309 / 128.309 |
| Luna llamadas desconocidas | 0; 0 | — | — | — |
| Sol 0–2 | 12; 11 | 34.299 / 34.299 | 202 / 202 | 34.474 / 34.474 |
| Sol 3–4 | 15; 15 | 48.269 / 48.269 | 255 / 255 | 48.520 / 48.520 |
| Sol 5+ | 5; 5 | 61.696 / 61.696 | 345 / 345 | 62.003 / 62.003 |
| Sol llamadas desconocidas | 6; 6 | 50.271 / 50.271 | 316 / 316 | 50.587 / 50.587 |

Los seis Sol con número de llamadas desconocido sí tienen tokens conocidos; el
turno Sol con uso desconocido está en el grupo 0–2 y no entra en sus cuantiles.
Una de las filas con tokens conocidos es la cancelación V8 conciliada.

### Solo turnos completados

| Modelo / llamadas | Completados; con uso conocido | Entrada p95/máx. | Salida p95/máx. | Total p95/máx. |
|---|---:|---:|---:|---:|
| Luna 0–2 | 12; 12 | 32.393 / 32.393 | 509 / 509 | 32.757 / 32.757 |
| Luna 3–4 | 13; 13 | 59.964 / 59.964 | 1.006 / 1.006 | 60.611 / 60.611 |
| Luna 5+ | 7; 7 | 59.301 / 59.301 | 875 / 875 | 60.030 / 60.030 |
| Luna llamadas desconocidas | 0; 0 | — | — | — |
| Sol 0–2 | 11; 11 | 34.299 / 34.299 | 202 / 202 | 34.474 / 34.474 |
| Sol 3–4 | 15; 15 | 48.269 / 48.269 | 255 / 255 | 48.520 / 48.520 |
| Sol 5+ | 5; 5 | 61.696 / 61.696 | 345 / 345 | 62.003 / 62.003 |
| Sol llamadas desconocidas | 0; 0 | — | — | — |

## Máximos y p95 globales

Esta tabla resume todos los envíos con uso conocido, incluidos errores. Los
máximos por columna son independientes y no se deben sumar. Los p95 también se
calculan por vector, excluyendo el uso no conocido.

| Modelo | n conocido / enviados | Máx. entrada | Máx. salida | Máx. total | p95 entrada | p95 salida | p95 total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Luna | 36 / 36 | 126.456 | 1.853 | 128.309 | 111.635 | 1.308 | 112.242 |
| Sol | 37 / 38 | 61.696 | 345 | 62.003 | 50.271 | 330 | 50.587 |

Por ejemplo, el máximo de entrada de Sol (61.696) y su máximo de salida (345)
no son una pareja que deba sumarse: el máximo de total observado es 62.003.
Un envío Sol mantiene entrada/salida desconocidas; no se imputa cero ni entra
en p95 o máximos.

## Historial, sonda y detalle de proveedor

Cada pregunta abrió una conversación de un turno. El uso con historial
multi-turno real más largo no se probó; llamadas de herramientas no representan
mensajes previos del usuario.

La sonda Luna se mantiene fuera del holdout: 46.623 tokens de entrada, 363 de
salida y 46.986 totales, completada con cinco o más llamadas de herramienta.
No se suma a los cuantiles anteriores.

La unión tiene 91 disposiciones de holdout. La inspección de disponibilidad de
campos encontró 90 filas de reportes crudos y una disposición respaldada solo
por checkpoint, sin fila cruda para consultar; además se revisó una fila de
sonda por separado. En las 90 filas de holdout, `cached_tokens` aparece como
`unknown` en 84 y está ausente en seis; `reasoning_tokens` está ausente en las
90. En la sonda, caché es `unknown` y razonamiento está ausente. No se observó
valor numérico de esos campos en los reportes de esas filas. Las ausencias y
`unknown` no son ceros.

Cinco reconciliaciones exactas de turnos raíz Luna sí recuperaron detalle:
367.346 de entrada, 4.945 de salida, 294.173 cached y 2.943 reasoning. Se
cuentan una sola vez por turno raíz; los reportes originales siguen mostrando
detalle desconocido. Es un subconjunto específico, no cobertura general ni una
base para extrapolar a Sol. La [verificación de Data Sharing](data-sharing-verification.md)
describe sus límites y la elegibilidad publicada de modelos.

## Piso de reserva propuesto

La regla de revisión es `ceil(1,25 × máximo total conocido / 10.000) × 10.000`.
Aplicada a la muestra observada, da **170.000 para Luna** (máximo total
128.309) y **80.000 para Sol** (máximo total 62.003). Son pisos metodológicos
para revisión, no límites contractuales o del proveedor. El histórico Sol con
uso desconocido impide tratar su máximo como peor caso probado; historial
multi-turno tampoco se midió.

El piso metodológico de Luna queda por encima de la reserva configurada vigente
de 150.000. Mantener el archivo/configuración actual apagado no equivale a
recomendar activarlo con 150.000 ni a bajarlo para obtener más preguntas: con
un consumo ilustrativo `q = 40.000`, `R = 170.000` y `D = 200.000` admiten una
pregunta. No hay evidencia segura para reducir la reserva de Luna usando su
p95 o promedio; el máximo observado por entrada es 126.456 y el máximo total
128.309.

Sol a 80.000 es una alternativa condicionada a revisión de calidad, decisión
del dueño sobre selección/política y cobertura del uso desconocido. Con
`q = 40.000` implica cuatro admisiones; con `q = 62.003` (máximo Sol observado)
implica dos. No se recomienda ni implementa esa alternativa ahora.

Con `D` como cupo diario operativo, `R` como reserva por pregunta y `q` como
consumo de referencia medido, la capacidad aproximada es:

```text
N(D, R, q) = 0                           si D < R
N(D, R, q) = 1 + floor((D - R) / q)     si D >= R
```

El control diario vigente es `D = 200.000` y la reserva configurada actual es
`R = 150.000`, que dan dos admisiones con `q = 40.000`; esa cuenta operativa
no demuestra que el piso Luna sea seguro. A 170.000 para Luna da una, y a
80.000 para Sol da cuatro con 40.000 o dos con 62.003. La recalculación real
debe comparar consumo medido, reservas pendientes y saldo diario; no se asume
una llamada fija del SDK ni una cota dura de tokens.

El dueño confirmó Tier 1: cuota publicada principal de 250.000 tokens y mini
de 2.500.000 para esta organización/proyecto. El control operativo de 200.000
está 50.000 por debajo de ese cupo principal; esa diferencia no se trata como
saldo seguro ni como presupuesto monetario. La elegibilidad e incentivo para
Agents API con tools no están confirmados. La oferta pública incluye Astra,
Sol y Luna en el grupo principal, no acredita `gpt-6.1-sol` por similitud de
nombre y permite terminar el programa con aviso de 30 días. No se asume
gratuidad ni crédito aplicado.

La validación monetaria del servicio exige que cada límite diario por usuario
y global cubra `R × max(tarifa_entrada, tarifa_salida) / 1.000.000`. Con los
pisos propuestos, la reserva individual requiere al menos **US$0,085 para
Luna** (170.000 × US$0,50/M) y **US$0,80 para Sol** (80.000 × US$10/M). Los
valores predeterminados actuales son US$2 por usuario y US$10 global, por lo
que pasan esa validación; no se modifican. Un límite por usuario de US$1
podría bloquear una cuarta pregunta Sol: tres costos medios medidos de
US$0,075538 más una reserva de US$0,80 sumarían aproximadamente US$1,0266.
El límite acumulado de US$10 de esta evaluación es distinto de esos cupos
diarios del servicio. Los límites y la reserva efectivos deben recalcularse
cuando cambie el modelo, precio o reserva dinámica por historial.

La recomendación de diseño para una revisión futura es conservar ambos guardas:
cupo operativo de **200.000 tokens diarios** para este proyecto y límites
monetarios a tarifa normal, sin basar admisión en un supuesto de Data Sharing
gratuito. Si una decisión posterior habilita Luna, los límites diarios iguales
por usuario y global de **US$0,10** cubrirían el piso matemático de US$0,085;
si habilita Sol, **US$2 por usuario y global** cubrirían la reserva US$0,80 y
el escenario de cuatro preguntas ilustrativo. Son valores condicionados a
revisión de calidad, decisión explícita del dueño y consumo observado; no son
configuración actual, autorización de uso ni recomendación para Astra sin una
muestra completa. Si el historial aumenta la reserva dinámica, los límites
monetarios deben subir acorde o el servicio debe rechazar la admisión.

## Proyección limitada de costo

Proyección a tarifas normales desde el promedio del subconjunto enviado con
tokens conocidos; incluye errores con uso conocido y excluye la excepción Sol
desconocida. Los valores no son costo total futuro ni factura.

| Base | Muestra conocida | Costo medio normal/pregunta | 100/mes | 1.000/mes | 10.000/mes |
|---|---:|---:|---:|---:|---:|
| Luna | 36 / 36 | US$0,004273 | US$0,43 | US$4,27 | US$42,73 |
| Sol | 37 / 38 | US$0,075538 | US$7,55 | US$75,54 | US$755,38 |
| Astra, solo referencia parcial | 11 / 11 | US$0,467972 | US$46,80 | US$467,97 | US$4.679,72 |

La muestra Astra terminó con 11 de 40 casos y no se proyecta como costo
representativo de la evaluación completa. Hosting se calcula por separado.

## Presupuesto y reproducibilidad

El subtotal conocido estimado a tarifas normales es **US$8,101306**:
**US$2,642014** antes de V10 más **US$5,459292** de V10. El corte incluye la
sonda y mantiene un ajuste previo no atribuido de 363 tokens de entrada Luna,
valorado en US$0,0000363. El total completo continúa **NULL** por el antiguo
uso desconocido de Sol; el gasto real y la factura no están verificados. El
límite autorizado de US$10 conserva US$1,898694 de capacidad conocida, menos
que la siguiente reserva Astra de US$1,90; por eso no se intentaron los 29
casos restantes. Se preservan el límite, las reservas y la excepción histórica
sin reset ni replay.

El JSON privado reproducible contiene denominadores, cuantiles, máximos,
tarifas, hashes y validación de unión; no contiene respuestas ni IDs de caso.
Los archivos V10 nuevos se guardan con permisos privados y nombres distintos
de los snapshots V8/V9. La generación requiere controladores terminales y la
señal explícita de root; no cambia fuentes del harness ni configuración.
