# Etapa 4 — Fuentes complementarias

Fecha de cierre: 2026-08-20
Estado: COMPLETA

## Qué se construyó

- Ingesta macro oficial de Banxico SIE para FIX USD/MXN (`SF43718`), INPC
  (`SP1`) y tasa objetivo (`SF61745`), con Federal Reserve H.10 como respaldo
  explícito y etiquetado solamente si Banxico falla.
- Serie diaria oficial EIA de jet fuel U.S. Gulf Coast
  (`EER_EPJK_PF4_RGC_DPG`) y calendarios hábiles gold con todo forward fill
  visible mediante `is_published` y `fill_method`.
- Precios OHLCV de AERO, VLRS, RYAAY, DAL e ICAGY; AERO pasa una compuerta de
  identidad contra evidencia SEC preservada y la página oficial de IR.
- Tráfico mensual oficial de ASUR y GAP vía EDGAR, OMA vía su portal de IR, y
  los hubs gubernamentales MEX y NLU vía AICM y AIFA. Los enlaces actuales de
  AICM/AIFA se descubren desde sus índices oficiales, no están fijados al mes.
- `dim_airport` desde OurAirports, enriquecida con grupo operador, y crosswalk
  de aerolíneas ampliado con códigos canónicos para las series de mercado.
- `dim_events` curada con 22 eventos y URL primaria; incluye regulación,
  reestructuración, IPO, resultados y publicaciones operativas.
- Recolección limitada de titulares, respetando el alcance del plan: cobertura
  mediática, no satisfacción del cliente ni sentimiento de marca.
- Parser offline de toda la Etapa 4 registrado en `python -m src.rebuild`, más
  validador ejecutable, fixtures mínimos ASUR/GAP/RSS y casos sintéticos AICM/AIFA.

## Datos obtenidos

| Salida | Cobertura | Filas | Tamaño |
|---|---|---:|---:|
| `macro_indicators.parquet` | 2015-01-01–2026-08-20 | 7,303 | 73,128 bytes |
| `fx_rates.parquet` | 2015-01-02–2026-08-20 | 2,926 | 53,984 bytes |
| `fuel_prices.parquet` | 2015-01-02–2026-08-18 | 2,908 | 43,934 bytes |
| `market_prices.parquet` | 2015-01-02–2026-08-20 | 11,897 | 420,870 bytes |
| `airport_traffic.parquet` | 2024M01–2026M07 | 613 | 23,240 bytes |
| `news_headlines.parquet` | 2025-10-08–2026-08-20 (CDMX) | 200 | 88,336 bytes |
| `dim_airport.parquet` | snapshot actual | 9,053 | 583,465 bytes |
| `dim_events.parquet` | 2020-06-30–2026-08-20 | 22 | 12,404 bytes |
| `dim_fx_period.parquet` | mensual + trimestral | 187 | 12,517 bytes |
| `dim_fuel_period.parquet` | mensual + trimestral | 187 | 12,545 bytes |

La sesión añadió 159 entradas físicas a bronze por 29,520,402 bytes. Las 159
coinciden con su SHA-256 del manifiesto. Diez cambios de contenido de claves
lógicas se registraron como nuevas versiones/restatements; ningún archivo fue
sobrescrito.

El mercado contiene 197 sesiones de AERO desde el IPO y 2,925 observaciones para
cada uno de VLRS, RYAAY, DAL e ICAGY. Aeropuertos contiene 80 filas ASUR, 180 GAP,
339 OMA y 14 gubernamentales: siete meses para MEX y siete para NLU.

## Validaciones ejecutadas

| Check | Resultado | Detalle |
|---|---|---|
| Suite completa | PASS | 73 tests |
| Definición de aceptación | PASS | 27/27 controles |
| Reconstrucción offline Etapa 4 | PASS | Dos corridas; 12/12 archivos con SHA-256 idéntico |
| Rebuild global | PASS | SEC, BMV, AFAC y Etapa 4 sin red |
| Integridad bronze de la sesión | PASS | 159/159 hashes correctos |
| FIX Banxico | PASS | `SF43718`, 2026-08-20 = 16.9583 MXN/USD |
| Calendario FX | PASS | 3,035 hábiles, cero nulos; 109 forward fills marcados |
| Calendario jet fuel | PASS | 3,033 hábiles, cero nulos; 125 forward fills marcados |
| Identidad AERO | PASS | Grupo Aeroméxico; primera sesión 2025-11-06 |
| Sesiones AERO | PASS | Cero huecos contra calendario NYSE observado en DAL/VLRS |
| MEX y NLU | PASS | 2026M01–2026M07, siete meses cada uno |
| Cobertura `dim_airport` | PASS | 172/172 códigos requeridos; cero faltantes |
| Grupos aeroportuarios ↔ AFAC | PASS | Pearson 0.993546 en seis meses comparables |
| Eventos | PASS | 22/22 con URL HTTPS |
| FAA IASA | PASS | México Categoría 1, verificado 2026-08-20 |
| Noticias | PASS limitado | 200 titulares RSS; limitaciones declaradas |

