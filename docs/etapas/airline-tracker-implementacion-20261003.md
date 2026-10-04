# Airline Tracker chat — entrega de implementación

Fecha de corte: 3 de octubre de 2026 (zona horaria del dueño). Esta entrega
implementa la base del chat, su adaptador oficial y las evaluaciones del plan
`traspaso-implementacion.md`. El documento adjunto se usó como especificación;
no se interpretó como autorización para consumir servicios pagados. Los seis
subagentes de programación y revisión usaron GPT-6 Luna. La comprobación inicial
confirmó que `OPENAI_API_KEY` estaba disponible, sin mostrarla.

## Entregado en este cambio

- Snapshot público inmutable y verificado, catálogo de 11 métricas y siete
  herramientas de lectura. Los planes validan unidades, periodos, entidades,
  dimensiones y versiones; los cálculos y referencias proceden de Python.
- API FastAPI con historial SQLite, cola persistente, SSE con replay,
  idempotencia, cancelación, cuotas y borrado del proveedor con reintentos.
  El modo local exige loopback; el piloto remoto requería bearer por usuario y
  CORS explícito (sustituido el 4 oct por contraseña: ver
  [`airline-tracker-remediacion-20261004.md`](airline-tracker-remediacion-20261004.md)). No se abre el warehouse desde el chat.
- Panel TypeScript lateral y móvil, contexto de pestaña/tarjeta, fuentes,
  Markdown seguro y gráficas acotadas. Está desactivado por defecto y no guarda
  tokens de autenticación en el navegador.
- Adaptador de `client.beta.agents` del SDK oficial `openai==3.13.0`, con
  `environment.type=none`, sesiones aisladas y sin reenvíos ambiguos. Sus pruebas
  usan eventos del SDK simulados; todavía no verifican acceso real a la API.
- Holdout de 40 preguntas bilingües, independiente de los ejemplos de prompt,
  con planes esperados y valores explícitos del snapshot público en 12
  consultas soportadas. Incluye ambigüedad de métricas, entidad/grano,
  porcentaje frente a puntos porcentuales, agregación ponderada, ausencia,
  rutas, contexto de tarjeta y prompts de privacidad.
- Evaluador reutilizable para observar planes, filas, unidades, referencias y
  términos de respuesta, más auditoría offline que verifica valores y
  referencias deterministas. Los otros 28 casos se dejan pendientes para evaluación de
  comportamiento real; no se fabrican respuestas ni se incluyen en la calidad
  medida offline.
- Modo dry-run sin llamadas que reporta candidatos, ventanas, llamadas,
  estimación de tokens, precios ingresados por candidato y destinos de salida.
  `--run` requiere presupuesto, modelos, precios ingresados y opt-in explícito.
  Incluye un puente directo al provider/runtime real; no se ejecutó modo live.
- Guías de instalación, límites, presupuesto, comparación de modelos y destino
  de despliegue de una instancia persistente.

## Validación y estado

Validación focalizada ejecutada contra las interfaces integradas del backend y
del snapshot:

| Comando | Resultado |
|---|---|
| `uv run pytest -q tests/test_chat_evaluation.py` | 4 passed. |
| `uv sync --all-extras --all-groups --locked` | Resolvió 149 paquetes; 145 instalados/disponibles. |
| `uv run --all-extras python -m src.conversational_analytics --help` | Arranque y CLI del servicio cargan sin hacer petición al proveedor. |
| `uv run python -m src.conversational_analytics.evaluation --dry-run --models gpt-6-luna gpt-6.1-sol gpt-6-astra --model-price gpt-6-luna=0.10:0.50 --model-price gpt-6.1-sol=2:10 --model-price gpt-6-astra=10:50` | 40 preguntas, 4 ventanas, 52 llamadas estimadas por candidato; cero llamadas reales. Estimación aproximada: US$0.0118 / US$0.236 / US$1.18 respectivamente. |
| `uv run python -m src.conversational_analytics.evaluation --audit-snapshot` | 12/12 filas estáticas y referencias pasaron. 28 casos de ambigüedad, seguridad y respuesta permanecen sin evaluar por modelo. |
| `pytest -q tests/test_chat_*.py tests/test_repo_budgets.py` | 43 passed: 40 del chat y 3 de límites del repositorio. |
| `pytest -m 'not local_data and not browser' -q` | 604 passed, 1 skipped; subconjunto público del proyecto. |
| `npm run check`, `npm test`, `npm run build` | Typecheck y build pasan; 81 Vitest pasan. El build conserva el aviso previo de tamaño de Plotly. |
| `pytest -m browser -q --require-local-data` | 12 passed, incluidos smoke del chat y paridad del sitio. Flujo local con servidor mock real, bearer, CORS y capturas desktop/móvil verificados. No prueban acceso a OpenAI. |
| Ruff check/format de todos los módulos y pruebas nuevos + `git diff --check` | Limpios; todos los módulos cumplen los límites del repositorio. |

