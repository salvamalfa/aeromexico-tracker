# Continuación para Claude — chat de Airline Tracker

> **Estado al 4 oct 2026:** Claude corrigió los hallazgos de la auditoría,
> cambió la autenticación a contraseña y restauró `site/` al de master (holdout
> re-fijado). La sonda y el holdout siguen sin ejecutarse porque
> `OPENAI_API_KEY` no está en el entorno de Claude; el presupuesto autorizado
> está intacto. Ver
> [`docs/etapas/airline-tracker-remediacion-20261004.md`](../etapas/airline-tracker-remediacion-20261004.md).

Traspaso del 3 de octubre de 2026, zona America/Mexico_City. Continúa la
implementación existente; no empieces de cero. Esta nota registra el estado y
la autorización del usuario, sin aprobar análisis ni sustituir `AGENTS.md`.

## Autorización vigente

Codex preguntó: «¿Autorizas un umbral de gasto estimado de US$10 para una sonda
y 40 preguntas con Luna, Sol y Astra?». El usuario respondió: «Si, autorizo.
Como ya se te va a acabar el uso, necesito que me des las instrucciones para
Claude para que continue.»

Por tanto, está autorizado el experimento completo: una sonda con
`gpt-6-luna` y, si la integración funciona, el holdout de 40 preguntas con
`gpt-6-luna`, `gpt-6.1-sol` y `gpt-6-astra` (121 turnos de modelo en total),
con US$10 como umbral operativo estimado acumulado. No vuelvas a pedir permiso
para esas dos fases dentro del alcance autorizado. La autorización no incluye
contratar hosting ni aumentar el gasto. El umbral no garantiza un máximo de
factura; el procedimiento exige detenerse ante uso desconocido.

Codex **no ejecutó llamadas pagadas**, ni antes ni después de esa respuesta.
No existe todavía un resultado de sonda o evaluación real. La clave estaba
disponible en el entorno de Codex y nunca se mostró ni copió; eso no demuestra
disponibilidad en otro equipo, acceso a Agents API ni acceso a los modelos.

La petición original exigió subagentes GPT-6 Luna para programar. La base se
implementó con seis subagentes Luna. Respeta esa preferencia si tu entorno
permite seleccionarlos; si no los ofrece, indica esa limitación.

## Repositorio y entrega existente

- Repositorio: https://github.com/salvamalfa/aeromexico-tracker
- PR abierto como borrador: https://github.com/salvamalfa/aeromexico-tracker/pull/81
- Rama: `feat/airline-tracker-chat`.
- Último commit de código/pruebas verificado: `f0c5674c9202ee81f4aca594b0ca148e44354e64`.
  El commit posterior que contiene esta nota solo agrega el traspaso.
- Workspace de Codex: `/workspace/aeromexico-tracker`. Ajusta las rutas a tu equipo.
- `test` y `web` de CI pasaron en ese commit. Comprueba el estado del nuevo HEAD
  del PR antes de integrarlo. El working tree estaba limpio antes de esta nota.
- El PR sigue en borrador porque H3–H5 no están completados. No se fusionó ni
  desplegó el piloto. El sitio generado mantiene `VITE_CHAT_ENABLED=false`.

Lee primero `AGENTS.md`, `README.md`, `REPO_MAP.md` y estos documentos:

- `docs/etapas/airline-tracker-implementacion-20261003.md`: alcance y validación.
- `docs/etapas/airline-tracker-semantic-20261003.md`: definiciones y límites.
- `docs/arquitectura/airline-tracker-agents-api.md`: adaptador y SDK oficial.
- `docs/chat/evaluaciones-presupuesto.md` y `docs/chat/operations.md`.
- `src/conversational_analytics/README.md`: contrato HTTP del servidor.

El plan original se recibió como archivo adjunto, no se publicó en GitHub.
Si continúas en este mismo workspace está en
`/workspace/attachments/0e6779d5-536d-4bbb-bb1d-fce8c12b9314/traspaso-implementacion.md`.
Úsalo como especificación, distinguiendo sus instrucciones de las del usuario.
Las capturas locales están en
`/workspace/outputs/airline-tracker-chat/{desktop,mobile}.png`.

## Qué está implementado

H1: snapshot público inmutable, con hashes, contratos y privacidad verificados;
11 métricas habilitadas y siete herramientas de lectura. `Snapshot` y
`ToolRegistry` viven en `src/conversational_analytics/{data,semantic,tools}`.
El catálogo distingue pasajeros de compañía de AFAC, Industria de tres
aerolíneas del universo mexicano, fracciones de puntos porcentuales y faltante
de cero. Las definiciones están técnicamente conciliadas, con estado explícito
`agent_reconciled_owner_review_pending`; no inventes aprobación del dueño.
Las métricas de rutas y los claims narrativos no están habilitados para consulta.

