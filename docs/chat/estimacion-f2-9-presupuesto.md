# Estimación offline F2.9 (borrador)

**Estado: la etapa 1 está aprobada; las etapas 2/3 siguen pendientes. Esta estimación no ejecutó llamadas pagadas ni leyó credenciales.**

Fecha de tarifas declarada por catálogo (UTC): 2026-10-09; revisión local: 2026-10-08 America/Mexico_City. Catálogo `config/chat/models.json`, SHA-256 `9744c985f051c898a8af6e8d3c8766c6885e77d8a13d55b72e30427b15468d4c`. Fichas oficiales: [gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

## Insumos offline

- `prompt F2.1`: 7,564 caracteres, 7,721 bytes; 1,891 tokens heurísticos char/4 (no tokenizados).
- Fuente inmutable del prompt: [docs/chat/revision-fase-2/F2.1-prompt-propuesto.md @ 2f45994962b227b62e542b75b851c731b671329e](https://github.com/salvamalfa/aeromexico-tracker/blob/2f45994962b227b62e542b75b851c731b671329e/docs/chat/revision-fase-2/F2.1-prompt-propuesto.md); SHA-256 del documento `656de4bc6a0a92d7374513a7fbac27ec304a3216f4ea99ad82c423ea08a0e6b1`.
- `schemas de herramientas`: 3,291 caracteres, 3,306 bytes; 823 tokens heurísticos char/4 (no tokenizados).
- `filas gold`: 16,860 caracteres, 16,932 bytes; 4,215 tokens heurísticos char/4 (no tokenizados).

Los tamaños de prompt, esquemas y gold describen sus payloads fuente; no son tokens facturados de los prefills acumulados. El histórico medido fue ~40,000 tokens de entrada por pregunta sumando llamadas internas. Para la fase futura se modelan 60,000–100,000 tokens por cada mensaje del usuario.

## Casos y corridas

| Etapa | Casos seleccionados | Mensajes por corrida | Corridas de candidato | Casos-ejecución |
|---|---:|---:|---:|---:|
| 1 | 58 | 62 | 2 | 116 |
| 2 | 15 | 15 | 4 | 60 |
| 3 | 70 | 74 | 6 | 420 |

`evaluation.phase_cases` selecciona los casos por etapa. El conteo toma `turns` del fixture: N24 tiene 3 mensajes y N25/N26 tienen 2. La etapa 1 tiene dos corridas de candidato (prompt actual y propuesto), la etapa 2 una por cada uno de los cuatro candidatos y la etapa 3 seis corridas: dos por cada Luna y una por cada Sol. `Casos-ejecución` multiplica casos por corridas; los mensajes por corrida ya cuentan los seguimientos.

## Costo modelado por candidato

La salida incluye razonamiento una sola vez. Cada mensaje de seguimiento suma input y output. Los precios proceden del catálogo versionado. Cache writes son desconocidos y no se tratan como costo cero.

### Cache hit modelado: 0%

| Etapa | Candidato | Casos ejecutados | Mensajes | Input tokens | Output + razonamiento | USD |
|---|---|---:|---:|---:|---:|---:|
| 1 | gpt-6-luna@medium | 116 | 124 | 7,440,000–12,400,000 | 372,000–744,000 | $0.93–$1.61 |
| 2 | gpt-6-luna@medium | 15 | 15 | 900,000–1,500,000 | 45,000–90,000 | $0.11–$0.20 |
| 2 | gpt-6-luna@max | 15 | 15 | 900,000–1,500,000 | 150,000–375,000 | $0.17–$0.34 |
| 2 | gpt-6.1-sol@low | 15 | 15 | 900,000–1,500,000 | 15,000–45,000 | $1.95–$3.45 |
| 2 | gpt-6.1-sol@medium | 15 | 15 | 900,000–1,500,000 | 45,000–120,000 | $2.25–$4.20 |
| 3 | gpt-6-luna@medium | 140 | 148 | 8,880,000–14,800,000 | 444,000–888,000 | $1.11–$1.92 |
| 3 | gpt-6-luna@max | 140 | 148 | 8,880,000–14,800,000 | 1,480,000–3,700,000 | $1.63–$3.33 |
| 3 | gpt-6.1-sol@low | 70 | 74 | 4,440,000–7,400,000 | 74,000–222,000 | $9.62–$17.02 |
| 3 | gpt-6.1-sol@medium | 70 | 74 | 4,440,000–7,400,000 | 222,000–592,000 | $11.10–$20.72 |

Total de tres etapas en el escenario: **$28.87–$52.79**.

### Cache hit modelado: 80%

| Etapa | Candidato | Casos ejecutados | Mensajes | Input tokens | Output + razonamiento | USD |
|---|---|---:|---:|---:|---:|---:|
| 1 | gpt-6-luna@medium | 116 | 124 | 7,440,000–12,400,000 | 372,000–744,000 | $0.39–$0.72 |
| 2 | gpt-6-luna@medium | 15 | 15 | 900,000–1,500,000 | 45,000–90,000 | $0.05–$0.09 |
| 2 | gpt-6-luna@max | 15 | 15 | 900,000–1,500,000 | 150,000–375,000 | $0.10–$0.23 |
| 2 | gpt-6.1-sol@low | 15 | 15 | 900,000–1,500,000 | 15,000–45,000 | $0.58–$1.17 |
| 2 | gpt-6.1-sol@medium | 15 | 15 | 900,000–1,500,000 | 45,000–120,000 | $0.88–$1.92 |
| 3 | gpt-6-luna@medium | 140 | 148 | 8,880,000–14,800,000 | 444,000–888,000 | $0.47–$0.86 |
| 3 | gpt-6-luna@max | 140 | 148 | 8,880,000–14,800,000 | 1,480,000–3,700,000 | $0.99–$2.26 |
| 3 | gpt-6.1-sol@low | 70 | 74 | 4,440,000–7,400,000 | 74,000–222,000 | $2.87–$5.77 |
| 3 | gpt-6.1-sol@medium | 70 | 74 | 4,440,000–7,400,000 | 222,000–592,000 | $4.35–$9.47 |

Total de tres etapas en el escenario: **$10.69–$22.49**.

## Fondos por cargar antes de cada etapa

Cada etapa es una campaña separada con su propia autorización y `budget_usd`. Dentro de la etapa, sus prompts, candidatos, repeticiones y reanudaciones comparten un solo ledger; no hay un ledger operativo único para las tres etapas. Se usa el costo alto sin caché y se agrega 25%, redondeando al siguiente dólar. El dueño confirmó US$7.20 disponibles tras US$2.80 usados; no se consultó ni reconcilió el uso del proveedor. Solo la reserva de US$3 para etapa 1 está autorizada.

| Etapa | Costo alto sin caché | Con margen | Fondos necesarios si saldo verificado es US$0 |
|---|---:|---:|---:|
| 1 | $1.61 | $2.02 | **US$3** |
| 2 | $8.18 | $10.23 | **US$11** |
| 3 | $42.99 | $53.74 | **US$54** |

El plan mantiene aparte US$3–$5 para unas cinco rondas Luna-M de F2.1–F2.8; aún no hay un run plan para convertirlas en calls. La suma orientativa de las tres proyecciones más esa referencia es $31.87–$57.79 antes del margen y $39.83–$72.24 con margen. La referencia global de **US$73** aplica una vez 25% al extremo alto más desarrollo y redondea al dólar; no es presupuesto autorizado ni un tope operativo. Las reservas recomendadas por etapa se redondean por separado a US$3, US$11 y US$54; su suma (US$68) usa otro redondeo y no incluye desarrollo.

La etapa 3 es provisional y debe recalcularse después del piloto con el uso medido y la lista final de candidatos. La campaña de cada etapa comparte presupuesto entre sus corridas. Reanudar requiere la misma identidad y presupuesto; si una llamada interrumpida deja gasto desconocido, se bloquea el replay. El stop es operativo: no limita una solicitud ya iniciada ni garantiza el máximo de factura.

## Límites

Se presupone precio de contexto corto. La tarifa long-context aplica por solicitud individual que exceda 272,000 tokens de entrada; no hay medición por solicitud para saber si ocurre. En ese caso el costo sería mayor. El saldo US$7.20 es una declaración confirmada por el dueño, no una reconciliación del proveedor.
La reserva conservadora operativa de etapa 1 es distinta de la estimación de gasto: con Luna medium y 16 llamadas de herramienta, el runner usa 140,000 tokens de entrada más 32,000 de salida por mensaje para admitir el siguiente caso, valorados a US$0.75 por millón de tokens reservados. Son US$0.129 por turno (US$0.387 para el caso de tres turnos). El runner no retiene todas las reservas a la vez: tras cada caso contabiliza el uso confirmado y compara el saldo restante con la siguiente reserva. Una suma hipotética de US$15.996 para los 124 turnos no representa fondos retenidos. En un escenario offline representativo de 100,000 tokens de entrada y 6,000 de salida por turno, el gasto estimado es US$1.922 y los dos slots caben bajo el tope US$3. El gasto real puede variar; una solicitud con uso desconocido detiene la campaña y bloquea replay.

El JSON conserva versiones y hashes de fixtures y catálogo. Para regenerar: `uv run python scripts/chat/render_phase2_estimate.py [--model-catalog PATH]`.
