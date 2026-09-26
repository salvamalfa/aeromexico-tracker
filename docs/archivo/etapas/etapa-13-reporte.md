# Etapa 13 · Cobertura financiera histórica

Estado: implementada localmente; pendiente de revisión y aceptación humana.
Autorización: «Adelante», tras aceptar Etapa 12. Fecha de entrega: 2026-09-05.

## Resultado visible

[Abrir el reporte financiero](../../prototypes/etapa-13/financial_history.html).
Incluye cobertura antes/después de los 22 trimestres, faltantes, diferencias entre
fuentes y 18 fichas con cifras originales, unidades, página y enlace oficial.
Es una entrega de comprobación del desarrollo, no contenido del dashboard.

Se extrajeron 299 registros de 18 PDF de 1T21–2T25: 290 cifras y 9 tipos de cambio.
Los 14 primeros trimestres reciben evidencia financiera; otros cuatro recuperan
su reporte propio para contrastarlo con comparativos posteriores. De 252 campos
objetivo, 214 están extraídos y 38 tienen una ausencia o definición distinta
documentada. No se convierten faltantes en cero ni se distribuyen gastos agrupados.

## Comprobación

- 217 pruebas del proyecto pasan; 25 enfocadas cubren extracción, contrato e integración.
- 94 conciliaciones dentro de tolerancias de precisión publicada.
- 64 comparaciones con la cobertura congelada: 61 compatibles con redondeo y
  tres diferencias documentales identificadas, sin armonización silenciosa.
- Cuaderno ejecutado de principio a fin: reextracción idempotente y huellas de
  las tablas Gold idénticas antes y después.
- PDF representativos inspeccionados visualmente: 1T21, 1T22, 4T22 y 1T24.
- HTML autocontenido verificado a 1440 y 390 px, incluyendo interacción con fuentes;
  revisión adicional a 360 y 736 px, sin desbordamiento de página ni errores JavaScript.

La ampliación añade un contrato Silver y un paso de extracción al pipeline.
Se actualizaron los controles que esperaban 29 tablas y 34 pasos: ahora son
30 tablas y 35 pasos. Tras pasar los controles, se regeneró el comprobante público
de validación. No se cambiaron las cifras Gold ni se desplegó el dashboard.

El lector portátil del plugin usaba `100vw` en su barra superior, provocando 8 px
de desbordamiento con scrollbars clásicos de Windows. El constructor del proyecto
aplica una corrección CSS limitada a esa barra y verifica el HTML antes de promoverlo.
El plugin instalado no se modificó; no se desactivó ninguna comprobación.

## Límites que debes revisar

En 3T24 el reporte propio muestra resultado neto de USD 195 millones; el comparativo
posterior, USD 211 millones. La diferencia se localiza contablemente en resultado
antes de impuestos (254 → 255) e impuesto (59 → 44), con cifras redondeadas.
El consumo cambia de 461.976 a 461.394 millones de litros. No se encontró una
explicación documental de las causas de estas revisiones. Quedan señaladas en
la configuración con valores y hashes exactos de ambas fuentes.

Por tanto, «sin diferencias de extracción sin explicar» no significa que se conozca
la causa económica de esos cambios de fuente. La aceptación del tratamiento de
estas tres discrepancias permanece pendiente de tu revisión.

La descarga actual de un documento antiguo no prueba que esa copia estuviera
disponible al corte histórico. Etapa 14 deberá certificar versiones y publicación.
Los importes ajustados por reestructura o PLM conservan definiciones separadas.
La conversión analítica a USD no hace intercambiables MXN, USD de conveniencia y
USD funcional. Los apéndices redondeados a millones limitan la precisión recuperada.

## Expediente y reproducción

[Índice de evidencia y comandos](../referencias/etapa-13/README.md).
[Cuaderno ejecutado](../referencias/etapa-13/verification.ipynb).

Etapa 13 permanece abierta para comentarios. No se inicia Etapa 14 sin autorización
explícita; tampoco se ha generado ni aprobado un análisis trimestral.

## Aceptación humana · 2026-09-05

El usuario acepta los faltantes anteriores a 2024, prioriza lecturas recientes y delega la elección documental de 3T24. Se conserva el reporte original para la lectura histórica y la revisión posterior por separado. Autoriza Etapa 14 con «Continua».
