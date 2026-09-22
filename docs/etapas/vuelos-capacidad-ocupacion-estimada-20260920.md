# Vuelos, capacidad y ocupación nacional estimados · 20 sep 2026

> **Método canónico:** el procedimiento completo y verificado de estimación
> de pasajeros por ruta y aerolínea está en
> [`../estimacion-pasajeros-ruta-aerolinea.md`](../estimacion-pasajeros-ruta-aerolinea.md).
> Este documento es un reporte de su etapa, no la especificación.

## Resultado integrado

La vista nacional de `Vuelos` muestra para marzo–julio de 2026 cuatro métricas
por mercado: pasajeros, asientos, vuelos y ocupación. Todas llevan `≈` porque
combinan estimaciones y ninguna se presenta como operación realizada observada.
El HTML principal regenerado es
[`prototypes/etapa-11/resumen_ejecutivo.html`](../../prototypes/etapa-11/resumen_ejecutivo.html)
y su copia pública byte por byte es
[`static/aeromexico_tracker.html`](../../static/aeromexico_tracker.html).

No se hicieron llamadas nuevas a AeroDataBox. La derivación reutilizó los
artefactos transitorios de las corridas ya autorizadas para 2026M03–2026M07,
por lo que el gasto adicional de API fue **0 unidades**.

## Qué mide cada columna

- **Pasajeros**: estimación AFAC + IPF por ruta, sentido y operador. La tabla
  interna distingue Aerovías de México de Aeroméxico Connect, pero la interfaz
  suma ambas como **Grupo Aeroméxico** y conserva su rango de sensibilidad.
- **Vuelos**: siete días distribuidos dentro del mes, uno por día de la semana,
  expandidos con la frecuencia real de cada día de la semana en el calendario.
  Es una estimación mensual de programación observada en AeroDataBox; no prueba
  que cada vuelo se haya realizado.
- **Asientos**: suma de los vuelos estimados multiplicados por la configuración
  del modelo de aeronave. Las configuraciones se versionaron en
  [`data/reference/aeromexico_aircraft_seat_capacity.csv`](../../data/reference/aeromexico_aircraft_seat_capacity.csv).
  El E190 usa 99 asientos; 787-8 y 787-9 usan 243 y 274; las familias 737 con
  configuraciones múltiples usan el punto medio y conservan mínimo y máximo.
- **Ocupación**: pasajeros estimados / asientos estimados. El rango combina el
  mínimo de pasajeros con el máximo de asientos y viceversa.

La referencia primaria de configuración es el [20-F 2025 de
Aeroméxico](https://www.sec.gov/Archives/edgar/data/1561861/000119312526197494/d101275d20f.htm),
que reporta E190 de 99 asientos, 787-8 de 243, 787-9 de 274, MAX 8 de 162–178,
MAX 9 de 178–193 y 737-800 de hasta 186. El punto genérico de 737 se ponderó
con la flota al 30 de junio de 2026: 34 B737-800, 47 MAX 8 y 30 MAX 9, según el
[reporte 2T26](https://www.globenewswire.com/news-release/2026/07/13/3326490/0/en/Aerom%C3%A9xico-Reports-Unaudited-Second-Quarter-2026-Results.html).
Para el límite inferior del 737-800 se usó el inventario de configuraciones
[160–186 asientos](https://seatmap.org/en/airlines/aeromexico); esa fuente se
declara secundaria y su uso solo determina el rango, no la existencia del vuelo.

## Cobertura y controles

La derivación produjo 708 celdas mensuales ruta × sentido × operador. La
cobertura de modelos válidos fue 99.96% en marzo, 99.44% en abril, 99.83% en
mayo, 99.91% en junio y 99.91% en julio. Se excluyeron unas pocas etiquetas que
no pertenecen a la flota operativa reportada por Aeroméxico, como Airbus y King
Air, en vez de asignarles una capacidad inventada. La puerta por celda exige al
menos 95% de cobertura de modelo.

| Mes | Mercados con pasajeros | Vuelos y asientos completos | Ocupación utilizable | Ocupación inconsistente |
|---|---:|---:|---:|---:|
| 2026M03 | 55 | 54 | 41 | 13 |
| 2026M04 | 55 | 53 | 42 | 11 |
| 2026M05 | 55 | 54 | 41 | 13 |
| 2026M06 | 56 | 51 | 39 | 12 |
| 2026M07 | 55 | 51 | 40 | 11 |
| **Total mercado–mes** | **276** | **263** | **203** | **60** |

Las 13 combinaciones sin capacidad completa dependen de soporte de rutas tomado
de meses cercanos o de una celda que no superó la puerta. Los 60 casos
inconsistentes sí conservan vuelos y asientos, pero no muestran ocupación: el
punto estimado supera 100%. Se explica en el `title` de la celda. No se añadió
ni redistribuyó ningún vuelo para forzar el cociente por debajo de 100%.

## Retención y publicación

La salida permanente
`fact_aeromexico_domestic_capacity_estimate.parquet` contiene solo agregados
mensuales por ruta, sentido y operador. No contiene vuelo, matrícula, horario,
número de vuelo ni conteo de modelos por ruta. Se conserva indefinidamente en
el repositorio privado `aeromexico-tracker-data` junto con un recibo de calidad.
El parquet local usado para reconstruir el dashboard está ignorado en el
repositorio público y no se publica como dataset; el HTML expone únicamente el
extracto agregado de Grupo Aeroméxico que necesita la interfaz.

Los JSON y las tablas de proveedor por vuelo permanecen sujetos a siete días de
retención. Se eliminaron de la copia de trabajo después de generar y verificar
los agregados; el artefacto privado de GitHub conserva su vencimiento original
del 27 de septiembre de 2026.

## Elegibilidad histórica

Este uso es retrospectivo para el dashboard. Todos los agregados mantienen
`historically_eligible_at_2026_07_13 = false` y `agent_eligible = false`. La
integración no activa `flight_evidence_v1`, no cambia el expediente aprobado de
2T26 y no incorpora estas estimaciones al Analysis Agent.

## Validación

- Cobertura de modelo: mayor a 99.4% en cada mes.
- Integridad: 708 filas únicas por periodo, origen, destino y operador.
- UI: junio muestra, por ejemplo, CUN–MEX con ≈796 vuelos, ≈142,862 asientos y
  ≈79.2% de ocupación; el detalle presenta Grupo Aeroméxico por sentido.
- Las ocupaciones publicadas están acotadas entre 0% y 100%; las inconsistentes
  quedan en N/D.
- El dashboard autónomo y el integrado se regeneraron desde sus generadores.
