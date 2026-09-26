# 16 — Etapa 11: Prototipo HTML del resumen ejecutivo

## Objetivo

Diseñar y entregar una sola vista ejecutiva, local y autocontenida, conectada al
backend curado del tracker. Esta etapa fija la jerarquía visual y el lenguaje de
negocio antes de trasladar el diseño aprobado a Streamlit.

## Alcance

- Generar únicamente el resumen ejecutivo; no construir ni rediseñar otras páginas.
- Consumir `v_aeromexico_quarterly` como fuente canónica y no copiar datos del HTML de
  referencia.
- Incluir todos los trimestres comparables que tengan RASK, CASK, ASK, factor de
  ocupación y pasajeros. Tras incorporar los comunicados oficiales preservados en
  Bronze, la cobertura esperada es `2021Q1–2026Q2`.
- Mantener el resultado local. No modificar la aplicación Streamlit pública, no hacer
  push a `master` y no desplegar.
- Conservar el diseño de negocio compacto de la referencia y adaptar los tokens del
  sistema visual proporcionado por el usuario a una superficie clara y accesible.

## Modelo de presentación

Una única función construirá un payload validado con:

- valores trimestrales de RASK, CASK, ASK, factor de ocupación y pasajeros;
- variación contra el trimestre anterior y contra el mismo trimestre del año previo;
- margen unitario calculado como `RASK - CASK`;
- conclusiones y narrativa deterministas, limitadas a movimientos observables;
- cobertura, fecha de corte, fuente y estado de cada comparación.

La ausencia de comparable debe mostrarse como `No disponible`; nunca se sustituye por
cero ni se infiere desde el HTML de referencia.

## Estructura visual

1. Encabezado compacto “Aeroméxico Tracker” y navegación trimestral mediante flechas.
2. Cinco tarjetas KPI con valor, QoQ y YoY; las variaciones positivas se distinguen
   en verde y las negativas en rojo.
3. Bloque de lectura ejecutiva con trimestre dinámico y placeholder explícito para
   el futuro output del agente de análisis.
4. Gráfica principal RASK vs CASK y barras de margen unitario en doble eje, con
   ventana seleccionable de historia completa, 12, 8 o 4 trimestres.
5. Gráfica pasajeros vs RASK para leer volumen y monetización.
6. Scatter factor de ocupación vs RASK, con color por año y trimestre identificado.
7. Datos trimestrales dentro de un desplegable, con variación QoQ junto a cada valor.

La tabla marca con una línea oscura cada cambio de año. La metodología histórica se
conserva en metadata y documentación, pero no ocupa espacio antes de la tabla.

El encabezado usa un azul sólido y la lectura ejecutiva se organiza verticalmente,
justo debajo de los KPI: título y trimestre en una línea, seguidos por el placeholder
del agente. En economía unitaria, las
barras de margen permanecen al fondo y las líneas RASK/CASK se dibujan por encima.

El historial narrativo determinista se retira del prototipo. Un análisis histórico
solo volverá cuando exista un proceso independiente, versionado y trazable que
produzca contenido específico para cada trimestre.

## Tecnología y seguridad

- HTML, CSS y JavaScript autocontenidos.
- Plotly se incrusta desde la dependencia ya instalada; no se usa CDN ni red en
  runtime.
- El payload se serializa de forma segura y se escapan textos antes de insertarlos.
- El generador se ejecuta desde Python y falla si el warehouse o la cobertura mínima
  no están disponibles.
- El HTML es generado; la lógica de métricas vive en Python y podrá reutilizarse en la
  integración posterior con Streamlit.

## Entregables

- Modelo de presentación reutilizable.
- Generador reproducible del HTML.
- HTML local autocontenido del resumen ejecutivo.
- Pruebas de datos, cálculos, seguridad, contenido y estructura.
- Validador ejecutable de Etapa 11.
- `docs/etapas/etapa-11-reporte.md`.

## Gate

El HTML se abre localmente para anotaciones. La etapa se detiene después de presentar
el prototipo y no comienza la integración con Streamlit hasta recibir aprobación
explícita del usuario.
