# Mantenimiento de pruebas, CI y dependencias

Mejoras no bloqueantes de la auditoría de arquitectura del 5 de octubre de 2026.
No cambian datos, `site/`, aprobaciones ni el comportamiento del pipeline o
del chat.

## Cambios

- **Validación reutilizada.** `Snapshot` (`src/conversational_analytics/data/snapshot.py`)
  y `src.publish.verify` recuerdan en memoria los pares (SHA-256 del archivo,
  digest del esquema) que ya validaron sin errores. Los bytes se comprueban
  contra el manifiesto antes de validar y la validación JSON Schema es
  determinista, así que repetir el mismo par no aporta nada. Una carga del
  sitio pasa de ~10 s a ~1.5 s cuando el proceso ya lo validó; una ejecución
  única de CLI o del servidor no cambia. Un archivo alterado tiene otro hash y
  se valida completo.
- **Ruff `F` en CI** sobre `src/` y `scripts/`, tras quitar 23 imports sin uso,
  un prefijo `f` vacío y dos asignaciones muertas sin efecto. `tests/` queda
  fuera por ahora: los fixtures de pytest importados por nombre aparecen como
  imports sin uso y corregirlos automáticamente rompería las pruebas.
- **CI y dependencias del repositorio.** `ci.yml` declara
  `permissions: contents: read` (compatible con la llamada desde `pages.yml`)
  y `.github/dependabot.yml` propone actualizaciones mensuales agrupadas de
  Actions, npm de `web/` y uv. Cada PR de Dependabot sigue el flujo de
  `AGENTS.md`.
- **Dependencias.** `playwright` pasa al grupo `dev` (pruebas de navegador y
  `src/smoke_test.py`) y `plotly` al extra `analytics` (notebooks y
  `src/analytics/build_notebook.py`). `uv.lock` se resolvió de nuevo con los
  mismos paquetes; CI instala todos los grupos y extras como antes.

## Validación

818 pruebas públicas aprobadas en 2 min 15 s (6 omitidas, 79 deseleccionadas),
antes ~7 min; `ruff check --select F src scripts`, `uv lock --check` y
`python -m scripts.check_chat_runtime`.

## Pendiente

Formatear con Ruff el resto del árbol por paquete, extender la revisión `F` a
`tests/` (declarando los fixtures en `conftest.py`) y evaluar la división del
bundle web para cargar los mapas solo en Vuelos.