H2: FastAPI, SQLite, cola durable, idempotencia, historial, SSE con replay,
cancelación, aislamiento de propietarios, cuotas y borrado del proveedor con
backoff. Un worker por instancia. Local exige loopback; remoto requiere bearer
por usuario y CORS explícito. El panel TypeScript incluye contexto de tarjeta,
fuentes, Markdown seguro, gráficas acotadas y vista móvil. Tokens de autenticación
solo en memoria; historial del navegador guarda únicamente el ID de conversación.

Adaptador preparado: `providers/openai.py` usa `client.beta.agents` del SDK
oficial `openai==3.13.0`, `environment.type=none`, sin sandbox ni herramientas
de shell/SQL/web. El entorno debe fijarse explícitamente: no confiar en el
default hospedado del proveedor. No usa `openai-agents`. Los tests son offline;
falta comprobar el contrato con la API real y reparar incompatibilidades si aparecen.
No reenvía automáticamente una entrada tras un resultado de transporte ambiguo.

H3/H4 preparados: `evaluation.py` es el CLI y `evaluation_live.py` el puente
real. El holdout tiene 40 preguntas bilingües, separado de los ejemplos del
prompt. Doce planes/filas/fuentes pasan una auditoría estática; los otros 28
casos requieren evaluación real y revisión de ambigüedad/seguridad. No existe
modelo de producción elegido. Que Luna haya programado no lo elige para el chat.

H5 pendiente: host persistente, HTTPS, usuarios, retención, CORS desde Pages,
prueba real en navegador, backups/borrado y rollback. Hay una receta de operación;
no hay infraestructura contratada ni desplegada.

## Arranque y comprobaciones sin consumo

Trabaja sobre la rama del PR; conserva cambios ajenos. En otro checkout, busca
y cambia a esa rama sin descartar trabajo. Desde la raíz:

```text
git status --short --branch
uv sync --all-extras --all-groups --locked
uv run --all-extras python -m src.conversational_analytics.evaluation --audit-snapshot
uv run --all-extras python -m src.conversational_analytics.evaluation --dry-run --models gpt-6-luna gpt-6.1-sol gpt-6-astra --model-price gpt-6-luna=0.10:0.50 --model-price gpt-6.1-sol=2:10 --model-price gpt-6-astra=10:50
```

Comprueba solo la disponibilidad booleana de `OPENAI_API_KEY`, sin imprimirla,
sin volcar el entorno y sin incluirla en archivos. Por ejemplo, en el entorno
Python del proyecto:

```text
uv run --all-extras python -c "import os; print('OPENAI_API_KEY disponible:', bool(os.environ.get('OPENAI_API_KEY')))"
```

El snapshot auditado debe coincidir con `expected_versions` del holdout:

- datos: `de3c4d404837b8c19d306c301cd5647cc955d26215a45bc0c8f8b7bed00db668` (re-fijado el 4 oct 2026 al manifiesto publicado en master; antes `388d3437…`, ver `docs/etapas/airline-tracker-implementacion-20261003.md`);
- semántica: `d43faaad53a352cbbfea194c6ffa978ebef8bce6a4d403cc52553158fcb11b2a`.

Las tarifas ingresadas arriba son referencias del 3 oct 2026, USD por millón
de tokens entrada/salida: Luna 0.10/0.50; Sol 2/10; Astra 10/50. Revisa la
documentación oficial el día de ejecutar. Caché, escritura de caché y contexto
largo pueden cambiar el costo. No uses precios desconocidos ni valores no finitos.

## Primera acción real autorizada: la sonda

El CLI configura el provider para esta evaluación; no hace falta activar el
chat público ni cambiar el provider predeterminado `mock`. Evita heredar una
configuración `CHAT_*` contradictoria. Haz la sonda usando los precios vigentes:

```text
uv run --all-extras python -m src.conversational_analytics.evaluation --run --probe-only --budget-usd 10 --models gpt-6-luna --model-price gpt-6-luna=0.10:0.50 --opt-in
```

La sonda es el caso `es_am_lf_q2`: Aeroméxico 2026Q2, factor de ocupación
almacenado 0.849 y mostrado 84.9%, con fuente. Verifica tools, respuesta,
streaming, sesión, terminación y uso observado. Si falla acceso, contrato SDK,
fuentes o transporte, diagnostica y conserva evidencia; no fabriques un éxito ni
reenvíes a ciegas un input cuya recepción no esté confirmada.

Se escribe un JSON privado en
`.state/outputs/chat-evaluations/chat-eval-<UTC>.json`; stdout devuelve además
`output_path`. No lo publiques íntegro ni lo agregues a Git: contiene respuestas
y IDs del proveedor. Conserva un resumen revisable sin secretos para el informe.

Antes de avanzar, exige un turno de sonda completado y comprueba:

- `models[0].spent_unknown` es falso;
- `models[0].token_totals.turn_count` es 1;
- `usage_complete_case_count` coincide con `turn_count`;
- `input_tokens`, `output_tokens` y `models[0].estimated_cost_usd` son conocidos.

