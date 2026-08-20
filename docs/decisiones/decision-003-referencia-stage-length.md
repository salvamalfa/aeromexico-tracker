# Decisión 003 — Referencia para ajuste por stage length

Fecha: 2026-08-20

## Contexto

El plan citaba 1,834 km como denominador de la fórmula de ajuste de RASK. La
revisión de todas las versiones del prospecto SEC demostró que ese valor pertenecía
al F-1 original y fue actualizado en enmiendas posteriores.

## Evidencia

| Filing | Fecha | Referencia publicada |
|---|---:|---:|
| F-1 `0001193125-24-137345` | 2024-05-13 | 1,834 km |
| F-1/A `0001193125-24-202983` | 2024-08-20 | 1,865 km |
| F-1/A `0001193125-24-272514` | 2024-12-06 | 1,909 km |
| F-1/A `0001193125-25-186482` | 2025-08-22 | 1,982 km |
| F-1/A `0001193125-25-213530` | 2025-09-23 | 1,982 km |
| F-1/A final `0001193125-25-242656` | 2025-10-17 | 1,982 km |

La fórmula del prospecto final es:

`SLA RASK = RASK × (carrier average stage length / 1,982)^0.5`

El mismo prospecto usa la referencia vigente para SLA CASK ex-fuel.

## Decisión

La Etapa 6 utilizará **1,982 km** cuando reproduzca la comparación del prospecto
final. El denominador no se hardcodeará como constante universal: se modelará con
su accession, periodo de referencia y vigencia. Las versiones anteriores se
conservan en `silver/sec_reference_text.parquet` para reproducir análisis históricos.

## Consecuencia

El valor 1,834 km permanece documentado como dato correcto del F-1 original, pero
no controla el análisis posterior al F-1/A final. Forzar 1,834 km habría reproducido
una versión obsoleta de la fuente.
