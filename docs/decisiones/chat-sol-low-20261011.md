# Chat: Sol con esfuerzo low

El 11 de octubre de 2026, el dueño eligió `gpt-6.1-sol` con `CHAT_REASONING_EFFORT=low` y autorizó activar esa configuración en producción. F2.0 contiene el control explícito; primero debe desplegarse y verificarse. Hasta entonces, Sol/low no está activo.

El dueño aprobó F2.1 el 9 de octubre para la evaluación. Se despliega su bloque exacto como `config/chat/system_prompt.txt` (SHA-256 `33b8f7a0900869812d98bba57daa2ce3ea2f6b5c02a86a7eb3b8e830c7f7694b`), junto con la política de periodo v2 evaluada en la campaña final Sol/low (prompt efectivo SHA-256 `439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5`). La aprobación y el alcance cubren las siete herramientas actuales; no agregan herramientas F2.3+.

Después del despliegue, conserva `CHAT_MODEL=gpt-6.1-sol`, las tarifas 2/10 USD por millón, los topes diarios de US$5 por usuario y global, la admisión y el límite de 16 herramientas vigentes. Cambia solo `CHAT_REASONING_EFFORT=low`, verifica en `/api/chat/health` el modelo, esfuerzo y hash efectivo, y usa una conversación nueva. Sol/low y el prompt seguirán pendientes hasta esa verificación.
