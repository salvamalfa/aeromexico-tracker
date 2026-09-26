# Etapa 16 · Primera lectura trimestral

Implementada para revisión editorial. La autorización «Adelante» aceptó Etapa 15
con sus restricciones y permitió desarrollar Etapa 16. No autoriza Etapa 17 ni
aprueba el contenido para consumo.

## Entrega

[Abrir lectura local](../../prototypes/etapa-16/quarterly_analysis.html).

El piloto de 2T26 tiene una tesis sobre crecimiento del ingreso por capacidad y
mayor presión del costo unitario. Contiene 194 palabras de resumen, 709 de detalle
y 16 afirmaciones clasificadas con referencias. Las cifras se insertan por Python.
Las atribuciones de la compañía mantienen fragmentos literales de respaldo.

El bloque azul y sus modales representan la propuesta para el dashboard. Los
controles explicativos del proceso están en una zona blanca separada. Desde la
lectura se abren el análisis completo y la evidencia por afirmación, con cierres
explícitos, Escape y devolución del foco. El dashboard de Etapa 11 no se modifica.

Se creó una skill del proyecto, el exportador de contexto cerrado, un importador
de borradores y controles mecánicos. La versión se conserva fuera de los directorios
regenerados, en `analysis_runs/drafts`, con hashes de contenido, instrucciones y
código. Repetir la misma importación reutiliza la versión; cambiar contenido crea
otra. No hay aprobación implícita ni comandos de publicación.

## Validación

- 267 pruebas del proyecto pasan; 17 casos corresponden al nuevo módulo.
- Rechazo de cifras literales, referencias rotas, unidades/periodos incompatibles,
  valores ausentes, fragmentos alterados, contexto incorrecto y estado approved.
- El cálculo se reproduce contra el paquete exacto y los originales verificados.
- Inmutabilidad e idempotencia comprobadas; contenido HTML escapado.
- Skill validada con el verificador de skill-creator.
- Navegación, modales superpuestos, Escape, foco y ancho sin desbordamiento a
  360, 736 y 1440 px; cero solicitudes de red al abrir, cero errores del navegador.
- Inspección visual de escritorio y detalle móvil realizada sobre capturas.

[Comprobantes](../referencias/etapa-16/README.md).

## Límites que siguen vigentes

Los controles son mecánicos. No sustituyen la auditoría independiente de fidelidad,
causalidad, contradicciones ni lenguaje genérico de Etapa 17. El estado del análisis
es `draft`, sin aprobación humana y sin publicación.

La cobertura del piloto es acotada. El comunicado respalda explicaciones atribuidas
y expectativas conocidas al corte; no se añadieron fuentes de negocio externas ni
acontecimientos posteriores. No se aíslan FX, coberturas, mezcla o precio de mercado.
Las variaciones desde tablas redondeadas pueden diferir del comunicado; no se mezclan
con cifras más precisas de la prosa. Se mantienen las cinco discrepancias de alcance
de CASK frente a gasto operativo/ASK, sin atribuir el margen financiero al puente.

La skill puede invocarse por ruta desde el workspace padre. El descubrimiento por
proyecto requiere trabajar dentro de Aeromexico Tracker. El identificador de modelo
no está expuesto verificablemente; queda null con motivo, no una etiqueta supuesta.

## Siguiente acción

Revisar tesis, contenido y extensión con el usuario; incorporar comentarios como
otra versión dentro de Etapa 16. Esperar autorización explícita antes de Etapa 17.
