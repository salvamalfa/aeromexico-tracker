# Decisión 009 — Hosting del backend del chat en Railway

Fecha: 2026-10-08 (registro de una decisión tomada entre el 4 y el 8 de octubre de 2026)
Estado: aceptada

## Contexto

El backend del chat (`src/conversational_analytics/`) necesita un proceso
Python siempre disponible, un volumen persistente para su estado SQLite y una
URL HTTPS que la página de GitHub Pages pueda llamar. Lo usa un solo dueño, de
forma intermitente. El 4 de octubre se compararon Railway (Free y Hobby) y un
VPS de Hostinger; esa comparación y la guía del VPS quedaron como historia en
`docs/archivo/chat-mvp/`.

## Decisión

- El backend corre en **Railway**: una sola instancia en la región `sfo`, con
  suspensión cuando no hay tráfico (serverless) y un volumen montado en
  `/data` para el estado del chat.
- Se construye con `Dockerfile.chat` y arranca con `scripts/start_chat_runtime.py`.
  Solo los archivos que entran a la imagen disparan un redespliegue: la lista
  está en la configuración del servicio y versionada en `railway.toml`.
- Acceso con contraseña de un solo usuario. Modelo, topes de gasto y límites
  se configuran con variables de Railway (ver `docs/chat/railway.md`).
- No se usa el VPS de Hostinger.

## Consecuencias

- No hay servidores que mantener (sistema operativo, TLS, respaldos del host);
  a cambio, la operación depende de la plataforma y de su conector.
- Tras la suspensión, la primera petición tarda unos segundos en arrancar.
- Con una sola instancia y un volumen, no hay alta disponibilidad; un turno
  en curso se corta si el servicio se redespliega. Por eso las rutas de
  redespliegue se limitan a los archivos de la imagen.
- Cambiar de proveedor implica migrar el volumen `/data` y la URL que usa la
  página publicada.
