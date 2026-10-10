# F2.9 · Estado del piloto, etapa 2

- Ejecución: commit `73db4d1c638e0c208feae433642e652485f5dfe6`; 15 casos, 60 ejecuciones planeadas.
- Identidad: fixture SHA-256 `824db2fb0bd1f1e58c08a16c234e8fe4d9d280f783e9010ded5ad8912b64092e`; prompt SHA-256 `439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5`.
- Estado: 9 intentos; 8 respuestas completas y un error en `en_am_rask`; los otros tres candidatos no comenzaron.
- Costo conocido: US$0.05460125; costo total desconocido por uso incompleto. La campaña quedó detenida y no se reanudó.
- Diagnóstico: sesión remota terminó como `failed` con un mensaje genérico de error interno, sin código; las lecturas no devolvieron turnos ni elementos para reconciliar uso.
- Revisión: UI A–D publicada en [review.html](https://salvamalfa.github.io/aeromexico-tracker/review.html) por [PR119](https://github.com/salvamalfa/aeromexico-tracker/pull/119); el JSON comparativo espera la reconciliación del consumo.
- No solicitar calificación sobre esta entrega incompleta; la reserva de US$8 ya fue autorizada y financiada.
- Validación: 130 pruebas focalizadas y 991 pruebas públicas más 14 subtests pasaron; 6 omisiones por artefactos locales o preview.
