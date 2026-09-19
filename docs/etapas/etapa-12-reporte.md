# Etapa 12 — Especificación y diagnóstico del Analysis Agent

Estado: IMPLEMENTADA LOCALMENTE — PENDIENTE DE REVISIÓN Y ACEPTACIÓN HUMANA.

## Resumen ejecutivo

Se guardó el plan por etapas, se especificaron los contratos futuros y se generó
una matriz reproducible de los 22 trimestres 2021Q1–2026Q2. La maqueta local permite
revisar jerarquía editorial, fuentes, estados sin análisis y evidencia insuficiente.
Su prosa está marcada como ilustrativa; los KPI proceden de la serie vigente.

No se ejecutó un analista ni se certificó un corte histórico. La Etapa 13 permanece
sin iniciar. Aceptar esta entrega y aprobar un análisis son actos separados.

## Qué se construyó

- Plan acordado: `docs/plan/17-analysis-agent-plan.md`.
- Alcance de esta etapa: `docs/plan/18-etapa-12-especificacion-diagnostico.md`.
- Contratos documentales: `docs/analysis-agent/contratos-v1.md`.
- Generador de solo lectura sobre datos: `src/analysis_agent/stage12.py`.
- Matriz JSON/CSV: `docs/referencias/etapa-12/`.
- Maqueta independiente: `prototypes/etapa-12/analysis_agent.html`.
- Ocho pruebas nuevas del diagnóstico; comandos `stage12-prototype` y
  `stage12-validate` registrados en `justfile`.
- Capturas y observaciones de QA: `docs/assets/etapa-12/`.

No se instalaron dependencias ni se descargaron fuentes. Se verificaron los 22 PDF
IR ya preservados en Bronze mediante SHA-256. Se leyeron el warehouse y los índices
Silver SEC existentes. Los hashes de esos insumos están en el diagnóstico.

## Hallazgos verificados

| Dominio | Resultado | Implicación |
|---|---|---|
| Cinco métricas operativas | 22/22 trimestres completos | Base actual del prototipo disponible |
| Seis métricas financieras | 8/22 completos | Extraer lo publicado de 2021Q1–2024Q2 |
| Ocho métricas de costos/consumo | 8/22 completos | Ampliar componentes para análisis financiero histórico |
| Comunicados IR locales | 22/22 hashes coincidentes | Los archivos están íntegros respecto del catálogo |
| Comparativos posteriores | 4 trimestres de ingreso | Revisar fuentes contemporáneas de 2024Q3–2025Q2 |
| Cortes históricos certificados | 0/22 en esta etapa | Falta acreditar publicación y versión; no confundir con ausencia histórica del documento |

Los ingresos de 2024Q3, 2024Q4, 2025Q1 y 2025Q2 provienen de los reportes SEC de
2025Q3, 2025Q4, 2026Q1 y 2026Q2, respectivamente. El caso visible 2024Q3 muestra
reporte 2025Q3 con filing 2025-11-12. Es evidencia de un comparativo posterior,
no una prueba de la cifra disponible al publicarse el reporte original.

El catálogo de artefactos tiene `downloaded_at`, pero no los campos que acrediten
publicación y disponibilidad de versiones. Las fechas SEC se muestran como
candidatos documentales; no se copian a `cutoff_date`.

Se observó que macro contiene agregaciones `average` y `close`; no son duplicados.
El diagnóstico cuenta meses distintos de `average`. La cobertura de aeropuertos y
grupos indica existencia de algún dato por mes, no completitud del mercado.

## Validaciones

