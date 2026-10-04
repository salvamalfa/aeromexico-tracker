# Comparación terminal de Airline Tracker — 4 de octubre de 2026

Este informe resume la unión terminal de los reportes del holdout y el estado
operativo. Las disposiciones originales y sus puntuaciones no se alteraron.
La revisión humana ciega sigue pendiente; el agregado no elige un modelo ni
aprueba el piloto.

## Corte y procedencia

El controlador V10 terminó con `stopped_budget_reservation`, sin proceso activo.
La unión deduplicada por modelo/caso conserva 40 disposiciones de Luna, 40 de
Sol y 11 de Astra: quedan 29 casos Astra sin admitir. V10 añadió cinco
disposiciones Sol y once Astra. No se reinició ni reprodujo ningún turno.

Las evaluaciones cruzan distintas implementaciones con las mismas versiones
congeladas de datos y semántica. PR #84 contiene los cambios de cierre,
cancelación y recuperación del worker. PR #85 contiene el acceso por proxy,
CIDR/XFF, la serie más reciente y etiquetas de fuente; no cambió el worker. La
procedencia se valida por reporte y controlador, sin tratar todas las fases
como un entorno de ejecución idéntico.

| Candidato | Disposiciones / 40 | Enviados al proveedor | Completados | Errores | Interrumpidos | Rechazos locales | Sin admitir |
|---|---:|---:|---:|---:|---:|---:|---:|
| gpt-6 Luna | 40 | 36 | 32 | 4 | 0 | 4 | 0 |
| gpt-6.1 Sol | 40 | 38 | 31 | 6 | 1 | 2 | 0 |
| gpt-6 Astra | 11 | 11 | 11 | 0 | 0 | 0 | 29 |

Los rechazos locales no son solicitudes al proveedor. Para el intento V10 el
reporte original mantiene uso de tokens NULL; una conciliación derivada,
vinculada por hash, confirma cero solicitudes y asigna costo atribuible cero,
sin convertir los tokens en medición cero. La excepción histórica de Sol
también conserva tokens NULL y su reserva operativa cero
autorizada cubre solo ese intento; no se afirma que el uso sea cero ni que la
factura esté verificada.

## Calidad y cobertura

Se mantienen las puntuaciones numéricas originales para los resultados
`supported`; no se puntuaron retrospectivamente los demás estados.

| Candidato | Pases / resultados numéricos puntuados | Casos `supported` en fixture | `supported` sin puntuar |
|---|---:|---:|---:|
| Luna | 7 / 9 | 12 | 3 |
| Sol | 9 / 10 | 12 | 2 |
| Astra | 8 / 9 | 12 | 3 |

Las tasas puntuadas son 77,8% (7/9), 90% (9/10) y 88,9% (8/9), por debajo del
gate de 95% para los tres candidatos. Astra además solo cubre los primeros 11
envíos admitidos y deja 29 casos pendientes; esa muestra parcial no representa cobertura equilibrada del
fixture. No se declara ganador.

La tabla siguiente presenta, por idioma, casos enviados/completados/puntuados.
Los denominadores del fixture son 14 en inglés y 26 en español.

| Candidato | Inglés | Español |
|---|---:|---:|
| Luna | 12 / 10 / 2 | 24 / 22 / 7 |
| Sol | 13 / 11 / 2 | 25 / 20 / 8 |
| Astra | 3 / 3 / 2 | 8 / 8 / 7 |

Por resultado esperado, las celdas son enviados/completados/puntuados; el
orden de categorías es `clarify`, `refused`, `supported`, `unsupported`.

| Candidato | Clarify | Refused | Supported | Unsupported |
|---|---:|---:|---:|---:|
| Luna | 11 / 10 / 0 | 8 / 8 / 0 | 10 / 9 / 9 | 7 / 5 / 0 |
| Sol | 11 / 7 / 0 | 8 / 7 / 0 | 12 / 10 / 10 | 7 / 7 / 0 |
| Astra | 1 / 1 / 0 | 0 / 0 / 0 | 9 / 9 / 9 | 1 / 1 / 0 |

La cobertura de métricas se resume como enviados/completados/puntuados:

