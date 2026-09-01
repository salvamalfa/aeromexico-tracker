# Auditoría independiente de arquitectura y datos — Etapa 9

Fecha: 2026-09-01
Resultado: APROBADA

## Dictamen técnico

La arquitectura **Bronze/Silver/Gold + Parquet + DuckDB + Streamlit** sigue siendo
adecuada para el volumen, el uso local y el destino público del proyecto. No se
identificó una justificación técnica o económica para migrar a BigQuery, introducir
dbt o sustituir el hecho largo `fact_carrier_metrics`.

La revisión independiente detectó defectos de severidad P0 y P1 en el historial BMV,
el checkout aislado, algunos contratos y la ejecución offline. Todos quedaron
corregidos y cubiertos por pruebas. Al cierre, el sistema reconstruye desde una copia
inmutable de Bronze, conserva el historial disponible, declara el estado de cada
fuente y permite rastrear el 100% de los registros en alcance hasta artefactos,
registros padre o una declaración explícita de curación.

## Alcance y método

La revisión se realizó en un frente separado del de implementación y evaluó:

- registro y dependencias del pipeline;
- aislamiento, bloqueo de red, promoción local y rollback del rebuild;
- contratos Silver y Gold, grano, relaciones e invariantes;
- semántica SCD2 de SEC, AFAC y BMV;
- catálogo de fuentes, manifiesto Bronze e integridad por SHA-256;
- identificadores estables y relación muchos-a-muchos de linaje;
- reconciliación del ledger de calidad;
- precedencia de fuentes y reglas de consolidación;
- separación entre aeropuertos físicos y totales de grupos;
- conservación de cifras ancla y compatibilidad con el dashboard existente.

La evidencia incluyó inspección de código y contratos, fixtures congelados, consultas
SQL/Python, validadores de etapas, la suite completa y dos rebuilds aislados desde el
mismo snapshot Bronze.

## Hallazgos independientes y resolución

| Severidad | Hallazgo | Riesgo | Resolución y evidencia |
|---|---|---|---|
| P0 | El orden anterior del backfill BMV podía producir intervalos SCD2 invertidos. | Una versión podía cerrar antes de comenzar y la fila corriente no necesariamente representaba el reporte correcto. | El backfill inicial se identifica como lote histórico y se ordena por periodo del paquete dentro de ese lote; las revisiones posteriores conservan orden de ingesta. Los contratos rechazan intervalos invertidos, traslapes, huecos, más de una fila corriente o incrementos de `restatement_count` sin cambio de valor. |
| P0 | El checkout limpio no copiaba `data/reference`, requerido por el crosswalk de aerolíneas. | El rebuild no era realmente reproducible desde sus insumos declarados. | La copia aislada incluye referencias versionadas y sigue excluyendo Silver, Gold, warehouse, modelos y analítica anteriores. Dos rebuilds posteriores completaron 19/19 pasos cada uno. |
| P1 | El grano contractual de BTS T-100 no distinguía toda la observación física. | Filas válidas podían parecer duplicadas o colisionar bajo una clave incompleta. | El contrato Silver usa la combinación completa de archivo, aerolínea, entidad, origen, destino, aeronave, configuración, año, mes y clase. |
| P1 | Los contratos declaraban columnas y tipos, pero no bastantes invariantes relacionales y temporales. | Un archivo podía satisfacer el esquema y aun contener estados imposibles. | Los 28 contratos Silver y 31 Gold ahora declaran grano; las relaciones seguras, dominios, rangos y reglas SCD2 se validan de forma ejecutable. |
| P1 | El gate inicial de Etapa 9 no probaba de punta a punta todas las garantías nuevas. | La etapa podía cerrar con catálogo, linaje o precedencia parcialmente validados. | El gate final reúne 12 controles: contratos, 27 relaciones, catálogo/manifiesto, linaje, ledger, grupos aeroportuarios, precedencia, consolidación, SCD2, anclas, salud y registro central. |
| P1 | La entrada única de `transform.stage4` no era una tupla por faltar la coma final. | El orquestador fallaba al iterar requisitos durante el rebuild. | Se corrigió la declaración y el modelo del registro valida que toda colección de entradas sea una tupla de requisitos válidos. |
| P1 | El bloqueo offline original también impedía la comunicación local del kernel de Jupyter. | El notebook reproducible fallaba aunque no intentara acceder a internet. | El guard permite únicamente direcciones loopback y mantiene bloqueada cualquier conexión externa; existe una prueba específica para ambas conductas. |
| P1 | La promoción de salidas necesitaba garantizar reversión completa ante una falla a mitad del intercambio. | Una corrida fallida podía dejar capas de distintas ejecuciones mezcladas. | Todas las salidas se preparan y verifican antes del intercambio; una falla simulada restaura cada destino. Solo se promueve una corrida completa. |
| P1 | Un checkout sin `.git` no tenía una versión de código estable para modelos y recibos. | Dos corridas del mismo código podían recibir identidad ambigua o `unknown`. | Se calcula una huella SHA-256 determinista del árbol de código permitido y se propaga como `code_version`. Los dos rebuilds comparados usaron `sha256:4fe1b181ce9ae7c7d4f4a09065dd4c21a9ae98d0b30c735ca83f590db6d30323`. |

