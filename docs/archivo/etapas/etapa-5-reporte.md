# Etapa 5 — Peers competitivos y BTS T-100

Fecha de cierre: 2026-08-23
Estado: COMPLETA

## Qué se construyó

- Pipeline SEC generalizado por `carrier_key` y CIK, sin duplicar el downloader de
  Aeroméxico.
- Perfiles YAML declarativos para Aeroméxico, Volaris, Viva Aerobus, Ryanair y Delta.
- Verificación de CIK contra el catálogo oficial SEC para Aeroméxico (`1561861`),
  Volaris (`1520504`), Ryanair (`1038683`) y Delta (`27904`).
- Ingesta y parseo trimestral de Volaris, Viva Aerobus y Delta; reconstrucción de
  Ryanair a trimestre calendario desde estadísticas mensuales.
- Extracción financiera trimestral de Delta desde el contexto inline XBRL consolidado,
  con conciliación independiente contra Companyfacts por accession y periodo exactos.
- Descarga anual BTS T-100 International Segment 2015–2026, filtrada a México–EE.UU.,
  con ASM, RPM y load factor derivados.
- Crosswalk de 210 identidades T-100: los peers tienen claves de negocio y el resto una
  clave BTS estable, sin nulos.
- Validadores ejecutables para CIK, cobertura trimestral, Delta, Ryanair y estabilidad
  T-100/Aeroméxico, registrados en el rebuild offline.
- Corrección preventiva en la conciliación AFAC/SEC: ahora filtra explícitamente
  `carrier_key = AEROMEXICO` al convivir peers en la tabla SEC.
- Matriz de definiciones y diferencias contables en `docs/peers-comparabilidad.md`.

## Datos obtenidos

La etapa añadió 126 artefactos físicos a bronze por 109,984,076 bytes. Los 126
coinciden con su SHA-256 del manifiesto; ningún archivo fue sobrescrito.

| Fuente | Artefactos | Bytes | Cobertura |
|---|---:|---:|---|
| SEC Volaris | 57 | 42,385,877 | 2022Q4–2026Q2 |
| SEC Ryanair | 10 | 28,197,882 | 20-F FY2023–FY2026 + catálogos |
| SEC Delta | 32 | 30,410,049 | 2023Q1–2026Q2 + 10-K |
| Viva IR | 14 | 4,873,862 | 2023Q1–2026Q2 |
| Ryanair IR | 1 | 235,984 | 2021M08–2026M07 |
| BTS T-100 | 12 | 3,880,422 | 2015M01–2026M05 |

| Salida silver | Filas | Rango | Tamaño |
|---|---:|---|---:|
| `sec_peer_identities.parquet` | 4 | snapshot | 5,105 bytes |
| `sec_peer_filings_index.parquet` | 39 | 2023–2026 | 8,014 bytes |
| `sec_peer_filing_documents.parquet` | 93 | 2023–2026 | 18,959 bytes |
| `peer_operating_metrics.parquet` | 352 | 2021M08–2026Q2 | 22,354 bytes |
| `peer_financials.parquet` | 61 | 2022Q4–2026Q2 | 16,530 bytes |
| `bts_t100_segment.parquet` | 189,854 | 2015M01–2026M05 | 7,258,706 bytes |
| `delta_companyfacts_reconciliation.parquet` | 33 | 2023Q1–2026Q2 | 5,782 bytes |
| `ryanair_fiscal_reconciliation.parquet` | 4 | FY2023–FY2026 | 5,951 bytes |
| `bts_t100_aeromexico_validation.parquet` | 3 | 2025Q1–2026Q1 | 2,371 bytes |

T-100 2026 contiene enero–mayo. Junio no se interpreta como cero ni como falla del
pipeline: la publicación internacional tiene rezago y restricción temporal.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Suite completa | PASS | 85 tests |
| Etapa 4 sin regresión | PASS | 27/27 controles |
| Definición de aceptación Etapa 5 | PASS | 12/12 controles |
| Rebuild global offline | PASS | SEC, BMV, AFAC, Etapa 4, peers y T-100 |
| Idempotencia offline | PASS | 6/6 salidas críticas con SHA-256 idéntico |
| Integridad bronze Etapa 5 | PASS | 126/126 hashes válidos |
| CIK SEC | PASS | 4/4 identidades verificadas |
| Volaris | PASS | 15 trimestres, 2022Q4–2026Q2 |
| Viva Aerobus | PASS | 14 trimestres, 2023Q1–2026Q2 |
| Ryanair | PASS | 19 trimestres, 2021Q4–2026Q2 |
| Delta | PASS | 11 trimestres, 2023Q1–2026Q2 |
| Delta 10-Q ↔ Companyfacts | PASS | 33/33; diferencia máxima 0.000% |
| Ryanair mensual ↔ fiscal | PASS | pasajeros máx. 0.296%; LF máx. 0.487 pp |
| T-100 México–EE.UU. | PASS | 189,854 filas; 2015M01–2026M05 |
| Crosswalk T-100 | PASS | 210 identidades; cero `carrier_key` nulos |
| T-100 AERO / ASM internacional | PASS | media 28.532%; CV 3.848%; QoQ máx. 8.686% |

