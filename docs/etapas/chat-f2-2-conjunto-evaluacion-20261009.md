# F2.2 · Conjunto de negocio, harness y estimación F2.9

Fecha: 9 de octubre de 2026. Este reporte registra el cierre técnico propuesto
de F2.2 y la planeación offline para F2.9. El fixture, el prompt, la rúbrica,
el alcance y cada etapa pagada siguen pendientes de sus decisiones humanas.

## Resultado

- Se prepararon 30 preguntas de negocio, con 34 mensajes de usuario porque
  N24–N26 son conversaciones completas de varios turnos. La propuesta muestra
  comportamiento esperado, paquetes requeridos, fallos críticos y criterios
  para la calificación ciega del dueño en
  [`F2.2-conjunto-propuesto.md`](../chat/revision-fase-2/F2.2-conjunto-propuesto.md).
- Ocho preguntas de un turno tienen plan y filas `supported` obtenidas por
  código con `ToolRegistry` contra el snapshot público fijado. Tres casos de
  varios turnos también incluyen gold para sus turnos soportados. N07, N11 y
  N21 calculan diferencias o suma desde las filas raw; los casos que necesitan
  paquetes de datos o fuentes pendientes no tienen gold aprobado.
- `safety_current.json` conserva 40 casos derivados de las preguntas y
  expectativas del holdout histórico. El holdout fuente permanece intacto; el
  derivado registra el blob Git y versiones de origen, y vuelve a anclar las
  expectativas al snapshot público actual.
- Se añadió el harness de campañas de F2.9 con identidad estable para cada
  corrida, presupuesto compartido entre las corridas de una misma campaña y
  continuidad solo con la misma identidad y presupuesto. Un gasto desconocido
  después de una llamada interrumpida bloquea el replay. Cada etapa tiene su
  propia campaña y autorización; no hay un ledger operativo único para las
  tres etapas.
- La estimación offline está en
  [`estimacion-f2-9-presupuesto.md`](../chat/estimacion-f2-9-presupuesto.md)
  y su JSON reproducible en
  [`estimacion-f2-9-presupuesto.json`](../chat/estimacion-f2-9-presupuesto.json).

## Presupuesto estimado

Con los precios del catálogo local (`pricing_as_of` 9 oct UTC; revisión local
del dueño 8 oct en America/Mexico_City), 60–100 mil tokens de entrada por cada
mensaje de usuario y salida con razonamiento según el plan:

| Etapa | Casos | Mensajes por corrida | Corridas | Casos-ejecución | Reserva sugerida con 25% si el saldo confirmado fuera cero |
|---|---:|---:|---:|---:|---:|
| 1 | 58 | 62 | 2 prompts | 116 | US$3 |
| 2 | 15 | 15 | 4 candidatos | 60 | US$11 |
| 3 | 70 | 74 | 6 corridas | 420 | US$54 |

El escenario sin caché estima US$28.87–52.79 para las tres etapas; con 80% de
cache hit modelado, US$10.69–22.49. El costo de desarrollo de F2.1–F2.8 queda
separado como referencia de US$3–5. La cifra global de US$73 es solo una
referencia de planeación: aplica una vez 25% al extremo alto de las tres
etapas más US$5 de desarrollo y redondea al siguiente dólar. No es un
presupuesto autorizado ni el límite de una campaña. Las reservas de US$3,
US$11 y US$54 son específicas por etapa y se redondean por separado; el saldo
real no está reconciliado y la referencia histórica de ~US$7 no se considera
disponible. Antes de cada campaña se confirma el saldo y se determina la carga
como `max(0, reserva − saldo confirmado)`.

La reserva y el stop de una campaña son operativos, no un techo contractual de
factura. Una llamada ya iniciada puede excederlos; costos de caché, uso
desconocido y long-context no se tratan como cero. La etapa 3 deberá
recalcularse después del piloto usando el uso medido y la lista final de
candidatos.

## Trazabilidad

- Business fixture SHA-256:
  `585adf3901c19581f563d2fe0f5b2d4f41ac90a614d6ce6f200a580d774c2b56`.
- Cohorte de seguridad derivado SHA-256:
  `2fce3196a5ca63edbe7c32e898f8ce456408ffd151788f263a3f105cd8aca2b6`.
- Versiones business y safety: data
  `d9c4e56d04ad67be5dff6d6e9f7f6615f4f4be985ec1e5ee59781a7735007037`;
  semántica
  `0b8de07ff211ca1ba984bd87281a2d68950a3e36268909b2121a7ed6b35e0365`.
- Catálogo `config/chat/models.json`, SHA-256
  `9744c985f051c898a8af6e8d3c8766c6885e77d8a13d55b72e30427b15468d4c`.
- Prompt F2.1 leído desde el commit inmutable
  [`2f45994962b227b62e542b75b851c731b671329e`](https://github.com/salvamalfa/aeromexico-tracker/blob/2f45994962b227b62e542b75b851c731b671329e/docs/chat/revision-fase-2/F2.1-prompt-propuesto.md),
  7,564 caracteres; SHA-256 del documento
  `656de4bc6a0a92d7374513a7fbac27ec304a3216f4ea99ad82c423ea08a0e6b1`.

## Validación y límites

- Suite pública estándar: **953 pruebas pasaron**, 6 se omitieron por páginas
  preview o datos locales intencionalmente ausentes, 79 se excluyeron por los
  marcadores `local_data` y `browser`, y 14 subtests pasaron. Comando:
  `uv run pytest -m "not local_data and not browser" -q`, después de
  `uv sync --all-extras --all-groups --locked`.
- Ruff `F` para `src/` y `scripts/`, compilación sintáctica de módulos F2.2 y
  `git diff --check` pasaron.
- No se hicieron llamadas de red o API pagada, no se leyeron credenciales, no
  se cambió producción y no se creó una aprobación humana. El prompt y la
  propuesta de preguntas permanecen en borrador.
