# Integración internacional de Vuelos

8 de septiembre de 2026. Autorización: «Adelante, integra la información». Alcance: HTML local y flujo Bronze → Silver → Gold para Brasil, Colombia y Reino Unido. Sin despliegue ni activación histórica en el Analysis Agent.

## Resultado

En 2T26, la red pasa de 40 mercados/33 aeropuertos de BTS a **46 mercados/39 aeropuertos**. Se añaden seis mercados con Ciudad de México. Continúan el selector trimestral, búsqueda y detalle direccional.

| Mercado añadido | Ventana utilizada | Pasajeros | Asientos | Vuelos |
|---|---|---:|---:|---:|
| MEX ↔ GRU | Abril–junio · ANAC | 41,071 pagados | 48,021 | 182 |
| MEX ↔ BOG | Abril–junio · Aerocivil | N/D | N/D | 552 |
| MEX ↔ MDE | Abril–junio · Aerocivil | N/D | N/D | 182 |
| MEX ↔ CTG | Abril–junio · Aerocivil | N/D | N/D | 182 |
| MEX ↔ CLO | Abril–junio · Aerocivil | N/D | N/D | 112 |
| MEX ↔ LHR | Junio · CAA | N/D | N/D | 60 |

Sumas de ambos sentidos. La ocupación queda N/D en las nuevas fuentes: ANAC requiere homologar pasajeros/etapas frente a capacidad; Aerocivil y CAA carecen de insumos. CAA contabiliza vuelos cotejados, excluye cancelados y bloquea la incorporación cuando hay vuelos no cotejados pendientes de reconciliar.

BTS conserva abril–mayo 2026 y comparación abril–mayo 2025. Cada fila informa fuente y meses. No se genera un total mundial que mezcle poblaciones o ventanas. Los comparativos nuevos requieren los mismos meses y ambos sentidos. Las curvas sin pasajeros usan ancho base.

## Flujo y linaje

1. **Bronze:** originales inmutables mediante `src/common/storage.py`; selección en `data/bronze/international_routes/selection.json`, con recibos fechados. URL, descarga, SHA-256 y versiones en metadata y `_manifest.jsonl`.
2. **Silver:** `data/silver/international_routes/observations.parquet`, generado por `src/transform/international_routes.py`. **298 registros**: 149 ANAC, 147 Aerocivil, 2 CAA. Todos los incorporados tienen explotador AMX; la consulta distingue AMX/SLI y no inventa datos para Connect.
3. **Gold:** `fact_international_route_observations.parquet` se construye leyendo Silver persistido y validado. `bridge_international_route_lineage.parquet` reutiliza las convenciones de identificadores y puente del proyecto. Se actualizan `dim_source`, `dim_source_artifact` y las tablas DuckDB.
4. **Consumo:** `src/dashboard/international_routes.py` lee Gold desde DuckDB. `flights.py` conserva el contrato BTS y añade una red enriquecida. Los generadores producen la vista autónoma y el HTML principal de Etapa 11.

Cada observación conserva `record_id`, `artifact_id`, SHA-256, archivo, URL, localizador, parser, definición y fecha de descarga. **298/298** registros resuelven hasta el artefacto y su hash mediante el puente. `record:n` indica posición de registro sin cabecera CSV u orden global de los bloques JSON.

Grano: fuente + operador + empresa comercial + mes + origen + destino, tras el filtro de tipo de operación. Aerocivil tiene tres particiones ruta/mes con varias etiquetas de empresa comercial, incluyendo vacías y AXM. Se conservan las etiquetas y se suman sus grupos de movimientos por explotador AMX. No se unen totales de mercado con tablas de compañía para atribuir pasajeros.

## Descargas y brechas

