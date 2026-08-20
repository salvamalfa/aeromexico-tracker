# Decision 002 — Acceso al portal IR de Aeroméxico

Fecha: 2026-08-20
Estado: Aceptada

## Niveles probados

- Nivel 1, httpx: **falló** por `ReadTimeout` a los 20 segundos.
- Nivel 2, Playwright headless: **falló** con `net::ERR_HTTP2_PROTOCOL_ERROR`.
- Nivel 3, Playwright visible con contexto nuevo: **funcionó**, HTTP 200 y título
  `Quarterly Results | Aeromexico`.
- Nivel 4, computer use: **no fue necesario**.

## Método adoptado

La fuente primaria de filings y comunicados será SEC EDGAR. El portal IR se
mantiene como fallback mediante Playwright visible y aislado. No se usarán
perfiles de navegador ni sesiones autenticadas del usuario.

## ¿Automatizable en CI?

No se dependerá de este portal en CI mientras EDGAR contenga el documento. Un
navegador visible requeriría display virtual y añade fragilidad sin aportar una
fuente más autoritativa. Esta decisión se revisará solo si EDGAR omite un anexo.

## Frecuencia

Trimestral, únicamente como fallback después de comprobar SEC EDGAR.
