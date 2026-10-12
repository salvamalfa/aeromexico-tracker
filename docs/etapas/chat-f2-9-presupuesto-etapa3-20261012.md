# F2.9 · Estimación offline de etapa 3 · 2026-10-12

Se reemplazó la proyección previa con una derivación contra el HEAD integrado
`476c3956f9582f11623fbc5fa28f13a0c5b9d068`. El plan actual fija 30 casos,
34 mensajes, Sol low y una reserva propuesta de US$8; estima US$7.06–7.23.
El saldo actual no está confirmado y solo afecta la recarga necesaria. R2 y la
campaña siguen pendientes de aprobación/fondeo.

La cobertura offline clasifica 12 casos como soportados, 12 con cobertura
faltante y 6 bloqueados por aprobación. Registró 55 llamadas deterministas,
95,316 bytes de resultados serializados y un máximo de 15,652 bytes, dentro del
límite de 16,000. El esquema live de 13 herramientas mide 7,620 bytes; el delta
de contexto R1→R2 más esquema es 6,543 bytes por solicitud. Se mantiene el
proxy explícito de 3–4 bytes UTF-8 por token y el extremo superior de 89
solicitudes. No se hizo llamada al proveedor ni se leyó una credencial.

El preflight y la admisión usan una reserva estimada por mensaje coherente con
34 mensajes. No es un hard cap: si se desconoce el gasto, la campaña detiene y
bloquea el resume; los resumes válidos conservan la identidad y el gasto
acumulado.

Artefactos vigentes: [estimación JSON](../chat/revision-fase-2/F2.9-etapa-3-presupuesto-actual.json),
[nota técnica](../chat/revision-fase-2/F2.9-etapa-3-presupuesto-actual.md) y
[matriz](../chat/revision-fase-2/F2.9-matriz-cobertura-final.md). El cierre de
etapa 2 permanece inmutable.