- **ANAC:** original completo de 208,844,798 bytes del bloque 2021–2030. La descarga continua falló; la descarga por rangos comprobó continuidad, total y mismo validador ETag/Last-Modified. Contiene arrays JSON consecutivos: el parser consume todos los bloques y rechaza truncamiento. El archivo completo aporta datos hasta junio 2026, ampliando la muestra parcial de investigación. La caché de descarga en `tmp/international_route_download` no alimenta Silver directamente.
- **Aerocivil:** respuesta completa para 2025–2026 y explotadores AMX/SLI, contrastada con el conteo API. Julio permanece disponible en datos; 2T26 selecciona abril–junio. Se filtra tipo S internacional y se valida el aeropuerto de registro contra llegada/salida.
- **CAA:** CSV completo junio 2026, reutilizado por hash desde `route_authority_research`. 7,265 filas; dos seleccionadas. Abril–mayo todavía pendientes de incorporar.
- **Bogotá–Tuxtla:** movimiento de junio sin sentido contrario conservado en Gold, excluido del mapa bidireccional hasta aclaración. Un registro de movimiento no certifica una oferta comercial sostenida.
- **Chile, España, Corea y demás países:** pendientes según el diagnóstico. Cobertura mundial incompleta.

## Análisis aprobado y corte histórico

Las observaciones nuevas tienen `agent_eligible=false`, `published_at=null`: no se ha certificado que estas versiones estuvieran disponibles el 13 de julio de 2026. El HTML usa la perspectiva retrospectiva actual.

Se conserva íntegra la versión aprobada `186ba823aea28830be12cb0293c5bb2890a433b173addc473c26aa8f89cab26f`, aprobación `85cc3fd9541695992576871f732eeaa94a535d89e15060496d8f208fda78b6bd`. No cambió su texto. El complemento SEC sigue como candidato sin activar e incluye la exclusión explícita de las nuevas fuentes.

## Comprobaciones

- **40 pruebas dirigidas aprobadas**: parsers, operador/comercializador, dirección, duplicados, JSON concatenado/truncado, ventanas, conciliación, BTS, reconstrucción de extensión, HTML y aprobación.
- `dim_source` y `dim_source_artifact` pasan sus contratos existentes.
- Chromium abrió el HTML local: búsqueda LHR, fuente CAA, N/D y detalle direccional; cero errores y cero solicitudes HTTP(S).
- Viewports 360, 736 y 1440 px sin desbordamiento horizontal del documento.
- Se detectó y eliminó una llamada de Plotly a un CDN: `world_110m.topojson` de 285,045 bytes se conserva localmente con URL/hash y se precarga en `PlotlyGeoAssets`. El límite HTML de las pruebas pasa de 6 MB a 6.5 MB para incluir esta topología offline y los mercados nuevos. Se evita duplicar redes en el HTML.
- Evidencia: `afac-rutas-evidencia-20260908/integration-ui.json`, `international-routes-desktop.png`, `integration-publication.json` y `data/quality/international_routes.json`.

## Operación manual

Desde la raíz del proyecto:

```powershell
# Solo para volver a consultar las fuentes:
.\.venv\Scripts\python.exe -m src.ingest.international_routes
# Reconstrucción local desde la selección Bronze:
.\.venv\Scripts\python.exe -m src.transform.international_routes
.\.venv\Scripts\python.exe -m src.dashboard.build_flights
.\.venv\Scripts\python.exe -m src.analysis_agent.stage18 --record analysis_runs/drafts/2026Q2/186ba823aea28830be12cb0293c5bb2890a433b173addc473c26aa8f89cab26f.json --output prototypes/etapa-11/resumen_ejecutivo.html
```

Incremento manual acotado, sin scheduler. Aerocivil está acotado a 2025–2026 y CAA a junio 2026; ampliar ventanas requiere actualizar la selección explícita. El constructor general del warehouse recarga las dos tablas de extensión desde Gold sin lanzar descargas. Las escrituras Parquet son atómicas por archivo y las sustituciones DuckDB usan transacción. Ante interrupción entre archivos Gold, repetir la transformación completa antes de regenerar HTML.

Próxima decisión: completar CAA abril–mayo, acceso normal a Aena o resolver JAC. No se inició esa ampliación ni se publicó en Streamlit.