La cobertura de aeropuertos une 38 códigos observados en tráfico con 140 tokens de
tres letras encontrados en textos SEC de Aeroméxico que además resuelven a un IATA
vigente en OurAirports. La fuente AFAC de la Etapa 3 es por aerolínea y no contiene
campo aeropuerto; por eso aporta cero códigos estructurados a esta prueba. La
correlación aeroportuaria usa únicamente los seis meses donde ASUR, GAP y OMA tienen
cobertura simultánea y es una señal de consistencia, no igualdad de perímetro.

La FAA mantiene a México en Categoría 1 en el archivo de resultados enlazado por su
página actual. El PDF fue publicado el 2025-04-18, la página indicaba actualización
2026-04-16 y la verificación se ejecutó el 2026-08-20. No se encontró una publicación
primaria posterior que cambiara la categoría; por tanto, no se inventó el evento de
una supuesta auditoría o degradación en agosto de 2026.

## Qué NO funcionó y por qué

- El endpoint GDELT respondió primero HTML en lugar de JSON y después HTTP 429 por
  límite compartido de IP. Ambos diagnósticos quedaron preservados; no se fabricó
  tono ni tema.
- El RSS de El Economista respondió HTTP 403. La salida conserva 200 titulares de
  Google News RSS en español e inglés y registra la fuente opcional fallida.
- El endpoint REST de Banxico requería token, pero se encontró y validó el exportador
  CSV público del propio SIE. La corrida final usa la serie FIX exacta, no el respaldo
  H.10 descargado durante el diagnóstico.
- OpenFlights no se utilizó: su endpoint raw fue inestable y su catálogo es histórico.
  OurAirports cubre aeropuertos y el crosswalk versionado mantiene manualmente los
  códigos canónicos de aerolíneas.
- No se incorporaron llegadas internacionales DATATUR/INEGI. El plan les asigna
  prioridad media y permite diferirlas a la Etapa 7, cuando pueda medirse si mejoran
  el forecast.

Los avisos `Ignoring wrong pointing object` de `pypdf` provienen de objetos internos
mal apuntados en algunos PDF de OMA. La extracción produjo filas válidas y consistentes;
no se silenció el aviso ni se modificó el documento fuente.

No fue necesario instalar paquetes adicionales ni usar computer use.

## Decisiones tomadas

- Usar Banxico SIE como fuente primaria y reservar H.10 exclusivamente como fallback
  con `source_system` distinto.
- Usar EIA directa, que es la fuente subyacente de la serie FRED equivalente.
- Completar calendarios únicamente en gold; silver conserva solo observaciones
  publicadas. Cada relleno queda marcado y auditable.
- Usar promedio de periodo para conversión P&L y cierre de periodo para balance;
  ambos métodos quedan declarados en `dim_fx_period`.
- Validar sesiones AERO contra sesiones comunes observadas de DAL/VLRS, evitando
  confundir fines de semana o feriados con huecos.
- Mantener las filas de cada aeropuerto y los totales de grupo; MEX y NLU se tratan
  como `GOVERNMENT`, no se atribuyen a ASUR/GAP/OMA.
- Mantener noticias como cobertura mediática. El dashboard no deberá presentarlas
  como satisfacción del cliente.
- Mantener bronze, silver, gold y quality fuera de git; se versionan manifiestos,
  parsers, contratos, crosswalk, documentación y fixtures mínimos.

## Supuestos hechos

- Las publicaciones actuales enlazadas por AICM, AIFA, OMA y FAA representan el
  corte público disponible al 2026-08-20.
- Yahoo Finance es una fuente práctica de precios para el proyecto de portafolio;
  la identidad de AERO se valida separadamente con fuentes primarias de Aeroméxico.
- La media de días hábiles es apropiada para P&L y el último valor disponible para
  balance; la capa gold futura deberá guardar el FX efectivamente aplicado por fila.
- Los códigos hallados en texto SEC se consideran candidatos de aeropuerto solo si
  coinciden con un IATA vigente; aun así, la lista de 140 debe entenderse como prueba
  amplia de cobertura, no como red actual confirmada de rutas.

## Preguntas para el usuario

Ninguna pendiente para cerrar la Etapa 4.

## Riesgos para la siguiente etapa

- GDELT puede seguir limitado por IP; su ausencia no debe bloquear el dashboard ni
  convertirse en un cero de tono.
- Google News RSS ofrece una ventana histórica limitada y títulos potencialmente
  duplicados semánticamente aunque la URL sea única.
- Yahoo Finance no es fuente primaria contractual; métricas de valuación deberán
  indicar proveedor y fecha de corte.
- Los sitios de IR y gobierno pueden cambiar HTML o formato PDF/XLSX. El descubrimiento
  de enlaces es dinámico, pero los parsers deben fallar explícitamente ante schema drift.
- Las 229 entidades AFAC no mapeadas de la Etapa 3 siguen limitando análisis de peers
  internacionales y deberán abordarse en la Etapa 5.
- Las series recientes pueden restatarse; bronze preserva versiones, pero el dashboard
  deberá mostrar fecha de corte y versión usada.

## Comandos para reproducir

```powershell
python -m src.ingest.stage4
python -m src.parse.stage4
python -m src.transform.stage4
python -m src.transform.validate_stage4
python -m src.rebuild
python -m pytest
```
