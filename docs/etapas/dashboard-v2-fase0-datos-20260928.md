# Dashboard v2 · Fase 0: datos de Volaris y Viva, representatividad y error por aerolínea

Fecha: 28 de septiembre de 2026. Rama `claude/aerolineas-tracker-redesign-zqk94j`.
Plan aprobado por el dueño: convertir el dashboard en un tracker de la industria
mexicana (Aeroméxico, Volaris y Viva) con un selector de aerolíneas por card.

Esta fase solo prepara y verifica datos. No cambia el dashboard, `site/`, el
Analysis Agent ni ninguna aprobación.

## Qué cambió

| Cambio | Archivo | Motivo |
|---|---|---|
| Pasajeros trimestrales de Volaris | `src/parse/profiles/volaris.yaml` | La economía unitaria exige pasajeros por trimestre y el perfil no los extraía. Fila `Passengers (thousands, scheduled & charter)`; los releases antiguos solo traen `Booked passengers (thousands)`, cuyo primer valor también es el trimestre. |
| Pasajeros trimestrales de Viva | `src/parse/profiles/viva_aerobus.yaml` | Fila `Booked passengers (thousands)`, presente en los 14 reportes 1T23–2T26. |
| **Corrección** de CASM ex-fuel de Volaris | `volaris.yaml` | El patrón sin ancla `casm ex fuel` capturaba el titular del release (“CASM ex fuel increased 7.9% to $4.39 cents”) y guardaba **el porcentaje de variación** como valor: 7.9, 5.7, 21, 17… (hasta 13 ¢/ASK-km, más que el CASK). Ahora se ancla a las filas de la tabla. Las 15 cifras nuevas coinciden con el valor citado en cada titular. |
| 2T23 de Volaris completo | `volaris.yaml` | Ese release parte las etiquetas entre celdas (`seat miles (ASMs)`, `operating revenue per ASM (TRASM)`, `expenses per ASM (CASM)`, `passenger miles (RPMs)`, `Factor (scheduled, RPMs/ASMs)`). Faltaban ASM, RPM, TRASM, CASM y ocupación. |
| Portabilidad Linux | `src/transform/international_routes.py` | Los manifiestos `selection-*.json` en Bronze (inmutable) guardan rutas con `\` de Windows; en Linux el transform fallaba. Se normaliza el separador al leer. |

### Gold regenerado

`uv run python -m src.parse`, luego `uv run python -m src.transform` y después la
fase `dashboard` del pipeline (`dashboard.prepare`, sin reentrenar modelos).

- `fact_carrier_metrics.parquet`: +163 filas nuevas (pasajeros, ingreso por
  pasajero, crecimientos y TTM de Volaris y Viva) y 84 valores corregidos, todos
  del CASM/CASK ex-fuel de Volaris y sus derivados. El resto de las filas
  conserva byte a byte el valor anterior. Una reconstrucción en Linux difiere de
  la de Windows solo en ruido de coma flotante (≤ 1e-14 relativo) y en la zona
  horaria de `downloaded_at`; esas diferencias se descartaron para no introducir
  cambios sin significado (`dim_source_artifact` y `dim_fuel_period` no cambian).
- `fact_dashboard_coverage.parquet` y `bridge_record_lineage.parquet` se
  regeneraron. La versión anterior de la cobertura estaba desfasada: registraba
  8 trimestres de RASK de Aeroméxico cuando `fact_carrier_metrics` ya tenía 22.

## Economía unitaria: cobertura por aerolínea

Trimestres completos (pasajeros, ASK, ocupación, RASK y CASK):

| Aerolínea | Trimestres | Rango | CASK ex-fuel |
|---|---:|---|---|
| Aeroméxico | 22 | 1T21–2T26 | 8 trimestres (3T24–2T26) |
| Volaris | 15 | 4T22–2T26 | 15 |
| Viva | 14 | 1T23–2T26 | 14 |

- **Ocupación de Viva:** el reporte publica ocupación “scheduled, RPM/ASM” desde
  1T25 y antes una definición que cambió en julio de 2024. El parser solo toma la
  etiqueta nueva, así que para 1T23–4T24 se usa la ocupación **calculada** RPM/ASM
  (`load_factor_derived`) y así se declara.
- **Unidades:** RASK y CASK se expresan en ¢ USD por ASK-km. Volaris y Viva
  reportan por milla; la conversión `/ 1.609344` ya existía en `stage6_facts.py`.
- **Panel de la industria:** para no mezclar paneles distintos, el agregado de
  industria solo existe donde reportan las tres: **1T23–2T26, 14 trimestres**.

## ¿Representan las tres a la industria? (AFAC, pasajeros)

AFAC publica una fila por aerolínea mexicana y agrega a las extranjeras solo en el
total del mercado.

| Trimestre | Nacional: % del mercado | Internacional: % de aerolíneas mexicanas | Internacional: % del mercado (con extranjeras) | Total: % de aerolíneas mexicanas | Total: % del mercado |
|---|---:|---:|---:|---:|---:|
| 2T25 | 98.5 | 99.6 | 30.4 | 98.8 | 66.4 |
| 3T25 | 98.3 | 99.6 | 35.1 | 98.7 | 70.0 |
| 4T25 | 98.4 | 99.6 | 31.2 | 98.8 | 66.1 |
| 1T26 | 98.5 | 99.7 | 27.2 | 98.8 | 61.2 |
| 2T26 | 98.7 | 100.0 | 33.3 | 99.0 | 68.5 |

**Conclusión:**
- **Industria mexicana:** Aeroméxico, Volaris y Viva **son** la industria: ~99 %
  de los pasajeros de aerolíneas mexicanas en cada trimestre.
- **Nacional:** representan ~98.5 % del mercado.
- **Internacional:** dos terceras partes de los pasajeros viajan en aerolíneas
  extranjeras, que AFAC no desglosa por aerolínea.

Participación en 2T26 (pasajeros AFAC):

| | Nacional | Internacional (sobre mercado) | Total (sobre mercado) |
|---|---:|---:|---:|
| Aeroméxico | 24.3 % | 15.2 % | 20.1 % |
| Volaris | 35.7 % | 13.2 % | 25.4 % |
| Viva | 38.6 % | 4.8 % | 23.1 % |

## Error del estimador ruta × aerolínea, medido por aerolínea

**1) Backtest contra T-100** (`python -m src.analytics.route_carrier_backtest`). La
semilla viene del mismo panel observado, así que es una **cota inferior** del
error (§10 de `docs/estimacion-pasajeros-ruta-aerolinea.md`). Rutas competidas:

| Periodo | Aerolínea | Error de participación ponderado | p90 | Error en pasajeros |
|---|---|---:|---:|---:|
| 2025 | Aeroméxico | 1.97 pp | 5.8 pp | 6.0 % |
| 2025 | Volaris | 2.24 pp | 9.6 pp | 5.9 % |
| 2025 | Viva | 2.55 pp | 9.1 pp | 10.9 % |
| 2026 (ene–may) | Aeroméxico | 2.05 pp | 5.1 pp | 6.6 % |
| 2026 (ene–may) | Volaris | 1.96 pp | 6.3 pp | 4.8 % |
| 2026 (ene–may) | Viva | 1.89 pp | 4.4 pp | 8.7 % |

**2) Contraste fuera de muestra con la captura real de AeroDataBox** (ajuste
internacional contra celdas México–EE. UU. observadas por T-100; derivados privados
`international_t100_backtest_<mes>.parquet`):

| Mes | Aerolínea | Celdas | Suma estimada / observada | Error absoluto ponderado | Celdas que el ajuste no ve |
|---|---|---:|---:|---:|---:|
| 2026M04 | Grupo Aeroméxico | 79 | 1.014 | 6.8 % | 10 |
| 2026M04 | Volaris | 132 | 0.982 | **4.3 %** | 0 |
| 2026M04 | Viva | 65 | 0.979 | **15.2 %** | 7 |
| 2026M05 | Grupo Aeroméxico | 72 | 1.022 | 6.0 % | 5 |
| 2026M05 | Volaris | 124 | 0.979 | **4.3 %** | 0 |
| 2026M05 | Viva | 54 | 0.977 | **14.9 %** | 4 |

**Lectura:**
- **Volaris:** se estima tan bien o mejor que Aeroméxico.
- **Viva:** error internacional de ~15 %, más del doble que Aeroméxico, y rutas que
  la semilla no ve. En el mercado nacional su backtest es comparable al de los
  demás en participación, pero con mayor error en pasajeros.
- **Recomendación para la fase 3:** publicar los mapas de Volaris y Viva como
  `estimado`, con la advertencia de mayor incertidumbre en el internacional de
  Viva. Donde T-100 observa la celda, se muestra la observación (`observed_t100`),
  como ya ocurre con Aeroméxico.
- **Decisión del dueño:** esta medición se le presenta para decidir antes de
  publicar las estimaciones.

**Cobertura temporal de las estimaciones por ruta:** nacional 2026M03–2026M07 e
internacional 2026M04–2026M07, para las tres aerolíneas; es la misma ventana que
Aeroméxico.

## Límites y hallazgos para el diseño

- **Participación y denominador:** la tarjeta “Mercado” de la v2 usará como
  denominador los pasajeros de aerolíneas mexicanas, coherente con la definición
  de Industria (~99 %). La cifra histórica de `docs/analytics/hallazgos.md` (jun-26:
  Aeroméxico 19.1 %, Volaris 26.2 %) usa el total AFAC con extranjeras; son
  denominadores distintos y se documentan como tales.
- **Perímetros de los trimestrales:**
  - Volaris consolida Costa Rica y El Salvador.
  - Viva reporta pasajeros “booked” (boletos comprados para volar en el
    periodo).
  - Aeroméxico reporta pasajeros transportados.
  - En economía unitaria, las cifras de cada aerolínea son las de su propio
    reporte; no se mezclan con AFAC.
- **Posible fusión Volaris–Viva:** los reportes de 4T25 y 1T26 de Viva mencionan una
  transacción aprobada por su consejo con certificados y marcas independientes. No
  cambia los datos, pero es contexto para la tesis de la industria.

## Validación

- `uv run pytest -q tests/test_stage5_peers.py tests/test_stage6.py
  tests/test_international_routes.py tests/test_stage9_scd2.py
  tests/test_verify_identities.py`.
- Suite completa sin navegador sobre los datos restaurados.
- Los resultados se registran en el PR.

## Corrección de la participación AFAC (30 sep 2026, revisión de Codex en el PR #77)

- **Denominador incompleto:** si falta cualquiera de las tres aerolíneas de Industria
  en un mes o trimestre y segmento, el total de aerolíneas mexicanas se trata como
  incompleto. En ese caso `mexican_carriers_passengers` y todas las participaciones de
  esa celda quedan en `null`. Antes se sumaba solo lo publicado, lo que inflaba la
  participación de las demás; por ejemplo, Volaris internacional falta en 2020.
- **Ruptura de 2021:** los libros AFAC de 2019–2020 que parsea el proyecto casi no
  traen pasajeros internacionales por aerolínea mexicana.

  | | 2019 (internacional) | 2021M01 (internacional) |
  |---|---|---|
  | Aeroméxico | 0 | 237 mil |
  | Suma de aerolíneas mexicanas | unos pocos miles al mes | 565 mil |

  Por eso `src/dashboard/market.py` publica internacional y total solo desde `2021M01`
  (`INTERNATIONAL_FIRST_MONTH`). Nacional conserva su serie desde 2019.
- **Contrato:** `market.schema.json` admite `null` en `mexican_carriers_passengers`.
- **Efecto:** de 2021 en adelante los meses no cambian. Los trimestres de 2021 solo
  pierden la comparación anual contra 2020.