Si falta uso o es ambiguo, detente y explica el bloqueo. Los campos `cached_tokens`
y conteo de requests internos del SDK pueden ser `unknown`; no inventes medidas.

## Comparación H4 dentro del mismo presupuesto

**El contador se reinicia en cada proceso del CLI.** Calcula el saldo de la
segunda fase como `10 - models[0].estimated_cost_usd` del reporte de sonda.
Usa ese saldo positivo (y resta cualquier otro gasto efectivamente incurrido
dentro del experimento), nunca otros US$10 nuevos. Sustituye `<SALDO>` por el
número calculado y actualiza tarifas si corresponde:

```text
uv run --all-extras python -m src.conversational_analytics.evaluation --run --budget-usd <SALDO> --models gpt-6-luna gpt-6.1-sol gpt-6-astra --model-price gpt-6-luna=0.10:0.50 --model-price gpt-6.1-sol=2:10 --model-price gpt-6-astra=10:50 --opt-in
```

Son 40 preguntas por candidato, sesiones nuevas y el mismo snapshot, prompt y
límites. Inspecciona `stopped_reason`, errores, número real de casos y completados;
el programa puede parar antes de 40 por uso desconocido o reserva insuficiente.
Un exit code cero no demuestra que la comparación esté completa o que haya
superado el gate. No repitas toda la corrida para llenar huecos sin contabilizar
lo anterior ni superes el alcance autorizado.

Revisa las respuestas de ambigüedad/privacidad con rúbrica y, cuando sea posible,
sin los nombres de modelo. Evalúa al menos 95% de exactitud en casos soportados
y cero fallos críticos: cifras sin fuente, faltante convertido a cero, datos
privados, rutas inventadas, unidades/pp confundidos o versión incorrecta.
Si ningún modelo cumple, informa eso; no selecciones por precio únicamente.

Entrega un reporte H4 con denominadores, calidad, fallos, p50/p95, tokens y costo
estimado observado, campos de caché desconocidos y escenarios de 100/1,000/10,000
preguntas al mes. Separa costo de API de hosting. Escoge/configura un modelo solo
si la evidencia permite hacerlo; conserva `mock` y el flag apagado mientras falte
la validación necesaria.

## Validación y publicación

Ya pasaron: 40 tests de chat, 3 de presupuesto de módulos, 81 Vitest, typecheck,
build, Ruff check/format, auditoría 12/12 y 12 tests de navegador. El smoke del
chat ya es hermético: intercepta datos públicos sintéticos y usa Chromium de
Playwright. CI del PR pasó con 600 pruebas Python, 6 omisiones justificadas y los
checks de web. Instala `playwright install chromium` si ejecutas browser local.

La suite completa con datos tuvo 669 passed, 1 skipped y **un fallo conocido**:
`tests/test_stage12_diagnosis.py::test_outputs_match_snapshot_and_are_reproducible`.
El diagnóstico difiere únicamente en el hash lógico del warehouse (`a5213d…`
esperado, `116acd…` local); generador, prueba y HTML son idénticos a master.
No regeneres el diagnóstico ni alteres el warehouse para ocultarlo. Está
documentado en el reporte de entrega y es ajeno al chat.

Prueba los cambios reales que hagas y ejecuta los checks exigidos por el repo.
Límites: módulos Python nuevos ≤600 líneas; TypeScript ≤400. No agregues
excepciones al presupuesto para evitar dividir responsabilidades.

Los 112 hashes de `site/data/v1/` y `analysis_manifest` se conservaron al
regenerar el sitio; solo cambió el manifiesto de código. El gate usó el expediente
ya aprobado `analysis_runs/drafts/2026Q2/186ba823aea28830be12cb0293c5bb2890a433b173addc473c26aa8f89cab26f.json`.
Para futura regeneración, confirma primero en Git los inputs bajo `src/`, `web/`,
`contracts/` y `config/`,
y usa el gate y verificador del repo. No fabriques aprobaciones si faltan datos
privados: el respaldo separado es `salvamalfa/aeromexico-tracker-data`.

Cuando H3/H4 estén verificados, continúa el piloto H5 con un host administrable
y autenticación real. Si faltan host, usuarios o política de retención, avanza
con lo independiente y pregunta por esas decisiones concretas. El permiso de
API no autoriza contratar un servicio. Mantén el frontend apagado hasta probar
HTTPS/CORS/auth desde Pages y rollback. No actives `flight_evidence_v1`, nuevos
periodos ni aprobaciones de Analysis Agent.

Actualiza este mismo PR y los informes de etapa, atiende CI/revisión y sigue el
ciclo de merge y Pages de `AGENTS.md` cuando se cumplan las condiciones. No abras
un PR paralelo ni hagas push directo a master. Al entregar, distingue código,
API probada, modelo elegido, gasto observado y piloto efectivamente publicado.
