# Revisión de conversaciones del chat

Fecha: 9 de octubre de 2026.

- `review.html` muestra los mensajes de usuario y asistente por turno, con los candidatos A/B/C en comparación responsive.
- Los turnos se leen de sus marcadores explícitos; los textos anteriores sin marcadores siguen visibles completos.
- Marcadores incompletos o fuera de secuencia quedan como texto seguro, sin completar ni reordenar turnos.
- La revisión presenta negritas, listas, tablas, citas, código y enlaces HTTPS confiables; HTML de respuestas permanece inactivo.
- El texto original completo de cada respuesta queda en un desplegable; las calificaciones, notas, caché e importación/exportación conservan su comportamiento.
- La referencia `multi_turn` resume criterios de conversación y conserva la rúbrica completa en el detalle.
- No se atribuye a `multi_turn` un valor numérico ni se infiere una referencia desde las respuestas o el dashboard.
- Validación: `npm run check`, 154 pruebas web y `npm run build` pasaron.
- QA en navegador cubrió turnos de dos y tres pasos, Markdown seguro, legado, calificaciones y vista móvil.
- Límite: los enlaces fuera de la lista confiable se muestran como texto; no se activan.
