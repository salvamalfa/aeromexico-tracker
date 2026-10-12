# F2.9 · Guardas de evaluación, etapa 2
- El evaluador fija el SHA-256 raw aprobado `824db2fb0bd1f1e58c08a16c234e8fe4d9d280f783e9010ded5ad8912b64092e` y lee los bytes una sola vez antes de parsear o preparar la campaña.
- La exportación combina fragmentos reanudados solo con identidad idéntica y conserva hashes de origen por caso.
- Validación de pin, evaluación y campaña: 37 pruebas pasaron; exportador de fragmentos: 8 pruebas pasaron.
- La ejecución original `73db4d1c638e0c208feae433642e652485f5dfe6` y sus ocho respuestas completas permanecen intactas.
- El consumo fallido sigue siendo desconocido; no se ejecutó ningún proveedor ni se reintentó la campaña.
- Seguimiento en [PR120](https://github.com/salvamalfa/aeromexico-tracker/pull/120); no se solicita nueva aprobación ni calificación.
