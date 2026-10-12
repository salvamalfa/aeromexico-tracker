# F2.9 · Integridad del preflight parcial · 2026-10-11

El perfil de etapa 3 ahora se llama `config/chat/f2_9_business_stage3_partial.json` y se identifica como `f2-9-stage-3-business-partial-v1`. Su alcance es solo negocio: 30 casos, 34 mensajes y una repetición de Sol low. La cohorte safety y los casos de prompt injection quedan excluidos por instrucción explícita del dueño; este preflight no afirma validación de seguridad completa.

`prepare_final_campaign.py` comprueba el SHA-256 del artefacto público `docs/chat/revision-fase-2/F2.9-cierre-etapa-2.json` (`bf03c82e52fcff3b89fbcf18794218300149ae6859950199a6fd90c56fdd522d`) antes de aceptar la evidencia de uso. Compara contra ese cierre los hashes de reporte y recuperación y los totales enteros positivos de entrada/salida (842,452 y 4,157). También verifica la selección de Sol low, 15 slots medidos, 30 casos y 34 mensajes; cambiar el perfil con hashes inventados, totales menores o tipos inválidos se rechaza antes de producir el plan.

La matriz vigente conserva los límites: dependencias F2.3–F2.8, Gold y versiones de snapshot/semántica aún deben revisarse, y hace falta aprobación de presupuesto nueva. La estimación de US$6.58 sigue siendo planificación, no reserva aprobada ni límite de factura. No se ejecutaron llamadas ni se leyeron credenciales.

Validación: `pytest tests/test_chat_f29_final_campaign_preflight.py tests/test_chat_stage2_budget_admission_lineage.py tests/test_chat_stage2_finalization.py tests/test_chat_stage2_finalization_lineage.py -q` dio 39 pruebas y 8 subtests aprobados. El dry-run produjo US$6.58 y enlazó el hash del cierre público; llamadas al proveedor: cero.
