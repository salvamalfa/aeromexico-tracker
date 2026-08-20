# Etapa 0 — Matriz de conectividad

Fecha de prueba: 2026-08-20
Entorno: Windows 11 Pro, Python 3.13.15, httpx 0.28.1, Playwright 1.62.0,
Chromium 151.0.7922.34

## Método

1. `python -m src.smoke_test --json` hizo un GET con `Range: bytes=0-2047`,
   redirects habilitados y timeout de 20 segundos por fuente.
2. Las llamadas SEC usaron el `SEC_USER_AGENT` real del `.env` local.
3. Solo las fallas sin explicación de credenciales escalaron a Playwright.
4. Aeroméxico IR se probó primero headless y luego en un perfil visible, nuevo y
   aislado. No se descargaron documentos ni se usaron sesiones existentes.

Los probes parciales no se consideran archivos fuente y no se almacenan. La única
descarga completa de esta etapa —el catálogo SEC de tickers— sí se preservó en
bronze con hash y metadata.

## Resultado

| Fuente | URL de prueba | HTTP directo | Playwright | Computer use | Evidencia / limitación |
|---|---|---:|---:|---:|---|
| SEC submissions | `https://data.sec.gov/submissions/CIK0001561861.json` | Sí, 206 | No | No | Range parcial aceptado; identidad SEC enviada |
| SEC companyfacts | `https://data.sec.gov/api/xbrl/companyfacts/CIK0001561861.json` | Sí, 206 | No | No | Range parcial aceptado; no valida aún contenido XBRL |
| Aeroméxico IR | `https://ir.aeromexico.com/financial-information/quarterly-results` | No, timeout | Sí, visible | No | Headless falló con `ERR_HTTP2_PROTOCOL_ERROR`; visible devolvió 200 y título `Quarterly Results | Aeromexico` |
| BMV XBRL | `https://www.bmv.com.mx/es/emisoras/archivos-estadar-xbrl` | Sí, 200 | No | No | Valida página; AJAX/filtros/ZIP se verifican en Etapa 2 |
| AFAC | URL pública de estadística mensual en gob.mx | Sí, 206 | No | No | Resultado mejor que la expectativa previa; enlaces de archivos se verifican en Etapa 3 |
| BTS TranStats | `https://transtats.bts.gov/` | Sí, 200 | No | No | Valida portada; POST y descarga T-100 se verifican en Etapa 5 |
| Banxico SIE | `https://www.banxico.org.mx/SieAPIRest/service/v1/token` | Sí, 200 | No | No | Página de obtención de token accesible; token todavía vacío |
| EIA API | `https://api.eia.gov/v2/` | Sí, condicionado | No | No | 403 esperado sin `EIA_API_KEY`; el host responde y requiere credencial gratuita |

## Conclusión operativa

- SEC es automatizable con httpx y rate limit de 5 solicitudes/segundo.
- El portal IR de Aeroméxico no debe ser dependencia primaria: usar EDGAR y
  reservar Playwright visible como fallback local.
- BMV, AFAC y BTS requieren una segunda prueba sobre sus descargas reales antes
  de declarar automatización end-to-end.
- No se encontró una necesidad actual de computer use.
- EIA no es un problema anti-bot; falta una API key o se usará FRED como alternativa.