| Métrica | Luna | Sol | Astra |
|---|---:|---:|---:|
| ask_km | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| cask_cents_per_km | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| company_passengers | 2 / 2 / 2 | 2 / 2 / 2 | 1 / 1 / 1 |
| load_factor | 2 / 1 / 1 | 3 / 3 / 3 | 2 / 2 / 2 |
| market_share | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| market_share_change_qoq_pp | 1 / 1 / 1 | 1 / 0 / 0 | 1 / 1 / 1 |
| rask_cents_per_km | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| unit_margin_cents_per_km | 1 / 1 / 1 | 2 / 1 / 1 | 1 / 1 / 1 |

## Latencia y costo

La latencia usa rango más cercano sobre latencias originales de turnos
completados. La muestra no incluye errores, interrupciones ni rechazos locales.

| Candidato | Completados con latencia | p50 (s) | p95 (s) |
|---|---:|---:|---:|
| Luna | 32 | 22,2313 | 32,0396 |
| Sol | 31 | 26,3606 | 31,9273 |
| Astra | 11 | 26,2423 | 39,2526 |

Las estimaciones monetarias usan tarifas normales de entrada/salida y consumo
observado conocido. Proyectan el subconjunto de turnos enviados con uso
conocido, no una factura ni el costo de cualquier población futura.

| Base observada | Muestra con uso conocido | 100 preguntas/mes | 1.000 | 10.000 |
|---|---:|---:|---:|---:|
| Luna | 36 / 36 | US$0,43 | US$4,27 | US$42,73 |
| Sol | 37 / 38 | US$7,55 | US$75,54 | US$755,38 |
| Astra | 11 / 11 | US$46,80 | US$467,97 | US$4.679,72 |

El subconjunto de Sol excluye un turno enviado cuyo uso sigue desconocido. La
muestra de Astra es parcial y se detuvo por presupuesto de reserva; su
proyección no representa los 40 casos. No se presupone Data Sharing gratis ni
se incluye hosting.

El subtotal conocido a tarifas normales es **US$8,101306**: **US$2,642014**
del corte previo más **US$5,459292** de V10. Incluye la sonda y el ajuste
contable previo de 363 tokens de entrada de Luna sin asignarlo a un caso. El
total completo y la factura real siguen **NULL / no verificados** por el uso
histórico desconocido de Sol. Del límite operativo autorizado de US$10 quedan
US$1,898694 de capacidad conocida; la siguiente reserva Astra era US$1,90, por
lo que V10 paró y dejó 29 casos sin intentar. No se redujo reserva ni hubo
llamadas adicionales después de esa parada.

## Cuantiles y revisión ciega

El análisis reproducible de tokens incluye distribuciones de Luna y Sol; la
muestra Astra de 11 se mantiene en las tablas agregadas de cobertura, latencia
y costo, pero queda fuera de la comparación de reserva de dos modelos. Un
registro de fixture en la unión procede de checkpoint sin fila de reporte
crudo; la auditoría de disponibilidad de campos inspecciona 90 filas crudas de
holdout y separa una fila de sonda. En las 90 filas, `cached_tokens` aparece
como desconocido en 84 y está ausente en seis; `reasoning_tokens` está ausente
en las 90. La sonda tiene caché desconocida y razonamiento ausente. Ninguna
ausencia o `unknown` equivale a cero. Cinco conciliaciones raíz de Luna
recuperaron detalles de caché/razonamiento, pero son solo ese subconjunto y no
se extrapolan.

Se creó una hoja ciega privada nueva con 40 preguntas y 74 respuestas
completadas, usando etiquetas A/B/C y una clave privada separada. Se preservaron
los scores numéricos originales; no se generaron calificaciones automáticas
nuevas ni se rellenó una rúbrica humana. Las casillas de revisión siguen vacías
y no hay selección de modelo. La hoja original y sus campos permanecen intactos.

La reserva de tokens se analiza en una [propuesta revisable separada](airline-tracker-reserva-propuesta-20261004.md). Ni este informe ni esa propuesta
cambian la configuración actual de 150.000 tokens, reactivan el proveedor o
aprueban un ajuste.
