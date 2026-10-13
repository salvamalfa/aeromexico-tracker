# Chat · periodo seleccionado y cierre de fase 2

El 12 oct 2026, el dueño entregó las calificaciones finales, consideró las respuestas buenas en general y autorizó corregir el uso del trimestre mediante un ajuste pequeño del prompt, sin nuevas evaluaciones pagadas. Se mantienen las aprobaciones de [R2, contenido y modelo](20261012-chat-fase2-r2-contenido-stage3.md).

La revisión contiene 30 calificaciones: 16 correctas y 14 con problema; 13 notas mencionan el periodo. En 12 de esos casos el evaluador envió contexto vacío; no prueban que el dashboard pierda la selección. La UI ya envía el periodo vigente en cada mensaje. Las calificaciones permanecen privadas y no se reinterpretan como aprobadas.

El ajuste usa el periodo seleccionado cuando la pregunta lo omite, conserva la prioridad del periodo explícito y del seguimiento inequívoco, y elimina una aclaración contradictoria del ejemplo. Si falta otro campo, pregunta solo por ese campo. La búsqueda de evidencia puede reformular términos en el idioma del pasaje: las búsquedas vacías de «combustible» no demostraban falta de acceso a los reportes ingleses sobre «fuel».

Se autorizan la implementación y publicación de este ajuste; se actualiza el recibo del prompt con su hash exacto. La activación de R2 y sus capacidades aprobadas continúa el cierre autorizado de fase 2 tras recibir esta revisión. Se verifican el contexto por turno, los recibos y el despliegue con pruebas offline y health, sin llamadas pagadas ni nueva ronda de calificación. Esto no acredita cumplimiento del modelo posterior al cambio ni el gate original de 70 casos/safety.

Procedencia privada: dataset `1fe493d362418df0832fb87a62192bac4f9558e3a59c00b31a35d4ff858cae80`; JSON `f2b9017a427503f0eab9c80e62bcaf096bd616ce8a494a7c55af8c6eb0e177ba`; calificaciones `2e32fb7bba6b61336d9bf74bebcd3e6a18f24d0990a23e9734d0d17525978951`. Registro de la autorización: 2026-10-13T00:44:04Z (12 oct en Ciudad de México).