Comando ejecutado:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_stage12_diagnosis.py tests/test_stage11_executive_prototype.py tests/test_stage9_lineage.py tests/test_stage9_precedence.py
```

Resultado: **30 passed in 27.54s** (8 nuevas + 22 de regresión enfocada).

| Comprobación | Resultado |
|---|---|
| Conteos por trimestre reconciliados con SQL independiente | PASS |
| Claves duplicadas rechazadas; nulos no convertidos en cero | PASS |
| Meses calendario exactos y agregaciones separadas | PASS |
| Comparativos posteriores señalados sin certificar corte | PASS |
| Archivo válido, alterado, ausente y ruta fuera de Bronze | PASS |
| Escape de contenido y rechazo de enlaces no oficiales | PASS |
| Ilustración explícita, sin runtime de aprobación/red/persistencia | PASS |
| Regeneración idéntica de JSON, CSV y HTML | PASS |
| Warehouse, Gold y HTML de Etapa 11 sin cambios por generación | PASS, hashes antes/después |

Los tests no sustituyen la futura auditoría financiera o temporal ni la aprobación
del usuario. No se ejecutó una ingesta o reconstrucción completa, ajena a esta etapa.

## QA visual y funcional

Se abrió la maqueta mediante el navegador in-app y un servidor limitado a su
carpeta local. Capturas completas guardadas en `docs/assets/etapa-12/`.

| Escenario | Observación |
|---|---|
| Escritorio 1280 × 900 | Cinco tarjetas, lectura y desplegables legibles |
| Tablet 736 × 900 | Tarjetas 3+2; ancho de contenido 721, sin desbordamiento de página |
| Móvil 360 × 800 | Tarjetas en dos columnas; ancho de contenido 345, sin desbordamiento de página |
| Matriz en móvil | Tabla de 438 px dentro de contenedor desplazable de 319 px; página sin overflow horizontal |
| 1T21 | Flecha previa deshabilitada y comparables `No disponible` |
| 2T26 | Métricas y selección final correctas; extremo siguiente deshabilitado |
| Sin análisis / evidencia insuficiente | Mensajes respectivos visibles; detalle editorial oculto |
| Selección desde matriz | Abre trimestre elegido en maqueta y actualiza fuentes |
| Detalle 3T24 | Expone fuente SEC posterior, filing y advertencia correspondiente |
| Teclado | Flecha izquierda cambia pestaña y traslada foco correctamente |
| Consola | Sin errores ni advertencias registradas |

Los cambios temporales de tamaño del navegador se restablecieron. La maqueta queda
abierta como entrega; el archivo HTML también puede abrirse directamente sin servidor.

## Qué no funcionó o no se puede afirmar todavía

- Gold actual no basta para acreditar información disponible en una fecha pasada.
  Se documentó la brecha en vez de asignar fechas de descarga como publicación.
- Los ocho trimestres financieros no equivalen a ocho paquetes contemporáneos:
  cuatro usan comparativos posteriores. Se amplió el trabajo documental previsto
  para las etapas 13–14 sin cambiar sus datos.
- La matriz móvil necesita desplazamiento horizontal dentro de su contenedor;
  no se comprimió el texto hasta hacerlo ilegible.
- Esta es una maqueta de estructura. La calidad de una tesis real solo se podrá
  revisar cuando exista el paquete de evidencia y el analista, en etapas posteriores.

## Decisiones y supuestos

- Separar diagnóstico actual, elegibilidad temporal y aprobación; no usar un único
  indicador verde que confunda esos tres estados.
- Mantener el corte histórico desconocido como null y explicar el motivo.
- Contratos v1 documentales: no se crearon tablas productivas ni un motor de estados.
- Reutilizar el payload de KPI actual sin cambiar la lógica ni la prosa del
  prototipo de Etapa 11. La maqueta de Etapa 12 es un archivo distinto.
- Toda fuente complementaria ausente limita su tema; evidencia esencial ausente
  bloquea una tesis que dependa de ella.
- No se realizó push, deploy ni instalación. La aprobación formal sigue pendiente;
  el commit de cierre se pospone hasta aceptar la etapa.

## Riesgos y siguiente etapa

La Etapa 13 deberá completar la extracción de reportes de 2021Q1–2024Q2 y revisar
las fuentes contemporáneas de 2024Q3–2025Q2. Los problemas de redondeo, monedas,
reorganización y ajustes se documentarán por reporte, sin forzar comparabilidad.
La Etapa 14 deberá acreditar publicación y versión para los 22 cortes.

Se entrega para anotaciones. **No comenzar la Etapa 13 sin autorización explícita.**

## Revisión visual solicitada · 2026-09-05

- Lectura ejecutiva y sus ventanas se identifican en azul claro como el módulo
  destinado al dashboard. Las etiquetas y el color de alcance son ilustrativos.
- Los accesos al análisis completo y a la evidencia están dentro de la tarjeta;
  ahora abren ventanas modales, en lugar de desplegar contenido debajo.
- La aprobación y la cobertura quedan identificadas como interfaz de trabajo.
- Comprobación en navegador: apertura de ambos diálogos, cierre visible, Escape
  y devolución del foco. A 360 × 800, la ventana de evidencia queda dentro del
  viewport (324 × 780); documento de 360 px, sin desbordamiento horizontal.
- Regeneración y 21 pruebas enfocadas aprobadas después del cambio.
- El servidor local de revisión se reinició tras detectar conexión rechazada.

Sigue pendiente la aceptación visual de Etapa 12. No se inició Etapa 13.

## Aceptación humana · 2026-09-05

El usuario autorizó continuar con «Adelante» después de revisar los ajustes de
ventanas y alcance visual. Etapa 12 aceptada; Etapa 13 autorizada. Esta aceptación
no aprueba contenido trimestral ni autoriza Etapa 14.
