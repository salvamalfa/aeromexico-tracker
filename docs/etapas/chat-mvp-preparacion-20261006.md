# Preparación del MVP del chat

## Contexto

El dueño quiere ver pronto el chat funcionando en el dashboard de Pages: panel
visible para todos y escritura protegida con contraseña. Después de calificar
los cortes en `review.html`, se elegirá el modelo, se pondrá la API key y se
encenderá OpenAI. Esta etapa corrige lo que habría impedido o roto ese MVP y que
se podía resolver sin API key ni evaluaciones pagadas. No cambia `site/`, los
datos publicados ni las aprobaciones, y no enciende el proveedor.

Decisiones del dueño (6 de octubre de 2026): tope de gasto en dólares en dos
capas (app y OpenAI Platform), integrar el PR #86 como registro, dejar S14
fuera de la base del chat y publicar el panel solo al encender OpenAI. Por
prioridad del MVP no se repiten evaluaciones ni se vuelve a medir el consumo
con los límites del PR #88.

## Cambios

- **Lanzador de Railway** (`scripts/start_chat_runtime.py`): ya no rechaza
  `CHAT_PROVIDER=openai` ni `CHAT_ADMISSION_ENABLED=true`. OpenAI sigue
  requiriendo `CHAT_OPENAI_ENABLED=true`, `CHAT_MODEL`, precios normales y
  contraseña (`ChatConfig.from_env`), y el lanzador valida antes de arrancar
  que una reserva mínima quepa en los topes diarios en dólares. Sin variables
  explícitas sigue en `mock` con la admisión cerrada. Antes, configurar OpenAI
  en Railway habría impedido arrancar el servicio.
- **Versión de datos** (`src/conversational_analytics/data/snapshot.py`):
  `data_version` usa solo las entradas `data/` del manifiesto, los hashes de
  contratos y el `analysis_manifest`. Las republicaciones de interfaz de los
  PRs #87 y #90 habían cambiado la versión (`de3c4d…` → `735d4e…`) sin cambiar
  datos, lo que reinicia las conversaciones abiertas. Con la regla nueva, los
  manifiestos de `326d4c8`, `36639b5` y `45f0677` comparten versión. El valor
  cambia una sola vez al desplegar; el holdout congelado conserva su versión
  histórica y una evaluación en vivo nueva debe fijar la vigente.
- **Política de gasto** (`config.py`, `service.py`): topes de US$1 diarios por
  usuario y global por defecto, y cupo de tokens de 2,000,000 diarios como
  freno de seguridad. La reserva monetaria cobra hasta 10,000 tokens
  (`CHAT_RESERVED_OUTPUT_TOKENS`) a la tarifa de salida y el resto a la de
  entrada; antes cobraba toda la reserva a la tarifa más cara. Reserva mínima
  de 150,000 tokens sin cambio: Luna ~US$0.019, Sol 6.1 ~US$0.38; Astra
  (~US$1.90) no cabe en US$1 y el servicio rechaza arrancar con ella.
- **S14 e importador** (`usage_import.py`): `--apply` con filas `unknown` exige
  `--allow-admission-block`, porque cualquier fila desconocida pausa todas las
  admisiones; el dry-run lo indica. S14 permanece en el expediente de la
  comparación y no se importa a la base del chat.
- **Panel en Pages** (`web/.env.production`): versiona la URL pública de la API
  con `VITE_CHAT_ENABLED=false`. Con el flag apagado, el build es idéntico byte
  a byte a `site/assets`. Activarlo es cambiar el flag y ejecutar `src.publish`
  (`docs/chat/railway.md`, «Activación del MVP»).
- **Documentación**: guía de activación, control de gasto en dos capas y
  rollback en `docs/chat/railway.md`; política en `data-sharing.md` y
  `operations.md`. El PR #86 se integró con una nota de que sus cifras se
  midieron con 5 llamadas y 90 segundos.

## Validación

- Suite pública: 817 pruebas aprobadas antes de esta documentación (6 omitidas,
  79 deseleccionadas), más pruebas nuevas del lanzador con OpenAI configurado e
  incompleto, de topes en dólares por modelo, de la versión de datos ante
  cambios de interfaz, datos y contratos, y del importador con filas
  desconocidas.
- `python -m scripts.check_chat_runtime`, Ruff en los archivos tocados,
  `npm run check`, `npm run test` (136) y `npm run build`: con el panel apagado
  los assets son idénticos a `site/assets`; con el panel encendido aparece el
  chunk del chat con la URL de Railway.
- `src.publish.verify site/` sin cambios en `site/`.

## Riesgos aceptados y pendientes

- El consumo por pregunta con 8 llamadas y 180 segundos no se volvió a medir;
  el tope en dólares acota su efecto.
- La elección del modelo, la API key, el encendido de OpenAI y la publicación
  del panel dependen de la revisión del dueño y de su autorización explícita de
  gasto.
- La cobertura de Data Sharing para Agents API con herramientas sigue sin
  confirmarse; ya no condiciona ningún control.