La repetición final de `pytest -m 'not browser' -q --require-local-data` tuvo
669 pruebas exitosas, 1 omitida y 12 deseleccionadas, con un solo fallo.
Los fallos iniciales de tamaño se corrigieron dividiendo módulos.
El diagnóstico de etapa 12 conserva una discrepancia preexistente de hash del
warehouse: el generador, la prueba y el HTML son idénticos a `origin/master`, y
el diagnóstico regenerado coincide por completo salvo `input_sha256.warehouse_content`
(`a5213d…` esperado, `116acd…` local). No se alteró el diagnóstico histórico ni
el warehouse para ocultar ese fallo. La suite completa no se declara verde.

`site/` se regeneró mediante el gate con el expediente ya aprobado de 2026Q2
y `VITE_CHAT_ENABLED=false`. Se verificó el manifiesto y se compararon los
112 hashes de `site/data/v1/` y `analysis_manifest` antes y después: permanecen
idénticos. Cambió la versión del manifiesto al fijar el nuevo commit de código;
el holdout se volvió a fijar a ese manifiesto, sin cambiar valores esperados.
Esta preparación en la rama no equivale a un despliegue del piloto.

Versión del snapshot auditado: `388d3437aad47fb088f72b17580489fbe78f2cc6265339f5e724b10ec8f4c210`
(el 4 oct `site/` volvió a ser el de master y el holdout se re-fijó a
`de3c4d404837b8c19d306c301cd5647cc955d26215a45bc0c8f8b7bed00db668`; ver el
informe de remediación).
Versión semántica: `d43faaad53a352cbbfea194c6ffa978ebef8bce6a4d403cc52553158fcb11b2a`.
No inferir resultados de API o calidad conversacional desde pruebas offline.

La auditoría disponible revisa el snapshot de `site/`, que es una proyección
pública versionada, y nunca abre `data/warehouse.duckdb`. La credencial
`OPENAI_API_KEY` estaba presente en el entorno al comenzar la revisión; no se
mostró ni se copió su valor. La presencia de la variable no verifica acceso a
Agents API.

| Hito | Estado |
|---|---|
| H1 — semántica revisada | Conciliación técnica completa; definiciones marcadas `agent_reconciled_owner_review_pending`, sin fabricar aprobación del dueño. |
| H2 — demo sin consumo | Implementada y verificada offline; 40 pruebas del chat, 81 Vitest y límites de módulos pasan. No se generó tráfico al proveedor. El fallo de diagnóstico histórico está documentado aparte. |
| H3 — chat real local | CLI gated y bridge real listos. Pendiente de consentimiento del experimento completo (sonda + holdout) y comprobar acceso a Agents API. La variable está presente; el acceso no está verificado. |
| H4 — modelo elegido | Pendiente de la sonda y comparación de 40 preguntas en 3 candidatos (121 turnos en total), con respuestas, p50/p95 y uso/caché observados; no hay modelo predeterminado. |
| H5 — piloto publicado | Pendiente de elegir y administrar un host persistente, autenticar usuarios, acordar retención y validar CORS desde Pages y rollback. |

## Límites y decisiones pendientes

Una evaluación offline no mide si un modelo interpreta una pregunta,
aclara ambigüedades o rehúsa una solicitud privada. El futuro reporte live debe
guardar el uso de todas las llamadas, sesiones y turnos, referencias, versiones,
latencia y datos de caché observados. Cualquier campo no reportado será
`unknown`; no se convertirá una estimación en medición. Se propone un gate de
al menos 95% de calidad en preguntas soportadas y cero errores críticos. El
reporte de presupuesto no es una promesa de techo de facturación.

Las secciones H3–H5 no están autorizadas por el hecho de tener una variable de
credencial en el entorno. No se contrató hosting, no se fijó política de
retención y no se consumieron créditos de API.
