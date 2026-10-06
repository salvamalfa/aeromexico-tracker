# Traspaso: activación del MVP del chat

Documento operativo para el agente que activa el chat (ChatGPT). Resume el
estado al 6 de octubre de 2026 y lo que falta. Las reglas de `AGENTS.md`
siguen vigentes.

## Roles

- **Dueño:** califica los cortes en `review.html` y entrega el archivo de
  «Exportar todas las calificaciones». Después elige el modelo y el tope entre
  las opciones que se le propongan. No configura Railway, la API key ni el
  repositorio.
- **Agente (ChatGPT):** consolida las calificaciones, aplica el gate de calidad,
  propone el modelo con evidencia, administra Railway y la API key como
  variables de entorno, y ejecuta la activación y la publicación del panel.

## Estado actual

- `master` contiene todo lo necesario para activar sin cambios de código:
  - lanzador que acepta OpenAI configurado de forma explícita;
  - `data_version` estable ante republicaciones de interfaz;
  - tope diario en dólares;
  - guard de `import-usage`;
  - `web/.env.production` con la URL de la API y el panel apagado.
  Detalle en `docs/etapas/chat-mvp-preparacion-20261006.md`.
- **Railway:** servicio sano en `mock`, admisión cerrada, contraseña activa.
- **Pages:** dashboard, `review.html` y `access.html` publicados; el panel del
  chat no está compilado (`VITE_CHAT_ENABLED=false`).
- **Dependabot:** solo propone versiones menores y de parche, y nunca el
  runtime del chat (`openai`, `fastapi`, `uvicorn`).

## Decisiones vigentes del dueño

- **Tope diario aprobado de US$1** por usuario y global
  (`CHAT_DAILY_COST_BUDGET_USER_USD`, `CHAT_DAILY_COST_BUDGET_GLOBAL_USD`).
  - La reserva mínima se cobra a la tarifa de salida: Luna US$0.075, unas 215
    preguntas al día; Sol 6.1 requiere un tope de al menos US$1.50 y Astra
    más de US$7.50.
  - Si se propone Sol o Astra, plantea el tope necesario al dueño junto con
    el modelo.
- **Respaldo de gasto:** el dueño cargará crédito prepagado de US$10–15 en
  OpenAI, sin recarga automática. Es opcional y no sustituye el tope de la app.
- **S14** no se importa a la base del chat: `unknown` pausaría todas las
  admisiones, e `import-usage` exige `--allow-admission-block` para eso.
- **Data Sharing** puede reducir la factura, pero no es un control de gasto.
- **Fuera de alcance del MVP:** volver a medir el consumo con 8 llamadas y 180 s
  (riesgo aceptado; el tope en dólares lo acota).

## Pasos pendientes

1. **Calificaciones:** recibir el JSON del dueño y consolidarlo con los
   resultados de la comparación (`docs/etapas/airline-tracker-comparacion-final-20261004.md`).
2. **Gate de calidad:**
   - 95% o más de respuestas correctas sobre **todos** los casos soportados,
     contando los no calificados y los fallidos en el denominador, y cero
     fallos críticos;
   - reportar por separado cuántos casos quedaron sin calificar;
   - las calificaciones previas miden el prompt anterior al PR #87: señala qué
     evidencia corresponde al prompt actual.
3. **Propuesta al dueño:** modelo recomendado, alternativa, costo estimado por
   pregunta, tope necesario y riesgos. Espera su elección explícita.
4. **Activación:** sigue `docs/chat/railway.md`, sección «Activación del MVP»:
   - variables de Railway, `CHAT_ALLOWED_ORIGINS` y `/api/chat/health`;
   - `VITE_CHAT_ENABLED=true`, `src.publish` con el registro ya aprobado,
     `src.publish.verify site/` y PR con `site/`.
5. **Prueba final:** login y una pregunta desde Pages y desde el teléfono con
   la computadora apagada. **Rollback:** `CHAT_ADMISSION_ENABLED=false` en
   Railway.

## Límites

- No encender OpenAI ni publicar el panel sin la elección explícita del dueño
  de modelo y tope.
- No consumir la API pagada fuera de esa activación (nuevas evaluaciones o la
  prueba de Data Sharing) sin una autorización específica.
- No cambiar aprobaciones ni datos publicados.
