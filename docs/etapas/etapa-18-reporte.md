# Etapa 18 — Integración local para revisión

## Ajuste de lectura solicitado después de la publicación

La versión pública tiene dos pestañas: Lectura ejecutiva (KPI y resumen) y
Economía unitaria (gráficos y tabla trimestral). Comparten el selector de periodo.
La letra del resumen es de 13 px. Se eliminó la ventana de evidencia técnica del
HTML de consumo, incluido su contenido oculto. El análisis completo conserva
superíndices con enlaces HTTPS a fragmentos del reporte original para valores
reportados; las variaciones y descomposiciones calculadas no reciben citas.
La capacidad convertida enlaza a ASMs y declara la conversión en el título del enlace.

El expediente completo de 2T26 está en
`analysis_runs/quarterly_evidence/2026Q2/26bc91353505dd8b0ec7df38af8dd9d715d92c36ef6a2cbcde8d9e97c2a0aaf1`:
análisis versionado, paquete, cálculos, auditoría, cuatro documentos originales,
índice con hashes y HTML técnico. El texto aprobado no cambió.

Validación: dos pestañas, periodo compartido, gráficos y tabla en la segunda,
superíndices, ausencia de evidencia técnica y desbordamiento a 360/736/1440 px;
7 pruebas enfocadas aprobadas. Ver `tabs_checks.json` y `reader_publication.json`
en `docs/referencias/etapa-18`. La SEC bloqueó el acceso desde Chromium automatizado;
se verificaron los destinos contra las fuentes conservadas y se pudo leer el
reporte con la herramienta web, pero no se confirmó visualmente el resaltado remoto.
La sintaxis usa rangos Text Fragments documentados en https://web.dev/text-fragments/.

## Cierre y publicación — 6 de septiembre de 2026

El usuario autorizó expresamente: «Adelante con la publicacion al HTML».
La versión `26bc91353505dd8b0ec7df38af8dd9d715d92c36ef6a2cbcde8d9e97c2a0aaf1`
pasó la auditoría independiente final (17 afirmaciones, 84 nodos comprobados).
Se corrigió la estructura editorial pendiente en el detalle; el resumen literal
y sus cinco énfasis permanecen intactos. La advertencia de redondeo es no bloqueante.

Estado final: **published**. Se incorporó a
`prototypes/etapa-11/resumen_ejecutivo.html` y
`prototypes/etapa-18/resumen_ejecutivo.html`. Ambas copias tienen SHA-256
`ef08ce8b324ad892c61c97ebfe6bf460a6d5f2124484f0c54f252fb34ad8824f`.
Comprobante y respaldo previo: `docs/referencias/etapa-18/closure_status.json`.

El archivo publicado pasó las comprobaciones en navegador a 360, 736 y 1440 px:
texto exacto, contexto visible, tarjeta blanca, ventanas, teclado/foco y navegación
trimestral, sin solicitudes de red ni errores. Comprobante:
`docs/referencias/etapa-18/published_browser_checks.json`.
Se aprobaron 33 pruebas enfocadas tras añadir el registro de autorización pendiente
de auditoría, además de las 66 pruebas previas de esta versión y su presentación.
Gold y los expedientes congelados conservan sus hashes. No se publicó en Streamlit
ni se inició la Etapa 19.

Para regenerar preservando esta publicación, usar `src.analysis_agent.stage18`
con `--record` apuntando a esta versión y `--output` al HTML de destino.
El constructor histórico de Etapa 11 genera su plantilla anterior sin análisis;
su incorporación al flujo general de mantenimiento queda para Etapa 20.

Las secciones siguientes conservan el reporte de revisión previo al cierre.

Fecha: 6 de septiembre de 2026.

## Resultado visible

`prototypes/etapa-18/resumen_ejecutivo_revision.html` conserva literalmente el título, las cuatro viñetas y los cinco énfasis del usuario. La tarjeta es blanca. Leer análisis completo y Ver evidencia abren ventanas dentro del flujo de lectura. La navegación muestra el contenido de 2T26 únicamente en ese trimestre.

Se agregó una nota visible de contexto: el crecimiento interanual supera 3T25 y 4T25; 1T26 creció 13.3%, frente a 12.6% en 2T26. RASK/CASK utilizan asiento-kilómetro ofrecido. La evidencia distingue el cálculo 10.3% desde niveles redondeados del 10.5% reportado por la compañía para TRASM. El texto original permanece intacto.

La auditoría independiente está en `analysis_runs/audits/literal_integration_review.json`. La nota responde al hallazgo sobre el alcance histórico. Esta presentación todavía requiere revisión de la versión conjunta, que incluye resumen literal, aclaración y detalle.

## Integración implementada

- `src.analysis_agent.stage18` construye un HTML autónomo desde datos del dashboard y versiones exactas autorizadas.
- Comprueba instrucciones, contenido, evidencia, auditoría y aprobación vigentes bajo el bloqueo del registro antes de exportar.
- Exporta solamente las afirmaciones autorizadas y sus fuentes; excluye el panel privado de revisión, los comentarios y las narrativas deterministas antiguas.
- Identifica versiones por trimestre; rechaza dos versiones de un mismo periodo.
- Conserva un manifiesto público de versiones y huellas y un comprobante privado de publicación.
- Escribe primero un intento inmutable, reemplaza el HTML atómicamente y registra su hash final. Un reintento vuelve a comprobar la aprobación.
- El estado `published` exige aprobación vigente, comprobante íntegro y coincidencia con los bytes del HTML. Si cambia el archivo, deja de demostrar publicación; una revocación elimina la elegibilidad para futuras exportaciones.

El archivo ya exportado es una copia estática: una revocación no puede retirar copias descargadas ni cambiar una pestaña abierta. Se debe regenerar el destino para retirar contenido revocado.

## Validación

- 39 pruebas enfocadas de Etapas 11, 17 y 18 aprobadas.
- Navegador: 360, 736 y 1440 px; texto literal, énfasis, fondo blanco, ventanas, Escape, devolución de foco, navegación trimestral, ausencia de desbordamiento y errores JavaScript.
- Comprobante: `docs/referencias/etapa-18/browser_checks.json`.
- El dashboard de consumo `prototypes/etapa-18/resumen_ejecutivo.html` muestra el estado pendiente de aprobación. No contiene el borrador literal.
- El HTML original de Etapa 11 y Gold no se modificaron por esta implementación.

## Operación

Propuesta visual:

```powershell
.\.venv\Scripts\python.exe -m src.analysis_agent.stage18_preview
```

Consumo sin análisis aprobados:

```powershell
.\.venv\Scripts\python.exe -m src.analysis_agent.stage18 --output prototypes/etapa-18/resumen_ejecutivo.html
```

Para incorporar versiones aprobadas, agregar `--record` con cada registro autorizado que deba aparecer. La lista es el conjunto completo a exportar, no una actualización incremental. La versión literal del usuario aún vive como propuesta editorial y no se puede pasar como registro analítico auditado a este comando.

## Pendiente para cerrar la etapa

Aceptar la aclaración visible y cerrar la versión estructurada que conserva el texto literal, con auditoría y aprobación específicas de ese contenido conjunto. Después se puede incorporar al HTML definitivo. No se inició la Etapa 19 ni el backfill.
