# Etapa 11 — Prototipo HTML del resumen ejecutivo

Fecha de entrega: 2026-09-04

Estado: REVISADA — PROTOTIPO LOCAL PENDIENTE DE APROBACIÓN VISUAL

## Resumen ejecutivo

Se construyó una sola Vista ejecutiva, autocontenida y conectada al modelo curado del
tracker. El prototipo no copia las cifras del HTML de referencia: consulta la vista
canónica `v_aeromexico_quarterly`, valida el grano trimestral y genera desde ese mismo
payload las tarjetas, conclusiones, narrativa, gráficas y tabla de detalle.

La cobertura comparable disponible es `2021Q1–2026Q2`: 22 trimestres completos con
RASK, CASK, ASK, factor de ocupación y pasajeros. El histórico se reconstruyó desde
22 comunicados trimestrales oficiales de Aeroméxico, preservados en Bronze y
normalizados en Silver; no se copiaron cifras del HTML de referencia.

El resultado permanece en la rama local `stage-11-executive-prototype`. No se cambió
la navegación de Streamlit, no se publicó el prototipo y no se hizo push.

## Qué se construyó

- Modelo de presentación reutilizable en `src/dashboard/executive_summary.py`.
- Generador de HTML autocontenido en `src/dashboard/executive_summary_html.py` y
  comando reproducible en `src/dashboard/build_stage11.py`.
- Hoja visual y comportamiento interactivo locales, sin CDN ni llamadas de red.
- Selector para recorrer los 22 trimestres; actualiza tarjetas, conclusiones,
  narrativa y énfasis de las gráficas.
- Cinco tarjetas: RASK, CASK, ASK, factor de ocupación y pasajeros, cada una con QoQ y
  YoY. El factor de ocupación se compara en puntos porcentuales.
- Gráfica principal RASK/CASK con barras de margen unitario sobre doble eje; gráfica
  de precio y volumen; y mapa de ocupación/RASK con color por año.
- Variaciones KPI positivas en verde y negativas en rojo.
- Jerarquía revisada: KPI primero, lectura ejecutiva inmediatamente debajo y después
  las gráficas. El contenido queda marcado como pendiente del agente trimestral.
- Navegación entre trimestres mediante flechas: abajo retrocede y arriba avanza.
- Selector de ventana para la gráfica principal: historia completa o últimos 12, 8
  o 4 trimestres, con periodos horizontales.
- RASK, CASK y margen identifican explícitamente centavos de USD y usan dos decimales
  en los tooltips.
- Encabezado en azul sólido, sin degradado ni ornamentos circulares.
- Barras de margen al fondo y líneas RASK/CASK sobrepuestas en primer plano.
- Lectura ejecutiva en una sola columna: título y trimestre arriba y un placeholder
  explícito debajo; no se presenta texto determinista como análisis terminado.
- Tabla trimestral desplegable con variación QoQ junto a cada métrica.
- Separadores oscuros entre años en la tabla y acceso directo a las filas, sin nota
  metodológica visible antes de los datos.
- Títulos abreviados y consistentes con `vs.`; la gráfica principal se denomina
  `RASK vs. CASK + Margen unitario`.
- El historial narrativo genérico fue retirado.
- Pruebas enfocadas y un validador de doce controles de aceptación.
- Comandos `stage11-prototype` y `stage11-validate` en el `justfile`.

## Datos utilizados

Se incorporaron los 22 comunicados oficiales disponibles entre 1T21 y 2T26. Los
archivos originales se preservaron de forma inmutable en Bronze, con URL y SHA-256;
el parser generó 70 observaciones Silver para los 14 trimestres que faltaban antes
de 3T24. Gold y el warehouse se reconstruyeron y el prototipo continúa leyendo
exclusivamente la vista semántica `v_aeromexico_quarterly`.

Los reportes de 1T26 y 2T26 se descargaron agenticamente de la página oficial de
relación con inversionistas. Sus cifras coinciden con las anclas SEC ya existentes,
por lo que el backfill amplió la historia sin cambiar los valores actuales.

Los archivos de diseño entregados por el usuario quedaron registrados en
`docs/referencias/etapa-11/`, separados explícitamente de las fuentes de datos. Los
PDF originales permanecen en Bronze y no se duplican dentro de `docs/`.

| Elemento | Resultado |
|---|---:|
| Trimestres comparables | 22 |
| Cobertura | 2021Q1–2026Q2 |
| Comunicados IR preservados | 22 |
| Observaciones Silver nuevas | 70 |
| KPIs por trimestre | 5 |
| Gráficas | 3 |
| Vistas/pestañas generadas | 1 |

## Cifras ancla visibles en 2026Q2

| Métrica | Valor backend | Presentación |
|---|---:|---:|
| Pasajeros | 6,014,000 | 6.01 M |
| ASK | 14,896,088,064 ASK-km | 14.90 mil M |
| Factor de ocupación | 0.849 | 84.9% |
| RASK | 9.9419390758 centavos/ASK-km | 9.94 ¢ |
| CASK | 9.5069792412 centavos/ASK-km | 9.51 ¢ |
| Margen unitario | 0.4349598346 centavos/ASK-km | 0.43 ¢ |

El margen reconcilia con `RASK - CASK`. Para 2026Q2, las tarjetas muestran RASK
`+2.6% QoQ / +10.3% YoY`, CASK `+10.9% / +28.6%`, ASK `+7.7% / +1.9%`, factor de
ocupación `+0.5 pp / -0.8 pp` y pasajeros `+3.9% / -2.7%`.

