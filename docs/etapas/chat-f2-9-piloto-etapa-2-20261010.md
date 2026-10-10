# F2.9 · Estado del piloto, etapa 2

- Ejecución: commit `73db4d1c638e0c208feae433642e652485f5dfe6`; 15 casos, 60 ejecuciones planeadas.
- Identidad: fixture SHA-256 `824db2fb0bd1f1e58c08a16c234e8fe4d9d280f783e9010ded5ad8912b64092e`; prompt SHA-256 `439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5`.
- Estado: 9 intentos; 8 respuestas completas y un error en `en_am_rask`; los otros tres candidatos no comenzaron.
- Costo estimado de las ocho respuestas completas: US$0.05460125; no es importe facturado. El costo total de campaña es desconocido; quedó detenida y no se reanudó.
- Diagnóstico: sesión remota terminó como `failed` con un mensaje genérico de error interno, sin código; las lecturas no devolvieron turnos ni elementos para reconciliar uso.
- Revisión: UI A–D publicada en [review.html](https://salvamalfa.github.io/aeromexico-tracker/review.html) por [PR119](https://github.com/salvamalfa/aeromexico-tracker/pull/119); el JSON comparativo espera la reconciliación del consumo.
- No solicitar calificación sobre esta entrega incompleta; la reserva de US$8 ya fue autorizada y financiada.
- Validación: 130 pruebas focalizadas y 991 pruebas públicas más 14 subtests pasaron; 6 omisiones por artefactos locales o preview.
- Parche posterior (`a52bc48a75ac0d549e6080da16a6988fd8503cbb`), separado de la ejecución original (`73db4d1c638e0c208feae433642e652485f5dfe6`): futuros errores conservan IDs privados y metadatos saneados, distinguen EOF, respuesta sin texto, HTTP y fallo terminal sin reenviar inputs; 181 pruebas focalizadas offline pasaron en integración y runtime smoke sin proveedor.