## Evidencia de cierre

| Control | Resultado comprobado |
|---|---|
| Registro central | 32 pasos importables: 13 de ingesta, 7 de parsing, 6 de transformación, 2 de analítica y 4 de preparación/validación del producto. |
| Rebuild aislado | Corridas A y B: 19/19 pasos completados; 28/28 Parquet Silver y 31/31 Gold idénticos por SHA-256 y conteo de filas. |
| Integridad Bronze | 1,506 archivos preservados; 752 artefactos públicos verificados contra el manifiesto. La huella del árbol fue idéntica en origen y ambos checkouts. |
| Contratos | 28 datasets Silver y 31 tablas Gold bajo `stage9_v1.0.0`. |
| Relaciones | 27 relaciones declaradas, todas con cero claves huérfanas. |
| Linaje | 277,805 registros declarados de 277,805 esperados; cobertura 100%; 412,139 filas en `bridge_record_lineage`. |
| Resolución de linaje | 208,909 registros con artefacto, 68,429 mediante registros padre y 467 con declaración explícita sin enlace exacto; cero artefactos o padres desconocidos. |
| Calidad | 499 filas operativas crudas se reconciliaron en 264 incidencias únicas; junto con 23 incidencias derivadas producen 287 filas canónicas. |
| Aeropuertos | 47 totales `ALL_ASUR`, `ALL_GAP` y `ALL_OMA` se movieron fuera de la dimensión de aeropuertos físicos. |
| SCD2 | SEC: 641 filas corrientes; AFAC: 3,642; BMV: 293 versiones, 40 posteriores a la base y 253 corrientes. Fixtures congelados prueban cambio y no cambio de valor. |
| Precedencia | SQL y Python seleccionaron las mismas 5,739 filas usando las 9 reglas de prioridad. |
| Consolidación | 99 métricas con método declarado: 39 `sum`, 5 `latest` y 55 `non_additive`; ningún ratio, margen o factor es aditivo. |
| Salud | 7 dominios, 15 datasets y 25 combinaciones de salud/frescura cubiertas. |
| Regresión | 142/142 pruebas, Etapa 6 25/25, Etapa 7 18/18, Etapa 8 18/18 y Etapa 9 12/12. |

## Robustez y límites

- El snapshot Bronze permanece local y fuera de Git. La reproducibilidad demostrada
  depende de conservar esa misma copia inmutable y su manifiesto.
- Las 467 declaraciones sin enlace exacto no son enlaces faltantes ocultos: identifican
  explícitamente resultados curados o derivados para los que no existe un único
  artefacto público atribuible.
- El snapshot real no contiene revisiones de valor para SEC o AFAC. La mecánica SCD2
  se probó con fixtures congelados; BMV sí aporta historial materializado real.
- El ledger canónico conserva 287 incidencias abiertas. La reconciliación elimina
  duplicados de ejecución, pero no convierte una incidencia sin resolver en resuelta.
- `weighted` es un valor permitido, pero no se usa mientras una métrica no declare su
  ponderador; esta ausencia bloquea la consolidación en vez de asumir uno.

## Conclusión

Los hallazgos P0 y P1 quedaron cerrados con evidencia ejecutable. El backend cumple el
gate de Etapa 9 sin alterar las cifras de negocio y sin aumentar la infraestructura
operativa. La recomendación es conservar la arquitectura actual y tratar los límites
anteriores como controles permanentes, no como razones para una migración de plataforma.
