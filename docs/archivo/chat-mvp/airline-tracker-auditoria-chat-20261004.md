# Correcciones de la auditoría del chat (PRs #81–#83)

## Alcance

Una auditoría de los PRs #81, #82 y #83 (chat analítico, cuotas y arranque en
Railway) encontró tres defectos en código ya fusionado y una implicación no
documentada de la política de tokens. Esta etapa los corrige. Los hallazgos
sobre el PR #84 (cierre ordenado, recuperación de uso tras cancelar y
Dockerfile simplificado) quedaron como revisión en ese PR y no se tocan aquí:
este cambio no modifica ninguno de sus archivos.

No cambian `site/`, los datos publicados, `config/chat/*.yaml` ni el esquema
semántico, así que `semantic_version` y las versiones fijadas del holdout se
conservan. No hay llamadas a proveedores, aprobaciones ni cambios de cuotas.

## Login detrás del edge de Railway

El launcher arranca Uvicorn con `proxy_headers=False` y sin
`CHAT_TRUSTED_PROXY`. En Railway todas las conexiones llegan desde el edge, de
modo que el límite de 5 intentos por cliente cada 15 minutos se volvía un
límite global: cualquiera con la URL podía bloquear el login del dueño de forma
indefinida.

- `CHAT_TRUSTED_PROXY` acepta IPs sueltas y redes CIDR. Una red solo se admite
  dentro de rangos loopback, privados o de espacio compartido (RFC 6598), para
  que una configuración no pueda confiar en direcciones públicas.
- `client_address` recorre `X-Forwarded-For` desde la derecha, omite los saltos
  confiables y usa la primera dirección restante. Lo que el cliente haya escrito
  más a la izquierda se ignora; una entrada inválida conserva la IP del par.
- `scripts/start_chat_runtime.py` fija por defecto `100.64.0.0/10`, el rango
  desde el que el edge de Railway llega al contenedor. Railway es la única
  entrada al servicio y reemplaza el `X-Forwarded-For` del cliente. Un valor
  explícito en el panel prevalece.

Fuentes: respuestas del personal de Railway en Central Station sobre
[cabeceras del edge](https://station.railway.com/questions/security-critical-questions-on-edge-prox-8fddd775)
y [IP real del cliente](https://station.railway.com/questions/which-header-should-i-rely-on-for-real-c-d78a6f96),
y registros públicos de despliegues en Railway con pares `100.64.0.x`. Railway
no publica el rango como contrato; si sus pares cambiaran, el límite vuelve al
comportamiento anterior (agrupado), sin abrir la confianza a direcciones
públicas. Con la CDN de Railway activa hay que verificar en logs que el límite
siga viendo clientes y no nodos de la CDN.

## Series de tiempo

`get_time_series` ordenaba los periodos de forma ascendente y aplicaba
`rows[:limit]` (máximo 20). Sobre `site/`, la participación de Aeroméxico de
2024M01 a 2026M06 devolvía hasta 2025M08, y la gráfica adjunta a la respuesta
terminaba ahí sin aviso. Con más de 32 periodos la herramienta fallaba en
`validate_plan`.

Ahora conserva los `limit` periodos más recientes, marca `truncated`, informa
`omitted_earlier_periods` y añade "(últimos N de M periodos)" al título de la
gráfica. Sin recorte, el título y las filas no cambian. Un rango sin periodos
publicados consulta solo sus extremos, que se reportan como faltantes (nunca
como cero).

## Etiquetas de procedencia

`_source_refs` rotulaba como "Fuente pública AFAC" cualquier host distinto del
dashboard, incluidos `sec.gov` y `github.com`. La etiqueta ahora depende del
host y de la ruta: solo `gob.mx/afac/...` se cita como AFAC. Las métricas
actuales conservan exactamente sus etiquetas.

## Política de tokens y Data Sharing

El cupo de 200.000 tokens diarios responde a la oferta de Data Sharing de
OpenAI (250.000 diarios para los modelos principales en niveles de uso 1–2),
ya documentada en `docs/chat/data-sharing.md`. La auditoría añade su capacidad
efectiva: con una reserva mínima de 150.000 y ~40.000 tokens medidos por
pregunta, se admiten unas dos preguntas al día. La página de OpenAI excluye
"tool use" del incentivo, y este chat usa herramientas `function`; por eso la
bonificación de esta integración sigue sin confirmarse. No se cambiaron los
valores: subir la capacidad es una decisión del dueño.

## Validación

- Pruebas nuevas: confianza por red y saltos confiables, rechazo de redes
  públicas en la configuración, valor por defecto del launcher, series largas
  (últimos periodos, más de 32 meses, `limit` inválido) y etiquetas por host.
- Pruebas focales del chat, suite pública completa, Ruff y formato en los
  archivos tocados; `git merge-tree` contra la rama del PR #84 sin conflictos.
