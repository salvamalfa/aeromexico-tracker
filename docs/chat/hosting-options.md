# Hosting para un único usuario

Revisión de precios y condiciones oficiales: **4 de octubre de 2026**. El dueño
usará el chat de 09:00 a 17:00 entre semana, de forma intermitente, y acepta
esperar el arranque. La recomendación es **probar Railway Free con Serverless y
un volumen persistente**, y pasar a Hobby si las mediciones superan el crédito
o los recursos disponibles. No se creó una cuenta ni se contrató un servicio.

## Opciones

| Opción | Costo de hosting | Recursos relevantes | Adecuación al piloto |
|---|---|---|---|
| Railway Free | US$0; US$1 de crédito mensual de recursos | Hasta 1 vCPU, 0,5 GB de RAM, un volumen de 0,5 GB, una réplica | Primera prueba razonable con suspensión; el crédito puede agotarse. |
| Railway Hobby | Mínimo US$5/mes, incluidos US$5 de uso; se paga el excedente | Hasta 5 GB de volumen y límites de CPU/RAM mayores | Alternativa sencilla si Free no alcanza; no requiere Pro para un usuario. |
| VPS Hostinger | Desde MX$100/mes según la cotización del dueño | Hay que verificar plan, plazo, renovación, impuestos y recursos | Control completo; requiere mantener Linux, TLS, backups y el servicio. |

Railway inicia con una **prueba de US$5 durante hasta 30 días**; después Free
dispone de US$1 por mes, sin acumulación. Es distinto del crédito permanente.
Una cuenta con Limited Trial tiene restricciones de salida: confirmar acceso
HTTPS a OpenAI antes de considerar viable esa cuenta. La verificación de cuenta
es independiente del correcto funcionamiento del código.

Free permite un dominio generado por Railway; así no hace falta cambiar DNS
de formamx.com. Su tabla actual no incluye dominios propios fuera del Trial;
Hobby sí los permite. El plan Web Empresarial existente puede conservar la otra
página, pero no ejecutar esta API Python.

## Suspensión y estimación de consumo

Serverless suspende un servicio después de aproximadamente **5–10 minutos sin
tráfico saliente** y lo despierta una petición. También cuentan las respuestas
a tráfico entrante, telemetría y conexiones externas. No equivale a programar
un horario de oficina: visitas o monitores de salud pueden mantenerlo despierto.
No añadas un monitor que consulte la API continuamente para este piloto.
El primer acceso puede tardar o devolver un 502 mientras arranca; el usuario
puede reintentar, conservando la deduplicación del envío del chat.

Los precios de contenedores publicados son US$10/GB de RAM al mes,
US$20/vCPU al mes, US$0,15/GB de volumen al mes y US$0,05/GB de salida.
No son las tarifas de las máquinas virtuales/sandboxes de Railway.

Como escenario ilustrativo, 22 días × 8 horas = **176 horas activas al mes**:

| Supuesto de RAM media durante esas horas | CPU media de 0,02 vCPU | Volumen usado de 0,1 GB y salida de 0,1 GB | Total aproximado de recursos |
|---|---:|---:|---:|
| 0,125 GB | US$0,10 | US$0,02 | US$0,42/mes |
| 0,25 GB | US$0,10 | US$0,02 | US$0,73/mes |
| 0,5 GB | US$0,10 | US$0,02 | US$1,34/mes |

El cálculo usa 720 horas como mes de referencia; son supuestos, no mediciones
de Railway ni cotizaciones. La actividad real intermitente puede ser menor.
Un servicio de 0,25 GB siempre despierto consumiría US$2,50/mes **solo en RAM**,
por lo que la suspensión sí importa para Free. No se suman los créditos Trial y
Free como una bonificación mensual de US$6.

La medición local del snapshot real, API simulada y worker al arrancar registró
**82,3 MiB de memoria máxima del proceso**. Una medición separada del import y
cliente OpenAI registró 58,2 MiB. No se suman como una medición del servicio
real ni incluyen picos de turnos, SSE, contenedor o concurrencia: todavía hay
que medir el despliegue. La instalación aislada del perfil `chat-runtime`
ocupó **40 MiB con 25 paquetes**; su prueba con autenticación, snapshot, worker
y una consulta simulada alcanzó 122,9 MiB de memoria máxima. Estas mediciones
respaldan probar Free, sin garantizar sus recursos para turnos reales. El
perfil evita instalar las dependencias del pipeline en el backend.

## Preparación y condiciones de publicación

El backend requiere **una sola instancia y un volumen persistente** para
SQLite, sus sidecars, el lock del worker y la contabilidad importada. No basta
el disco efímero: suspensiones, reinicios o redespliegues deben conservar el
historial y las reservas. Los volúmenes de Railway no admiten réplicas y tienen
una breve interrupción durante redespliegues, compatible con este piloto.

El perfil de dependencias ligero se instala desde el lock del repo:

```bash
uv sync --locked --only-group chat-runtime
```

La configuración pública debe exigir contraseña y un origen HTTPS explícito
de Pages. Mantener `VITE_CHAT_ENABLED=false` y empezar con `CHAT_PROVIDER=mock`:
probar volumen/backup, suspensión/despertar, login, CORS y SSE antes de usar
OpenAI. No confiar cabeceras de proxy de cualquier origen para calcular IPs;
verificar primero el contrato de la plataforma y la cadena de proxies.

La elección Free/Hobby no aprueba la semántica ni completa las evaluaciones.
Antes del piloto real siguen vigentes los gates de calidad, HTTPS, retención y
revisión semántica. Las tarifas OpenAI y el presupuesto acumulado de US$10 de
comparación se conservan aparte del hosting; no se presume gratuidad por Data
Sharing. Medir uso y disco en Railway antes de decidir un upgrade.

## Fuentes oficiales

- [Railway: precios](https://railway.com/pricing).
- [Planes, crédito y tarifas de recursos](https://docs.railway.com/reference/pricing/plans).
- [Trial y restricciones de red](https://docs.railway.com/reference/pricing/free-trial).
- [Serverless: suspensión y arranque](https://docs.railway.com/reference/app-sleeping).
- [Volúmenes, límites y persistencia](https://docs.railway.com/reference/volumes).
- Para la alternativa VPS, [guía preparada de Hostinger](hostinger-vps.md).
