# Chat analítico de Airlines Tracker

El chat permite preguntar por las cifras del dashboard, compararlas y consultar
sus fuentes. Usa una copia verificada de los datos publicados; los cálculos los
ejecuta Python y el modelo redacta la respuesta. Su acceso requiere la
configuración del servicio y una contraseña autorizada: el panel público no
concede acceso abierto al backend.

## Interfaz del dashboard

1. Selecciona una vista, aerolínea y periodo en el dashboard.
2. Abre el chat o pulsa **Pregunta** en una tarjeta. La tarjeta aparece como un
   contexto adjunto que puedes quitar; este paso no envía una consulta.
3. Escribe la pregunta. Por ejemplo: «Compara los pasajeros de Aeroméxico y
   Volaris en el trimestre seleccionado» o «¿Qué significa esta métrica y cuál
   es su fuente?».
4. Comprueba el periodo, la unidad y las fuentes de la respuesta. Si cambias de
   tema o de datos, puedes iniciar otra conversación.

También puedes pedir una serie histórica, una comparación entre periodos o
evidencia de reportes y noticias, según las herramientas habilitadas. «Pasajeros»
puede requerir aclaración: los reportes de las empresas y AFAC tienen universos
distintos. Una pregunta no garantiza que el dato exista en el periodo elegido.

El chat acompaña al dashboard en escritorio y se abre como diálogo en pantallas
pequeñas. Se puede cerrar y volver a abrir desde el icono de interrogación. Un
fallo de conexión aparece como aviso; no se muestran respuestas simuladas.

## Datos y contexto

Cada conversación fija una versión de datos y de definiciones. El chat lee
`site/data/v1/`, sin abrir el almacén privado ni las capas bronze o silver.
Las herramientas validan la métrica, entidad, periodo y filtros antes de
calcular. Las tablas, gráficas y referencias provienen de esos resultados.

La vista y la tarjeta adjunta ayudan a interpretar la pregunta. Sus filtros no
amplían la cobertura ni conceden permisos. La respuesta debe indicar el periodo
utilizado y conservar los faltantes como `missing`, sin convertirlos en cero.
Aeroméxico consolidado, Aerovías y Connect mantienen las distinciones de cada
fuente. Los porcentajes y los puntos porcentuales tampoco son intercambiables.

Las búsquedas de reportes y noticias usan un índice de extractos aprobados;
no consultan todo internet ni descargan artículos durante la conversación.
El catálogo de [métricas](../../config/chat/metrics.yaml) y
[entidades](../../config/chat/entities.yaml) define el alcance disponible.

### Mapa de vuelos regulares

El mapa oficial tiene una herramienta y una activación propias. Cuando están
habilitadas, la pregunta conserva el ámbito, meses, región y aerolíneas de la
selección. Los datos AFAC son por pares de ciudades para todas las aerolíneas;
BTS permite consultar los operadores publicados entre México y Estados Unidos.
El mapa mide vuelos realizados, con cobertura declarada; no mide pasajeros ni
rentabilidad. Un periodo sin observaciones conserva el faltante.

El [contrato del mapa en el backend](../../src/conversational_analytics/README.md#mapa-de-vuelos-regulares)
explica filtros, versiones y límites. La
[guía de Railway](railway.md#activar-el-mapa-oficial) documenta su activación.

## Estado de entrega

La [verificación operativa documentada](../etapas/chat-fase2-cierre-operativo-20261012.md)
del 12 de octubre de 2026 registró R2 con `gpt-6.1-sol` en Railway y las
capacidades de rutas, métricas financieras y evidencia activas. Esa comprobación
no acredita disponibilidad actual ni calidad de todas las respuestas.

La evaluación histórica incluyó 30 casos y 34 mensajes: la revisión del dueño
clasificó 16 casos correctos y 14 con problemas. Después se ajustó el prompt
sin repetir la evaluación pagada. No se acreditó el criterio original de
70 casos. El expediente, sus límites y los requisitos para una campaña nueva
están en [evaluaciones y presupuesto](evaluaciones-presupuesto.md).

### Registro histórico al 8 de octubre de 2026

La [activación del MVP](../etapas/chat-mvp-activacion-20261007.md), las
[correcciones de recuperación](../etapas/chat-recuperacion-correcciones-20261008.md)
y la [incorporación de tablas](../etapas/chat-tablas-presentacion-20261008.md)
conservan la evidencia de esas entregas. Sus resultados corresponden a sus
versiones y fechas; no validan por sí solos el prompt actual.

## Arquitectura y operación

- [Cómo funciona el ciclo del chat](../arquitectura/airline-tracker-agents-api.md):
  modelo, herramientas, datos y respuesta, con diagramas y recorridos visuales.
- [Referencia del backend](../../src/conversational_analytics/README.md):
  API, autenticación, configuración y versiones.
- [Operación local](operations.md) y [despliegue en Railway](railway.md).
- [Revisión de respuestas](revision-respuestas.md) e [intercambio de datos](data-sharing.md).

## Recuperar un turno `provider_error`

La recuperación excepcional de un turno fallido usa
`scripts/chat/reconcile_failed_turn.py`. Primero comprueba la elegibilidad en
modo de solo lectura; aplicar cambios requiere una petición explícita del
dueño. No reenvía la pregunta ni genera otra respuesta. El
[procedimiento del backend](../../src/conversational_analytics/README.md#recuperar-un-turno-provider_error)
conserva los controles de identidad y versiones.

## F2.0 — Modelo y esfuerzo fijados

El servicio registra el modelo, esfuerzo y verbosidad de cada turno. Cambiar
esa configuración requiere una conversación nueva. Los valores permitidos
están en [la referencia del backend](../../src/conversational_analytics/README.md#proveedores-y-configuración)
y en [`config/chat/models.json`](../../config/chat/models.json).

## Cierre documental del 19 de octubre

El [índice histórico](../archivo/README.md#retiro-de-instrucciones-reemplazadas-del-chat-19-de-octubre-de-2026)
conserva los enlaces fijos a las instrucciones retiradas al cerrar la fase 2.
La [auditoría documental](../referencias/source-updates-20261018/lifecycle-audit.json)
registra qué se conservó y por qué. Los presupuestos, recibos, decisiones y
pruebas históricas siguen disponibles para reproducir su expediente.
