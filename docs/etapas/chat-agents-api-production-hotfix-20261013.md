# Chat · corrección del contrato de funciones Agents API · 13 oct 2026

Agents API rechazó una solicitud con HTTP 400 por `agent.tools[0].strict`.
El mismo generador de herramientas se utiliza en el runtime de producción R1.
Este hotfix omite únicamente ese campo de Responses API al enviar funciones
a Agents API y conserva los esquemas JSON normalizados y su validación estricta.

La prueba offline captura el POST del SDK oficial con transporte mock, verifica
los trece contratos de herramientas existentes y confirma que una declaración
explícita `strict=False` continúa siendo rechazada. El cambio no altera el
prompt, las capacidades activas, el sitio ni sus datos. No consume API pagada.
Las pruebas focalizadas de proveedor, herramientas y conciliación pasaron:
**144 pruebas**. `git diff --check` también pasó.
