# Entrega GitHub y respaldo privado · 2026-09-19

## Resultado

El proyecto quedó dividido en dos repositorios con funciones distintas:

- `salvamalfa/aeromexico-tracker` conserva código, contratos, documentación,
  Gold publicables y el dashboard.
- `salvamalfa/aeromexico-tracker-data` conserva un snapshot privado bajo Git
  LFS para continuidad, recuperación y trabajo de agentes autorizados.

El snapshot está asociado al commit público
`652172dd8c5836849345bb980f797c47186b5de8`. Contiene Bronze, Silver, quality,
analytics, `warehouse.duckdb`, `analysis_runs/` y modelos. Excluye `.env`,
secretos de Streamlit, cachés, logs, temporales y `.venv`.

## Evidencia de integridad

| Comprobación | Resultado |
|---|---:|
| Archivos en manifiesto | 1,879 |
| Bytes verificados | 1,278,880,052 |
| Archivos bajo Git LFS | 1,879 |
| `git lfs fsck` en clon nuevo | OK |
| Fallos SHA-256 en clon nuevo | 0 |
| Archivos restaurados | 1,879 |
| `.env` restaurado | No |

La primera prueba de checkout reveló que algunas rutas excedían el límite
normal de Windows. La prueba final usó `git -c core.longpaths=true clone` en una
ruta corta; la instrucción quedó incorporada en ambos repositorios.

## Warehouse saneado

El archivo físico local contenía dos secuencias en páginas internas que
coincidían con patrones genéricos de credenciales, aunque ninguna aparecía en
las 616 columnas de texto consultables. La copia del respaldo se recreó mediante
una copia lógica de DuckDB y se comparó con el original:

| Propiedad | Resultado |
|---|---:|
| Tablas | 43, iguales |
| Vistas | 21, iguales |
| Conteos por tabla | Iguales |
| Filas acumuladas de `SHOW TABLES` | 932,361 |
| Patrones OpenAI/AWS/GitHub en la copia | 0 |

El respaldo conserva el contenido consultable y elimina páginas físicas
obsoletas. La evidencia detallada viaja en
`warehouse_export_verification.json` dentro del repositorio privado.

## Alerta de GitHub

La alerta de secret scanning en `data/gold/bridge_record_lineage.parquet` se
revisó contra el archivo lógico y el resto del árbol versionado. La secuencia
solo existía en bytes comprimidos del Parquet y no en una celda. La alerta se
cerró como falso positivo.

## Frontera operativa

El respaldo privado resuelve la continuidad cuando la PC principal está
apagada, siempre que el agente o entorno tenga autorización para ambos
repositorios y Git LFS. No convierte datos privados o licenciados en públicos,
no sustituye secretos del entorno y no concede aprobación para activar
`flight_evidence_v1`, publicar el dashboard o cambiar el estado del Analysis
Agent.

Los snapshots futuros deben ser deliberados. Antes de cada actualización hay
que revisar licencias y secretos, regenerar el manifiesto, verificar todos los
hashes y completar al menos una restauración desde un clon nuevo.