## Validaciones automatizadas

| Check | Resultado | Evidencia |
|---|---|---|
| Suite completa | PASS | 199/199 pruebas |
| Suite enfocada Etapas 9 y 11 | PASS | 42/42 pruebas |
| Aceptación Etapa 11 | PASS | 14/14 controles |
| Fuente única | PASS | `v_aeromexico_quarterly` |
| Cobertura | PASS | 22 periodos únicos, 2021Q1–2026Q2 |
| Reconciliación | PASS | margen y cifras visibles coinciden con el warehouse |
| Seguridad | PASS | sin red, CDN, rutas absolutas, credenciales ni correo SEC |
| Determinismo | PASS | el artefacto regenerado coincide byte por byte |

## QA visual y funcional

| Escenario | Resultado observado |
|---|---|
| Escritorio | Jerarquía compacta, cinco tarjetas y tres gráficas legibles |
| Tablet, 736 × 900 | Tarjetas 3+2, gráficas sin colisiones ni overflow |
| Móvil, 360 × 800 | Tarjetas en dos columnas, gráficas de 297 px y cero overflow horizontal |
| Flechas trimestrales | Retroceden y avanzan; se deshabilitan en los extremos |
| Selector de ventana | Historia completa, 12, 8 y 4 trimestres funcionan |
| Primeros periodos | Las comparaciones sin antecedente aparecen como `No disponible` |
| Desplegable | Tabla visible con 22 filas y 132 variaciones QoQ |
| Consola del navegador | Cero errores |

## Qué no funcionó y por qué

1. La precisión esperada inicial del ASK no coincidía con el valor completo del
   warehouse. Se corrigió el ancla de prueba; no se alteró el dato.
2. Un control de correo encontró la dirección del autor incluida en la licencia de
   Plotly. La validación ahora distingue el código de terceros del contenido del
   proyecto, mientras continúa prohibiendo correos y credenciales en el payload.
3. Un patrón de secretos demasiado amplio confundió `ASK-km` con un token `sk-`.
   Se reemplazó por patrones de credenciales reales.
4. La primera narrativa conjugaba en singular la métrica plural `pasajeros` y mostraba
   un signo negativo después de `disminuyó`. La revisión visual detectó ambos casos y
   se corrigieron antes del cierre.
5. Los datos completos anteriores a 3T24 no estaban modelados en Gold. Se importaron
   los comunicados IR oficiales y se creó un parser específico. Para 1T21–3T22, el
   RASK publicado en MXN por ASK se normalizó a centavos de USD con el tipo de cambio
   promedio que Aeroméxico publicó en el mismo comunicado; la metodología queda
   expuesta en el desplegable de datos.

## Decisiones y supuestos

- RASK se presenta como monetización por ASK-km; ASK permanece como capacidad. No se
  usa ASK como sustituto de precio.
- La referencia visual guía densidad, tarjetas y jerarquía, pero no aporta datos ni
  conclusiones al prototipo.
- Plotly se incrusta desde la dependencia existente para que el archivo funcione sin
  internet. El peso cercano a 4.9 MB es deliberado en esta versión local.
- Las conclusiones describen movimientos observados y no atribuyen causalidad.
- La cobertura comienza en 2021Q1, primer comunicado trimestral disponible en el
  archivo oficial utilizado.
- La traducción a componentes Streamlit se hará solo después de recibir anotaciones y
  aprobación explícita de esta composición.

## Riesgos abiertos para la siguiente etapa

- Confirmar que la densidad, orden de lectura, colores y lenguaje ejecutivo cumplen
  la expectativa antes de trasladarlos a Streamlit.
- Mantener paridad visual y funcional al convertir el prototipo sin duplicar la lógica
  de métricas ni introducir una segunda fuente de datos.
- Vigilar que futuras revisiones de comunicados IR entren como nuevas versiones sin
  sobrescribir los artefactos preservados.

## Propuesta para análisis trimestral profundo

El historial automático de frases repetitivas no debe regresar. La alternativa
propuesta es ejecutar, después de cada cierre trimestral, un agente de análisis que:

1. reciba un paquete de evidencia cerrado con el comunicado, métricas Gold, QoQ, YoY,
   tráfico, capacidad, mercado y macro disponibles para ese trimestre;
2. produzca una salida estructurada con desempeño, impulsores observados, riesgos,
   preguntas abiertas y referencias exactas a artefactos o registros;
3. valide cada cifra contra Gold y rechace causalidad sin evidencia;
4. guarde borrador, versión, modelo, fecha y linaje en una tabla dedicada;
5. publique el texto únicamente después de aprobación humana.

Para el histórico 2021–2026 se ejecutaría un backfill controlado, trimestre por
trimestre, con la misma estructura y revisión. Esto permite análisis realmente
distintos sin convertir texto generado en una fuente de datos.

## Comandos para reproducir

```powershell
just stage11-prototype
just stage11-validate
uv run pytest -q tests/test_stage11_executive_prototype.py
uv run pytest -q
```

## Cierre de etapa

El prototipo cumple los criterios de datos, contenido, seguridad, interactividad y
respuesta visual de la Etapa 11. Se presenta localmente para anotaciones y el trabajo
se detiene aquí. No se iniciará la integración en Streamlit ni otra página sin un
`go` explícito del usuario.
