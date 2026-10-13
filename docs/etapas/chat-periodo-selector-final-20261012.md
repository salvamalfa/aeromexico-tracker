# Chat · ajuste final del periodo · 12 oct 2026 (Ciudad de México)

Stage 3 completó 30 casos/34 mensajes; revisión privada: 16 correctos, 14 problemas y 13 notas de periodo.
En 12 casos con nota de periodo el evaluador envió contexto vacío; la UI ya transmite automáticamente el selector en cada mensaje.
El ajuste mínimo de R2 prioriza el periodo seleccionado si la pregunta lo omite, preserva periodo explícito y seguimiento inequívoco, y pregunta solo por otros campos faltantes.
La búsqueda puede reformular términos al idioma de la evidencia; una búsqueda española vacía no demuestra falta de acceso al reporte inglés.
Autorización sin otra evaluación pagada: [decisión fijada](https://github.com/salvamalfa/aeromexico-tracker/blob/76407da561ac1ff799c012ce5390c01176b30772/docs/decisiones/20261012-chat-periodo-selector-cierre-fase2.md).
Prompt y hash exacto final: [configuración versionada](../../config/chat/prompt_candidates/system_prompt_r2-proposed.json) y [recibo](../../config/chat/prompt_approval.json).
Validación: 40 pruebas focalizadas; selector Q1/Q2 con proveedor falso confirma el contexto actual en sesiones nuevas y reutilizadas, sin consumo del modelo.
Estas pruebas no acreditan cumplimiento del modelo tras el ajuste ni un gate de calidad nuevo.
Fase 2 implementada; la activación explícita de R2 y capacidades aprobadas queda pendiente de verificar el despliegue.
