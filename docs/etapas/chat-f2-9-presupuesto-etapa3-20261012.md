# F2.9 · Cotización offline de etapa 3 · 2026-10-12

Se sustituyó la proyección heredada de US$6.58 por una estimación basada en el
uso observado de Sol low en etapa 2, los 30 casos/34 mensajes de negocio, el
prompt R2 propuesto y el esquema actual de 13 herramientas. La cotización
resulta en US$7.05–7.21 con margen de 35%; si el saldo confirmado fuera cero,
propone US$8 disponibles. La autorización de US$8 de etapa 2 no se reutiliza.

El preflight offline observó 55 llamadas deterministas de herramienta,
95,232 bytes agregados de resultados serializados y un máximo de 15,652 bytes,
dentro del límite de 16,000. Se modelaron hasta 89 solicitudes y se aplicó un
proxy explícito de 3–4 bytes UTF-8 por token al delta de 6,359 bytes por
solicitud (R1→R2 y esquema de 7→13 definiciones). La salida no presenta ese
proxy como medición de tokens del proveedor. El saldo de cuenta es desconocido;
el presupuesto y R2 siguen sin aprobación/fondeo y no se hicieron llamadas ni
se leyeron credenciales.

Validación focal: `pytest tests/test_chat_f29_final_campaign_preflight.py
tests/test_chat_f29_stage3_coverage.py -q` pasó 30 pruebas. El preflight offline
confirmó el mismo hash de campaña con reserva propuesta US$8 que el JSON
público agregado. Artefactos reproducibles: [cotización JSON](../chat/revision-fase-2/F2.9-etapa-3-presupuesto-actual.json)
y [nota técnica](../chat/revision-fase-2/F2.9-etapa-3-presupuesto-actual.md).
