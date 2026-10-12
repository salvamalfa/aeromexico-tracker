# F2.9 · Preflight offline y export de revisión de etapa 3 · 2026-10-12

La cobertura de etapa 3 se deriva localmente de las herramientas y del
snapshot actual para los 30 casos de negocio congelados (34 mensajes, sin casos
de inyección). La derivación no llama al proveedor. La ejecución real continúa
cerrada hasta recibir recibos externos con el hash exacto de campaña, alcance,
vigencia y capacidades publicados; los recibos sintéticos solo prueban el
despacho a un runner falso en tests. La campaña propone Sol low, una repetición,
y los límites runtime incluidos en identidad y recibos. La reserva de US$6.58
sigue siendo una estimación conservadora, no aprobación de gasto ni límite
duro.

El reporte distingue índice ausente de índice presente pero vacío; la presencia
de `search_reports` y `search_news` se obtiene del catálogo real de herramientas.
Un índice vacío no se considera publicado y bloquea el preflight live. Las
expectativas exportadas conservan evidencia numérica, cálculos derivados,
limitaciones y referencias de fuente; las salidas live solo se aceptan si su
identidad canónica corresponde a todos los pins de cobertura, incluido el
prompt, fixture, snapshot, herramientas y límites. Los JSON privados se escriben
bajo `.state/` con directorios `0700` y archivos `0600`.

N05 limita la comparación a pasajeros AFAC de Aeroméxico, Volaris y Viva en
4T25; no define “más grande”, no abarca todas las aerolíneas de México y no
permite declarar ganador. N08 compara solo 2T25 con 2T26, no años completos.
N07 y N11 expresan las diferencias interanuales en puntos porcentuales. N21
expresa la suma de las participaciones de Volaris y Viva como porcentaje de los
pasajeros domésticos AFAC del mercado, conservando ese denominador.

Validación focal: `tests/test_chat_f29_stage3_coverage.py`,
`tests/test_chat_f29_stage3_receipt_run.py`, `web/src/review/expected.test.ts`
y `npm run check`. No se ejecutó una campaña de proveedor, no se aprobó ni
publicó dato nuevo, y el alcance sigue siendo parcial: 30 casos/34 mensajes,
no la calidad completa de 70 slots de etapa 2.
