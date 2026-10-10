# F2.9 · Finalización de etapa 2

- Ejecuciones fuente: piloto `73db4d1c638e0c208feae433642e652485f5dfe6` y continuación `8f671846f819db57dd0a96d70074d4d568551100`.
- La continuación se detuvo con SIGINT controlado. Conserva dos corridas cerradas (6 y 15 casos) y un progreso SolLow agregado de 13 casos sin filas detalladas persistidas; esas 13 respuestas se perdieron y no se reconstruyen desde agregados.
- Una lectura GET recuperó el turno remoto completado e idle del caso activo; uso completo de 137,951 tokens de entrada y 499 de salida. La latencia no es válida y la recuperación no autocalifica ni infiere llamadas a herramientas.
- La finalización pendiente agrupa 29 solicitudes nuevas: 13 reemplazos del checkpoint perdido, un caso SolLow nunca intentado y 15 casos SolMedium. No repite el caso recuperado ni el fallo original.
- El plan fija los nueve artefactos fuente por hash y bloquea el replay automático; antes de otra corrida siguen siendo requisito un plazo duro y un checkpoint detallado por caso antes de borrar progreso.
- De la reserva autorizada de US$8, el arrastre estimado conservador es US$2.274144375 y quedan US$5.725855625. El progreso de 13 casos permanece como agregado; el fallo original conserva uso individual desconocido. No son importes facturados.
- La UI A–D está en [review.html](https://salvamalfa.github.io/aeromexico-tracker/review.html); seguimiento técnico en [PR120](https://github.com/salvamalfa/aeromexico-tracker/pull/120). Esta actualización no ejecutó proveedor ni modificó los artefactos fuente.
