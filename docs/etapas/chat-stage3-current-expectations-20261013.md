# Stage 3 · expectativas actuales y revisión humana · 13 oct 2026

La revisión de PR #126 detectó que el runner live todavía usaba expectativas
históricas del fixture de negocio, aunque la cobertura se calcula sobre el
snapshot financiero y de evidencia aprobado. Por ejemplo, N04 podía conservar
`unsupported` y producir una calificación automática obsoleta.

El runner ahora copia los casos y reemplaza únicamente su expectativa de
evaluación por la cobertura actual fijada en el expediente. No modifica el
fixture ni las preguntas, turnos o contexto enviados al proveedor. Para Stage 3,
la calificación queda explícitamente sin puntuar y pendiente de la rúbrica
ciega del dueño; no se inventa un resultado aprobado o rechazado ni se usa el
gold histórico para una exactitud automática.

El exportador ya construía las expectativas del JSON de revisión a partir de
la cobertura actual. Una regresión confirma que no exporta calificaciones
automáticas históricas del reporte privado. Las pruebas también verifican N04,
N24 y N26, la identidad de los insumos enviados al proveedor y que la evidencia
esperada nunca llega al modelo. Los reportes privados existentes conservan sus
bytes y hashes; esta corrección no repite inferencias ni modifica su consumo.

Validación: **40 pruebas focalizadas pasaron**, junto con Ruff pyflakes y
`git diff --check`. El sitio, la configuración aprobada y el fixture no cambiaron.