La proporción T-100 EE.UU. / ASM internacional reportado fue 30.026% en 2025Q1,
27.417% en 2025Q2 y 28.152% en 2026Q1. Solo entran trimestres completos en ambas
fuentes; 2026Q2 queda fuera porque T-100 aún no publica junio.

## Qué NO funcionó y por qué

- IAG devolvió HTTP 403 con `httpx` y con Playwright headless por Cloudflare.
- Una prueba visible de Playwright fue cerrada durante la ejecución y no se usó como
  evidencia. Después se obtuvo autorización explícita antes de volver a abrir navegador.
- El control de Chrome se detuvo por no poder confirmar de forma segura la URL activa.
- El navegador integrado sí superó la verificación automática y confirmó la página
  oficial y el Annual Report 2025. El visor no produjo un archivo local exportable, por
  lo que no se añadió un pseudoarchivo ni una descarga incompleta a bronze.
- La primera reconstrucción global mezcló pasajeros mensuales de Ryanair con la
  conciliación AFAC/SEC porque esa validación heredada no filtraba `carrier_key`. Se
  corrigió el filtro y la correlación Aeroméxico volvió a 0.999303 con 14 meses.

## Decisiones tomadas

- Mantener cuatro peers implementados en el MVP: Volaris, Viva Aerobus, Ryanair y
  Delta.
- Excluir IAG del MVP. Es un grupo multi-aerolínea y su relación esfuerzo/beneficio es
  inferior; la decisión y la ruta futura están en
  `docs/decisiones/decision-006-acceso-iag.md`.
- Recomendar **Copa** como siguiente peer opcional por similitud de red/hub y exposición
  latinoamericana. **LATAM** sería el segundo candidato por escala regional.
- Diferir **Gol** y **Azul** hasta resolver comparabilidad de reestructuraciones,
  definiciones y moneda. No se implementó ningún peer opcional sin autorización.
- Reconstruir Ryanair en calendario únicamente para métricas operativas. Los financieros
  conservan año fiscal marzo y una advertencia explícita.
- Para Delta, usar inline XBRL del 10-Q como extracción primaria y Companyfacts como
  verificación; no sustituir silenciosamente una cifra parseada por la cifra ancla.
- Generar claves estables `BTS_*` para carriers no prioritarios. “Mapeado” significa
  identidad trazable, no asignación forzada a una marca del proyecto.
- Añadir PyYAML 6.0.3 al entorno reproducible con autorización del usuario.

## Supuestos hechos

- El catálogo SEC descargado es la autoridad para CIK y ticker de emisores SEC.
- La tabla mensual oficial de Ryanair es apropiada para reconstruir pasajeros y load
  factor calendario; no permite reconstruir estados financieros calendario.
- La distancia T-100 se expresa en millas y permite derivar ASM/RPM como
  `seats/passengers × distance` para cada segmento.
- La estabilidad T-100 se evalúa solo donde Aeroméxico tiene tres meses completos de
  ASM internacional y BTS tiene tres meses completos.
- IAG solo sería comparable como grupo; una cifra consolidada nunca se etiquetará como
  Iberia.

## Preguntas para el usuario

Ninguna pendiente para cerrar la Etapa 5.

## Riesgos para la siguiente etapa

- Etapa 6 deberá convertir millas/kilómetros y USD/EUR con reglas explícitas por periodo.
- Ryanair requiere doble eje temporal (`calendar_period_id` y `fiscal_period_id`).
- IFRS 16 y ASC 842 limitan comparaciones de deuda, arrendamientos y EBITDAR con Delta.
- Companyfacts puede restatar comparativos; la conciliación por accession evita mezclar
  una versión posterior con el 10-Q original.
- T-100 2026 seguirá cambiando al liberarse meses internacionales; cada actualización
  debe crear nueva evidencia bronze sin sobrescribir.
- Los 229 nombres AFAC no mapeados siguen fuera del business view; no afectan las claves
  T-100 generadas en esta etapa.

## Comandos para reproducir

```powershell
python -m src.ingest.peers.stage5
python -m src.ingest.bts.t100
python -m src.parse.peers.stage5
python -m src.parse.bts.t100
python -m src.transform.validate_stage5
python -m src.rebuild
python -m pytest
```
