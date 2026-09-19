# Etapa 17 · Auditoría independiente y aprobación versionada

## Revisión editorial posterior solicitada por el usuario

La entrega original descrita abajo se conserva como antecedente. El usuario pidió
una lectura de negocio para todos los reportes: título directo, viñetas con ideas
principales en negritas y explicación de conceptos antes de siglas entre paréntesis.
Se actualizó la skill del proyecto y se reescribieron resumen y análisis completo.
Se mantiene asiento-kilómetro ofrecido; no se incorporan afirmaciones no demostradas
sobre aceleración de ingresos ni causalidad. La versión editorial más reciente y su
auditoría constan en `business_receipt.json` del expediente de revisión. Sigue siendo
una revisión dentro de Etapa 17, sin aprobación de contenido ni publicación.

Implementada para revisión del usuario. Autorizada mediante «Adelante» después de
la explicación de Etapa 17. No se recibió aprobación del análisis ni autorización
de Etapa 18.

## Resultado visible

[Abrir análisis auditado](../../prototypes/etapa-17/audited_analysis.html).

El auditor independiente revisó las dieciséis afirmaciones de 2T26 contra el paquete
cerrado, reprodujo los cálculos y recalculó independientemente 252 nodos derivados.
La primera revisión encontró un bloqueo de cita y tres mejoras. Se conservó la
versión original y se creó una revisada:

- Cita retrospectiva de combustible añadida, separada de la expectativa futura.
- Precisión explicada correctamente: el paquete combina tablas e importes narrativos.
- Referencia directa a crecimiento de RASK añadida en el resumen comercial.
- Preguntas reformuladas y contexto de demanda de junio/capacidad atribuido y citado.

La reauditoría cerró los cuatro hallazgos, sin nuevos bloqueos ni advertencias.
Las cifras y los insumos no cambiaron. Resumen: 194 palabras; detalle: 724 palabras.

Versión revisada:
`efa01d1304aeca7348887b0c34a2f89687c4ec3c11be29746538c509313128cc`.
Estado actual: **validated**, sin autorización de contenido. La versión anterior
conserva su auditoría con cambios solicitados y permanece draft.

## Implementación y comprobación

Se implementaron eventos inmutables con secuencia, enlaces por hash, cabecera y
control de escritor; auditoría, comentarios, aprobación exacta y revocación. Una
proyección SQLite local contiene `fact_quarterly_analysis` y `analysis_events`.
Los originales y eventos siguen fuera de las carpetas regeneradas del pipeline.

El contrato de consumo rechaza versiones sin aprobación humana, vuelve a verificar
los insumos y entrega identificadores de aprobación/auditoría para comprobarlos
al incorporar el contenido. El consumidor futuro debe mantener el bloqueo durante
su escritura atómica. No se implementó ni ejecutó publicación en esta etapa.

- **289 pruebas del proyecto pasan**, 22 específicas del ciclo de revisión.
- Los cuatro casos semánticos adversariales fueron rechazados por el auditor:
  correlación presentada como causa, outlook como garantía, instrucción dentro de
  una fuente y sustitución de RASK/CASK con referencias existentes.
- El último ataque pasó el control mecánico en memoria; la auditoría semántica
  lo rechazó. No se atribuye esa capacidad a una regla automática inexistente.
- Revisión técnica independiente: tres hallazgos corregidos sobre reutilización
  de autorización retirada, vigencia de payload y repetición de revocaciones.
- Casos de consentimiento incorrecto, cambio de versión, auditoría fallida,
  historial alterado/truncado, interrupción y bloqueo concurrente comprobados.
- La prueba positiva de aprobación usa autorizaciones ficticias exclusivamente en
  almacenamiento temporal. En los expedientes reales no existe aprobación.
- Vista local comprobada a 360, 736 y 1440 px: comparación, modales, Escape, foco,
  ausencia de desbordamiento y cero solicitudes de red al abrir.

[Comprobantes](../referencias/etapa-17/README.md).

## Limitaciones y siguiente decisión

Auditoría semántica asistida por Codex; no es un clasificador automático ni garantía
absoluta. El piloto sigue con cobertura acotada, cinco restricciones de conciliación
y sin contribuciones aisladas de divisas/coberturas/mezcla. No se inició backfill.
Los modelos del analista y auditor se registran como desconocidos con motivo.

La autenticidad del consentimiento se verifica en la conversación por el coordinador;
los archivos locales no constituyen firma digital ni control de acceso externo.
La proyección SQLite es privada y reconstruible. Las interrupciones dudosas bloquean
promoción; el manual de recuperación operativa completa corresponde a Etapa 20.

Esperar comentarios y aceptación de esta etapa. Aprobar el análisis de esta versión
y autorizar avanzar a Etapa 18 son decisiones diferentes. El dashboard permanece
sin cambios; no hay exportación de borradores, comentarios ni aprobaciones a Gold.
